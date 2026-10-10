import json, os
import streamlit as st, pandas as pd, pydeck as pdk
from google import genai

st.set_page_config(page_title="대전 트램 상권 지도", layout="wide")
OUT = "tram_model/outputs"
df = pd.read_csv("map_data.csv", encoding="utf-8-sig")
_st = "tram_model/data/tram_stations.csv"          # 설계도면 보정 좌표 (있으면 우선)
stations = pd.read_csv(_st if os.path.exists(_st) else "tram_model/data/tram_stations_approx.csv", encoding="utf-8-sig")
stations = stations.sort_values("station_no")


@st.cache_data
def load_area():
    prof = pd.read_csv(f"{OUT}/area_profile.csv", encoding="utf-8-sig")
    gj = json.load(open(f"{OUT}/sangkwon_polygons.geojson", encoding="utf-8"))           # 상권 핵심 영역(반경 기반)
    rg_f = f"{OUT}/sangkwon_regions.geojson"                                               # 대전 전체를 나눈 권역
    rg = json.load(open(rg_f, encoding="utf-8")) if os.path.exists(rg_f) else None
    lp = pd.read_csv(f"{OUT}/landprice_area_panel.csv", encoding="utf-8-sig") \
        if os.path.exists(f"{OUT}/landprice_area_panel.csv") else None
    sp = pd.read_csv(f"{OUT}/store_panel.csv", dtype={"period": str}, encoding="utf-8-sig") \
        if os.path.exists(f"{OUT}/store_panel.csv") else None
    return prof, gj, rg, lp, sp


prof, gj, rg, lp, sp = load_area()
gj, rg = json.loads(json.dumps(gj)), (json.loads(json.dumps(rg)) if rg else None)   # 캐시 원본 보호
def _opt(name, **kw):
    p = f"{OUT}/{name}"
    return pd.read_csv(p, encoding="utf-8-sig", **kw) if os.path.exists(p) else None


fc = _opt("forecast_land.csv")
st_sum = _opt("station_summary.csv")                 # build_station_summary.py
st_areas = _opt("station_areas.csv")
ind_area = _opt("industry_by_area.csv")              # analyze_industry.py
events = pd.read_csv("tram_model/data/area_events.csv", encoding="utf-8-sig") \
    if os.path.exists("tram_model/data/area_events.csv") else None

# ── 사이드바 ──
st.sidebar.title("대전 트램 상권 지도")
view = st.sidebar.radio("보기", ["상권(20개)", "격자(250m)"], horizontal=True)
SCEN = {"기본(대전 실측)": "tram_effect", "낮음": "tram_effect_low", "높음(논문)": "tram_effect_high"}
SCEN = {k: v for k, v in SCEN.items() if v in df.columns}
scen = st.sidebar.radio("트램 시나리오", list(SCEN), horizontal=True)
st.sidebar.caption("트램 효과 = 개통 6년 후 정거장 500m 안 매출 변화 추정(%). "
                   "기본: 대전 1호선 1단계 역세권 지가 효과(+5.8%)를 업종·버스밀도·상권 위치로 조정. "
                   "높음: 영국 경전철 연구(Lan 2025) 업종별 계수. 낮음: 버스가 적은 지역 계수.")

import sys
sys.path.insert(0, "tram_model")
from tram_route import route_paths                                     # 순환선 + 연축 지선 (번호 ≠ 노선 순서)
route = [{"path": p} for p in route_paths(stations)]
lay_route = pdk.Layer("PathLayer", route, get_path="path", get_color=[30, 90, 200, 140], width_min_pixels=2)
stop_df = stations.merge(st_sum[["station_no", "n_stores"]], on="station_no", how="left") if st_sum is not None \
    else stations.assign(n_stores=None)
stop_df = stop_df.assign(name=stop_df.station_no.astype(str) + " " + stop_df.get("station_name", ""), type="트램 정거장",
                         val_label="500m 안 점포 " + stop_df.n_stores.fillna(0).astype(int).astype(str) + "개 · 클릭하면 영향권 표시")
lay_stop = pdk.Layer("ScatterplotLayer", stop_df, id="stations", get_position=["lon", "lat"], get_radius=70,
                     radius_min_pixels=4, get_fill_color=[30, 90, 200, 230], get_line_color=[255, 255, 255],
                     stroked=True, line_width_min_pixels=1, pickable=True)


def color_scale(v, rev=False):
    v = pd.to_numeric(v, errors="coerce")
    t = ((v - v.min()) / (v.max() - v.min() + 1e-9)).fillna(0)
    t = 1 - t if rev else t
    return [[255, int(220 * (1 - x)), 0, 150] for x in t]


def deck(layers, tooltip):
    return pdk.Deck(layers=layers, map_style="light", tooltip=tooltip,
                    initial_view_state=pdk.ViewState(latitude=36.345, longitude=127.39, zoom=11.3))


# ================================================================ 상권 보기
if view == "상권(20개)":
    prof["tram_sel"] = prof[SCEN[scen]]
    GROUPS = {
        "종합 진단": {"quadrant": "진단 (4분류)", "risk_score": "쇠퇴 위험 점수 (0~100)", "growth_score": "성장 가능 점수 (0~100)"},
        "트램 효과": {"tram_sel": f"트램 효과 (%, {scen})"},
        "땅값(공시지가)": {"land_chg_5y_pct": "5년 상승률 (%)", "land_rel_idx": "대전 평균 대비 (2015=100)"},
        "점포": {"store_share_chg_5y_pct": "대전 내 점포 비중 5년 변화 (%)", "close_rate_q_pct": "분기 폐업률 (%)",
               "n_stores": "점포 수 (2026-06)"},
        "상권 유형": {"cluster": "유형 (K-means 4개)"},
    }
    GROUPS = {g: {k: v for k, v in m.items() if k in prof.columns} for g, m in GROUPS.items()}
    GROUPS = {g: m for g, m in GROUPS.items() if m}
    AM = {k: v for m in GROUPS.values() for k, v in m.items()}
    grp = st.sidebar.radio("색칠 주제", list(GROUPS))
    opts = GROUPS[grp]
    am = st.sidebar.radio("지표", list(opts), format_func=opts.get) if len(opts) > 1 else list(opts)[0]
    if am == "quadrant":                                      # 진단 4분류
        QC = {"성장 지속": [44, 160, 44, 170], "트램 반등 기회": [255, 127, 14, 170], "쇠퇴 우려": [214, 39, 40, 170],
              "정체·안정": [150, 150, 150, 150]}
        colors = {c: QC.get(q, [200, 200, 200, 100]) for c, q in zip(prof.code, prof.quadrant)}
        st.sidebar.markdown("🟢 성장 지속 · 🟠 트램 반등 기회 · 🔴 쇠퇴 우려 · ⚪ 정체·안정")
    elif am == "cluster":                                       # 유형은 색 구분 (1 파랑, 2 주황, 3 초록, 4 빨강, …)
        PAL = [[31, 119, 180, 160], [255, 127, 14, 160], [44, 160, 44, 160], [214, 39, 40, 160], [148, 103, 189, 160]]
        colors = {c: PAL[(int(k) - 1) % len(PAL)] if pd.notna(k) else [180, 180, 180, 120]
                  for c, k in zip(prof.code, prof.cluster)}
        st.sidebar.markdown("\n".join(f"- **{int(k)}. {n}**" for k, n in
                                       prof.drop_duplicates("cluster").sort_values("cluster")[["cluster", "type_name"]].values))
    else:
        colors = dict(zip(prof.code, color_scale(prof[am].clip(upper=prof[am].quantile(.95)))))   # 노랑(낮음) → 빨강(높음)
        st.sidebar.caption("연한 노랑 = 낮음 → 진한 빨강 = 높음")
    show_region = rg is not None and st.sidebar.toggle("대전 전체를 상권 권역으로 채우기", value=True,
                                                       help="대전 모든 지점을 가장 가까운 상권에 배정한 권역. 끄면 상권 핵심 영역만 표시")
    info = prof.set_index("code")
    for f in gj["features"] + (rg["features"] if rg else []):
        c = f["properties"]["code"]
        r = info.loc[c]
        f["properties"].setdefault("nearest_tram", int(r.nearest_tram) if pd.notna(r.get("nearest_tram")) else None)
        f["properties"].setdefault("nearest_tram_m", int(r.nearest_tram_m) if pd.notna(r.get("nearest_tram_m")) else None)
        f["properties"].update({"fill": colors[c], "val": None if pd.isna(r[am]) else (r[am] if isinstance(r[am], str) else round(float(r[am]), 2)),
                                "tram_sel": round(float(r.tram_sel), 2)})
    names = dict(zip(prof.code, prof.code + " " + prof.name))
    order = list(prof.code)
    # 지도 클릭 결과는 rerun 시작 시 session_state["map"] 에 들어 있음 → 지도 그리기 전에 선택 반영
    ss = st.session_state
    ss.setdefault("sel_area", order[0]); ss.setdefault("sel_station", None)
    sel_obj = (ss.get("map") or {}).get("selection", {}) if isinstance(ss.get("map"), dict) else \
        (getattr(ss.get("map"), "selection", None) or {})
    objs = sel_obj.get("objects", {}) if sel_obj else {}
    click_area = (objs.get("areas") or [{}])[0].get("properties", {}).get("code") if objs.get("areas") else None
    click_stn = (objs.get("stations") or [{}])[0].get("station_no") if objs.get("stations") else None
    if click_area and click_area != ss.get("_last_area"):
        ss._last_area = click_area; ss.sel_area = click_area
    if click_stn is not None and click_stn != ss.get("_last_stn"):
        ss._last_stn = click_stn; ss.sel_station = int(click_stn)

    for f in gj["features"] + (rg["features"] if rg else []):
        f["properties"]["val_label"] = f"{AM[am]}: {f['properties']['val']}<br/>가까운 트램 " \
                                       f"{f['properties'].get('nearest_tram')}번 {f['properties'].get('nearest_tram_m')}m"
    sel = ss.sel_area
    fill_src = rg if show_region else gj
    lay_poly = pdk.Layer("GeoJsonLayer", fill_src, id="areas", pickable=True, stroked=True, filled=True,
                         get_fill_color="properties.fill", get_line_color=[255, 255, 255, 230],
                         line_width_min_pixels=1.5, auto_highlight=True)
    lay_core = pdk.Layer("GeoJsonLayer", gj, id="core", pickable=False, stroked=True, filled=False,
                         get_line_color=[60, 60, 60, 160], line_width_min_pixels=1)       # 상권 핵심 영역 윤곽
    sel_gj = {"type": "FeatureCollection", "features": [f for f in fill_src["features"] if f["properties"]["code"] == sel]}
    lay_sel = pdk.Layer("GeoJsonLayer", sel_gj, id="sel_area", pickable=False, stroked=True, filled=False,
                        get_line_color=[37, 99, 235, 255], line_width_min_pixels=4)
    layers = [lay_poly] + ([lay_core] if show_region else []) + [lay_sel, lay_route]
    if ss.sel_station is not None:
        srow = stations[stations.station_no == ss.sel_station]
        layers.append(pdk.Layer("ScatterplotLayer", srow, id="buffer", get_position=["lon", "lat"], get_radius=500,
                                filled=True, get_fill_color=[37, 99, 235, 30], stroked=True,
                                get_line_color=[37, 99, 235, 220], line_width_min_pixels=2, pickable=False))
    layers.append(lay_stop)
    d = deck(layers, {"html": "<b>{name}</b> ({type})<br/>{val_label}"})
    try:                                                     # Streamlit 1.39+ : 상권·정거장 클릭
        st.pydeck_chart(d, on_select="rerun", selection_mode="single-object", key="map")
    except TypeError:
        st.pydeck_chart(d)
    st.caption("색칠된 권역을 클릭하면 파란 테두리로 선택되고, 파란 정거장 점을 클릭하면 500m 영향권이 표시됩니다. "
               "회색 윤곽 = 상권 핵심 영역(점포 밀집, 지표 계산 범위) · 색칠 권역 = 그 상권이 가장 가까운 지역(표시용)")

    # ── 정거장 500m 영향권 ──
    c_a, c_b = st.columns([3, 1])
    stn_opts = [None] + list(stations.station_no.astype(int))
    stn_lab = dict(zip(stations.station_no.astype(int), stations.station_no.astype(str) + " " + stations.get("station_name", "")))
    pick = c_a.selectbox("정거장 선택 (지도에서 점을 클릭해도 됨)", stn_opts,
                         index=stn_opts.index(ss.sel_station) if ss.sel_station in stn_opts else 0,
                         format_func=lambda v: "선택 안 함" if v is None else stn_lab[v])
    if pick != ss.sel_station:
        ss.sel_station = pick; ss._last_stn = pick; st.rerun()
    if ss.sel_station is not None and st_sum is not None:
        t = st_sum.set_index("station_no").loc[ss.sel_station]
        st.markdown(f"#### 🚈 {ss.sel_station} {t.station_name} — 500m 영향권")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("점포 수 (2026-06)", f"{int(t.n_stores):,}")
        k2.metric("음식 / 소매 비율", f"{t.food_pct:.0f}% / {t.retail_pct:.0f}%", f"체인 {t.branch_pct:.0f}%", delta_color="off")
        k3.metric("공시지가 중앙값", f"{t.land_price / 1e4:,.0f}만원/㎡" if pd.notna(t.get("land_price")) else "-",
                  f"5년 {t.land_growth_5y_pct:+.1f}%" if pd.notna(t.get("land_growth_5y_pct")) else None)
        te = t.get(f"tram_effect_{SCEN[scen].replace('tram_effect', '').strip('_') or 'base'}")
        k4.metric(f"트램 효과 ({scen})", f"{te:+.1f}%" if pd.notna(te) else "분석 상권 밖")
        st.caption(f"주요 업종: {t.top3_mid}  ·  좌표: {t.coord_source}")
        if st_areas is not None:
            a = st_areas[st_areas.station_no == ss.sel_station]
            if len(a):
                cols = {"name": "상권", "stores_in_500m": "영향권 안 점포", "share_of_area_pct": "상권 점포 중 비율(%)",
                        "quadrant": "진단", "risk_score": "위험", "growth_score": "성장", "type_name": "유형",
                        "tram_gain": "2034 트램 효과(지가 p)"}
                st.dataframe(a[[c for c in cols if c in a.columns]].rename(columns=cols).round(1),
                             hide_index=True, use_container_width=True)
            else:
                st.info("이 정거장 500m 안에는 20개 분석 상권이 없습니다.")
        if c_b.button("영향권 닫기"):
            ss.sel_station = None; st.rerun()
    st.divider()

    sel = st.selectbox("상권 선택 (지도에서 클릭해도 됨)", order, format_func=names.get,
                       index=order.index(ss.sel_area) if ss.sel_area in order else 0)
    if sel != ss.sel_area:
        ss.sel_area = sel; ss._last_area = sel; st.rerun()
    r = info.loc[sel]

    st.subheader(f"{sel} {r['name']} · {r.gu} · {r.type}"
                 + (f" · 유형 {int(r.cluster)} {r.type_name}" if "type_name" in r and pd.notna(r.get("type_name")) else ""))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("점포 수 (2026-06)", f"{int(r.n_stores):,}" if pd.notna(r.n_stores) else "-",
              f"{r.store_share_chg_5y_pct:+.1f}% (5년, 대전 대비)" if pd.notna(r.get("store_share_chg_5y_pct")) else None)
    c2.metric("공시지가 5년", f"{r.land_chg_5y_pct:+.1f}%" if pd.notna(r.get("land_chg_5y_pct")) else "-",
              f"대전 평균 대비 {r.land_rel_idx:.0f}" if pd.notna(r.get("land_rel_idx")) else None)
    c3.metric("분기 폐업률", f"{r.close_rate_q_pct:.1f}%" if pd.notna(r.get("close_rate_q_pct")) else "-")
    c4.metric(f"트램 효과 ({scen})", f"{r.tram_sel:+.1f}%",
              f"{int(r.nearest_tram)}번 정거장 {int(r.nearest_tram_m)}m" if pd.notna(r.nearest_tram) else None,
              delta_color="off")
    st.caption(f"주요 업종: {r.top3_mid}")
    if "risk_score" in r and pd.notna(r.get("risk_score")):
        st.markdown(f"**진단: {r.quadrant}** · 쇠퇴 위험 {r.risk_score:.0f}점 ({r.risk_drivers}) · "
                    f"성장 가능 {r.growth_score:.0f}점 ({r.growth_drivers})")
    if "bad_pct" in r and pd.notna(r.get("bad_pct")):
        st.caption(f"2021 소상공인 실태조사 ({r.survey_dong}, 상권이 속한 행정동): 매출·이익 감소 {r.decline_pct:.0f}%, "
                   f"폐업·업종전환 고려 {r.closing_pct:.0f}% (대전 평균 74% / 7%, 코로나 시기)")
    if sel == "A12":
        st.info("도룡동 점포 수 급증은 2021년 대전신세계 입점 매장이 등록된 영향입니다.")

    g1, g2 = st.columns(2)
    if lp is not None:
        t = lp[lp.code.isin([sel, "ALL"])].pivot(index="year", columns="code", values="idx")
        t.columns = [names.get(c, "대전 전체") for c in t.columns]
        g1.markdown("**공시지가 지수 (2015 = 100)**")
        g1.line_chart(t)
    if fc is not None and sel in set(fc.code):
        f = fc[fc.code == sel].set_index("year")
        h = lp[lp.code == sel].set_index("year").idx if lp is not None else None
        base = h.iloc[-1] / 100 if h is not None else 1
        ch = pd.DataFrame({"실제": h.loc[2015:] if h is not None else None,
                           "예측(트램 없음)": f.base_path * base, "예측(트램 기본)": f.tram_base * base,
                           "80% 하한": f.lo80 * base, "80% 상한": f.hi80 * base})
        st.markdown("**공시지가 예측 (2015 = 100, 2028 트램 개통)** — 범위가 넓어 상권 비교용")
        st.line_chart(ch)
    if sp is not None:
        s = sp[sp.code == sel].copy()
        s["date"] = pd.to_datetime(s.period, format="%Y%m")
        g2.markdown("**점포 수 (분기)** — 2023-03·2024-12·2026-06 은 수집 기준이 바뀐 분기라 급변은 자료 탓일 수 있음")
        g2.line_chart(s.set_index("date")[["n_stores"]])

    def area_context(code):
        """AI 해설용 상권 정보 묶음 (진단·유형·예측·트램·실태조사·업종 변화·과거 사건)."""
        r = info.loc[code]
        g = lambda k, nd=1: (None if k not in r or pd.isna(r[k]) else (round(float(r[k]), nd) if not isinstance(r[k], str) else r[k]))
        ctx = {"상권": f"{code} {r['name']} ({r.gu}, {r.type})",
               "유형(K-means)": g("type_name"), "진단": g("quadrant"),
               "쇠퇴 위험 점수(0~100, 20개 상권 중 순위 기반)": g("risk_score", 0), "위험 주요 원인": g("risk_drivers"),
               "성장 가능 점수(0~100)": g("growth_score", 0), "성장 주요 근거": g("growth_drivers"),
               "점포 수(2026-06)": g("n_stores", 0), "주요 업종": g("top3_mid"),
               "대전 내 점포 비중 5년 변화(%)": g("store_share_chg_5y_pct"), "분기 폐업률(%, 최근 3년)": g("close_rate_q_pct", 2),
               "공시지가 5년·10년 상승률(%)": (g("land_chg_5y_pct"), g("land_chg_10y_pct")),
               "공시지가 대전 평균 대비(2015=100)": g("land_rel_idx"),
               "가까운 트램 정거장": f"{g('nearest_tram', 0)}번, {g('nearest_tram_m', 0)}m",
               "트램 효과 개통 6년 후(%) 낮음/기본/높음": (g("tram_effect_low", 2), g("tram_effect", 2), g("tram_effect_high", 2))}
        if fc is not None and code in set(fc.code):
            f = fc[(fc.code == code)].set_index("year")
            y = f.index.max()
            ctx[f"{y}년 공시지가 예측(2026=100): 트램 없음 / 트램 기본 / 80% 범위"] = (
                round(f.loc[y, "base_path"], 1), round(f.loc[y, "tram_base"], 1),
                f"{f.loc[y, 'lo80']:.0f}~{f.loc[y, 'hi80']:.0f}")
        if pd.notna(r.get("bad_pct")) if "bad_pct" in r else False:
            ctx["2021 실태조사(소속 행정동)"] = f"{r.survey_dong}: 매출·이익 감소 {r.decline_pct:.0f}%, 폐업·전환 고려 " \
                                          f"{r.closing_pct:.0f}% (대전 평균 74%·7%, 코로나 시기)"
        if ind_area is not None and code in set(ind_area.iloc[:, 0]):
            ia = ind_area.set_index(ind_area.columns[0]).loc[code]
            ctx["업종 비율 변화 2016→2026(%p)"] = {c.replace("_변화p", ""): ia[c] for c in ia.index if c.endswith("_변화p")}
        if events is not None:
            ev = events[events.area_codes.fillna("").str.contains(code)]
            if len(ev):
                ctx["과거 사건"] = [f"{e.date} {e.description}" for e in ev.itertuples()]
        if st_areas is not None:
            sa = st_areas[st_areas.code == code]
            if len(sa):
                ctx["트램 정거장 500m 영향권에 드는 점포"] = [f"{int(x.station_no)}번 정거장 {int(x.stores_in_500m)}개"
                                                   f"({x.share_of_area_pct:.0f}%)" for x in sa.itertuples()]
        return ctx

    @st.cache_data(show_spinner=False)
    def ai_area(ctx_text, scen_text):
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        prompt = f"""너는 대전 상권 분석가야. 아래는 우리 팀이 공공데이터로 분석한 상권 정보야.
{ctx_text}

[지표 설명]
- 진단: 쇠퇴 위험 50점 이상 + 트램 효과 3p 이상이면 '트램 반등 기회', 트램 효과 없으면 '쇠퇴 우려', 위험 50 미만이면 '성장 지속'/'정체·안정'
- 트램 효과: 2028 개통 6년 후 정거장 500m 안 매출 변화 추정(%). 기본 = 대전 1호선 역세권 지가 효과(+5.8%)를 업종·버스밀도·중심/주변으로 조정, 낮음 0.9%(중국 청두 트램 수준), 높음 = 1호선 추세 보정값(+9.3%). 선택된 시나리오: {scen_text}
- 공시지가 예측: 상권별 ARIMA + 트램 효과, 80% 범위가 넓어 비교용
- 매출 금액은 위치별 실측이 없어 사용하지 않음

[작성 형식] 한국어, 각 항목 1~2줄, 숫자 근거를 괄호로 인용
1. 한 줄 요약 (현재 상태: 성장/정체/쇠퇴)
2. 근거 수치 3개
3. 트램 개통 기회
4. 위험 요인
5. 추천 업종 2개와 피할 업종 1개 (업종 비율 변화·폐업률 근거)
6. 상권 활성화 정책 제안 1개
추정치는 '추정'이라고 표시하고, 위 정보에 없는 사실은 지어내지 마."""
        return client.models.generate_content(model="gemini-3.8-flash", contents=prompt).text

    if st.button("🧠 AI 상권 해설 받기"):
        ctx = area_context(sel)
        with st.expander("AI 에게 보낸 정보 보기"):
            st.json(ctx)
        with st.spinner("AI가 분석 중..."):
            try:
                st.markdown(ai_area(json.dumps(ctx, ensure_ascii=False, default=str, indent=1), scen))
            except Exception as e:
                st.error(f"AI 호출 실패: {e}")
    st.subheader("20개 상권 비교")
    st.dataframe(prof.set_index("code")[["name", "type"] + list(AM)].rename(columns=AM)
                 .sort_values(AM[am], ascending=False))

# ================================================================ 격자 보기 (예전 화면)
else:
    cats = st.sidebar.multiselect("업종", sorted(df.category.unique()), default=["음식", "소매"])
    df["tram_sel"] = df[SCEN[scen]]
    LABEL = {"sales": "월평균 매출(합성값)", "tram_sel": f"트램 효과(%, {scen})", "resid_pct": "입지 대비 잔차(%)"}
    if "land_price" in df.columns:
        LABEL.update({"land_price": "공시지가(원/㎡)", "land_growth_5y": "공시지가 5년 상승률(%)"})
    metric = st.sidebar.radio("지표", list(LABEL), format_func=LABEL.get)
    style = st.sidebar.radio("표현 방식", ["격자 색칠", "히트맵"])
    agg = dict(lat=("lat", "first"), lon=("lon", "first"), dong=("dong", "first"), zone=("zone", "first"),
               sales=("sales", "sum"), tram_sel=("tram_sel", "mean"), resid_pct=("resid_pct", "first"))
    if "land_price" in df.columns:
        agg.update(land_price=("land_price", "first"), land_growth_5y=("land_growth_5y", "first"))
    d = df[df.category.isin(cats)].groupby("cell_id").agg(**agg).reset_index()
    d["tram_sel"] = d.tram_sel.round(2)
    v = d[metric]
    if v.notna().any():
        d["norm"] = ((v - v.min()) / (v.max() - v.min() + 1e-9)).fillna(0)
    else:
        d["norm"] = 0.0
        st.warning(f"'{LABEL[metric]}' 값이 map_data.csv 에 없습니다.")
    d["color"] = d.norm.apply(lambda t: [255, int(220 * (1 - t)), 0, 170])
    if style == "격자 색칠":
        main = pdk.Layer("ScatterplotLayer", d, get_position=["lon", "lat"], get_radius=120,
                         get_fill_color="color", pickable=True)
    else:
        main = pdk.Layer("HeatmapLayer", d, get_position=["lon", "lat"], get_weight="norm", radius_pixels=60)
    st.pydeck_chart(deck([main, lay_route, lay_stop],
                         {"text": "{zone} · {dong} {cell_id}\n매출 {sales}\n트램효과 {tram_sel}%\n잔차 {resid_pct}%"}))
    st.subheader(f"{LABEL[metric]} 상위 격자")
    st.dataframe(d.sort_values(metric, ascending=False).head(20).drop(columns=["color", "norm"]))

    @st.cache_data(show_spinner=False)
    def ai_comment(row_text, cats_text, scen_text):
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        return client.models.generate_content(
            model="gemini-3.8-flash",
            contents=(f"대전 트램 상권 분석 격자 데이터야: {row_text}. 선택 업종: {cats_text}. "
                      f"트램 효과(tram_sel)는 '{scen_text}' 시나리오의 개통 6년 후 매출 변화 추정치(%)야. "
                      "창업자 관점에서 장점, 위험, 추천 업종을 5줄로 정리하고 추정은 추정이라고 표시해줘.")).text

    st.subheader("AI 격자 해설")
    sel = st.selectbox("해설 볼 격자", d.sort_values(metric, ascending=False).cell_id)
    if st.button("해설 받기"):
        row = d[d.cell_id == sel].drop(columns=["color", "norm"]).iloc[0].to_dict()
        with st.spinner("AI가 분석 중..."):
            try:
                st.write(ai_comment(str(row), str(cats), scen))
            except Exception as e:
                st.error(f"AI 호출 실패: {e}")
