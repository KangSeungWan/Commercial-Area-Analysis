"""B. 상권 × 연도 패널 (점포 + 공시지가 + 사건) → outputs/area_panel.csv

입력: outputs/store_panel.csv (build_store_panel.py), outputs/landprice_area_panel.csv (build_landprice.py),
      outputs/area_profile.csv (make_map_data.py, 없어도 됨), data/area_events.csv, data/sangkwon_areas.csv
출력: outputs/area_panel.csv  (20개 상권 × 1990~2026년)

열
- 공시지가 (1990~): land_idx(2015=100), land_rel_idx(대전 전체 대비), land_median, land_yoy(전년 대비)
- 점포 (2015~, 매년 12월 분기 값, 2026 은 6월): n_stores, store_share_idx(자료 단절을 빼고 이은 대전 내 비중 지수, 2016=100),
  store_share_yoy, food_ratio, diversity_mid(업종 다양성, 섀넌), hhi_major(업종 집중도), branch_share(체인 비율)
- 개폐업 (그 해 분기 평균 × 4 ≈ 연 비율, 단절·미기록 분기 제외): open_rate_y, close_rate_y
- 사건: ev_E01 … = 사건 뒤 경과 연수(사건 해 = 0, 이전은 음수, 해당 없는 상권은 빈칸), post_any_anchor 등
- 정적: name, type(원도심/신도심), p6_zone, tram_group, nearest_tram_m
"""
import numpy as np
import pandas as pd

import config as C


def store_annual():
    T = pd.read_csv(C.OUT_DIR / "store_panel.csv", dtype={"period": str}, encoding="utf-8-sig")
    T = T.sort_values(["code", "period"])
    r = (T.share / T.groupby("code").share.shift()).where(T.data_break == 0, 1.0).fillna(1.0)
    T["share_chain"] = r.groupby(T.code).cumprod()
    T["year"] = T.period.str[:4].astype(int)
    # 연 대표값: 12월 분기 (2026 은 마지막 분기)
    last = T.period.max()
    snap = T[T.period.str.endswith("12") | (T.period == last)].sort_values("period").groupby(["code", "year"]).tail(1)
    base = snap[snap.year == 2016].set_index("code").share_chain
    snap = snap.assign(store_share_idx=lambda d: (d.share_chain / d.code.map(base) * 100).round(2))
    rates = T.groupby(["code", "year"]).agg(open_rate_y=("open_rate", lambda v: v.mean() * 4 if v.notna().sum() >= 2 else np.nan),
                                            close_rate_y=("close_rate", lambda v: v.mean() * 4 if v.notna().sum() >= 2 else np.nan))
    S = snap.set_index(["code", "year"])[["period", "n_stores", "store_share_idx", "food_ratio", "diversity_mid",
                                          "hhi_major", "branch_share"]].join(rates)
    S = S.rename(columns={"period": "store_period"}).reset_index()
    S["store_share_yoy"] = S.groupby("code").store_share_idx.pct_change().round(4)
    return S


def main():
    areas = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig")
    L = pd.read_csv(C.OUT_DIR / "landprice_area_panel.csv", encoding="utf-8-sig")
    L = L[L.code != "ALL"].rename(columns={"idx": "land_idx", "rel_idx": "land_rel_idx", "median_price": "land_median"})
    L = L.sort_values(["code", "year"])
    L["land_yoy"] = L.groupby("code").land_idx.pct_change().round(4)
    years = range(int(L.year.min()), int(L.year.max()) + 1)
    P = pd.MultiIndex.from_product([areas.code, years], names=["code", "year"]).to_frame(index=False)
    P = P.merge(L[["code", "year", "land_idx", "land_rel_idx", "land_median", "land_yoy"]], on=["code", "year"], how="left")
    P = P.merge(store_annual(), on=["code", "year"], how="left")

    # 사건: 경과 연수
    ev = pd.read_csv(C.ROOT / "data" / "area_events.csv", encoding="utf-8-sig")
    ev["yr"] = pd.to_datetime(ev.date).dt.year
    for _, e in ev.iterrows():
        tg = list(areas.code) if e.area_codes == "ALL" else e.area_codes.split(";")
        P[f"ev_{e.event_id}"] = np.where(P.code.isin(tg), P.year - e.yr, np.nan)
    anchor = ev[ev.event_type.isin(["anchor_open"])]
    P["post_anchor_open"] = 0
    for _, e in anchor.iterrows():
        P.loc[P.code.isin(e.area_codes.split(";")) & (P.year > e.yr), "post_anchor_open"] = 1
    P["post_line1"] = 0
    for eid in ("E01", "E02"):
        e = ev[ev.event_id == eid].iloc[0]
        P.loc[P.code.isin(e.area_codes.split(";")) & (P.year > e.yr), "post_line1"] = 1

    stat = areas[["code", "name", "gu", "type", "p6_zone"]]
    pf = C.OUT_DIR / "area_profile.csv"
    if pf.exists():
        stat = stat.merge(pd.read_csv(pf, encoding="utf-8-sig")[["code", "tram_group", "nearest_tram_m"]], on="code", how="left")
    P = stat.merge(P, on="code")
    P.to_csv(C.OUT_DIR / "area_panel.csv", index=False, encoding="utf-8-sig")
    n_store = P.n_stores.notna().sum()
    print(f"area_panel.csv: 상권 {P.code.nunique()}개 × {P.year.nunique()}년 = {len(P)}행 "
          f"(공시지가 {P.land_idx.notna().sum()}칸, 점포 {n_store}칸)")
    return P


if __name__ == "__main__":
    main()
