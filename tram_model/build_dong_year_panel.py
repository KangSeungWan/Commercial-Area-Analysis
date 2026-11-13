"""행정동 82개 × 연도 패널 (공시지가 + 점포 + 개폐업 + 8989 카드매출·유동인구) → outputs/dong_year_panel.csv

입력: outputs/dong_panel_land.csv (build_dong_panel.py), outputs/dong_panel_store.csv, outputs/dong_profile.csv,
      outputs/survey_dong.csv, outputs/8989/dong_panel_8989.csv + dong_code_map.csv (build_8989_tables.py, 없어도 됨)
출력: outputs/dong_year_panel.csv  (82개 동 × 1990~2026)

열 (area_panel.csv 와 같은 이름을 씀 → 상권용 코드 재사용)
- 정적: dong_id(통계청 10자리), si, dong, old_town(동·중·대덕), nearest_tram, nearest_tram_m, tram500_share, n_stores_2026, areas(겹치는 핵심 상권)
- 공시지가 (1990~, 지목 '대'; 없는 동은 전체지목 → land_sample 열): land_idx(2015=100), land_rel_idx(대전 전체 대비), land_median, land_yoy
- 점포 (2015~, 매년 12월 분기, 2026 은 6월): n_stores, store_share_idx(단절 보정 비중 지수, 2016=100), store_share_yoy,
  food_ratio, retail_ratio, branch_share
- 개폐업 (연 비율, 단절·미기록 분기 제외): open_rate_y, close_rate_y
- 8989 (2024~): sales_m(월평균 카드매출, 79업종 합계; 2025=1~12월, 2026=1~8월), sales_food_m, sales_retail_m, sales_yoy(2026은 1~8월 동월 비교),
  floating_daily(연평균), resident(연평균), closures_8989(연 폐업 수 합)
- 실태조사 2021: survey_bad_pct, survey_decline_pct
"""
import numpy as np
import pandas as pd

import config as C

OUT = C.OUT_DIR


def store_annual():
    T = pd.read_csv(OUT / "dong_panel_store.csv", dtype={"period": str, "dong_id": str}, encoding="utf-8-sig")
    T = T.sort_values(["dong_id", "period"])
    r = (T.share / T.groupby("dong_id").share.shift()).where(T.data_break == 0, 1.0).fillna(1.0)
    T["share_chain"] = r.groupby(T.dong_id).cumprod()
    T["year"] = T.period.str[:4].astype(int)
    last = T.period.max()
    snap = T[T.period.str.endswith("12") | (T.period == last)].sort_values("period").groupby(["dong_id", "year"]).tail(1)
    base = snap[snap.year == 2016].set_index("dong_id").share_chain
    snap = snap.assign(store_share_idx=lambda d: (d.share_chain / d.dong_id.map(base) * 100).round(2),
                       food_ratio=lambda d: (d["n_음식"] / d.n_stores).round(4),
                       retail_ratio=lambda d: (d["n_소매"] / d.n_stores).round(4))
    rates = T.groupby(["dong_id", "year"]).agg(open_rate_y=("open_rate", lambda v: v.mean() * 4 if v.notna().sum() >= 2 else np.nan),
                                               close_rate_y=("close_rate", lambda v: v.mean() * 4 if v.notna().sum() >= 2 else np.nan))
    S = snap.set_index(["dong_id", "year"])[["period", "n_stores", "store_share_idx", "food_ratio", "retail_ratio", "branch_share"]].join(rates)
    S = S.rename(columns={"period": "store_period"}).reset_index()
    S["store_share_yoy"] = S.groupby("dong_id").store_share_idx.pct_change().round(4)
    return S


def sales_annual():
    f = OUT / "8989" / "dong_panel_8989.csv"
    if not f.exists():
        print("8989 패널 없음 → 매출·유동인구 열 생략"); return None
    D = pd.read_csv(f, dtype={"plcCd": str, "stdrYm": str, "adm_cd2": str}, encoding="utf-8-sig")
    D["year"] = D.stdrYm.str[:4].astype(int); D["mon"] = D.stdrYm.str[4:].astype(int)
    g = D.groupby(["adm_cd2", "year"])
    A = g.agg(sales_m=("useAmount_합계", "mean"), sales_food_m=("useAmount_음식점", "mean"), sales_retail_m=("useAmount_도소매", "mean"),
              floating_daily=("floating_daily", "mean"), resident=("resident", "mean"), closures_8989=("clsbiz", "sum"),
              sales_months=("useAmount_합계", "count")).reset_index()
    A.loc[A.sales_months == 0, ["sales_m", "sales_food_m", "sales_retail_m"]] = np.nan
    # 전년 대비: 두 해에 모두 있는 달(동월)끼리 비교
    def yoy(code):
        d = D[D.adm_cd2 == code].dropna(subset=["useAmount_합계"]); out = {}
        for y in sorted(d.year.unique()):
            a, b = d[d.year == y], d[d.year == y - 1]
            m = sorted(set(a.mon) & set(b.mon))
            if len(m) >= 3:
                out[y] = (a[a.mon.isin(m)].useAmount_합계.mean() / b[b.mon.isin(m)].useAmount_합계.mean() - 1) * 100
        return out
    A["sales_yoy"] = [yoy(c).get(y, np.nan) for c, y in zip(A.adm_cd2, A.year)]
    return A.rename(columns={"adm_cd2": "dong_id"}).round(2)


def main():
    prof = pd.read_csv(OUT / "dong_profile.csv", dtype={"id": str}, encoding="utf-8-sig")
    stat = prof.rename(columns={"id": "dong_id", "n_stores": "n_stores_2026"})[["dong_id", "si", "dong", "nearest_tram", "nearest_tram_m", "tram500_share", "n_stores_2026", "areas"]]
    stat["old_town"] = stat.si.isin(["동구", "중구", "대덕구"]).astype(int)

    L = pd.read_csv(OUT / "dong_panel_land.csv", dtype={"dong_id": str}, encoding="utf-8-sig")
    has_dae = set(L[L["sample"] == "대"].dong_id)            # '대' 표본이 없는 동(월평3동, 아파트 단지)은 전체지목으로 대체
    L = L[(L["sample"] == "대") | (~L.dong_id.isin(has_dae) & (L["sample"] == "전체지목"))]
    L = L.rename(columns={"idx": "land_idx", "rel_idx": "land_rel_idx", "median_price": "land_median", "sample": "land_sample"}).sort_values(["dong_id", "year"])
    L["land_yoy"] = L.groupby("dong_id").land_idx.pct_change(fill_method=None).round(4)
    years = range(int(L.year.min()), int(L.year.max()) + 1)
    P = pd.MultiIndex.from_product([stat.dong_id, years], names=["dong_id", "year"]).to_frame(index=False)
    P = P.merge(L[["dong_id", "year", "land_idx", "land_rel_idx", "land_median", "land_yoy", "n_parcels", "land_sample"]], on=["dong_id", "year"], how="left")
    P = P.merge(store_annual(), on=["dong_id", "year"], how="left")
    A = sales_annual()
    if A is not None: P = P.merge(A, on=["dong_id", "year"], how="left")
    sv = pd.read_csv(OUT / "survey_dong.csv", dtype={"동코드": str}, encoding="utf-8-sig").rename(columns={"동코드": "dong_id", "bad_pct": "survey_bad_pct", "decline_pct": "survey_decline_pct"})
    stat = stat.merge(sv[["dong_id", "survey_bad_pct", "survey_decline_pct"]], on="dong_id", how="left")
    P = stat.merge(P, on="dong_id").sort_values(["si", "dong", "year"])
    P.to_csv(OUT / "dong_year_panel.csv", index=False, encoding="utf-8-sig")
    print(f"dong_year_panel.csv: 동 {P.dong_id.nunique()}개 × {P.year.nunique()}년 = {len(P)}행 "
          f"(공시지가 {P.land_idx.notna().sum()}칸, 점포 {P.n_stores.notna().sum()}칸, 매출 {P.sales_m.notna().sum() if 'sales_m' in P else 0}칸)")
    return P


if __name__ == "__main__":
    main()
