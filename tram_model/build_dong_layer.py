"""행정동(82개) 경계 폴리곤에 상권 지표를 붙여 지도 앱용 GeoJSON 만들기.

입력
- data/daejeon_dong_2023.geojson : 대전 행정동 경계 (통계청 2023-01 기준, 사용자 제공 지도에서 추출)
- 상가정보 2026-06 (data/raw), 트램 정거장 좌표, 1호선 역 좌표
- outputs/landprice_parcels.csv.gz, landprice_long.pkl (build_landprice.py)
- data/sangkwon_areas.csv (행정동 안에 있는 상권 표시)

출력: outputs/dong_polygons.geojson (properties 에 지표), outputs/dong_profile.csv

지표
- n_stores, top3 : 2026-06 점포 수, 업종 대분류 상위 3
- tram500_share  : 트램 정거장 500m 안 점포 비율
- tram_effect(_low/_high) : 트램 효과(%, 개통 6년 후) = tram500_share × 정거장 권역 효과
    기본 = 대전 1호선 1단계 지가 효과(landprice_effects.csv), 낮음 = P2 버스 저밀 0.89%, 높음 = P2 음식·소매 평균
- land_price, land_chg_5y_pct, land_chg_10y_pct : 지목 '대' 필지 공시지가 중앙값, 같은 필지 상승률 중앙값
"""
import json

import numpy as np
import pandas as pd
from matplotlib.path import Path as MPath
from scipy.spatial import cKDTree

import config as C
from build_dataset import load_stores, to_xy

DONG = C.ROOT / "data" / "daejeon_dong_2023.geojson"


def polygons(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    return geom["coordinates"]


def label_points(gj, lon, lat):
    """점 → 행정동 번호 (-1 = 대전 밖)."""
    lab = np.full(len(lon), -1)
    pts = np.c_[lon, lat]
    for k, f in enumerate(gj["features"]):
        for poly in polygons(f["geometry"]):
            ring = np.asarray(poly[0])
            x0, y0 = ring.min(0); x1, y1 = ring.max(0)
            box = (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1) & (lab < 0)
            if not box.any():
                continue
            inside = MPath(ring).contains_points(pts[box])
            for hole in poly[1:]:
                inside &= ~MPath(np.asarray(hole)).contains_points(pts[box])
            idx = np.where(box)[0][inside]
            lab[idx] = k
    return lab


def tram_effects():
    lit = pd.read_csv(C.LIT_PARAMS).set_index("param_id").value.astype(float, errors="ignore")
    f = C.OUT_DIR / "landprice_effects.csv"
    dj = np.log1p(0.058)
    if f.exists():
        E = pd.read_csv(f, encoding="utf-8-sig")
        r = E[E.analysis.str.contains("1호선 1단계")]
        if len(r):
            dj = np.log1p(r.effect_pct.iloc[0] / 100)
    low = float(lit["P2_mod_bus_low"])
    high = (float(lit["P2_POI_eatdrink"]) + float(lit["P2_POI_retail"])) / 2
    return {"tram_effect": dj, "tram_effect_low": low, "tram_effect_high": high}


def main():
    gj = json.load(open(DONG, encoding="utf-8"))
    n = len(gj["features"])
    print(f"행정동 {n}개", flush=True)

    # 점포
    s = load_stores()
    s["dong_k"] = label_points(gj, s.lon.values, s.lat.values)
    exact = C.ROOT / "data" / "tram_stations.csv"
    st = pd.read_csv(exact if exact.exists() else C.ROOT / "data" / "tram_stations_approx.csv", encoding="utf-8-sig")
    st["x"], st["y"] = to_xy(st.lat, st.lon)
    d, _ = cKDTree(st[["x", "y"]].values).query(s[["x", "y"]].values)
    s["tram500"] = d <= 500
    g = s[s.dong_k >= 0].groupby("dong_k")
    D = pd.DataFrame({"n_stores": g.size(), "tram500_share": g.tram500.mean()})
    D["top3"] = g["상권업종대분류명"].agg(lambda v: " / ".join(f"{a} {b}" for a, b in v.value_counts().head(3).items()))

    # 공시지가 (지목 '대')
    pf, lf = C.OUT_DIR / "landprice_parcels.csv.gz", C.OUT_DIR / "landprice_long.pkl"
    if pf.exists() and lf.exists():
        G = pd.read_csv(pf, encoding="utf-8-sig", usecols=["pnu", "lat", "lon", "is_dae"])
        G = G[G.is_dae == 1]
        G["dong_k"] = label_points(gj, G.lon.values, G.lat.values)
        L = pd.read_pickle(lf)
        ly = int(L.year.max())
        W = L[L.year.isin([ly, ly - 5, ly - 10]) & L.pnu.isin(G.pnu)].pivot(index="pnu", columns="year", values="price")
        W = W.join(G.set_index("pnu").dong_k)
        W = W[W.dong_k >= 0]
        gw = W.groupby("dong_k")
        D["land_price"] = gw[ly].median()
        D["land_chg_5y_pct"] = (np.expm1(gw.apply(lambda x: np.log(x[ly] / x[ly - 5]).median())) * 100).round(1)
        D["land_chg_10y_pct"] = (np.expm1(gw.apply(lambda x: np.log(x[ly] / x[ly - 10]).median())) * 100).round(1)
        print(f"공시지가 {ly}년 기준 필지 {len(W):,}개", flush=True)

    # 트램 효과 (점포 기준 500m 비율 × 권역 효과)
    for col, eff in tram_effects().items():
        D[col] = (D.tram500_share * np.expm1(eff) * 100).round(2)

    # 행정동 안 상권, 가장 가까운 트램 정거장
    areas = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig")
    cen = areas.anchors.str.split(";").str[0].str.split(expand=True).astype(float)
    areas["dong_k"] = label_points(gj, cen[1].values, cen[0].values)
    D["areas"] = areas[areas.dong_k >= 0].groupby("dong_k").apply(
        lambda a: ", ".join(a["code"] + " " + a["name"]), include_groups=False)

    rows = []
    for k, f in enumerate(gj["features"]):
        ring = np.asarray(polygons(f["geometry"])[0][0])
        clon, clat = ring.mean(0)
        cx, cy = to_xy(clat, clon)
        dist, j = cKDTree(st[["x", "y"]].values).query([cx, cy])
        p = f["properties"]
        r = {"id": p["adm_cd2"], "kind": "dong", "name": f"{p['si']} {p['dong']}", "si": p["si"], "dong": p["dong"],
             "nearest_tram": int(st.station_no.iloc[j]), "nearest_tram_m": int(round(dist))}
        if k in D.index:
            for c, v in D.loc[k].items():
                r[c] = None if (isinstance(v, float) and np.isnan(v)) else (round(float(v), 4) if isinstance(v, (float, np.floating)) else (int(v) if isinstance(v, (np.integer,)) else v))
        f["properties"] = r
        rows.append(r)
    P = pd.DataFrame(rows)
    P.to_csv(C.OUT_DIR / "dong_profile.csv", index=False, encoding="utf-8-sig")
    json.dump(gj, open(C.OUT_DIR / "dong_polygons.geojson", "w", encoding="utf-8"), ensure_ascii=False)
    print(P.sort_values("tram_effect", ascending=False)[["name", "n_stores", "tram500_share", "tram_effect",
                                                         "land_chg_5y_pct"]].head(8).to_string(index=False))
    print("→ outputs/dong_polygons.geojson, dong_profile.csv")


if __name__ == "__main__":
    main()
