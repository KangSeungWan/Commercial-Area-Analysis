"""C. 20개 상권 유형 나누기 (K-means).

입력: outputs/area_panel.csv (build_area_panel.py)
출력
- outputs/area_types.csv        : 상권별 유형 번호·이름·특징값
- outputs/area_type_centers.csv : 유형별 평균 (표준화 전 값)
- outputs/area_type_k.csv       : k=2~6 엘보우(관성)·실루엣
- outputs/area_types.png        : 실루엣/엘보우, 유형 지도(주성분 2개), 유형별 특징 열지도

특징 (2016~2026, 모든 상권에 값이 있는 기간)
- land_g10      : 공시지가 10년 상승률 (log, 2016→2026)
- land_rel_g10  : 대전 전체 대비 지가 변화 (log)  → +면 대전 평균보다 더 오름
- land_recent   : 최근 지가 추세 (log, 2022→2026; 2022 고점 이후)
- land_vol      : 지가 연 변화율의 표준편차 (변동성)
- store_g       : 대전 내 점포 비중 변화 (log, 2016→2026, 자료 단절 보정)
- store_recent  : 최근 3년 점포 비중 변화 (log, 2023→2026)
- close_rate    : 연 폐업률 평균 (2017~2025)
- open_rate     : 연 개업률 평균
- food_ratio, diversity, branch_share : 최근 업종 구성
- size          : log(점포 수)
극단값(예: 도룡동 신세계 입점 +600%)은 표준화 후 ±2.5 로 자름
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score

import config as C

FEATS = {"land_g10": "지가 10년 상승", "land_rel_g10": "지가 대전 대비", "land_recent": "지가 최근 4년",
         "land_vol": "지가 변동성", "store_g": "점포 비중 10년", "store_recent": "점포 비중 최근 3년",
         "close_rate": "폐업률", "open_rate": "개업률", "food_ratio": "음식점 비율",
         "diversity": "업종 다양성", "branch_share": "체인 비율", "size": "규모(점포 수)"}
USE = ["land_rel_g10", "land_recent", "store_g", "store_recent", "close_rate", "size"]   # 군집에 쓰는 6개
# 20개 표본에 12개 특징은 너무 많아(차원의 저주) 성장·최근 추세·폐업·규모를 대표하는 6개만 사용, 나머지는 설명용
ARTIFACT = {"A12": ["store_g", "store_recent"]}   # 도룡동: 2021 신세계 입점점포 등록으로 점포 지표 왜곡 → 학습 제외, 이 값은 평균 취급
K_RANGE = range(2, 7)
SEED = 42


def features(P):
    rows = []
    for code, g in P.groupby("code"):
        g = g.set_index("year")
        li, lr, si = g.land_idx, g.land_rel_idx, g.store_share_idx
        last = g[g.n_stores.notna()].index.max()
        rows.append({
            "code": code, "name": g.name.iloc[0], "type": g.type.iloc[0],
            "land_g10": np.log(li[2026] / li[2016]), "land_rel_g10": np.log(lr[2026] / lr[2016]),
            "land_recent": np.log(li[2026] / li[2022]), "land_vol": g.land_yoy.loc[2016:2026].std(),
            "store_g": np.log(si[last] / si[2016]), "store_recent": np.log(si[last] / si[2023]),
            "close_rate": g.close_rate_y.loc[2017:2025].mean(), "open_rate": g.open_rate_y.loc[2017:2025].mean(),
            "food_ratio": g.food_ratio[last], "diversity": g.diversity_mid[last],
            "branch_share": g.branch_share[last], "size": np.log(g.n_stores[last]),
        })
    return pd.DataFrame(rows).set_index("code")


def name_type(z):
    """유형 중심(12개 특징 표준화 평균) → 이름."""
    if z.land_rel_g10 > 1.0:
        return "지가 급등형" + (" · 음식 중심" if z.food_ratio > 0.5 else "")
    if z.store_g < -0.5 and z.land_recent < -0.4:
        return "정체·쇠퇴형"
    if z.close_rate < -0.8:
        return "저회전 안정형" + (" · 비음식(소매·업무) 중심" if z.food_ratio < -0.5 else "")
    if z.store_g > 0.5:
        return "점포 확장·경쟁형" if z.close_rate > 0.3 else "점포 확장형"
    if z.land_rel_g10 > 0.5:
        return "지가 상승형"
    return "중간형"


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

    P = pd.read_csv(C.OUT_DIR / "area_panel.csv", encoding="utf-8-sig")
    F = features(P)
    fit = F.drop(index=list(ARTIFACT))
    mu, sd = fit[USE].mean(), fit[USE].std()
    Z = ((fit[USE] - mu) / sd).clip(-2.5, 2.5)

    ks = []
    for k in K_RANGE:
        km = KMeans(n_clusters=k, n_init=100, random_state=SEED).fit(Z)
        b = np.bincount(km.labels_)
        ks.append({"k": k, "inertia": round(km.inertia_, 2), "silhouette": round(silhouette_score(Z, km.labels_), 3),
                   "min_size": int(b.min()), "max_size": int(b.max())})
    K = pd.DataFrame(ks)
    # k 선택: 3~5 중, 상권 1개짜리 유형이 없고 한 유형에 절반 넘게 몰리지 않는 k 가운데 실루엣 최대
    cand = K[(K.k.between(3, 5)) & (K.min_size >= 2) & (K.max_size <= len(Z) // 2)]
    k_best = int((cand if len(cand) else K).sort_values("silhouette", ascending=False).k.iloc[0])
    km = KMeans(n_clusters=k_best, n_init=100, random_state=SEED).fit(Z)
    # 전체 20개 배정 (왜곡 상권은 해당 지표를 평균(0)으로 두고 가장 가까운 유형)
    Zall = ((F[USE] - mu) / sd).clip(-2.5, 2.5)
    for code, cols in ARTIFACT.items():
        Zall.loc[code, cols] = 0.0
    lab = km.predict(Zall)
    cz = pd.DataFrame(km.cluster_centers_, columns=USE)
    order = cz[["land_rel_g10", "store_g"]].mean(axis=1).sort_values(ascending=False).index
    remap = {old: i + 1 for i, old in enumerate(order)}
    F["cluster"] = [remap[l] for l in lab]
    cz.index = [remap[i] for i in cz.index]
    cz = cz.sort_index()
    # 설명용: 12개 특징 전체의 유형별 표준화 평균
    A = F[list(FEATS)].copy()
    for code, cols in ARTIFACT.items():
        A.loc[code, cols + ["open_rate", "diversity"]] = np.nan      # 신세계 입점 등록으로 같이 왜곡된 값
    allz = ((A - A.mean()) / A.std()).clip(-2.5, 2.5).fillna(0.0)
    czall = allz.groupby(F.cluster).mean()
    names = {c: name_type(czall.loc[c]) for c in cz.index}
    seen = {}
    for c in names:                                   # 이름이 겹치면 번호 붙이기
        seen[names[c]] = seen.get(names[c], 0) + 1
        if seen[names[c]] > 1:
            names[c] += f" {seen[names[c]]}"
    F["type_name"] = F.cluster.map(names)
    F["note"] = ["점포 지표 왜곡(신세계 입점) → 지가·규모로 배정" if c in ARTIFACT else "" for c in F.index]
    # ── 안정성: 표본 재추출(부트스트랩) · 특징 하나 빼기 · 시작값 바꾸기 → 같은 유형이 다시 나오는가
    fit_codes = list(Z.index)
    base_lab = pd.Series(km.predict(Z), index=fit_codes)
    rng = np.random.default_rng(SEED)
    same = pd.DataFrame(0.0, index=fit_codes, columns=fit_codes); cnt = same.copy()
    aris = []
    for b in range(300):
        idx = rng.choice(len(Z), len(Z), replace=True)
        kb = KMeans(n_clusters=k_best, n_init=20, random_state=b).fit(Z.iloc[idx])
        lb = pd.Series(kb.predict(Z), index=fit_codes)
        aris.append(adjusted_rand_score(base_lab, lb))
        eq = (lb.values[:, None] == lb.values[None, :]).astype(float)
        same += eq; cnt += 1
    co = same / cnt
    stab = {c: co.loc[c, base_lab[base_lab == base_lab[c]].index.drop(c)].mean()
            if (base_lab == base_lab[c]).sum() > 1 else np.nan for c in fit_codes}
    drop_ari = {}
    for f in USE:
        cols = [c for c in USE if c != f]
        kd = KMeans(n_clusters=k_best, n_init=100, random_state=SEED).fit(Z[cols])
        drop_ari[f] = adjusted_rand_score(base_lab, kd.labels_)
    seed_ari = [adjusted_rand_score(base_lab, KMeans(n_clusters=k_best, n_init=1, random_state=s).fit(Z).labels_)
                for s in range(50)]
    F["stability"] = F.index.map(lambda c: round(stab.get(c, np.nan), 2) if c in stab else np.nan)
    S = pd.DataFrame({"test": ["부트스트랩 300회 평균 ARI", "시작값 50개 평균 ARI"] + [f"'{FEATS[f]}' 빼고 ARI" for f in USE],
                      "ari": [np.mean(aris), np.mean(seed_ari)] + list(drop_ari.values())}).round(3)
    S.to_csv(C.OUT_DIR / "area_type_stability.csv", index=False, encoding="utf-8-sig")
    print("\n[안정성] ARI (1 = 똑같이 나뉨, 0 = 우연 수준)\n", S.to_string(index=False))
    print("  상권별 안정도(같은 유형 상권과 다시 묶이는 비율) 낮은 순:",
          ", ".join(f"{F.loc[c, 'name']} {v:.2f}" for c, v in sorted(stab.items(), key=lambda x: x[1])[:5]))

    Z = Zall
    pca = PCA(2, random_state=SEED).fit(Z)
    pc = pca.transform(Z)
    F["pc1"], F["pc2"] = pc[:, 0].round(3), pc[:, 1].round(3)

    centers = F.groupby("cluster")[list(FEATS)].mean()
    centers.insert(0, "n_areas", F.groupby("cluster").size())
    centers.insert(0, "type_name", centers.index.map(names))
    centers["members"] = F.groupby("cluster").name.apply(lambda v: ", ".join(v))
    F.round(4).reset_index().to_csv(C.OUT_DIR / "area_types.csv", index=False, encoding="utf-8-sig")
    centers.round(4).to_csv(C.OUT_DIR / "area_type_centers.csv", encoding="utf-8-sig")
    K.to_csv(C.OUT_DIR / "area_type_k.csv", index=False, encoding="utf-8-sig")

    print("[k 선택]\n", K.to_string(index=False), f"\n→ k = {k_best}")
    for c in cz.index:
        m = F[F.cluster == c]
        zc = czall.loc[c]
        top = zc.abs().sort_values(ascending=False).index[:4]
        print(f"\n유형 {c} [{names[c]}] {len(m)}개: {', '.join(m.name)}")
        print("   두드러진 특징: " + ", ".join(f"{FEATS[t]} {'높음' if zc[t] > 0 else '낮음'}({zc[t]:+.1f}σ)" for t in top))

    # 그림
    fig = plt.figure(figsize=(16, 10))
    ax1 = fig.add_subplot(2, 3, 1)
    ax1.plot(K.k, K.silhouette, "o-", c="C0"); ax1.set_title("실루엣 (높을수록 잘 나뉨)"); ax1.set_xticks(list(K.k)); ax1.axvline(k_best, c="gray", ls=":")
    ax2 = fig.add_subplot(2, 3, 4)
    ax2.plot(K.k, K.inertia, "o-", c="C1"); ax2.set_title("엘보우 (관성)"); ax2.set_xticks(list(K.k)); ax2.axvline(k_best, c="gray", ls=":")
    ax3 = fig.add_subplot(1, 3, 2)
    for c in cz.index:
        m = F[F.cluster == c]
        ax3.scatter(m.pc1, m.pc2, s=90, label=f"{c}. {names[c]}")
        for code, r in m.iterrows():
            ax3.annotate(r["name"].split("(")[0], (r.pc1, r.pc2), fontsize=8, xytext=(4, 3), textcoords="offset points")
    ax3.set_title(f"상권 유형 (주성분 2개, 설명력 {pca.explained_variance_ratio_.sum():.0%})")
    ax3.legend(fontsize=8, loc="best"); ax3.axhline(0, c="k", lw=.4); ax3.axvline(0, c="k", lw=.4)
    ax4 = fig.add_subplot(1, 3, 3)
    cz = czall
    im = ax4.imshow(cz.values.T, cmap="RdBu_r", vmin=-2, vmax=2, aspect="auto")
    ax4.set_yticks(range(len(cz.columns))); ax4.set_yticklabels([FEATS[c] + (" ★" if c in USE else "") for c in cz.columns], fontsize=9)
    ax4.set_xticks(range(len(cz))); ax4.set_xticklabels([f"{c}" for c in cz.index])
    for i in range(cz.shape[0]):
        for j in range(cz.shape[1]):
            ax4.text(i, j, f"{cz.values[i, j]:+.1f}", ha="center", va="center", fontsize=8)
    ax4.set_title("유형별 특징 (표준화, 빨강 = 평균보다 높음, ★ = 군집에 사용)"); plt.colorbar(im, ax=ax4, shrink=.6)
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "area_types.png", dpi=130)
    print("\n→ outputs/area_types.csv, area_type_centers.csv, area_type_k.csv, area_types.png")
    return F


if __name__ == "__main__":
    main()
