"""3D 지도 시제품 (B안) — 분석 결과 파일을 읽어 deck.gl 3D 지도 HTML 한 장을 만든다.

- 상권 20개 핵심 영역을 기둥처럼 세움 (높이 = 땅값 전망 / 상권 가치(땅값) 기준 트램 효과 / 업종 변화(카페 비중) / 임대료 부담 / 점포 수 / 쇠퇴 위험)
- 색 = 진단 4분류 (app.py 와 같은 색)
- 2026→2034 연도 재생, 2030 개통 후 트램이 노선을 따라 달림 (운행 간격은 연출용, 실제 시간표 아님)
- 바닥 = 행정동 경계 (배경 지도 타일 없이 그림 → 인터넷 지도 서버에 기대지 않음)
- outputs/buildings_3d.geojson 이 있으면 실제 건물 높이도 함께 올림 (속성 height_m)

사용:
    python tram_model/map3d.py            → outputs/map3d.html (브라우저로 바로 열 수 있음)
    app.py 지도 화면의 '3D' 보기 → show() (Streamlit 부품, 클릭하면 앱 선택 상권이 바뀜)
    app_3d.py → make_html() 단독 화면
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
COMP_DIR = HERE / "map3d_component"                    # Streamlit 부품 폴더 (index.html = 화면 원본)
TEMPLATE = COMP_DIR / "index.html"
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


def _quad_before(r):
    """트램이 없을 때의 진단: '반등 기회'만 정거장 없이 다시 분류 (app.py · score_areas.py 와 같은 규칙)."""
    if r.quadrant != "트램 반등 기회":
        return r.quadrant if r.quadrant in QUAD else "정체·안정"
    return "쇠퇴 우려" if r.risk_score >= 50 else "성장 지속" if r.growth_score >= 50 else "정체·안정"


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
    comp = _csv(OUT / "composition_forecast.csv")       # 업종 변화: 카페·빵 비중 증가 %p (연도·시나리오별)
    rent = _csv(OUT / "rent_pressure.csv")              # 임대료 부담 위험 (점수 0~100, 등급)
    if comp is not None:
        comp = comp[comp.level == "상권"]
    if rent is not None:
        rent = rent[rent.level == "상권"].set_index("key")

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
                 qb=_quad_before(r),
                 eff={"low": _r(r.tram_effect_low, 2), "base": _r(r.tram_effect, 2), "high": _r(r.tram_effect_high, 2)},
                 nearest=f"{int(r.nearest_tram)}번 정거장 {int(r.nearest_tram_m)}m" if pd.notna(r.nearest_tram) else "")
        if fc is not None:
            g = fc[fc.code == r.code].set_index("year").reindex(years)
            a["fc"] = {k: [_r(v, 2) for v in g[c].ffill().tolist()]
                       for k, c in [("none", "base_path"), ("low", "tram_low"), ("base", "tram_base"), ("high", "tram_high")]}
        if comp is not None and years:
            g = comp[comp.key == r.code]
            a["comp"] = {s: [_r(v, 2) for v in g[g.scenario == s].set_index("year").cafe_bakery_pp.reindex(years).fillna(0).tolist()]
                         for s in ("low", "base", "high")}
        if rent is not None and r.code in rent.index:
            rr = rent.loc[r.code]
            a["rent"] = dict(grade=str(rr.rent_pressure), score=_r(rr.rent_pressure_score, 1) if pd.notna(rr.rent_pressure_score) else None,
                             drivers=str(rr.rent_drivers) if pd.notna(rr.rent_drivers) else "")
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


_COMPONENT = None


def show(data, tram="after", scen="base", metric=None, sel=None, height=600, key="map3d", mode="panel"):
    """앱(app.py) 지도 칸에 3D 지도를 넣음. 기둥·정거장을 누르면 {"area"|"station": …, "t": …} 를 돌려줌.
    tram: "after"/"before", scen: "low"/"base"/"high", metric: "land"/"tram"/"comp"/"rent"/"stores"/"risk" (None 이면 3D 안에서 고름).
    mode: "panel" = 지도 화면 칸 안(좁게), "full" = '3D 지도' 화면(넓게, 상권 카드의 '이 상권 진단 보기' → {"goto": 코드})."""
    global _COMPONENT
    import streamlit.components.v1 as components
    if _COMPONENT is None:
        _COMPONENT = components.declare_component("map3d", path=str(COMP_DIR))
    state = {"tram": tram, "scen": scen, "sel": sel}
    if metric:
        state["metric"] = metric
    return _COMPONENT(data=data, state=state, mode=mode, height=height, key=key, default=None)


def make_html(data=None, standalone=True):
    """standalone=True 이면 브라우저로 바로 여는 완성 문서, False 면 본문만(아티팩트 게시용).
    index.html 은 Streamlit 부품이 그대로 쓰는 완성 문서 → 데이터 자리(/*__DATA__*/null)만 채움."""
    data = data or make_data()
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    if not standalone:
        html = html.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    return html


if __name__ == "__main__":
    p = OUT / "map3d.html"
    p.write_text(make_html(), encoding="utf-8")
    print(f"저장: {p} ({os.path.getsize(p) / 1024:.0f}KB)")
