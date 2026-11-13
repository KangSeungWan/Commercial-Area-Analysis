"""업종별 분석: 대전 업종 구성 변화, 지역(원도심·신도심·트램 권역)별 업종 이동, 20개 상권 업종 구성 변화, 트램 효과 업종별.

입력: outputs/dong_panel_store.csv, dong_profile.csv (build_dong_layer.py), store_panel.csv, scenario_tram_uplift.csv
출력 (outputs/)
- industry_city_trend.csv   : 업종 대분류별 대전 점포 수 지수 (2016-12 = 100, 자료 단절 보정)
- industry_by_group.csv     : 지역 묶음 × 업종, 2016-12 → 최근 '대전 안 그 업종 비중' 변화(%)
- industry_by_area.csv      : 20개 상권 × 업종 6개, 상권 안 업종 비율 변화(%p)
- industry_tram_effect.csv  : 업종별 트램 효과(정거장 500m 셀 평균, 낮음·기본·높음)
- industry.png
비교 시점: 2016-12 와 최근(2026-06) 두 점. 교육·보건의료는 2023-03~2024-09 에만 절반 가까이 빠졌다가
돌아온 '업종별 자료 단절'이 있어 이어 붙이기(chain) 대신 두 끝점 원값과 '업종 구성비'(전체 대비 비율)로 비교
"""
import numpy as np
import pandas as pd

import config as C
from build_dong_panel import CATS


def chain(series_by_period, breaks):
    r = (series_by_period / series_by_period.shift()).where(~breaks, 1.0).fillna(1.0)
    return r.cumprod()


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

    S = pd.read_csv(C.OUT_DIR / "dong_panel_store.csv", dtype={"period": str}, encoding="utf-8-sig")
    per = S.drop_duplicates("period").set_index("period").sort_index()
    brk = per.data_break.astype(bool)
    base_p, last_p = "201612", S.period.max()

    # 1) 대전 전체: 원값 변화 + 구성비 변화
    city = S.groupby("period")[[f"n_{c}" for c in CATS]].sum().sort_index()
    city.columns = CATS
    tot = city.sum(axis=1)
    idx = city / city.loc[base_p] * 100
    idx.round(2).to_csv(C.OUT_DIR / "industry_city_trend.csv", encoding="utf-8-sig")
    comp0, comp1 = city.loc[base_p] / tot[base_p] * 100, city.loc[last_p] / tot[last_p] * 100
    g_city = pd.DataFrame({"점포 수 변화(%)": (idx.loc[last_p] - 100).round(1),
                           "구성비 2016(%)": comp0.round(1), "구성비 최근(%)": comp1.round(1),
                           "구성비 변화(%p)": (comp1 - comp0).round(1)}).sort_values("구성비 변화(%p)", ascending=False)
    g_city.to_csv(C.OUT_DIR / "industry_city_summary.csv", encoding="utf-8-sig")
    print(f"[대전 업종 변화 {base_p} → {last_p}] (전체 점포 {tot[last_p] / tot[base_p] * 100 - 100:+.1f}%)\n",
          g_city.to_string())

    # 2) 지역 묶음별: 대전 안 그 업종 비중 변화
    prof = pd.read_csv(C.OUT_DIR / "dong_profile.csv", encoding="utf-8-sig")
    prof["k"] = range(len(prof))                                    # dong_profile 은 geojson 순서 = k
    grp = {"원도심(동·중·대덕)": prof.k[prof.si.isin(["동구", "중구", "대덕구"])],
           "신도심(서·유성)": prof.k[prof.si.isin(["서구", "유성구"])],
           "트램 권역(점포 50%↑ 500m 안)": prof.k[prof.tram500_share >= 0.5],
           "트램 밖(점포 10%↓ 500m 안)": prof.k[prof.tram500_share < 0.1]}
    rows = []
    for gname, ks in grp.items():
        sub = S[S.k.isin(set(ks))].groupby("period")[[f"n_{c}" for c in CATS]].sum().sort_index()
        sub.columns = CATS
        for c in CATS:
            sh = sub[c] / city[c]
            rows.append({"group": gname, "category": c, "n_dongs": len(ks), "n_stores_latest": int(sub[c].iloc[-1]),
                         "share_of_city_latest_pct": round(sh.loc[last_p] * 100, 1),
                         "share_chg_pct": round((sh.loc[last_p] / sh.loc[base_p] - 1) * 100, 1)})
    G = pd.DataFrame(rows)
    G.to_csv(C.OUT_DIR / "industry_by_group.csv", index=False, encoding="utf-8-sig")
    pv = G.pivot(index="group", columns="category", values="share_chg_pct")[CATS]
    print("\n[지역별: 대전 안 그 업종 비중 변화 %] (+ = 그 지역으로 업종이 모이는 중)\n", pv.to_string())

    # 3) 20개 상권 업종 구성 (store_panel 의 6개 업종, 상권 안 비율 변화 %p)
    T = pd.read_csv(C.OUT_DIR / "store_panel.csv", dtype={"period": str}, encoding="utf-8-sig")
    six = {"n_food": "음식", "n_retail": "소매", "n_personal": "수리·개인", "n_edu": "교육", "n_health": "보건의료",
           "n_lodging": "숙박"}
    a0 = T[T.period == base_p].set_index("code")
    a1 = T[T.period == last_p].set_index("code")
    A = pd.DataFrame({"name": a1.name})
    for col, nm in six.items():
        A[f"{nm}_2016"] = (a0[col] / a0.n_stores * 100).round(1)
        A[f"{nm}_최근"] = (a1[col] / a1.n_stores * 100).round(1)
        A[f"{nm}_변화p"] = (A[f"{nm}_최근"] - A[f"{nm}_2016"]).round(1)
    ch_cols = [f"{nm}_변화p" for nm in six.values()]
    A["가장 늘어난 업종"] = A[ch_cols].idxmax(axis=1).str.replace("_변화p", "")
    A["가장 줄어든 업종"] = A[ch_cols].idxmin(axis=1).str.replace("_변화p", "")
    A.to_csv(C.OUT_DIR / "industry_by_area.csv", encoding="utf-8-sig")
    print("\n[20개 상권: 상권 안 업종 비율 변화 %p, 2016-12 → 최근]\n",
          A[["name"] + ch_cols + ["가장 늘어난 업종", "가장 줄어든 업종"]].to_string())

    # 4) 업종별 트램 효과 (정거장 500m 셀)
    sc = pd.read_csv(C.OUT_DIR / "scenario_tram_uplift.csv", encoding="utf-8-sig")
    t = sc[sc.in_tram_500 == 1].groupby("cat_name")[["eff_low", "eff_base", "eff_high"]].mean()
    t = (np.expm1(t) * 100).round(2).sort_values("eff_base", ascending=False)
    t.columns = ["낮음(%)", "기본(%)", "높음(%)"]
    t.to_csv(C.OUT_DIR / "industry_tram_effect.csv", encoding="utf-8-sig")
    print("\n[업종별 트램 효과, 정거장 500m 셀 평균, 개통 초기 1~4년, 땅값 기준 추정]\n", t.to_string())

    # 그림
    fig = plt.figure(figsize=(17, 6.5))
    ax1 = fig.add_subplot(1, 3, 1)
    for c in g_city.index:
        s = idx[c]
        ax1.plot(pd.to_datetime(s.index, format="%Y%m"), s.values, label=f"{c} {g_city.loc[c, '점포 수 변화(%)']:+.0f}%")
    ax1.axvspan(pd.Timestamp("2023-03-01"), pd.Timestamp("2024-09-30"), color="gray", alpha=.15)
    ax1.axhline(100, c="k", lw=.5); ax1.set_title("대전 업종별 점포 수 (2016-12 = 100)\n회색 = 교육·보건의료 일부 누락 구간")
    ax1.legend(fontsize=7)
    ax2 = fig.add_subplot(1, 3, 2)
    im = ax2.imshow(pv.values, cmap="RdBu_r", vmin=-15, vmax=15, aspect="auto")
    ax2.set_xticks(range(len(CATS))); ax2.set_xticklabels(CATS, rotation=45, ha="right", fontsize=8)
    ax2.set_yticks(range(len(pv))); ax2.set_yticklabels(pv.index, fontsize=8)
    for i in range(pv.shape[0]):
        for j in range(pv.shape[1]):
            ax2.text(j, i, f"{pv.values[i, j]:+.0f}", ha="center", va="center", fontsize=7)
    ax2.set_title("지역별 업종 비중 변화 (%, 빨강 = 그 지역으로 모임)"); plt.colorbar(im, ax=ax2, shrink=.6)
    ax3 = fig.add_subplot(1, 3, 3)
    yy = np.arange(len(t))[::-1]
    ax3.barh(yy, t["기본(%)"], color="C3", label="기본")
    ax3.scatter(t["높음(%)"], yy, c="C1", zorder=3, label="높음")
    ax3.scatter(t["낮음(%)"], yy, c="gray", zorder=3, label="낮음")
    ax3.set_yticks(yy); ax3.set_yticklabels(t.index, fontsize=8)
    ax3.set_title("업종별 트램 효과 (정거장 500m, 개통 초기, 땅값 기준 추정 %) — 업종 비율은 가정"); ax3.legend(fontsize=8)
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "industry.png", dpi=130)
    print("→ outputs/industry_city_summary.csv, industry_city_trend.csv, industry_by_group.csv, industry_by_area.csv, industry_tram_effect.csv, industry.png")


if __name__ == "__main__":
    main()
