"""20개 상권 '권역' 폴리곤: 대전시 행정구역 전체를 빈틈없이 20개로 나눔 (지도 색칠용).

- 대전 경계 = 행정동 82개 폴리곤 합 (data/daejeon_dong_2023.geojson)
- 대전 안 모든 지점을 '가장 가까운 상권'에 배정 (기준점까지 거리 ÷ 상권 반경, build_areas.assign 과 같은 규칙)
  → 이웃 권역끼리 경계가 정확히 맞닿는 지도 (가중 보로노이)
- 40m 격자로 나눈 뒤 경계선을 따서 폴리곤으로 (단순화 안 함 → 이웃 경계가 어긋나지 않음)
- 데이터(점수·지표)는 상권 그대로. 권역은 '그 상권이 가장 가까운 지역'이라는 표시용
출력: outputs/sangkwon_regions.geojson (properties: code, name, area_km2)
"""
import json

import numpy as np
import pandas as pd
from matplotlib.path import Path as MPath

import config as C
from build_areas import assign, from_xy
from build_dataset import to_xy
from build_dong_layer import DONG, polygons

GRID = 40


def main():
    from skimage import measure
    gj = json.load(open(DONG, encoding="utf-8"))
    rings = [np.asarray(p[0]) for f in gj["features"] for p in polygons(f["geometry"])]
    allpts = np.vstack(rings)
    x0, y0 = to_xy(allpts[:, 1].min(), allpts[:, 0].min())
    x1, y1 = to_xy(allpts[:, 1].max(), allpts[:, 0].max())
    gx = np.arange(float(x0) - GRID, float(x1) + GRID, GRID)
    gy = np.arange(float(y0) - GRID, float(y1) + GRID, GRID)
    XX, YY = np.meshgrid(gx, gy)
    la, lo = from_xy(XX.ravel(), YY.ravel())
    pts = np.c_[lo, la]
    inside = np.zeros(len(pts), bool)
    for ring in rings:
        bx0, by0 = ring.min(0); bx1, by1 = ring.max(0)
        m = (~inside) & (pts[:, 0] >= bx0) & (pts[:, 0] <= bx1) & (pts[:, 1] >= by0) & (pts[:, 1] <= by1)
        if m.any():
            inside[np.where(m)[0][MPath(ring).contains_points(pts[m])]] = True
    print(f"대전 경계 안 격자 {inside.sum():,}개 ({inside.sum() * GRID * GRID / 1e6:.0f}㎢)", flush=True)

    anc = pd.read_csv(C.OUT_DIR / "sangkwon_anchors.csv", encoding="utf-8-sig")
    anc["x"], anc["y"] = to_xy(anc.lat, anc.lon)
    areas = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig")
    codes = list(areas.code)
    # 반경 제한 없이 가장 가까운 상권 (assign 의 '1 넘으면 -1' 을 피하려고 반경을 크게 늘려서 같은 비율 유지)
    big = anc.assign(radius_m=anc.radius_m * 1e4)
    lab, _ = assign(XX.ravel()[inside], YY.ravel()[inside], big, codes)
    L = np.full(XX.size, -1)
    L[inside] = lab
    L = L.reshape(XX.shape)

    feats = []
    for k, c in enumerate(codes):
        mask = np.pad((L == k).astype(float), 1)
        if mask.sum() == 0:
            continue
        polys = []
        for cont in measure.find_contours(mask, 0.5):
            if len(cont) < 4:
                continue
            yy = gy[0] + (cont[:, 0] - 1) * GRID
            xx = gx[0] + (cont[:, 1] - 1) * GRID
            lat, lon = from_xy(xx, yy)
            ring = [[round(float(a), 6), round(float(b), 6)] for a, b in zip(lon, lat)]
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            area = 0.5 * abs(np.dot(xx, np.roll(yy, 1)) - np.dot(yy, np.roll(xx, 1)))
            polys.append((area, ring))
        polys.sort(key=lambda t: -t[0])
        # 다른 고리 안에 들어간 고리는 구멍
        shells, holes = [], []
        for area, ring in polys:
            p = np.asarray(ring)
            host = next((i for i, (sa, sr) in enumerate(shells) if MPath(np.asarray(sr)).contains_point(p[0])), None)
            (holes.append((host, ring)) if host is not None else shells.append((area, ring)))
        geom_polys = [[sr] + [hr for h, hr in holes if h == i] for i, (sa, sr) in enumerate(shells)]
        r = areas.set_index("code").loc[c]
        geom = {"type": "Polygon", "coordinates": geom_polys[0]} if len(geom_polys) == 1 else \
            {"type": "MultiPolygon", "coordinates": geom_polys}
        feats.append({"type": "Feature", "geometry": geom,
                      "properties": {"code": c, "name": r["name"], "gu": r.gu, "type": r.type,
                                     "area_km2": round(float((L == k).sum() * GRID * GRID / 1e6), 1)}})
    json.dump({"type": "FeatureCollection", "features": feats},
              open(C.OUT_DIR / "sangkwon_regions.geojson", "w", encoding="utf-8"), ensure_ascii=False)
    sizes = {f["properties"]["name"]: f["properties"]["area_km2"] for f in feats}
    print("권역 면적(㎢):", dict(sorted(sizes.items(), key=lambda t: -t[1])))
    print(f"→ outputs/sangkwon_regions.geojson ({len(feats)}개 권역)")


if __name__ == "__main__":
    main()
