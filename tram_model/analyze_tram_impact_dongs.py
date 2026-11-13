"""행정동 82개 트램 효과 금액 (analyze_tram_impact.py 의 행정동 합계판)

입력: outputs/landprice_parcels.csv.gz (필지 좌표·정거장 거리), outputs/parcel_value.csv.gz (2026 면적·공시가),
      outputs/dong_polygons.geojson, outputs/dong_forecast_land.csv, outputs/dong_scores.csv, tram_effect.py
출력: outputs/dong_tram_money.csv  (동별 정거장 500m 안 공시지가 총액·증가액 낮음/기본/높음, 동 전체 총액, 2034 트램 유무 차이)
방법: 필지 좌표 → 행정동 폴리곤(점-다각형), 공공 지목(도로·하천 등) 제외, 금액 = 총액 × 시나리오 효과 % (상권과 같은 식)
"""
import json
import numpy as np
import pandas as pd

import config as C
import tram_effect as TE
from analyze_tram_impact import PUBLIC_JIMOK, EOK

OUT = C.OUT_DIR


def point_in_poly(lon, lat, poly):
    x, y = np.asarray(lon), np.asarray(lat); inside = np.zeros(len(x), bool)
    px, py = np.array(poly)[:, 0], np.array(poly)[:, 1]; j = len(px) - 1
    for i in range(len(px)):
        cond = ((py[i] > y) != (py[j] > y)) & (x < (px[j] - px[i]) * (y - py[i]) / (py[j] - py[i] + 1e-12) + px[i]); inside ^= cond; j = i
    return inside


def assign_dong(G):
    gj = json.load(open(OUT / "dong_polygons.geojson", encoding="utf-8"))
    G = G.copy(); G["dong_id"] = None
    lon, lat = G.lon.values, G.lat.values
    for ft in gj["features"]:
        geom = ft["geometry"]; polys = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
        # 경계 상자로 먼저 거르기
        pts = np.array([p for poly in polys for p in poly]); bb = (lon >= pts[:, 0].min()) & (lon <= pts[:, 0].max()) & (lat >= pts[:, 1].min()) & (lat <= pts[:, 1].max())
        idx = np.where(bb & G.dong_id.isna().values)[0]
        if not len(idx): continue
        m = np.zeros(len(idx), bool)
        for poly in polys: m |= point_in_poly(lon[idx], lat[idx], poly)
        G.iloc[idx[m], G.columns.get_loc("dong_id")] = str(ft["properties"]["id"])
    return G


def main():
    L = TE.levels(); pct = {s: L[s]["pct"] / 100 for s in TE.SCEN}
    G0 = pd.read_csv(OUT / "landprice_parcels.csv.gz", encoding="utf-8-sig")
    V = pd.read_csv(OUT / "parcel_value.csv.gz", encoding="utf-8-sig")
    G = G0.merge(V, on="pnu", how="inner"); G = G[~G.jimok.isin(PUBLIC_JIMOK)]
    print(f"필지 {len(G):,}개 → 행정동 배정 중 (1~2분) ...", flush=True)
    G = assign_dong(G); print("배정 안 된 필지:", int(G.dong_id.isna().sum()))
    near = G[G.d_tram <= 500]
    tot = G.groupby("dong_id").value.sum(); tn = near.groupby("dong_id").agg(n_parcels_500=("pnu", "size"), area_km2_500=("area_m2", lambda v: v.sum() / 1e6), value_500=("value", "sum"))
    names = {str(f["properties"]["id"]): f["properties"]["name"] for f in json.load(open(OUT / "dong_polygons.geojson", encoding="utf-8"))["features"]}
    M = pd.DataFrame({"dong_id": list(names), "name": list(names.values())}).set_index("dong_id")
    M["value_total_eok"] = (tot.reindex(M.index) / EOK).round(1)
    M = M.join(tn); M["value_500_eok"] = (M.value_500 / EOK).round(1); M["share_500_value"] = (M.value_500 / tot.reindex(M.index)).round(3)
    for s in TE.SCEN: M[f"gain_{s}_eok"] = (M.value_500.fillna(0) * pct[s] / EOK).round(1)
    # 2034 트램 유무 차이 (예측 경로 × 동 전체 총액)
    F = pd.read_csv(OUT / "dong_forecast_land.csv", dtype={"code": str}, encoding="utf-8-sig"); f = F[F.year == F.year.max()].set_index("code")
    for s in TE.SCEN: M[f"gap2034_{s}_eok"] = ((f[f"tram_{s}"] / f.base_path - 1).reindex(M.index) * M.value_total_eok).round(1)
    Sc = pd.read_csv(OUT / "dong_scores.csv", dtype={"dong_id": str}, encoding="utf-8-sig").set_index("dong_id")
    M["quadrant"] = Sc.quadrant.reindex(M.index); M["risk_score"] = Sc.risk_score.reindex(M.index)
    M = M.drop(columns=["value_500"]).fillna({"n_parcels_500": 0, "area_km2_500": 0, "value_500_eok": 0, "share_500_value": 0}).sort_values("gain_base_eok", ascending=False).reset_index()
    M.to_csv(OUT / "dong_tram_money.csv", index=False, encoding="utf-8-sig")
    print(f"500m 안 총액 합계 {M.value_500_eok.sum():,.0f}억 원, 기본 증가액 합계 {M.gain_base_eok.sum():,.0f}억 (낮음 {M.gain_low_eok.sum():,.0f} ~ 높음 {M.gain_high_eok.sum():,.0f})")
    print(M.head(12)[["name", "quadrant", "value_total_eok", "value_500_eok", "share_500_value", "gain_base_eok", "gap2034_base_eok"]].to_string(index=False))
    print("먼저 지원 동 합계(기본):", round(M[M.quadrant == "먼저 지원"].gain_base_eok.sum()), "억,  2034 차이 합계:", round(M[M.quadrant == "먼저 지원"].gap2034_base_eok.sum()), "억")


if __name__ == "__main__":
    main()
