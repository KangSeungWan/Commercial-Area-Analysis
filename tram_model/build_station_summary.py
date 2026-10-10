"""트램 정거장 45개 × 500m 영향권 요약 (지도 앱 정거장 클릭용).

입력: 상가정보 2026-06(data/raw), 트램 정거장 좌표, outputs/sangkwon_anchors.csv, area_scores.csv,
      landprice_cells.csv, scenario_tram_uplift.csv
출력
- outputs/station_summary.csv : 정거장별 500m 안 점포 수·업종 비율·체인 비율·공시지가·트램 기본 효과·포함 상권
- outputs/station_areas.csv   : 정거장 × 상권 (영향권 안 그 상권 점포 수·비율, 진단·점수)
"""
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import config as C
from build_dataset import load_stores, to_xy
from build_areas import assign

R = 500


def main():
    exact = C.ROOT / "data" / "tram_stations.csv"
    st = pd.read_csv(exact if exact.exists() else C.ROOT / "data" / "tram_stations_approx.csv", encoding="utf-8-sig")
    st["x"], st["y"] = to_xy(st.lat, st.lon)
    s = load_stores()
    anc = pd.read_csv(C.OUT_DIR / "sangkwon_anchors.csv", encoding="utf-8-sig")
    anc["x"], anc["y"] = to_xy(anc.lat, anc.lon)
    areas = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig")
    codes = list(areas.code)
    lab, _ = assign(s.x.values, s.y.values, anc, codes)
    s["area"] = np.where(lab >= 0, np.array(codes)[np.clip(lab, 0, None)], None)
    tree = cKDTree(s[["x", "y"]].values)
    scores = pd.read_csv(C.OUT_DIR / "area_scores.csv", encoding="utf-8-sig").set_index("code") \
        if (C.OUT_DIR / "area_scores.csv").exists() else None
    lpc = pd.read_csv(C.OUT_DIR / "landprice_cells.csv", encoding="utf-8-sig") \
        if (C.OUT_DIR / "landprice_cells.csv").exists() else None
    if lpc is not None:
        lpc["x"], lpc["y"] = (lpc.gx + 0.5) * C.CELL_M, (lpc.gy + 0.5) * C.CELL_M
    sc = pd.read_csv(C.OUT_DIR / "scenario_tram_uplift.csv", encoding="utf-8-sig")
    eff_by_station = sc[sc.in_tram_500 == 1].groupby("nearest_tram")[["eff_low", "eff_base", "eff_high"]].mean()

    rows, arows = [], []
    for _, t in st.iterrows():
        idx = tree.query_ball_point([t.x, t.y], R)
        g = s.iloc[idx]
        vc = g["상권업종대분류명"].value_counts()
        r = {"station_no": int(t.station_no), "station_name": t.station_name, "lat": t.lat, "lon": t.lon,
             "coord_source": t.get("coord_source", ""), "n_stores": len(g),
             "food_pct": round(vc.get("음식", 0) / max(len(g), 1) * 100, 1),
             "retail_pct": round(vc.get("소매", 0) / max(len(g), 1) * 100, 1),
             "branch_pct": round(g.is_branch.mean() * 100, 1) if len(g) else np.nan,
             "top3": " / ".join(f"{k} {v}" for k, v in vc.head(3).items()),
             "top3_mid": " / ".join(f"{k} {v}" for k, v in g["상권업종중분류명"].value_counts().head(3).items())}
        if lpc is not None:
            m = np.hypot(lpc.x - t.x, lpc.y - t.y) <= R
            r["land_price"] = float(lpc.land_price[m].median()) if m.any() else np.nan
            r["land_growth_5y_pct"] = round(float(lpc.land_growth_5y[m].median()) * 100, 1) if m.any() else np.nan
        if t.station_no in eff_by_station.index:
            e = eff_by_station.loc[t.station_no]
            for k in ("low", "base", "high"):
                r[f"tram_effect_{k}"] = round(float(np.expm1(e[f"eff_{k}"]) * 100), 2)
        ga = g[g.area.notna()].area.value_counts()
        r["areas"] = ", ".join(f"{a} {areas.set_index('code').name[a]}({n})" for a, n in ga.items())
        rows.append(r)
        for a, n in ga.items():
            tot = int((s.area == a).sum())
            ar = {"station_no": int(t.station_no), "code": a, "name": areas.set_index("code").name[a],
                  "stores_in_500m": int(n), "share_of_area_pct": round(n / tot * 100, 1)}
            if scores is not None and a in scores.index:
                for c in ("quadrant", "risk_score", "growth_score", "type_name", "tram_gain"):
                    ar[c] = scores.loc[a, c]
            arows.append(ar)
    S = pd.DataFrame(rows)
    A = pd.DataFrame(arows)
    S.to_csv(C.OUT_DIR / "station_summary.csv", index=False, encoding="utf-8-sig")
    A.to_csv(C.OUT_DIR / "station_areas.csv", index=False, encoding="utf-8-sig")
    print(S.sort_values("n_stores", ascending=False)[["station_no", "station_name", "n_stores", "food_pct",
                                                       "land_growth_5y_pct", "tram_effect_base", "areas"]].head(10).to_string(index=False))
    print(f"→ outputs/station_summary.csv ({len(S)}개 정거장), station_areas.csv ({len(A)}행)")


if __name__ == "__main__":
    main()
