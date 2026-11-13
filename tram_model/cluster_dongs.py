"""행정동 82개 유형 나누기 (K-means) — cluster_areas.py 의 행정동판

입력: outputs/dong_year_panel.csv (build_dong_year_panel.py)
출력: outputs/dong_types.csv, dong_type_centers.csv, dong_type_k.csv, dong_type_stability.csv, dong_types.png
특징(2016~2026): land_g10, land_rel_g10, land_recent, land_vol, store_g, store_recent, close_rate, open_rate, food_ratio, retail_ratio, branch_share, size
군집에 쓰는 6개 USE 는 상권과 같음. 추가 설명용: sales_per_store(8989 2026), sales_yoy(8989), tram500_share
- 점포 200개 미만 동은 '점포 적음'으로 표시(군집에는 포함)
- 신성동(도룡동 신세계 2021 입점 등록)은 점포 지표 왜곡 → 학습 제외 후 배정
sklearn 이 없으면 numpy 로 같은 K-means(k-means++, n_init)를 돌림.
"""
import numpy as np
import pandas as pd

import config as C

try:
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score
    HAVE_SK = True
except ImportError:
    HAVE_SK = False

FEATS = {"land_g10": "지가 10년 상승", "land_rel_g10": "지가 대전 대비", "land_recent": "지가 최근 4년",
         "land_vol": "지가 변동성", "store_g": "점포 비중 10년", "store_recent": "점포 비중 최근 3년",
         "close_rate": "폐업률", "open_rate": "개업률", "food_ratio": "음식점 비율", "retail_ratio": "소매 비율",
         "branch_share": "체인 비율", "size": "규모(점포 수)"}
USE = ["land_rel_g10", "land_recent", "store_g", "store_recent", "close_rate", "size"]
EXTRA = {"sales_per_store": "점포당 카드매출(8989, 2026)", "sales_yoy": "카드매출 증감(8989)", "tram500_share": "정거장 500m 점포 비율"}
ARTIFACT = {"3020055000": ["store_g", "store_recent", "open_rate"]}   # 신성동
K_RANGE = range(3, 8); SEED = 42; SMALL = 200


# ── numpy K-means (sklearn 없을 때) ──
def _kmeans_np(X, k, n_init=50, seed=0, iters=300):
    rng = np.random.default_rng(seed); best = None
    for _ in range(n_init):
        c = [X[rng.integers(len(X))]]
        for _j in range(1, k):                      # k-means++
            d2 = np.min(((X[:, None, :] - np.array(c)[None]) ** 2).sum(-1), axis=1)
            c.append(X[rng.choice(len(X), p=d2 / d2.sum())])
        c = np.array(c)
        for _it in range(iters):
            lab = np.argmin(((X[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
            nc = np.array([X[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(k)])
            if np.allclose(nc, c): break
            c = nc
        inertia = ((X - c[lab]) ** 2).sum()
        if best is None or inertia < best[0]: best = (inertia, lab, c)
    return best

class NPKMeans:
    def __init__(self, n_clusters, n_init=50, random_state=0): self.k, self.n_init, self.seed = n_clusters, n_init, random_state
    def fit(self, X):
        X = np.asarray(X, float); self.inertia_, self.labels_, self.cluster_centers_ = _kmeans_np(X, self.k, self.n_init, self.seed); return self
    def predict(self, X):
        X = np.asarray(X, float); return np.argmin(((X[:, None, :] - self.cluster_centers_[None]) ** 2).sum(-1), axis=1)

def _silhouette(X, lab):
    X = np.asarray(X, float); D = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1)); s = []
    for i in range(len(X)):
        same = lab == lab[i]
        a = D[i, same].sum() / max(1, same.sum() - 1) if same.sum() > 1 else 0
        b = min(D[i, lab == j].mean() for j in set(lab) if j != lab[i])
        s.append(0 if same.sum() <= 1 else (b - a) / max(a, b))
    return float(np.mean(s))

def _ari(a, b):
    a, b = np.asarray(a), np.asarray(b); from math import comb
    ct = pd.crosstab(a, b).values
    sum_ij = sum(comb(int(n), 2) for n in ct.ravel()); sa = sum(comb(int(n), 2) for n in ct.sum(1)); sb = sum(comb(int(n), 2) for n in ct.sum(0))
    tot = comb(len(a), 2); exp = sa * sb / tot if tot else 0; mx = (sa + sb) / 2
    return (sum_ij - exp) / (mx - exp) if mx != exp else 1.0

if not HAVE_SK:
    KMeans, silhouette_score, adjusted_rand_score = NPKMeans, _silhouette, _ari


def features(P):
    rows = []
    for code, g in P.groupby("dong_id"):
        g = g.set_index("year"); li, lr, si = g.land_idx, g.land_rel_idx, g.store_share_idx
        last = g[g.n_stores.notna()].index.max()
        rows.append({"dong_id": code, "name": f"{g.si.iloc[0]} {g.dong.iloc[0]}", "si": g.si.iloc[0], "dong": g.dong.iloc[0],
                     "old_town": int(g.old_town.iloc[0]), "n_stores": g.n_stores[last],
                     "land_g10": np.log(li[2026] / li[2016]), "land_rel_g10": np.log(lr[2026] / lr[2016]),
                     "land_recent": np.log(li[2026] / li[2022]), "land_vol": g.land_yoy.loc[2016:2026].std(),
                     "store_g": np.log(si[last] / si[2016]), "store_recent": np.log(si[last] / si[2023]),
                     "close_rate": g.close_rate_y.loc[2017:2025].mean(), "open_rate": g.open_rate_y.loc[2017:2025].mean(),
                     "food_ratio": g.food_ratio[last], "retail_ratio": g.retail_ratio[last], "branch_share": g.branch_share[last],
                     "size": np.log(g.n_stores[last]),
                     "sales_per_store": (g.sales_m.get(2026, np.nan) / g.n_stores[last]) if "sales_m" in g else np.nan,
                     "sales_yoy": g.sales_yoy.get(2026, np.nan) if "sales_yoy" in g else np.nan,
                     "tram500_share": g.tram500_share.iloc[0]})
    return pd.DataFrame(rows).set_index("dong_id")


def name_type(z):
    if z.land_rel_g10 > 1.0: return "지가 급등형"
    if z.store_g < -0.5 and z.land_recent < -0.4: return "정체·쇠퇴형"
    if z.close_rate < -0.8: return "저회전 안정형"
    if z.store_g > 0.5: return "점포 확장·경쟁형" if z.close_rate > 0.3 else "점포 확장형"
    if z.land_rel_g10 > 0.5: return "지가 상승형"
    if z.land_rel_g10 < -0.5 and z.store_g < 0: return "상대 하락형"
    return "중간형"


def main():
    P = pd.read_csv(C.OUT_DIR / "dong_year_panel.csv", dtype={"dong_id": str}, encoding="utf-8-sig")
    F = features(P)
    F["small"] = (F.n_stores < SMALL).astype(int)
    fit = F.drop(index=[c for c in ARTIFACT if c in F.index])
    mu, sd = fit[USE].mean(), fit[USE].std()
    Z = ((fit[USE] - mu) / sd).clip(-2.5, 2.5)
    ks = []
    for k in K_RANGE:
        km = KMeans(n_clusters=k, n_init=50, random_state=SEED).fit(Z); b = np.bincount(km.labels_)
        ks.append({"k": k, "inertia": round(float(km.inertia_), 2), "silhouette": round(silhouette_score(Z, km.labels_), 3), "min_size": int(b.min()), "max_size": int(b.max())})
    K = pd.DataFrame(ks)
    cand = K[(K.k.between(3, 6)) & (K.min_size >= 5) & (K.max_size <= len(Z) * 0.55)]
    k_best = int((cand if len(cand) else K).sort_values("silhouette", ascending=False).k.iloc[0])
    km = KMeans(n_clusters=k_best, n_init=50, random_state=SEED).fit(Z)
    Zall = ((F[USE] - mu) / sd).clip(-2.5, 2.5)
    for code, cols in ARTIFACT.items():
        if code in Zall.index: Zall.loc[code, [c for c in cols if c in USE]] = 0.0
    lab = km.predict(Zall)
    cz = pd.DataFrame(km.cluster_centers_, columns=USE)
    order = cz[["land_rel_g10", "store_g"]].mean(axis=1).sort_values(ascending=False).index
    remap = {old: i + 1 for i, old in enumerate(order)}
    F["cluster"] = [remap[l] for l in lab]
    A = F[list(FEATS)].copy()
    for code, cols in ARTIFACT.items():
        if code in A.index: A.loc[code, cols] = np.nan
    allz = ((A - A.mean()) / A.std()).clip(-2.5, 2.5).fillna(0.0)
    czall = allz.groupby(F.cluster).mean()
    names = {c: name_type(czall.loc[c]) for c in sorted(F.cluster.unique())}
    seen = {}
    for c in names:
        seen[names[c]] = seen.get(names[c], 0) + 1
        if seen[names[c]] > 1: names[c] += f" {seen[names[c]]}"
    F["type_name"] = F.cluster.map(names)
    F["note"] = ["점포 지표 왜곡(신세계 입점) → 지가·규모로 배정" if c in ARTIFACT else ("점포 200개 미만, 참고" if s else "") for c, s in zip(F.index, F.small)]
    # 안정성
    fit_codes = list(Z.index); base_lab = pd.Series(km.predict(Z), index=fit_codes); rng = np.random.default_rng(SEED)
    same = pd.DataFrame(0.0, index=fit_codes, columns=fit_codes); aris = []; B = 100
    for b in range(B):
        idx = rng.choice(len(Z), len(Z), replace=True)
        kb = KMeans(n_clusters=k_best, n_init=10, random_state=b).fit(Z.iloc[idx]); lb = pd.Series(kb.predict(Z), index=fit_codes)
        aris.append(adjusted_rand_score(base_lab, lb)); same += (lb.values[:, None] == lb.values[None, :]).astype(float)
    co = same / B
    stab = {c: co.loc[c, base_lab[base_lab == base_lab[c]].index.drop(c)].mean() for c in fit_codes}
    drop_ari = {f: adjusted_rand_score(base_lab, KMeans(n_clusters=k_best, n_init=50, random_state=SEED).fit(Z[[c for c in USE if c != f]]).labels_) for f in USE}
    F["stability"] = F.index.map(lambda c: round(stab[c], 2) if c in stab else np.nan)
    S = pd.DataFrame({"test": [f"부트스트랩 {B}회 평균 ARI"] + [f"'{FEATS[f]}' 빼고 ARI" for f in USE], "ari": [np.mean(aris)] + list(drop_ari.values())}).round(3)
    S.to_csv(C.OUT_DIR / "dong_type_stability.csv", index=False, encoding="utf-8-sig")
    centers = F.groupby("cluster")[list(FEATS) + list(EXTRA)].mean()
    centers.insert(0, "n_dongs", F.groupby("cluster").size()); centers.insert(0, "type_name", centers.index.map(names))
    centers["old_town_share"] = F.groupby("cluster").old_town.mean().round(2)
    centers["members"] = F.groupby("cluster").dong.apply(lambda v: ", ".join(v))
    F.round(4).reset_index().to_csv(C.OUT_DIR / "dong_types.csv", index=False, encoding="utf-8-sig")
    centers.round(4).to_csv(C.OUT_DIR / "dong_type_centers.csv", encoding="utf-8-sig")
    K.to_csv(C.OUT_DIR / "dong_type_k.csv", index=False, encoding="utf-8-sig")
    print("[k 선택]\n", K.to_string(index=False), f"\n→ k = {k_best}  (sklearn {'사용' if HAVE_SK else '없음 → numpy'})")
    print("[안정성]\n", S.to_string(index=False))
    for c in sorted(names):
        m = F[F.cluster == c]; zc = czall.loc[c]; top = zc.abs().sort_values(ascending=False).index[:4]
        print(f"\n유형 {c} [{names[c]}] {len(m)}개 (원도심 비율 {m.old_town.mean():.0%}, 점포당 매출 {m.sales_per_store.mean()/1e4:,.0f}만, 매출 증감 {m.sales_yoy.mean():+.1f}%): {', '.join(m.dong)}")
        print("   특징: " + ", ".join(f"{FEATS[t]} {'높음' if zc[t] > 0 else '낮음'}({zc[t]:+.1f}σ)" for t in top))
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        from matplotlib import font_manager as fm
        for f in fm.findSystemFonts():
            if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
                fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(1, 2, figsize=(15, 7))
        ax[0].plot(K.k, K.silhouette, "o-"); ax[0].axvline(k_best, c="gray", ls=":"); ax[0].set_title("실루엣")
        im = ax[1].imshow(czall.values.T, cmap="RdBu_r", vmin=-2, vmax=2, aspect="auto")
        ax[1].set_yticks(range(len(czall.columns))); ax[1].set_yticklabels([FEATS[c] + (" ★" if c in USE else "") for c in czall.columns], fontsize=9)
        ax[1].set_xticks(range(len(czall))); ax[1].set_xticklabels([f"{c}. {names[c]} ({(F.cluster==c).sum()})" for c in czall.index], fontsize=8, rotation=15)
        for i in range(czall.shape[0]):
            for j in range(czall.shape[1]): ax[1].text(i, j, f"{czall.values[i, j]:+.1f}", ha="center", va="center", fontsize=8)
        plt.colorbar(im, ax=ax[1], shrink=.6); plt.tight_layout(); plt.savefig(C.OUT_DIR / "dong_types.png", dpi=130)
    except Exception as e:
        print("그림 생략:", e)
    return F


if __name__ == "__main__":
    main()
