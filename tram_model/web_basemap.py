"""공개 웹사이트 지도 바탕(자체 제작): 행정동 경계(통계청)에서 대전 시 경계·구 경계 선과 구 이름 위치를 만듦 (2026-10-28)

외부 지도 타일 없이 그리기 위한 것 — 저작권·키·서비스 중단 걱정 없음.
  city   : 시 경계 (어느 동과도 공유되지 않는 변)
  gu     : 구 경계 (서로 다른 구의 동 두 개가 공유하는 변)
  labels : 구 이름 자리 — 구 안에서, 핵심 상권·트램 노선과 가장 먼 곳(이름이 지도 내용을 가리지 않게)
사용: export_web.py 가 불러 web_data/geo_gu.json 으로 저장
"""
import collections
import math

import numpy as np
from matplotlib.path import Path as MPath

GU = {"30110": "동구", "30140": "중구", "30170": "서구", "30200": "유성구", "30230": "대덕구"}
VIEW = (127.27, 127.54, 36.30, 36.455)   # 첫 화면에 보이는 범위(대략) — 이름이 화면 안에 들어오게


def _rings(geom):
    return geom["coordinates"] if geom["type"] == "Polygon" else [r for p in geom["coordinates"] for r in p]


def _chain(edges):
    """변 목록 → 이어진 선(polyline) 목록"""
    adj = collections.defaultdict(list)
    for a, b in edges:
        adj[a].append(b); adj[b].append(a)
    seen, lines = set(), []
    starts = [p for p in adj if len(adj[p]) != 2] + list(adj)
    for s in starts:
        for n in adj[s]:
            e = tuple(sorted((s, n)))
            if e in seen:
                continue
            line, prev, cur = [s], s, n
            seen.add(e)
            while True:
                line.append(cur)
                nxt = [q for q in adj[cur] if q != prev and tuple(sorted((cur, q))) not in seen]
                if len(adj[cur]) != 2 or not nxt:
                    break
                seen.add(tuple(sorted((cur, nxt[0])))); prev, cur = cur, nxt[0]
            lines.append([list(p) for p in line])
    return lines


def build(geo_dongs, geo_core=None, route=None, stations=None):
    E = collections.defaultdict(set)
    polys = collections.defaultdict(list)
    for f in geo_dongs["features"]:
        did = str(f["properties"]["dong_id"]); gu = did[:5]
        for r in _rings(f["geometry"]):
            pts = [(round(x, 6), round(y, 6)) for x, y in r]
            polys[gu].append(MPath(np.array(pts)))
            for a, b in zip(pts, pts[1:]):
                if a != b:
                    E[tuple(sorted((a, b)))].add((did, gu))
    city = [e for e, s in E.items() if len(s) == 1]
    gul = [e for e, s in E.items() if len(s) == 2 and len({x[1] for x in s}) == 2]

    # 피할 점: 핵심 상권 경계 점 + 트램 노선 점
    avoid = []
    if geo_core:
        for f in geo_core["features"]:
            for r in _rings(f["geometry"]):
                avoid += [(x, y) for x, y in r[::3]]
    for path in route or []:
        avoid += [tuple(p) for p in path]
    for st in stations or []:
        avoid.append((st["lon"], st["lat"]))
    av = np.array(avoid) if avoid else np.zeros((0, 2))
    k = math.cos(math.radians(36.35))
    # 구마다 자기 경계(시 경계 + 구 경계 중 그 구에 닿는 변) 점
    gub = collections.defaultdict(list)
    for e, sset in E.items():
        gus = {x[1] for x in sset}
        if len(sset) == 1 or len(gus) == 2:
            for g in gus:
                gub[g] += [e[0], e[1]]

    def mind(pts, ref):
        if not len(ref):
            return np.full(len(pts), 1e9)
        dx = (pts[:, None, 0] - ref[None, :, 0]) * k; dy = pts[:, None, 1] - ref[None, :, 1]
        return np.sqrt(dx * dx + dy * dy).min(1) * 111.2   # km

    labels = []
    xs = np.linspace(VIEW[0], VIEW[1], 80); ys = np.linspace(VIEW[2], VIEW[3], 55)
    grid = np.array([(x, y) for x in xs for y in ys])
    for code, name in GU.items():
        inside = np.zeros(len(grid), bool)
        for p in polys[code]:
            inside |= p.contains_points(grid)
        cand = grid[inside]
        if not len(cand):
            continue
        d_edge = mind(cand, np.array(gub[code]))      # 구 안쪽 깊이 (구의 '가운데')
        d_av = mind(cand, av)                           # 상권·노선과 거리
        # 구의 가운데 쪽이면서(경계에서 1km 이상) 상권·노선·정거장 이름표에서 떨어진 곳
        cen = cand.mean(0)                              # 구(화면 안 부분)의 무게중심에서 너무 멀면 감점 → 구를 대표하는 자리
        d_cen = np.hypot((cand[:, 0] - cen[0]) * k, cand[:, 1] - cen[1]) * 111.2
        score = np.minimum(d_edge, 2.5) + 1.2 * np.minimum(d_av, 2.5) - (d_edge < 1.0) * 3 - 0.35 * d_cen
        i = int(np.argmax(score))
        labels.append({"name": name, "pos": [round(float(cand[i][0]), 5), round(float(cand[i][1]), 5)]})
    return {"city": _chain(city), "gu": _chain(gul), "labels": labels,
            "source": "통계청 행정동 경계에서 만든 시·구 경계(자체 제작)"}


if __name__ == "__main__":
    import json, sys
    d = sys.argv[1]
    out = build(json.load(open(f"{d}/geo_dongs.json")), json.load(open(f"{d}/geo_core.json")), json.load(open(f"{d}/meta.json"))["route"], json.load(open(f"{d}/meta.json"))["stations"])
    json.dump(out, open(f"{d}/geo_gu.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(len(out["city"]), len(out["gu"]), out["labels"])
