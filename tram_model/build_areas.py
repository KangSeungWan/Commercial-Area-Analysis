"""대전 20개 상권: 기준점 보정 → 겹치지 않는 폴리곤 → 상권 요약.

입력
- data/sangkwon_areas.csv : 상권 정의 (편집용). anchors = "위도 경도;위도 경도" (여러 지점이면 이어 붙인 상권)
- data/raw 상가정보, 버스정류장 (build_dataset.py 와 같은 원본)
- data/tram_stations.csv (설계도면 확정, 있으면 우선) / data/tram_stations_approx.csv (추정)

출력
- outputs/sangkwon_polygons.geojson : 지도용 폴리곤 (클릭 시 보여줄 속성 포함)
- outputs/sangkwon_summary.csv      : 상권별 요약 (점포 수, 업종 구성, 트램·버스 접근성)
- outputs/sangkwon_anchors.csv      : 보정 전·후 기준점

방법
1) 기준점 보정: 각 기준점을 반경×0.6 안 점포들의 중심으로 최대 150m까지 이동 (3회 반복)
2) 영역: 점(또는 격자)마다 '가장 가까운 기준점까지 거리 ÷ 반경' 이 가장 작은 상권에 배정, 그 값 ≤ 1 이면 포함
   → 이웃 상권과 겹치지 않음 (으능정이–대전역, 탄방역–탄방네거리처럼 붙어 있는 곳)
3) 폴리곤: 20m 격자 배정 결과의 경계선을 따서 GeoJSON 으로 저장 (scikit-image 필요)

python build_areas.py
"""
import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import config as C
from build_dataset import load_stores, load_bus, load_stations, to_xy, MX, MY

AREAS_CSV = C.ROOT / "data" / "sangkwon_areas.csv"
GRID_M = 20
MAX_SHIFT_M = 150


def from_xy(x, y):
    return np.asarray(y) / MY + C.LAT0, np.asarray(x) / MX + 127.0


def load_areas():
    a = pd.read_csv(AREAS_CSV, encoding="utf-8-sig", dtype={"line1_station": str})
    rows = []
    for _, r in a.iterrows():
        for i, p in enumerate(str(r.anchors).split(";")):
            lat, lon = map(float, p.split())
            rows.append({"code": r.code, "anchor_no": i + 1, "lat0": lat, "lon0": lon, "radius_m": r.radius_m})
    anc = pd.DataFrame(rows)
    anc["x0"], anc["y0"] = to_xy(anc.lat0, anc.lon0)
    return a, anc


def refine_anchors(anc, sxy, tree):
    """점포 밀집 중심으로 기준점을 조금 옮김 (랜드마크 좌표 오차 보정)."""
    xs, ys = [], []
    for _, r in anc.iterrows():
        x, y = r.x0, r.y0
        for _ in range(3):
            idx = tree.query_ball_point([x, y], r.radius_m * 0.6)
            if len(idx) < 10:
                break
            cx, cy = sxy[idx].mean(0)
            dx, dy = cx - r.x0, cy - r.y0
            d = np.hypot(dx, dy)
            if d > MAX_SHIFT_M:                        # 원래 지점에서 너무 멀어지지 않게
                cx, cy = r.x0 + dx / d * MAX_SHIFT_M, r.y0 + dy / d * MAX_SHIFT_M
            x, y = cx, cy
        xs.append(x); ys.append(y)
    anc["x"], anc["y"] = xs, ys
    anc["lat"], anc["lon"] = from_xy(anc.x, anc.y)
    anc["shift_m"] = np.hypot(anc.x - anc.x0, anc.y - anc.y0).round(0)
    return anc


def assign(px, py, anc, codes):
    """각 점 → (상권 코드, 정규화 거리). 정규화 거리 > 1 이면 어느 상권에도 속하지 않음."""
    best = np.full(len(px), np.inf)
    lab = np.full(len(px), -1)
    for k, c in enumerate(codes):
        g = anc[anc.code == c]
        d = np.min(np.hypot(px[:, None] - g.x.values, py[:, None] - g.y.values) / g.radius_m.values, axis=1)
        better = d < best
        best[better], lab[better] = d[better], k
    lab[best > 1] = -1
    return lab, best


def polygons(anc, codes):
    from skimage import measure
    pad = anc.radius_m.max() + 3 * GRID_M
    x0, x1 = anc.x.min() - pad, anc.x.max() + pad
    y0, y1 = anc.y.min() - pad, anc.y.max() + pad
    gx = np.arange(x0, x1, GRID_M); gy = np.arange(y0, y1, GRID_M)
    XX, YY = np.meshgrid(gx, gy)
    lab, _ = assign(XX.ravel(), YY.ravel(), anc, codes)
    lab = lab.reshape(XX.shape)
    out = {}
    for k, c in enumerate(codes):
        mask = np.pad((lab == k).astype(float), 1)
        rings = []
        for cont in measure.find_contours(mask, 0.5):
            cont = measure.approximate_polygon(cont, tolerance=0.6)
            if len(cont) < 4:
                continue
            yy = y0 + (cont[:, 0] - 1) * GRID_M
            xx = x0 + (cont[:, 1] - 1) * GRID_M
            la, lo = from_xy(xx, yy)
            ring = [[round(float(a), 6), round(float(b), 6)] for a, b in zip(lo, la)]
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            area = 0.5 * abs(np.dot(xx, np.roll(yy, 1)) - np.dot(yy, np.roll(xx, 1)))
            rings.append((area, ring))
        rings.sort(key=lambda t: -t[0])
        out[c] = [r for _, r in rings]   # 첫 번째 = 바깥 경계 (지금 구조에선 구멍 없음)
    return out


def main():
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    a, anc = load_areas()
    s = load_stores()
    sxy = s[["x", "y"]].values
    tree = cKDTree(sxy)
    anc = refine_anchors(anc, sxy, tree)
    codes = list(a.code)

    # 점포 배정
    lab, _ = assign(s.x.values, s.y.values, anc, codes)
    s["area"] = np.where(lab >= 0, np.array(codes)[np.clip(lab, 0, None)], None)
    inside = s[s.area.notna()]

    # 버스·트램
    bus = load_bus()
    blab, _ = assign(bus[:, 0], bus[:, 1], anc, codes)
    st = load_stations()

    rows = []
    for k, r in a.iterrows():
        c = r.code
        g = inside[inside.area == c]
        ga = anc[anc.code == c]
        cx, cy = (g.x.mean(), g.y.mean()) if len(g) else (ga.x.mean(), ga.y.mean())
        lat, lon = from_xy(cx, cy)
        # 트램: 상권 안(정규화 거리 ≤1)이거나 가장 가까운 정거장
        dn = np.min(np.hypot(st.x.values[:, None] - ga.x.values, st.y.values[:, None] - ga.y.values)
                    / ga.radius_m.values, axis=1)
        dm = np.min(np.hypot(st.x.values[:, None] - ga.x.values, st.y.values[:, None] - ga.y.values), axis=1)
        within = st.station_no[dn <= 1].astype(str).tolist()
        cat = g["상권업종대분류명"].value_counts()
        mid = g["상권업종중분류명"].value_counts().head(3)
        rows.append({
            "code": c, "name": r["name"], "gu": r.gu, "type": r.type, "radius_m": r.radius_m,
            "n_anchors": len(ga), "center_lat": round(float(lat), 6), "center_lon": round(float(lon), 6),
            "n_stores": len(g),
            "share_food": round(cat.get("음식", 0) / max(len(g), 1), 3),
            "share_retail": round(cat.get("소매", 0) / max(len(g), 1), 3),
            "top3_mid": " / ".join(f"{i} {v}" for i, v in mid.items()),
            "branch_share": round(float(g.is_branch.mean()) if len(g) else 0, 3),
            "n_bus_stops": int((blab == k).sum()),
            "tram_in_area": ",".join(within),
            "nearest_tram": int(st.station_no.values[dm.argmin()]),
            "nearest_tram_m": int(dm.min()),
            "line1_station": r.line1_station if isinstance(r.line1_station, str) else "",
            "tram_group": "트램 근접" if within or dm.min() <= 500 else "노선 밖(비교군)",
        })
    summ = pd.DataFrame(rows)
    summ.to_csv(C.OUT_DIR / "sangkwon_summary.csv", index=False, encoding="utf-8-sig")
    anc[["code", "anchor_no", "lat0", "lon0", "lat", "lon", "shift_m", "radius_m"]].round(6) \
        .to_csv(C.OUT_DIR / "sangkwon_anchors.csv", index=False, encoding="utf-8-sig")

    polys = polygons(anc, codes)
    feats = []
    for _, r in summ.iterrows():
        rings = polys.get(r.code, [])
        if not rings:
            continue
        props = {k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()}
        geom = ({"type": "Polygon", "coordinates": [rings[0]]} if len(rings) == 1 else
                {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]})
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    json.dump({"type": "FeatureCollection", "features": feats},
              open(C.OUT_DIR / "sangkwon_polygons.geojson", "w", encoding="utf-8"), ensure_ascii=False)

    print(summ[["code", "name", "n_stores", "tram_in_area", "nearest_tram", "nearest_tram_m", "tram_group"]]
          .to_string(index=False))
    print(f"\n기준점 이동 거리(m): 평균 {anc.shift_m.mean():.0f}, 최대 {anc.shift_m.max():.0f}")
    print(f"→ {C.OUT_DIR / 'sangkwon_polygons.geojson'} ({len(feats)}개 폴리곤)")


if __name__ == "__main__":
    main()
