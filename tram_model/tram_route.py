"""트램 2호선 노선 순서 (정거장 번호 ≠ 노선 순서).

- 순환선: 201 → … → 240 → 201 (본선 40개)
- 연축지선: 순환선에서 가장 가까운 정거장 → 241 동춘당 → 242 법동 → 243 읍내 → 244 연축
- 진잠지선: 233 관저네거리 → 245 진잠네거리 (KDI 2024 재검토: 관저네거리 = 본선·진잠지선 분기, 진잠 = 편측단선)
  (2026-10-25 수정: 전에는 245를 대정(231)과 원앙네거리(232) 사이 순환선 안에 넣었음)
번호가 바뀌거나 정거장이 늘면 LOOP / BRANCH 만 고치면 됨.
"""
import numpy as np

LOOP = list(range(201, 241))
BRANCH = [241, 242, 243, 244]
SPURS = [(233, [245])]                                 # (갈라지는 순환선 정거장, 지선 정거장들)


def route_paths(st):
    """st: station_no, lat, lon 이 있는 표 → [순환선 [[lon,lat],…], 지선 [[lon,lat],…]] (pydeck PathLayer 용)."""
    pos = {int(r.station_no): (float(r.lon), float(r.lat)) for r in st.itertuples()}
    loop = [pos[n] for n in LOOP if n in pos]
    paths = [loop + loop[:1]]
    br = [pos[n] for n in BRANCH if n in pos]
    if br:
        lon0, lat0 = br[0]
        d = [np.hypot((lo - lon0) * 0.806, la - lat0) for lo, la in loop]   # 경도 축척 cos(36.3°)
        paths.append([loop[int(np.argmin(d))]] + br)
    for anchor, stops in SPURS:
        sp = [pos[n] for n in stops if n in pos]
        if sp and anchor in pos:
            paths.append([pos[anchor]] + sp)
    return [[list(p) for p in path] for path in paths]
