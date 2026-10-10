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
    gj = json.load(open(f"{OUT}/sangkwon_polygons.geojson", encoding="utf-8"))
    lp = pd.read_csv(f"{OUT}/landprice_area_panel.csv", encoding="utf-8-sig") \
        if os.path.exists(f"{OUT}/landprice_area_panel.csv") else None
    sp = pd.read_csv(f"{OUT}/store_panel.csv", dtype={"period": str}, encoding="utf-8-sig") \
        if os.path.exists(f"{OUT}/store_panel.csv") else None
    return prof, gj, lp, sp


prof, gj, lp, sp = load_area()

# ── 사이드바 ──
st.sidebar.title("대전 트램 상권 지도")
view = st.sidebar.radio("보기", ["상권(20개)", "격자(250m)"], horizontal=True)
SCEN = {"기본(대전 실측)": "tram_effect", "낮음": "tram_effect_low", "높음(논문)": "tram_effect_high"}
SCEN = {k: v for k, v in SCEN.items() if v in df.columns}
scen = st.sidebar.radio("트램 시나리오", list(SCEN), horizontal=True)
st.sidebar.caption("트램 효과 = 개통 6년 후 정거장 500m 안 매출 변화 추정(%). "
                   "기본: 대전 1호선 1단계 역세권 지가 효과(+5.8%)를 업종·버스밀도·상권 위치로 조정. "
                   "높음: 영국 경전철 연구(Lan 2025) 업종별 계수. 낮음: 버스가 적은 지역 계수.")

route = stations[["lon", "lat"]].values.tolist()
route = [{"path": route + route[:1]}]                                  # 2호선 순환선 (정거장 순서 연결)
lay_route = pdk.Layer("PathLayer", route, get_path="path", get_color=[30, 90, 200, 140], width_min_pixels=2)
lay_stop = pdk.Layer("ScatterplotLayer", stations, get_position=["lon", "lat"], get_radius=55,
                     get_fill_color=[30, 90, 200, 230], pickable=False)


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
    AM = {"tram_sel": f"트램 효과(%, {scen})", "land_chg_5y_pct": "공시지가 5년 상승률(%)",
          "land_rel_idx": "공시지가: 2015년 이후 대전 평균 대비(100=평균)",
          "store_share_chg_5y_pct": "점포 비중 5년 변화(%)", "close_rate_q_pct": "분기 폐업률(%, 최근 3년)",
          "n_stores": "점포 수(2026-06)", "cluster": "상권 유형(K-means)"}
    AM = {k: v for k, v in AM.items() if k in prof.columns}
    am = st.sidebar.radio("상권 색칠 기준", list(AM), format_func=AM.get)
    if am == "cluster":                                       # 유형은 색 구분 (1 파랑, 2 주황, 3 초록, 4 빨강, …)
        PAL = [[31, 119, 180, 160], [255, 127, 14, 160], [44, 160, 44, 160], [214, 39, 40, 160], [148, 103, 189, 160]]
        colors = {c: PAL[(int(k) - 1) % len(PAL)] if pd.notna(k) else [180, 180, 180, 120]
                  for c, k in zip(prof.code, prof.cluster)}
        st.sidebar.markdown("\n".join(f"- **{int(k)}. {n}**" for k, n in
                                       prof.drop_duplicates("cluster").sort_values("cluster")[["cluster", "type_name"]].values))
    else:
        colors = dict(zip(prof.code, color_scale(prof[am].clip(upper=prof[am].quantile(.95)))))   # 노랑(낮음) → 빨강(높음)
    info = prof.set_index("code")
    for f in gj["features"]:
        c = f["properties"]["code"]
        r = info.loc[c]
        f["properties"].update({"fill": colors[c], "val": None if pd.isna(r[am]) else round(float(r[am]), 2),
                                "tram_sel": round(float(r.tram_sel), 2)})
    lay_poly = pdk.Layer("GeoJsonLayer", gj, id="areas", pickable=True, stroked=True, filled=True,
                         get_fill_color="properties.fill", get_line_color=[80, 80, 80, 200], line_width_min_pixels=1,
                         auto_highlight=True)
    d = deck([lay_poly, lay_route, lay_stop],
             {"html": "<b>{name}</b> ({type})<br/>" + AM[am] + ": {val}<br/>가까운 트램 {nearest_tram}번 {nearest_tram_m}m"})
    try:                                                     # Streamlit 1.39+ : 지도 클릭으로 상권 선택
        ev = st.pydeck_chart(d, on_select="rerun", selection_mode="single-object", key="map")
        objs = (ev.selection.get("objects", {}) or {}).get("areas", []) if ev else []
        clicked = objs[0]["properties"]["code"] if objs else None
    except TypeError:
        st.pydeck_chart(d); clicked = None
    names = dict(zip(prof.code, prof.code + " " + prof.name))
    order = list(prof.code)
    sel = st.selectbox("상권 선택 (지도에서 클릭해도 됨)", order, format_func=names.get,
                       index=order.index(clicked) if clicked in order else 0)
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
    if sel == "A12":
        st.info("도룡동 점포 수 급증은 2021년 대전신세계 입점 매장이 등록된 영향입니다.")

    g1, g2 = st.columns(2)
    if lp is not None:
        t = lp[lp.code.isin([sel, "ALL"])].pivot(index="year", columns="code", values="idx")
        t.columns = [names.get(c, "대전 전체") for c in t.columns]
        g1.markdown("**공시지가 지수 (2015 = 100)**")
        g1.line_chart(t)
    if sp is not None:
        s = sp[sp.code == sel].copy()
        s["date"] = pd.to_datetime(s.period, format="%Y%m")
        g2.markdown("**점포 수 (분기)** — 2023-03·2024-12·2026-06 은 수집 기준이 바뀐 분기라 급변은 자료 탓일 수 있음")
        g2.line_chart(s.set_index("date")[["n_stores"]])

    @st.cache_data(show_spinner=False)
    def ai_area(text, scen_text):
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        return client.models.generate_content(
            model="gemini-3.8-flash",
            contents=(f"대전 상권 요약 데이터야: {text}. 트램 효과는 '{scen_text}' 시나리오의 개통 6년 후 매출 변화 "
                      "추정치(%)이고, 기본값은 대전 1호선 역세권 지가 효과로 보정한 값이야. 점포 비중 변화는 대전 전체 대비, "
                      "공시지가 rel_idx 는 2015년 이후 대전 평균 대비(100=평균)야. 이 상권의 현재 상태(성장/정체/쇠퇴), "
                      "트램 개통 기회, 위험, 추천 업종을 6줄로 정리하고 추정은 추정이라고 표시해줘.")).text

    if st.button("AI 상권 해설 받기"):
        with st.spinner("AI가 분석 중..."):
            try:
                st.write(ai_area(str(r.drop(labels=["tram_effect", "tram_effect_low", "tram_effect_high"],
                                            errors="ignore").to_dict()), scen))
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
