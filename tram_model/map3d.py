"""3D 지도 시제품 (B안) — 분석 결과 파일을 읽어 deck.gl 3D 지도 HTML 한 장을 만든다.

- 상권 20개 핵심 영역을 기둥처럼 세움 (높이 = 땅값 전망 / 땅값 기준 트램 효과 / 점포 수 / 쇠퇴 위험)
- 색 = 진단 4분류 (app.py 와 같은 색)
- 2026→2034 연도 재생, 2030 개통 후 트램이 노선을 따라 달림 (운행 간격은 연출용, 실제 시간표 아님)
- 바닥 = 행정동 경계 (배경 지도 타일 없이 그림 → 인터넷 지도 서버에 기대지 않음)
- outputs/buildings_3d.geojson 이 있으면 실제 건물 높이도 함께 올림 (속성 height_m)

사용:
    python tram_model/map3d.py            → outputs/map3d.html (브라우저로 바로 열 수 있음)
    app_3d.py 에서 make_html() 을 불러 Streamlit 화면에 넣음
"""
import json, math, os
from pathlib import Path

import pandas as pd

try:
    from tram_route import route_paths
except ImportError:                                    # app_3d.py 처럼 프로젝트 폴더에서 불렀을 때
    from tram_model.tram_route import route_paths

HERE = Path(__file__).resolve().parent
OUT, DATA = HERE / "outputs", HERE / "data"
TEMPLATE = HERE / "map3d_template.html"
OPEN_YEAR = 2030                                       # app.py 와 같음
QUAD = ["성장 지속", "트램 반등 기회", "쇠퇴 우려", "정체·안정"]


def _csv(p):
    return pd.read_csv(p, encoding="utf-8-sig") if p.exists() else None


def _r(v, n=5):
    return round(float(v), n)


def _ring(geom):
    """GeoJSON Polygon/MultiPolygon → 가장 큰 바깥 고리 [[lon,lat],…] (deck.gl PolygonLayer 용)."""
    rings = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
    return [[_r(x), _r(y)] for x, y in max(rings, key=len)]


def _simplify_geojson(gj, step=2):
    """행정동 경계를 점 간격으로 솎아 용량을 줄임 (바닥 그림용이라 정밀도 불필요)."""
    def thin(ring):
        r = ring[::step]
        return [[_r(x, 4), _r(y, 4)] for x, y in (r + [ring[-1]] if r[-1] != ring[-1] else r)]
    out = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for p in polys:
            if len(p[0]) >= 4:
                out.append(thin(p[0]))
    return out


def make_data():
    prof = _csv(OUT / "area_profile.csv")
    gj = json.load(open(OUT / "sangkwon_polygons.geojson", encoding="utf-8"))
    stations = _csv(DATA / "tram_stations.csv")
    if stations is None:
        stations = _csv(DATA / "tram_stations_approx.csv")
    stations = stations.sort_values("station_no")
    fc = _csv(OUT / "forecast_land.csv")
    ssum = _csv(OUT / "station_summary.csv")
    scen = _csv(OUT / "tram_scenarios.csv")
    dong_p = OUT / "dong_polygons.geojson"

    poly = {f["properties"]["code"]: f for f in gj["features"]}
    years = sorted(fc.year.unique().tolist()) if fc is not None else []
    areas = []
    for r in prof.itertuples():
        f = poly.get(r.code)
        if f is None:
            continue
        p = f["properties"]
        a = dict(code=r.code, name=r.name, gu=r.gu, quadrant=r.quadrant if r.quadrant in QUAD else "정체·안정",
                 type_name=getattr(r, "type_name", ""), poly=_ring(f["geometry"]),
                 center=[_r(p.get("center_lon")), _r(p.get("center_lat"))],
                 n_stores=int(r.n_stores), risk=_r(r.risk_score, 1), growth=_r(r.growth_score, 1),
                 eff={"low": _r(r.tram_effect_low, 2), "base": _r(r.tram_effect, 2), "high": _r(r.tram_effect_high, 2)},
                 nearest=f"{int(r.nearest_tram)}번 정거장 {int(r.nearest_tram_m)}m" if pd.notna(r.nearest_tram) else "")
        if fc is not None:
            g = fc[fc.code == r.code].set_index("year").reindex(years)
            a["fc"] = {k: [_r(v, 2) for v in g[c].ffill().tolist()]
                       for k, c in [("none", "base_path"), ("low", "tram_low"), ("base", "tram_base"), ("high", "tram_high")]}
        areas.append(a)

    n500 = dict(zip(ssum.station_no, ssum.n_stores)) if ssum is not None else {}
    stns = [dict(no=int(s.station_no), name=str(s.station_name), lon=_r(s.lon), lat=_r(s.lat),
                 n=int(n500.get(s.station_no, 0) or 0)) for s in stations.itertuples()]
    route = route_paths(stations)

    # 처음 보는 위치: 상권·정거장 전체 범위의 가운데
    xs = [x for a in areas for x, _ in a["poly"]] + [s["lon"] for s in stns]
    ys = [y for a in areas for _, y in a["poly"]] + [s["lat"] for s in stns]
    lon0, lat0 = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span_km = max((max(xs) - min(xs)) * 111.32 * math.cos(math.radians(lat0)), (max(ys) - min(ys)) * 111.32)

    def mid(codes):
        c = [a["center"] for a in areas if a["code"] in codes]
        return [_r(sum(x for x, _ in c) / len(c)), _r(sum(y for _, y in c) / len(c))] if c else [lon0, lat0]

    views = {"전체": dict(center=[_r(lon0), _r(lat0)], zoom=round(math.log2(40000 / span_km) + 0.35, 2), pitch=52, bearing=-18),
             "원도심": dict(center=mid({"A04", "A05", "A06"}), zoom=13.6, pitch=58, bearing=-28),
             "둔산": dict(center=mid({"A07", "A08", "A11"}), zoom=13.8, pitch=58, bearing=24),
             "유성": dict(center=mid({"A12", "A13", "A14"}), zoom=13.5, pitch=58, bearing=-40)}

    scen_lab = {"low": "낮음", "base": "기본", "high": "높음"}
    if scen is not None:
        scen_lab.update({r.scenario: f"{r.label} +{r.effect_pct:g}%" for r in scen.itertuples()})

    data = dict(areas=areas, stations=stns, route=route, years=years, open_year=OPEN_YEAR, views=views,
                scen_label=scen_lab,
                ground=_simplify_geojson(json.load(open(dong_p, encoding="utf-8"))) if dong_p.exists() else [])

    bp = OUT / "buildings_3d.geojson"                  # 선택: GIS건물통합정보 등에서 만든 건물 (height_m)
    if bp.exists():
        b = json.load(open(bp, encoding="utf-8"))
        data["buildings"] = [dict(p=_ring(f["geometry"]), h=_r(f["properties"].get("height_m", 10), 1))
                             for f in b["features"] if f.get("geometry")]
    return data


def make_html(data=None, standalone=True):
    """standalone=True 이면 브라우저로 바로 여는 완성 문서, False 면 본문만(아티팩트 게시용)."""
    data = data or make_data()
    body = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    if standalone:
        body = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1"></head><body>' + body + "</body></html>")
    return body


if __name__ == "__main__":
    p = OUT / "map3d.html"
    p.write_text(make_html(), encoding="utf-8")
    print(f"저장: {p} ({os.path.getsize(p) / 1024:.0f}KB)")
