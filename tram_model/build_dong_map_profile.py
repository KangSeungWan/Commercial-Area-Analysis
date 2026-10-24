"""지도용 행정동 82개 요약표 (상권 area_profile.csv 의 행정동판)

입력: dong_profile.csv (build_dong_layer), dong_types.csv, dong_scores.csv, dong_forecast_land.csv, dong_forecast_store.csv,
      dong_year_panel.csv, survey_dong.csv, outputs/8989/dong_8989_summary.csv(있으면), dong_polygons.geojson, data/tram_stations.csv
출력: outputs/dong_map_profile.csv, outputs/dong_map.geojson (폴리곤 + 핵심 지표), outputs/dong_station_summary.csv (정거장 45개 → 걸친 동)
"""
import json
import numpy as np
import pandas as pd

import config as C

OUT = C.OUT_DIR


def main():
    prof = pd.read_csv(OUT / "dong_profile.csv", dtype={"id": str}, encoding="utf-8-sig").rename(columns={"id": "dong_id"})
    T = pd.read_csv(OUT / "dong_types.csv", dtype={"dong_id": str}, encoding="utf-8-sig")
    S = pd.read_csv(OUT / "dong_scores.csv", dtype={"dong_id": str}, encoding="utf-8-sig")
    FL = pd.read_csv(OUT / "dong_forecast_land.csv", dtype={"code": str}, encoding="utf-8-sig")
    FS = pd.read_csv(OUT / "dong_forecast_store.csv", dtype={"code": str}, encoding="utf-8-sig")
    P = pd.read_csv(OUT / "dong_year_panel.csv", dtype={"dong_id": str}, encoding="utf-8-sig")

    D = prof[["dong_id", "name", "si", "dong", "nearest_tram", "nearest_tram_m", "n_stores", "tram500_share", "top3", "land_price", "land_chg_5y_pct", "land_chg_10y_pct", "areas"]].copy()
    D = D.merge(T[["dong_id", "cluster", "type_name", "stability", "land_rel_g10", "land_recent", "store_g", "store_recent", "close_rate", "open_rate", "food_ratio", "retail_ratio", "branch_share", "small"]].rename(columns={"stability": "type_stability"}), on="dong_id", how="left")
    D = D.merge(S[["dong_id", "risk_score", "growth_score", "quadrant", "quadrant_stability", "quadrant_alt", "quadrant_uncertain", "risk_drivers", "growth_drivers", "tram_gain", "fc_base", "fc_tram", "note", "survey_bad_pct"]].rename(columns={"tram_gain": "tram_effect", "note": "score_note"}), on="dong_id", how="left")
    end = FL.year.max()
    fl = FL[FL.year == end].set_index("code"); fs = FS[FS.year == end].set_index("code")
    D["land_2034_base"], D["land_2034_lo80"], D["land_2034_hi80"], D["land_2034_tram"] = [D.dong_id.map(fl[c]) for c in ("base_path", "lo80", "hi80", "tram_base")]
    D["store_2034_base"], D["store_2034_tram"] = D.dong_id.map(fs.base_path), D.dong_id.map(fs.tram_base)
    last = P.sort_values("year").groupby("dong_id").tail(1).set_index("dong_id")
    D["land_rel_idx"] = D.dong_id.map(last.land_rel_idx)
    D["store_share_chg_5y_pct"] = D.dong_id.map(((P[P.year == 2026].set_index("dong_id").store_share_idx / P[P.year == 2021].set_index("dong_id").store_share_idx - 1) * 100).round(1))
    f = OUT / "8989" / "dong_8989_summary.csv"
    if f.exists():
        E = pd.read_csv(f, dtype={"adm_cd2": str}, encoding="utf-8-sig").set_index("adm_cd2")
        for c in ("sales_2026_m", "sales_yoy_pct", "sales_per_store_2026", "floating_2026", "resident_2026", "resident_chg_24_26_pct", "closure_rate_12m_pct"):
            D["s89_" + c] = D.dong_id.map(E[c])
        D["s89_market_caveat"] = D.dong_id.isin(E[E.sales_per_store_2026 < 1.5e6].index)   # 전통시장 동: 점포당 150만 원 미만 → 카드매출 과소
    D["tram_group"] = np.select([D.tram500_share >= 0.5, D.tram500_share >= 0.1], ["트램 영향권", "일부"], "영향권 밖")
    D = D.round(4)
    D.to_csv(OUT / "dong_map_profile.csv", index=False, encoding="utf-8-sig")

    gj = json.load(open(OUT / "dong_polygons.geojson", encoding="utf-8"))
    keep = ["dong_id", "name", "si", "dong", "type_name", "cluster", "risk_score", "growth_score", "quadrant", "quadrant_uncertain", "tram_effect", "tram500_share", "tram_group",
            "nearest_tram", "nearest_tram_m", "n_stores", "small", "land_rel_idx", "land_chg_5y_pct", "land_2034_base", "land_2034_tram", "s89_sales_yoy_pct", "s89_sales_per_store_2026", "s89_market_caveat", "areas"]
    Di = D.set_index("dong_id")
    for ft in gj["features"]:
        k = str(ft["properties"]["id"]); r = Di.loc[k] if k in Di.index else None
        ft["properties"] = {c: (None if r is None or (isinstance(r.get(c), float) and np.isnan(r.get(c))) else (r.get(c).item() if hasattr(r.get(c), "item") else r.get(c))) for c in keep if c != "dong_id"} | {"dong_id": k}
    json.dump(gj, open(OUT / "dong_map.geojson", "w", encoding="utf-8"), ensure_ascii=False)

    # 정거장 45개 → 500m 안에 걸친 동 (동 폴리곤과 정거장 500m 원이 겹치는지: 폴리곤 꼭짓점까지 최소 거리로 근사)
    st = pd.read_csv(C.ROOT / "data" / "tram_stations.csv", encoding="utf-8-sig")
    rows = []
    for _, s in st.iterrows():
        for ft in gj["features"]:
            geom = ft["geometry"]; polys = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
            pts = np.array([p for poly in polys for p in poly])
            dx = (pts[:, 0] - s.lon) * 111320 * np.cos(np.radians(s.lat)); dy = (pts[:, 1] - s.lat) * 110540
            dmin = float(np.sqrt(dx ** 2 + dy ** 2).min())
            # 정거장이 폴리곤 안이면 0
            inside = False
            for poly in polys:
                px, py = np.array(poly)[:, 0], np.array(poly)[:, 1]; j = len(px) - 1
                for i in range(len(px)):
                    if ((py[i] > s.lat) != (py[j] > s.lat)) and (s.lon < (px[j] - px[i]) * (s.lat - py[i]) / (py[j] - py[i] + 1e-12) + px[i]): inside = not inside
                    j = i
            d = 0.0 if inside else dmin
            if d <= 500:
                p = ft["properties"]
                rows.append(dict(station_no=int(s.station_no), station_name=s.station_name, dong_id=p["dong_id"], dong=p["name"], dist_m=round(d), inside=inside,
                                 quadrant=p["quadrant"], risk_score=p["risk_score"], growth_score=p["growth_score"], type_name=p["type_name"], n_stores=p["n_stores"], sales_yoy=p.get("s89_sales_yoy_pct")))
    SS = pd.DataFrame(rows).sort_values(["station_no", "dist_m"])
    SS.to_csv(OUT / "dong_station_summary.csv", index=False, encoding="utf-8-sig")
    print(f"dong_map_profile.csv {D.shape}, dong_map.geojson {len(gj['features'])}개, dong_station_summary.csv {len(SS)}행 (정거장 {SS.station_no.nunique()}개)")
    print(D.quadrant.value_counts().to_dict()); print(SS.groupby("station_no").size().describe().round(1)[["min", "50%", "max"]].to_dict())


if __name__ == "__main__":
    main()
