import json, os, sys
import numpy as np
import streamlit as st, pandas as pd, pydeck as pdk, altair as alt
from google import genai

st.set_page_config(page_title="대전 트램 상권 지도", layout="wide", page_icon="🚈")
sys.path.insert(0, "tram_model")
from tram_route import route_paths
from about_page import show_about                                      # 분석 방법 팝업

OUT, DATA = "tram_model/outputs", "tram_model/data"
ss = st.session_state


# ── 파일 읽기 (한 번 읽고 캐시 → 클릭 반응 빠르게) ──
@st.cache_data
def read_csv(path, **kw):
    return pd.read_csv(path, encoding="utf-8-sig", **kw) if os.path.exists(path) else None


@st.cache_data
def read_json(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


df = read_csv("map_data.csv")
stations = read_csv(f"{DATA}/tram_stations.csv")
if stations is None:
    stations = read_csv(f"{DATA}/tram_stations_approx.csv")
stations = stations.sort_values("station_no")
prof = read_csv(f"{OUT}/area_profile.csv")
gj = read_json(f"{OUT}/sangkwon_polygons.geojson")           # 상권 핵심 영역 (점포 밀집, 지표 계산 범위)
rg = read_json(f"{OUT}/sangkwon_regions.geojson")            # 대전 전체를 나눈 권역 (표시용)
lp = read_csv(f"{OUT}/landprice_area_panel.csv")
sp = read_csv(f"{OUT}/store_panel.csv", dtype={"period": str})
fc = read_csv(f"{OUT}/forecast_land.csv")
st_sum = read_csv(f"{OUT}/station_summary.csv")
st_areas = read_csv(f"{OUT}/station_areas.csv")
ind_area = read_csv(f"{OUT}/industry_by_area.csv")
events = read_csv(f"{DATA}/area_events.csv")

# ── 색 (진단 4분류 색은 지도·배지·요약·표에서 똑같이 사용) ──
QC = {"성장 지속": [34, 139, 84], "트램 반등 기회": [235, 130, 20], "쇠퇴 우려": [200, 50, 50], "정체·안정": [140, 140, 140]}
QHEX = {k: "#%02x%02x%02x" % tuple(v) for k, v in QC.items()}
PAL = [[52, 110, 190], [235, 130, 20], [34, 139, 84], [200, 50, 50], [128, 90, 180]]       # 상권 유형 1~5
ROUTE_C = [35, 39, 46]                                     # 트램 노선·정거장: 짙은 먹색 (지표 색과 겹치지 않게)
REG_A, CORE_A = 95, 225                                     # 권역은 옅게, 점포가 모인 핵심 영역은 진하게
RAMP = {"bad": ["#fff4d6", "#f2a65a", "#b8322a"],          # 높을수록 나쁨 (위험·폐업률)
        "good": ["#eef7ee", "#83c58f", "#1d7a46"],         # 높을수록 좋음 (성장)
        "tram": ["#eef1fb", "#8ea2e6", "#2c3fa8"],         # 트램 효과
        "neutral": ["#f1f3f5", "#9aa5b1", "#2f3b48"],      # 좋고 나쁨 없음 (점포 수)
        "div": ["#2c6fbb", "#f4f4f4", "#c8382f"]}          # 증감: 감소 파랑 · 0 흰색 · 증가 빨강
BREAKS = ["2023-03", "2024-12", "2026-06"]                 # 점포 자료 수집 기준이 바뀐 분기

st.markdown("""<style>
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:13px;font-weight:600;color:#fff;margin-left:6px;vertical-align:middle}
.badge.gray{background:#eef0f3;color:#333}
.card{border:1px solid #e3e6ea;border-radius:10px;padding:12px 16px;margin:4px 0 10px 0;background:#fafbfc}
.card .t{font-size:20px;font-weight:700}.card .code{color:#888;font-size:14px;margin-right:6px}
.card .k{margin-top:6px;color:#333;font-size:14px}.card .k b{font-size:16px}
.lg{display:flex;align-items:center;gap:8px;font-size:13px;color:#444;margin:2px 0 4px 0;flex-wrap:wrap}
.lg .bar{width:180px;height:10px;border-radius:5px}.lg .dot{width:11px;height:11px;border-radius:50%;display:inline-block;margin:0 4px 0 10px}
.qh{font-weight:700;font-size:14px;margin-bottom:2px}
.maphead{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px 18px;
  border:1px solid #e3e6ea;border-bottom:none;border-radius:10px 10px 0 0;padding:8px 12px;background:#fff;margin-bottom:-2px}
.maphead .lg{margin:0}
.sym{display:flex;align-items:center;gap:6px;font-size:12.5px;color:#555;flex-wrap:wrap}
.sym .ln{display:inline-block;width:22px;height:3px;background:#23272e;border-radius:2px;margin-left:8px}
.sym .st{display:inline-block;width:9px;height:9px;border-radius:50%;background:#fff;border:2px solid #23272e;margin-left:8px}
.sym .sq{display:inline-block;width:12px;height:12px;border-radius:3px;margin-left:8px;border:1px solid #ccc}
.sym .sq.strong{background:#8a8f98}.sym .sq.weak{background:#dfe1e4}
</style>""", unsafe_allow_html=True)


def _hex(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def _interp(stops, t):
    n = len(stops) - 1
    i = min(int(t * n), n - 1)
    f = t * n - i
    a, b = _hex(stops[i]), _hex(stops[i + 1])
    return [int(a[j] + (b[j] - a[j]) * f) for j in range(3)]


def colorize(values, kind, center=None):
    """숫자 → 색. kind: seq_bad / seq_good / seq_tram / seq_neutral / div0(0 기준 증감) / div100(100 기준)
    / divavg(center = 대전 평균 기준)."""
    v = pd.to_numeric(values, errors="coerce")
    if kind.startswith("div"):
        c = center if center is not None else (100 if kind == "div100" else 0)
        m = float((v - c).abs().quantile(.95)) or 1.0
        t = ((v - c).clip(-m, m) / m + 1) / 2
        stops, lo, hi = RAMP["div"], c - m, c + m
    else:
        lo, hi = float(v.min()), float(v.quantile(.95))
        t = (v.clip(upper=hi) - lo) / (hi - lo + 1e-9)
        stops = RAMP[kind.split("_")[1]]
    cols = [_interp(stops, float(x)) + [190] if pd.notna(x) else [210, 210, 210, 90] for x in t]
    return cols, (stops, lo, hi)


def legend_bar(label, stops, lo, hi, kind, center=None):
    if kind == "divavg":
        left, right = f"평균보다 낮음 {lo:+.0f}", f"높음 {hi:+.0f} · 흰색 = 대전 평균 {center:+.1f}"
    elif kind.startswith("div"):
        c = 100 if kind == "div100" else 0
        left, right = f"감소 {lo:+.0f}" if c == 0 else f"평균보다 약함 {lo:.0f}", \
            f"증가 {hi:+.0f}" if c == 0 else f"평균보다 강함 {hi:.0f}"
    else:
        left, right = f"낮음 {lo:,.0f}", f"높음 {hi:,.0f}+"
    return (f'<div class="lg"><b>{label}</b>&nbsp;{left}<span class="bar" '
            f'style="background:linear-gradient(90deg,{",".join(stops)})"></span>{right}</div>')


def legend_cat(label, items):
    return f'<div class="lg"><b>{label}</b>' + "".join(
        f'<span class="dot" style="background:rgb({c[0]},{c[1]},{c[2]})"></span>{n}' for n, c in items) + "</div>"


TIP_STYLE = {"backgroundColor": "#ffffff", "color": "#1d1d1f", "fontSize": "12.5px", "lineHeight": "1.5",
             "borderRadius": "8px", "border": "1px solid #e3e6ea", "boxShadow": "0 4px 14px rgba(0,0,0,.14)",
             "padding": "8px 11px", "fontFamily": "Pretendard, 'Apple SD Gothic Neo', sans-serif"}
# 첫 화면: 트램 노선 전체가 꽉 차게 (대전 전체가 아니라 분석 대상에 초점)
VIEW0 = dict(latitude=float((stations.lat.min() + stations.lat.max()) / 2),
             longitude=float((stations.lon.min() + stations.lon.max()) / 2), zoom=12.0)


def deck(layers, tooltip, view=None):
    if isinstance(tooltip, dict):
        tooltip = {**tooltip, "style": TIP_STYLE}
    return pdk.Deck(layers=layers, map_style="light", tooltip=tooltip,
                    initial_view_state=view or pdk.ViewState(**VIEW0, min_zoom=10, max_zoom=16))


def px(lon, lat, zoom=VIEW0["zoom"]):
    """경위도 → 첫 화면 기준 픽셀 좌표 (라벨 겹침 계산용)."""
    import math
    m = 156543.03 * math.cos(math.radians(VIEW0["latitude"])) / 2 ** zoom
    return ((lon - VIEW0["longitude"]) * 111320 * math.cos(math.radians(VIEW0["latitude"])) / m,
            (lat - VIEW0["latitude"]) * 111320 / m)


def show_map(d, select=True):
    """지도 크게(620px) + 클릭 선택. 오래된 Streamlit이면 가능한 기능만 사용."""
    tries = ([dict(on_select="rerun", selection_mode="single-object", key="map", height=620),
              dict(on_select="rerun", selection_mode="single-object", key="map")] if select else []) + \
            [dict(height=620), dict()]
    for kw in tries:
        try:
            return st.pydeck_chart(d, **kw)
        except TypeError:
            continue


# ── 사이드바 (보기 → 색칠 → 시나리오 → 분석 방법) ──
st.sidebar.title("대전 트램 상권 지도")
view = st.sidebar.radio("보기", ["상권(20개)", "격자(250m) · 실험용"], horizontal=True)
box = st.sidebar.container()                         # 색칠 기준은 보기별로 아래에서 채움
# 트램 시나리오: 이름·설명을 결과 파일(tram_scenarios.csv)에서 읽어 실제 값과 항상 일치
_ts = read_csv(f"{OUT}/tram_scenarios.csv")
_TS = {r.scenario: r for r in _ts.itertuples()} if _ts is not None else {}
_COL = {"base": "tram_effect", "low": "tram_effect_low", "high": "tram_effect_high"}
SCEN, SCEN_HELP = {}, []
for _k in ("base", "low", "high"):
    _r = _TS.get(_k)
    _lab = f"{_r.label} {_r.effect_pct:+.1f}%" if _r is not None else {"base": "기본", "low": "낮음", "high": "높음"}[_k]
    if _COL[_k] in prof.columns:
        SCEN[_lab] = _COL[_k]
        if _r is not None:
            SCEN_HELP.append(f"{_r.label} {_r.effect_pct:+.1f}%: {_r.source}"
                             + (f" (95% 구간 {_r.ci95}%)" if isinstance(_r.ci95, str) and _r.ci95 else ""))
TRAM_DEF = "개통 초기 1~4년, 정거장 500m 안 땅값 기준 추정 효과(%) · 매출 변화가 아님"
scen = st.sidebar.radio("트램 시나리오", list(SCEN), horizontal=True,
                        help=" / ".join(SCEN_HELP) + " · 효과 = 수준 × 업종 비율 × 상권 중 500m 안 비율. "
                             "대전 1호선에서는 개통 6년 뒤 효과가 약 1/3로 줄었음")
st.sidebar.caption(f"트램 효과 = {TRAM_DEF}")
show_about(st)

route = [{"path": p} for p in route_paths(stations)]
lay_route = [pdk.Layer("PathLayer", route, id="route_case", get_path="path", get_color=[255, 255, 255, 235],
                       width_min_pixels=6, cap_rounded=True, joint_rounded=True),           # 흰 테두리 (어떤 색 위에서도 보이게)
             pdk.Layer("PathLayer", route, id="route", get_path="path", get_color=ROUTE_C + [255],
                       width_min_pixels=3, cap_rounded=True, joint_rounded=True)]
stop_df = stations.merge(st_sum[["station_no", "n_stores"]], on="station_no", how="left") if st_sum is not None \
    else stations.assign(n_stores=None)
stop_df = stop_df.assign(name=stop_df.station_no.astype(str) + "번 " + stop_df.get("station_name", ""), type="트램 정거장",
                         qcolor="#23272e",
                         val_label="500m 안 점포 " + stop_df.n_stores.fillna(0).astype(int).astype(str) + "개 · 클릭하면 영향권 표시")
lay_stop = pdk.Layer("ScatterplotLayer", stop_df, id="stations", get_position=["lon", "lat"], get_radius=55,
                     radius_min_pixels=4.5, radius_max_pixels=9, get_fill_color=[255, 255, 255, 255],
                     get_line_color=ROUTE_C + [255], stroked=True, line_width_min_pixels=1.8, pickable=True,
                     auto_highlight=True, highlight_color=[35, 39, 46, 255])

# ================================================================ 상권 보기
if view == "상권(20개)":
    prof["tram_sel"] = prof[SCEN[scen]]
    info = prof.set_index("code")
    order = list(prof.code)
    NM = dict(zip(prof.code, prof.name))
    names = {c: f"{c} {n}" for c, n in NM.items()}
    STN = dict(zip(stations.station_no.astype(int), stations.station_no.astype(str) + " " + stations.get("station_name", "")))

    # 지표 정의: (이름, 묶음, 색 종류, 도움말)
    M = {"quadrant": ("진단 (4분류)", "종합 진단", "cat",
                      "상대 쇠퇴 위험 50점 이상 + 상권 점포 절반 이상이 정거장 500m 안 → 트램 반등 기회, "
                      "500m 밖 → 쇠퇴 우려 / 위험 50 미만은 성장 점수로 성장 지속·정체·안정. "
                      "15가지 변형(지표 빼기·기준 45/55·반경 400/600m)에서 80% 미만으로 같으면 '불확실'"),
         "risk_score": ("상대 쇠퇴 위험 (0~100)", "종합 진단", "seq_bad",
                        "땅값 상대 하락·점포 비중 감소·폐업률을 20개 상권 안 순위로 합친 점수. 절대 수준이 아니라 "
                        "20곳 중 상대 비교라 언제나 약 절반이 50점 이상"),
         "growth_score": ("상대 성장 가능 (0~100)", "종합 진단", "seq_good",
                          "트램 효과·개업률·최근 점포 비중을 20개 상권 안 순위로 합친 점수"),
         "tram_sel": ("트램 효과 (%)", "트램 효과", "seq_tram", TRAM_DEF),
         "land_chg_5y_pct": ("땅값 5년 상승률 (%)", "땅값(공시지가)", "divavg", "2021→2026 같은 필지 공시지가 변화의 중앙값"),
         "land_rel_idx": ("대전 평균 대비 땅값 흐름 (100=평균)", "땅값(공시지가)", "div100",
                          "2015년 이후 이 상권 땅값이 대전 평균보다 얼마나 더(100 초과)·덜(100 미만) 올랐는지"),
         "store_share_chg_5y_pct": ("대전 내 점포 비중 5년 변화 (%)", "점포", "div0",
                                    "대전 전체 점포 중 이 상권 몫이 5년간 늘었는지(+) 줄었는지(-)"),
         "close_rate_q_pct": ("분기 폐업률 (%)", "점포", "seq_bad", "최근 3년 분기마다 문 닫은 점포 비율의 평균"),
         "n_stores": ("점포 수 (2026-06)", "점포", "seq_neutral", "소상공인 상가정보 기준 상권 핵심 영역 안 점포 수"),
         "cluster": ("상권 유형 (4개)", "상권 유형", "cat", "땅값·점포 흐름이 비슷한 상권끼리 자동으로 묶은 유형(K-means)")}
    # ── 업종 점수 (score_industry.py: 상권 × 업종 100점, 트램 건설 전·후) ──
    IS = read_csv(f"{OUT}/industry_scores.csv")
    ISW = read_csv(f"{OUT}/industry_score_weights.csv")
    _IND_ORDER = ["음식", "소매", "수리·개인", "교육", "보건의료", "숙박"]
    IND_LIST = ([i for i in _IND_ORDER if i in set(IS.industry)] + sorted(set(IS.industry) - set(_IND_ORDER))) \
        if IS is not None else []
    ALL_IND = "전체 (상권 지표)"
    if ss.get("ind") not in [ALL_IND] + IND_LIST:
        ss.ind = ALL_IND
    ss.setdefault("tram_after", False)
    if IS is not None:
        box.selectbox("업종", [ALL_IND] + IND_LIST, key="ind",
                      help="업종을 고르면 지도가 그 업종 점수(100점)로 칠해지고, 아래 '업종 점수' 패널에서 순위·근거를 볼 수 있음")
        box.toggle("트램 건설 후 (2028 개통 반영)", key="tram_after",
                   help="업종 점수에 '트램 효과' 항목(10점)을 넣어 다시 계산. 끄면 건설 전 점수")
    tram_after = bool(ss.tram_after)
    W_DEF = {r.key: float(r.weight_before) for r in ISW.itertuples() if r.key != "tram"} if ISW is not None else {}
    TRAM_W = float(ISW.set_index("key").weight_after.get("tram", 10)) if ISW is not None else 10.0
    ss.setdefault("ind_w", dict(W_DEF))
    SCEN_KEY = {"tram_effect": "base", "tram_effect_low": "low", "tram_effect_high": "high"}[SCEN[scen]]

    def ind_scores(after, w=None):
        """업종 점수 = 항목 점수(0~100) 가중 평균. 건설 후 = 트램 항목 TRAM_W 점 + 나머지를 (100-TRAM_W) 로 맞춤."""
        w = dict(w or ss.ind_w)
        tot = sum(w.values()) or 1.0
        w = {k: v / tot * 100 for k, v in w.items()}
        if after:
            w = {k: v * (100 - TRAM_W) / 100 for k, v in w.items()} | {"tram": TRAM_W}
        S = IS[[f"s_{k}" for k in w]].values
        Wm = np.where(~np.isnan(S), np.array(list(w.values())), 0.0)
        den = Wm.sum(1)
        sc = np.where(den > 0, (np.nan_to_num(S) * Wm).sum(1) / np.where(den > 0, den, 1), np.nan)
        out = IS.assign(score=np.round(sc, 1))
        out.loc[IS.score_before.isna(), "score"] = np.nan          # 업종 점포가 거의 없는 상권
        return out, w

    if IS is not None and ss.ind != ALL_IND:
        _cur, _ = ind_scores(tram_after)
        prof["ind_score"] = prof.code.map(_cur[_cur.industry == ss.ind].set_index("code").score)
        info = prof.set_index("code")
        M = {"ind_score": (f"{ss.ind} 점수 (100점, {'트램 건설 후' if tram_after else '트램 건설 전'})", "업종 점수",
                           "seq_good", "성장·규모·특화도·생존·땅값(+건설 후 트램 효과)을 업종 안 20개 상권 순위로 합친 점수. "
                           "근거·가중치는 아래 '업종 점수' 패널")} | M
    M = {k: v for k, v in M.items() if k in prof.columns}
    HELP = {k: v[3] for k, v in M.items()}

    # 색칠 기준 (사이드바)
    groups = list(dict.fromkeys(v[1] for v in M.values()))
    grp = box.radio("색칠 주제", groups)
    opts = [k for k, v in M.items() if v[1] == grp]
    am = box.radio("지표", opts, format_func=lambda k: M[k][0]) if len(opts) > 1 else opts[0]
    show_region = rg is not None and box.toggle("대전 전체를 상권 권역으로 채우기", value=True,
                                                help="대전 모든 지점을 가장 가까운 상권에 배정한 권역. 끄면 상권 핵심 영역만 표시")
    show_label = box.toggle("상권 이름 표시", value=True)

    kind = M[am][2]
    if am == "quadrant":
        colors = {c: QC.get(q, [200, 200, 200]) + [190] for c, q in zip(prof.code, prof.quadrant)}
        legend = legend_cat("진단", [(k, v) for k, v in QC.items()])
    elif am == "cluster":
        colors = {c: PAL[(int(k) - 1) % len(PAL)] + [170] if pd.notna(k) else [190, 190, 190, 110]
                  for c, k in zip(prof.code, prof.cluster)}
        tn = prof.drop_duplicates("cluster").sort_values("cluster")
        legend = legend_cat("유형", [(f"{int(k)}. {n}", PAL[(int(k) - 1) % len(PAL)]) for k, n in tn[["cluster", "type_name"]].values])
    else:
        cen = None
        if kind == "divavg" and lp is not None:              # 대전 전체 5년 상승률을 기준(흰색)으로
            a = lp[lp.code == "ALL"].set_index("year").idx
            cen = float((a.iloc[-1] / a.loc[a.index.max() - 5] - 1) * 100)
        elif kind == "divavg":
            cen = float(prof[am].median())
        cl, (stops, lo, hi) = colorize(prof[am], kind, cen)
        colors = dict(zip(prof.code, cl))
        legend = legend_bar(M[am][0], stops, lo, hi, kind, cen)

    # ── 선택 상태: 첫 실행은 주소(공유 링크)에서, 이후는 클릭·선택 상자에서 ──
    qp = st.query_params if hasattr(st, "query_params") else {}
    if "inited" not in ss:
        ss.inited = True
        a = qp.get("area")
        ss.sel_area = a if a in order else (prof.sort_values("risk_score", ascending=False).code.iloc[0]
                                            if "risk_score" in prof else order[0])
        s = qp.get("station")
        ss.sel_station = int(s) if s and str(s).isdigit() and int(s) in STN else None
        ss.ai = {}
    ss.setdefault("panel", "상권 상세")
    if "_pending_panel" in ss:
        ss.panel = ss.pop("_pending_panel")

    sel_obj = (ss.get("map") or {}).get("selection", {}) if isinstance(ss.get("map"), dict) else \
        (getattr(ss.get("map"), "selection", None) or {})
    objs = sel_obj.get("objects", {}) if sel_obj else {}
    _hit = objs.get("core") or objs.get("areas")                   # 핵심 영역·권역 어느 쪽을 눌러도 같은 상권
    click_area = (_hit or [{}])[0].get("properties", {}).get("code") if _hit else None
    click_stn = (objs.get("stations") or [{}])[0].get("station_no") if objs.get("stations") else None
    if click_area and click_area != ss.get("_last_area"):
        ss._last_area = click_area; ss.sel_area = click_area; ss.panel = "상권 상세"
    if click_stn is not None and click_stn != ss.get("_last_stn"):
        ss._last_stn = click_stn; ss.sel_station = int(click_stn); ss.panel = "정거장 500m"

    def go_area(code):                              # 요약 칩·버튼 → 상권 이동
        ss.sel_area = code; ss.panel = "상권 상세"

    def chip_cb(key):
        v = ss.get(key)
        if v:
            go_area(v)
        ss[key] = None

    # ── 한눈에 보기 (진단별 상권, 누르면 이동) ──
    if "quadrant" in prof:
        cnt = prof.quadrant.value_counts()
        st.markdown(f"#### 한눈에 보기 · {scen} 시나리오 20개 상권 평균 트램 효과 **{prof.tram_sel.mean():+.1f}%**")
        qcols = st.columns(4)
        for col, q in zip(qcols, QC):
            codes = list(prof[prof.quadrant == q].sort_values("risk_score", ascending=False).code)
            col.markdown(f'<div class="qh"><span class="dot" style="display:inline-block;width:11px;height:11px;'
                         f'border-radius:50%;background:{QHEX[q]};margin-right:6px"></span>{q} {cnt.get(q, 0)}곳</div>',
                         unsafe_allow_html=True)
            if not codes:
                continue
            if hasattr(st, "pills"):
                col.pills(q, codes, format_func=NM.get, key=f"chip_{q}", label_visibility="collapsed",
                          on_change=chip_cb, args=(f"chip_{q}",))
            else:
                for c in codes:
                    col.button(NM[c], key=f"btn_{c}", on_click=go_area, args=(c,))

    # ── 지도 ──
    for f in gj["features"] + (rg["features"] if rg else []):
        c = f["properties"]["code"]
        r = info.loc[c]
        val = r[am]
        val = "-" if pd.isna(val) else (val if isinstance(val, str) else
                                        (f"{int(val)}. {r.type_name}" if am == "cluster" else f"{float(val):,.1f}"))
        near = f"가까운 트램 {int(r.nearest_tram)}번 정거장 · {int(r.nearest_tram_m)}m" if pd.notna(r.get("nearest_tram")) else ""
        q = r.quadrant if "quadrant" in r and pd.notna(r.quadrant) else ""
        f["properties"].update({"fill": colors[c][:3] + [REG_A], "fill_core": colors[c][:3] + [CORE_A],
                                "name": r["name"], "type": q, "qcolor": QHEX.get(q, "#999"),
                                "val_label": f"{M[am][0]} <b>{val}</b><br/><span style='color:#777'>{near}</span>"})
    sel = ss.sel_area
    fill_src = rg if show_region else gj
    HL = dict(auto_highlight=True, highlight_color=[255, 255, 255, 90])
    layers = []
    if show_region:                                   # 1) 권역: 옅게 (그 상권이 가장 가까운 지역)
        layers.append(pdk.Layer("GeoJsonLayer", rg, id="areas", pickable=True, stroked=True, filled=True,
                                get_fill_color="properties.fill", get_line_color=[255, 255, 255, 255],
                                line_width_min_pixels=1.2, **HL))
    layers.append(pdk.Layer("GeoJsonLayer", gj, id="core", pickable=True, stroked=True, filled=True,   # 2) 핵심 영역: 진하게
                            get_fill_color="properties.fill_core", get_line_color=[255, 255, 255, 255],
                            line_width_min_pixels=1, **HL))
    sel_gj = {"type": "FeatureCollection", "features": [f for f in fill_src["features"] if f["properties"]["code"] == sel]}
    layers += [pdk.Layer("GeoJsonLayer", sel_gj, id="sel_halo", pickable=False, stroked=True, filled=False,     # 3) 선택: 흰 후광 + 먹색 선
                         get_line_color=[255, 255, 255, 255], line_width_min_pixels=8),
               pdk.Layer("GeoJsonLayer", sel_gj, id="sel_area", pickable=False, stroked=True, filled=False,
                         get_line_color=ROUTE_C + [255], line_width_min_pixels=3.5)]
    layers += lay_route                                # 4) 트램 노선 (흰 테두리 + 먹색)
    if ss.sel_station is not None:                     # 5) 정거장 500m 영향권
        srow = stations[stations.station_no == ss.sel_station]
        layers += [pdk.Layer("ScatterplotLayer", srow, id="buffer", get_position=["lon", "lat"], get_radius=500,
                             filled=True, get_fill_color=ROUTE_C + [28], stroked=True,
                             get_line_color=ROUTE_C + [240], line_width_min_pixels=2.5, pickable=False)]
    layers.append(lay_stop)
    if ss.sel_station is not None:
        layers.append(pdk.Layer("ScatterplotLayer", srow, id="sel_stop", get_position=["lon", "lat"], get_radius=90,
                                radius_min_pixels=7, get_fill_color=ROUTE_C + [255], get_line_color=[255, 255, 255, 255],
                                stroked=True, line_width_min_pixels=2, pickable=False))
    if show_label:                                    # 6) 상권 이름: 점포 많은 순으로 놓고, 첫 화면에서 겹치면 생략
        cen_xy = {}
        for f in gj["features"]:
            g = f["geometry"]
            ring = g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len)
            cen_xy[f["properties"]["code"]] = (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
        pri = prof.assign(p=prof.n_stores.fillna(0) + 1e9 * (prof.code == sel)).sort_values("p", ascending=False).code
        boxes, lab = [], []
        for c in pri:
            if c not in cen_xy:
                continue
            t = NM[c].split("(")[0]
            x, y = px(*cen_xy[c])
            w, h = len(t) * 12.5 + 8, 20
            for dx, dy in [(0, 0), (0, 20), (0, -20), (w / 2 + 6, 0), (-w / 2 - 6, 0), (0, 38), (0, -38)]:  # 겹치면 위·아래·옆으로
                bx = (x + dx - w / 2, y + dy - h / 2, x + dx + w / 2, y + dy + h / 2)
                if c == sel or not any(not (bx[2] < o[0] or bx[0] > o[2] or bx[3] < o[1] or bx[1] > o[3]) for o in boxes):
                    break
            else:
                continue                                  # 어디에도 자리가 없으면 생략 (마우스를 올리면 보임)
            boxes.append(bx)
            lab.append({"text": t, "lon": cen_xy[c][0], "lat": cen_xy[c][1], "sel": c == sel,
                        "off": [dx, -dy]})               # 화면 y는 아래가 + 이므로 부호 반대
        lab = pd.DataFrame(lab)
        TXT = dict(get_position=["lon", "lat"], get_text="text", size_units="pixels", character_set="auto",
                   font_family='Pretendard, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif',
                   font_settings={"sdf": True, "fontSize": 64, "buffer": 8}, outline_color=[255, 255, 255, 245],
                   get_pixel_offset="off", pickable=False)
        layers.append(pdk.Layer("TextLayer", lab[~lab.sel], id="labels", get_size=12.5, get_color=[30, 30, 30, 255],
                                font_weight=600, outline_width=3, **TXT))
        layers.append(pdk.Layer("TextLayer", lab[lab.sel], id="label_sel", get_size=15, get_color=ROUTE_C + [255],
                                font_weight=800, outline_width=3.5, **TXT))

    # 지도 제목줄: 무엇을 칠했는지 + 범례 + 기호 설명
    st.markdown(f'<div class="maphead">{legend}<div class="sym">'
                f'<span class="ln"></span>트램 2호선<span class="st"></span>정거장'
                f'<span class="sq strong"></span>상권 핵심(점포 밀집)'
                + ('<span class="sq weak"></span>그 상권의 영향 권역' if show_region else "")
                + '</div></div>', unsafe_allow_html=True)
    show_map(deck(layers, {"html": "<div style='font-weight:700;font-size:14px'>{name}</div>"
                                   "<div><span style='color:{qcolor}'>●</span> {type}</div>{val_label}"}))
    st.caption("권역이나 정거장을 누르면 아래에 상세 정보가 나옵니다 · 이름이 겹치는 상권은 확대하거나 마우스를 올리면 보입니다")

    # ── 선택 요약 카드 + 선택 상자 ──
    r = info.loc[sel]
    cA, cB, cC = st.columns([5, 2, 2])
    q = r.get("quadrant")
    kp = []
    if pd.notna(r.get("n_stores")):
        kp.append(f"점포 <b>{int(r.n_stores):,}</b>개")
    if pd.notna(r.get("land_chg_5y_pct")):
        kp.append(f"땅값 5년 <b>{r.land_chg_5y_pct:+.1f}%</b>")
    kp.append(f"트램 효과 <b>{r.tram_sel:+.1f}%</b> ({scen})")
    if pd.notna(r.get("risk_score")):
        kp.append(f"상대 위험 <b>{r.risk_score:.0f}</b> · 상대 성장 <b>{r.growth_score:.0f}</b>")
    cA.markdown(f'<div class="card"><span class="code">{sel}</span><span class="t">{r["name"]}</span>'
                + (f'<span class="badge" style="background:{QHEX.get(q, "#999")}">{q}</span>' if pd.notna(q) else "")
                + (f'<span class="badge" style="background:#fff;color:#b8322a;border:1px solid #b8322a">불확실 '
                   f'{r.quadrant_stability * 100:.0f}%</span>' if bool(r.get("quadrant_uncertain", False)) else "")
                + (f'<span class="badge gray">{r.type_name}</span>' if pd.notna(r.get("type_name")) else "")
                + f'<div class="k">{r.gu} · {r.type} &nbsp;|&nbsp; ' + " · ".join(kp) + "</div></div>",
                unsafe_allow_html=True)
    pick_a = cB.selectbox("상권 선택", order, format_func=names.get,
                          index=order.index(sel), help="지도에서 권역을 클릭해도 됩니다")
    if pick_a != sel:
        ss.sel_area = pick_a; ss._last_area = pick_a; ss._pending_panel = "상권 상세"; st.rerun()
    stn_opts = [None] + list(STN)
    pick_s = cC.selectbox("정거장 선택", stn_opts, index=stn_opts.index(ss.sel_station) if ss.sel_station in stn_opts else 0,
                          format_func=lambda v: "선택 안 함" if v is None else STN[v], help="지도에서 파란 점을 클릭해도 됩니다")
    if pick_s != ss.sel_station:
        ss.sel_station = pick_s; ss._last_stn = pick_s
        ss._pending_panel = "정거장 500m" if pick_s is not None else ss.panel
        st.rerun()

    # 공유 링크: 지금 선택이 주소창에 남음
    try:
        st.query_params["area"] = sel
        if ss.sel_station is not None:
            st.query_params["station"] = str(ss.sel_station)
        elif "station" in st.query_params:
            del st.query_params["station"]
    except Exception:
        pass

    panel = st.radio("보기 패널", ["상권 상세", "정거장 500m", "상권 비교", "업종 점수"], horizontal=True, key="panel",
                     label_visibility="collapsed")

    # ── 차트 ──
    def land_chart(codes):
        if lp is None:
            return None
        t = lp[lp.code.isin(codes + ["ALL"])].copy()
        t["상권"] = t.code.map(lambda c: "대전 전체" if c == "ALL" else NM.get(c, c))
        dom = [NM[c] for c in codes] + ["대전 전체"]
        rng = ["#1f4fa3", "#e07b1a", "#2e9a5b"][:len(codes)] + ["#9aa0a6"]
        base = alt.Chart(t).mark_line(strokeWidth=2.5).encode(
            x=alt.X("year:Q", title=None, axis=alt.Axis(format="d")),
            y=alt.Y("idx:Q", title="지수 (2015=100)", scale=alt.Scale(zero=False)),
            color=alt.Color("상권:N", scale=alt.Scale(domain=dom, range=rng), legend=alt.Legend(orient="top", title=None)),
            tooltip=["상권", "year", alt.Tooltip("idx:Q", format=".1f")])
        ch = base
        if events is not None and len(codes) == 1:
            ev = events[events.area_codes.fillna("").str.contains(codes[0])].copy()
            if len(ev):
                ev["year"] = pd.to_datetime(ev.date).dt.year + pd.to_datetime(ev.date).dt.month / 12
                ch = ch + alt.Chart(ev).mark_rule(color="#888", strokeDash=[3, 3]).encode(
                    x="year:Q", tooltip=["date", "description"])
        return ch.properties(height=260)

    def store_chart(code):
        s = sp[sp.code == code].copy()
        s["date"] = pd.to_datetime(s.period, format="%Y%m")
        br = pd.DataFrame({"date": pd.to_datetime(BREAKS), "설명": "수집 기준 변경 (급변은 자료 탓일 수 있음)"})
        line = alt.Chart(s).mark_line(strokeWidth=2.5, color="#1f4fa3", point=alt.OverlayMarkDef(size=18)).encode(
            x=alt.X("date:T", title=None), y=alt.Y("n_stores:Q", title="점포 수", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("date:T", format="%Y-%m"), "n_stores"])
        rule = alt.Chart(br).mark_rule(color="#c8382f", strokeDash=[4, 3]).encode(x="date:T", tooltip=["설명"])
        return (line + rule).properties(height=260)

    def forecast_chart(code):
        f = fc[fc.code == code].set_index("year")
        h = lp[lp.code == code].set_index("year").idx
        b = h.iloc[-1] / 100
        band = pd.DataFrame({"year": f.index, "lo": f.lo80 * b, "hi": f.hi80 * b})
        ln = pd.concat([pd.DataFrame({"year": h.loc[2015:].index, "v": h.loc[2015:].values, "구분": "실제"}),
                        pd.DataFrame({"year": f.index, "v": f.base_path.values * b, "구분": "예측 (트램 없음)"}),
                        pd.DataFrame({"year": f.index, "v": f.tram_base.values * b, "구분": "예측 (트램 기본)"})])
        dom, rng = ["실제", "예측 (트램 없음)", "예측 (트램 기본)"], ["#222222", "#9aa0a6", "#e07b1a"]
        a = alt.Chart(band).mark_area(opacity=.18, color="#1f4fa3").encode(
            x=alt.X("year:Q", axis=alt.Axis(format="d"), title=None), y=alt.Y("lo:Q", title="지수 (2015=100)",
                                                                                scale=alt.Scale(zero=False)), y2="hi:Q")
        l = alt.Chart(ln).mark_line(strokeWidth=2.5).encode(
            x="year:Q", y="v:Q", color=alt.Color("구분:N", scale=alt.Scale(domain=dom, range=rng),
                                                 legend=alt.Legend(orient="top", title=None)),
            strokeDash=alt.StrokeDash("구분:N", scale=alt.Scale(domain=dom, range=[[1, 0], [5, 4], [1, 0]]), legend=None),
            tooltip=["구분", "year", alt.Tooltip("v:Q", format=".1f")])
        op = alt.Chart(pd.DataFrame({"year": [2028], "t": ["트램 개통"]}))
        return (a + l + op.mark_rule(color="#1f4fa3").encode(x="year:Q")
                + op.mark_text(align="left", dx=4, color="#1f4fa3").encode(x="year:Q", y=alt.value(10), text="t")).properties(height=280)

    # ================= 패널 1: 상권 상세
    if panel == "상권 상세":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("점포 수 (2026-06)", f"{int(r.n_stores):,}" if pd.notna(r.n_stores) else "-",
                  f"{r.store_share_chg_5y_pct:+.1f}% (5년, 대전 내 비중)" if pd.notna(r.get("store_share_chg_5y_pct")) else None,
                  help=HELP.get("store_share_chg_5y_pct"))
        c2.metric("땅값 5년 상승률", f"{r.land_chg_5y_pct:+.1f}%" if pd.notna(r.get("land_chg_5y_pct")) else "-",
                  f"대전 평균 대비 {r.land_rel_idx:.0f}" if pd.notna(r.get("land_rel_idx")) else None,
                  delta_color="off", help=HELP.get("land_rel_idx"))
        c3.metric("분기 폐업률", f"{r.close_rate_q_pct:.1f}%" if pd.notna(r.get("close_rate_q_pct")) else "-",
                  help=HELP.get("close_rate_q_pct"))
        c4.metric(f"트램 효과 ({scen})", f"{r.tram_sel:+.1f}%",
                  f"{int(r.nearest_tram)}번 정거장 {int(r.nearest_tram_m)}m" if pd.notna(r.nearest_tram) else None,
                  delta_color="off", help=HELP.get("tram_sel"))
        if pd.notna(r.get("risk_score")):
            stab = r.get("quadrant_stability")
            if pd.notna(stab):
                alt_q = r.get("quadrant_alt") if isinstance(r.get("quadrant_alt"), str) and r.get("quadrant_alt") else ""
                st.caption(f"진단 안정도 {stab * 100:.0f}% (15가지 변형 중 같은 진단 비율)"
                           + (f" · 바뀔 때는 '{alt_q}'" if alt_q else "")
                           + (" · 80% 미만이라 불확실" if stab < 0.8 else ""))
            st.markdown(f"**진단 근거** · 상대 쇠퇴 위험 {r.risk_score:.0f}점: {r.risk_drivers} · "
                        f"상대 성장 가능 {r.growth_score:.0f}점: {r.growth_drivers}")
        notes = [f"주요 업종: {r.top3_mid}"]
        if pd.notna(r.get("bad_pct")):
            notes.append(f"2021 소상공인 실태조사({r.survey_dong}): 매출·이익 감소 {r.decline_pct:.0f}%, "
                         f"폐업·전환 고려 {r.closing_pct:.0f}% (대전 평균 74% / 7%, 코로나 시기)")
        if IS is not None:
            _b, _ = ind_scores(False)
            _a, _ = ind_scores(True)
            _b, _a = _b[_b.code == sel].set_index("industry").score, _a[_a.code == sel].set_index("industry").score
            notes.append("업종 점수(트램 건설 전→후): " + " · ".join(
                f"{i} {_b[i]:.0f}→{_a[i]:.0f}" if pd.notna(_b.get(i)) else f"{i} –" for i in IND_LIST))
        st.caption(" · ".join(notes))
        if sel == "A12":
            st.info("도룡동 점포 수 급증은 2021년 대전신세계 입점 매장이 등록된 영향입니다.")

        g1, g2 = st.columns(2)
        if lp is not None:
            g1.markdown("**땅값 지수** · 점선 = 이 상권의 주요 사건")
            g1.altair_chart(land_chart([sel]), use_container_width=True)
        if sp is not None:
            g2.markdown("**점포 수 (분기)** · 빨간 점선 = 자료 수집 기준 변경")
            g2.altair_chart(store_chart(sel), use_container_width=True)
        if fc is not None and lp is not None and sel in set(fc.code):
            st.markdown("**땅값 예측** · 파란 띠 = 80% 범위 (넓으므로 상권끼리 비교용) · 트램 효과는 대전 1호선처럼 "
                        "개통 1~4년에 가장 크고 이후 줄어드는 모양")
            st.altair_chart(forecast_chart(sel), use_container_width=True)

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
                   "트램 효과(개통 초기 1~4년, 땅값 기준 추정 %) 낮음/기본/높음": (g("tram_effect_low", 2), g("tram_effect", 2), g("tram_effect_high", 2)),
                   "진단 안정도(15가지 변형 중 같은 진단 비율)": g("quadrant_stability", 2)}
            if fc is not None and code in set(fc.code):
                f = fc[(fc.code == code)].set_index("year")
                y = f.index.max()
                ctx[f"{y}년 공시지가 예측(2026=100): 트램 없음 / 트램 기본 / 80% 범위"] = (
                    round(f.loc[y, "base_path"], 1), round(f.loc[y, "tram_base"], 1),
                    f"{f.loc[y, 'lo80']:.0f}~{f.loc[y, 'hi80']:.0f}")
            if "bad_pct" in r and pd.notna(r.get("bad_pct")):
                ctx["2021 실태조사(소속 행정동)"] = f"{r.survey_dong}: 매출·이익 감소 {r.decline_pct:.0f}%, 폐업·전환 고려 " \
                                              f"{r.closing_pct:.0f}% (대전 평균 74%·7%, 코로나 시기)"
            if ind_area is not None and code in set(ind_area.iloc[:, 0]):
                ia = ind_area.set_index(ind_area.columns[0]).loc[code]
                ctx["업종 비율 변화 2016→2026(%p)"] = {c.replace("_변화p", ""): ia[c] for c in ia.index if c.endswith("_변화p")}
            if IS is not None:
                _b, _ = ind_scores(False)
                _a, _ = ind_scores(True)
                _b, _a = _b[_b.code == code].set_index("industry").score, _a[_a.code == code].set_index("industry").score
                ctx["업종 점수(100점, 20개 상권 중 상대, 트램 건설 전→후)"] = {
                    i: (f"{_b[i]:.0f}→{_a[i]:.0f}" if pd.notna(_b.get(i)) else "점포 부족") for i in IND_LIST}
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
        def ai_area(ctx_text, scen_text, nonce=0):
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            prompt = f"""너는 대전 상권 분석가야. 아래는 우리 팀이 공공데이터로 분석한 상권 정보야.
{ctx_text}

[지표 설명]
- 점수: 20개 상권 안 상대 순위(0~100). 절대적 쇠퇴 판정이 아님
- 진단: 상대 쇠퇴 위험 50점 이상이면서 상권 점포 절반 이상이 트램 정거장 500m 안이면 '트램 반등 기회', 아니면 '쇠퇴 우려', 위험 50 미만이면 '성장 지속'/'정체·안정'. 진단 안정도가 0.8 미만이면 '불확실'이라고 꼭 말할 것
- 트램 효과: {TRAM_DEF}. 시나리오 근거: {' / '.join(SCEN_HELP)}. 지하철 효과를 지상 트램에 빌려 쓴 것이라 과대일 수 있음. 선택된 시나리오: {scen_text}
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

        st.markdown("#### AI 상권 해설")
        key = (sel, scen)
        ss.setdefault("ai", {})
        have = key in ss.ai
        if st.button("AI 해설 다시 받기" if have else "AI 해설 받기", key="ai_btn"):
            ctx = json.dumps(area_context(sel), ensure_ascii=False, default=str, indent=1)
            with st.spinner("AI가 분석 중... (10초 정도)"):
                try:
                    ss.ai[key] = ai_area(ctx, scen, ss.get("_ai_n", 0) + (1 if have else 0))
                    ss._ai_n = ss.get("_ai_n", 0) + (1 if have else 0)
                except Exception as e:
                    st.error(f"AI 호출 실패: {e}")
        if key in ss.ai:
            st.markdown(ss.ai[key])
            with st.expander("AI 에게 보낸 정보 보기"):
                st.json(area_context(sel))
        else:
            st.caption("버튼을 누르면 이 상권의 진단·예측·트램 효과를 근거로 해설을 만듭니다. 한 번 받은 해설은 다른 상권을 보고 와도 남아 있습니다.")

    # ================= 패널 2: 정거장 500m
    elif panel == "정거장 500m":
        if ss.sel_station is None or st_sum is None:
            st.info("지도에서 파란 정거장 점을 클릭하거나, 위의 '정거장 선택'에서 고르세요.")
        else:
            t = st_sum.set_index("station_no").loc[ss.sel_station]
            st.markdown(f"#### 🚈 {ss.sel_station} {t.station_name} · 500m 영향권")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("점포 수 (2026-06)", f"{int(t.n_stores):,}")
            k2.metric("음식 / 소매 비율", f"{t.food_pct:.0f}% / {t.retail_pct:.0f}%", f"체인점 {t.branch_pct:.0f}%",
                      delta_color="off", help="체인점 = 지점이 있는 브랜드 점포 비율")
            k3.metric("공시지가 중앙값", f"{t.land_price / 1e4:,.0f}만원/㎡" if pd.notna(t.get("land_price")) else "-",
                      f"5년 {t.land_growth_5y_pct:+.1f}%" if pd.notna(t.get("land_growth_5y_pct")) else None)
            te = t.get(f"tram_effect_{SCEN[scen].replace('tram_effect', '').strip('_') or 'base'}")
            k4.metric(f"트램 효과 ({scen})", f"{te:+.1f}%" if pd.notna(te) else "분석 상권 밖", help=HELP.get("tram_sel"))
            st.caption(f"주요 업종: {t.top3_mid} · 좌표: {t.coord_source}")
            a = st_areas[st_areas.station_no == ss.sel_station] if st_areas is not None else pd.DataFrame()
            if len(a):
                st.markdown("**영향권에 걸친 상권** · 행을 누르면 그 상권으로 이동")
                cols = {"code": "코드", "name": "상권", "stores_in_500m": "영향권 안 점포", "share_of_area_pct": "상권 점포 중 비율(%)",
                        "quadrant": "진단", "risk_score": "위험", "growth_score": "성장", "type_name": "유형",
                        "tram_gain": "2034 트램 효과(땅값 %p)"}
                tb = a[[c for c in cols if c in a.columns]].rename(columns=cols).round(1).reset_index(drop=True)
                try:
                    ev = st.dataframe(tb, hide_index=True, use_container_width=True, on_select="rerun",
                                      selection_mode="single-row", key="stn_tbl")
                    rows = ev.selection.rows if ev is not None else []
                except TypeError:
                    st.dataframe(tb, hide_index=True, use_container_width=True); rows = []
                if rows:
                    ss.sel_area = tb["코드"].iloc[rows[0]]; ss._last_area = ss.sel_area
                    ss._pending_panel = "상권 상세"; st.rerun()
            else:
                st.info("이 정거장 500m 안에는 20개 분석 상권이 없습니다.")

    # ================= 패널 3: 상권 비교
    elif panel == "상권 비교":
        others = [c for c in order if c != sel]
        default = prof[prof.code != sel].sort_values("growth_score", ascending=False).code.iloc[0] \
            if "growth_score" in prof else others[0]
        o = st.selectbox(f"{names[sel]} 와(과) 비교할 상권", others, index=others.index(default), format_func=names.get)
        ro = info.loc[o]
        rows = [(M[k][0], k) for k in ["quadrant", "risk_score", "growth_score", "tram_sel", "land_chg_5y_pct",
                                         "land_rel_idx", "store_share_chg_5y_pct", "close_rate_q_pct", "n_stores"] if k in M]
        fmt = lambda v: v if isinstance(v, str) else ("-" if pd.isna(v) else f"{v:,.1f}")
        ct = pd.DataFrame({"지표": [n for n, _ in rows], NM[sel]: [fmt(r[k]) for _, k in rows],
                           NM[o]: [fmt(ro[k]) for _, k in rows]})
        x1, x2 = st.columns([2, 3])
        x1.dataframe(ct, hide_index=True, use_container_width=True, height=360)
        if lp is not None:
            x2.markdown("**땅값 지수 비교 (2015=100)**")
            x2.altair_chart(land_chart([sel, o]), use_container_width=True)

        st.markdown("#### 20개 상권 한 표로 보기 · 행을 누르면 그 상권으로 이동")
        keep = ["code", "name", "quadrant", "quadrant_stability", "risk_score", "growth_score", "tram_sel", "land_chg_5y_pct",
                "store_share_chg_5y_pct", "close_rate_q_pct", "n_stores", "type_name"]
        tb = prof[[c for c in keep if c in prof.columns]].copy()
        tb.insert(0, "선택", tb.code.eq(sel).map({True: "▶", False: ""}))
        sort_col = am if am not in ("quadrant", "cluster") else "risk_score"
        tb = tb.sort_values(sort_col, ascending=False).reset_index(drop=True)
        CC = st.column_config
        cfg = {"code": "코드", "name": "상권", "quadrant": "진단", "type_name": "유형",
               "quadrant_stability": CC.NumberColumn("진단 안정도", format="%.2f",
                                                     help="15가지 변형 중 같은 진단 비율. 0.8 미만 = 불확실"),
               "risk_score": CC.ProgressColumn("상대 위험", min_value=0, max_value=100, format="%.0f", help=HELP.get("risk_score")),
               "growth_score": CC.ProgressColumn("상대 성장", min_value=0, max_value=100, format="%.0f", help=HELP.get("growth_score")),
               "tram_sel": CC.NumberColumn(f"트램 효과 ({scen})", format="%+.1f%%", help=HELP.get("tram_sel")),
               "land_chg_5y_pct": CC.NumberColumn("땅값 5년", format="%+.1f%%"),
               "store_share_chg_5y_pct": CC.NumberColumn("점포 비중 5년", format="%+.1f%%", help=HELP.get("store_share_chg_5y_pct")),
               "close_rate_q_pct": CC.NumberColumn("분기 폐업률", format="%.1f%%"),
               "n_stores": CC.NumberColumn("점포 수", format="%d")}
        try:
            ev = st.dataframe(tb, hide_index=True, use_container_width=True, column_config=cfg, height=740,
                              on_select="rerun", selection_mode="single-row", key="cmp_tbl")
            rws = ev.selection.rows if ev is not None else []
        except TypeError:
            st.dataframe(tb, hide_index=True, use_container_width=True, column_config=cfg); rws = []
        if rws and tb.code.iloc[rws[0]] != sel:
            ss.sel_area = tb.code.iloc[rws[0]]; ss._last_area = ss.sel_area
            ss._pending_panel = "상권 상세"; st.rerun()

    # ================= 패널 4: 업종 점수
    else:
        if IS is None:
            st.info("업종 점수 결과가 없습니다. python tram_model/run_all.py --from score_industry 를 실행하세요.")
        else:
            cur = ss.ind if ss.ind != ALL_IND else ss.get("ind_last", IND_LIST[0])
            ss.ind_last = cur

            def _ind_cb():
                ss.ind = ss.ind_panel

            def _tram_cb():
                ss.tram_after = ss.tram_after_panel

            ss.ind_panel, ss.tram_after_panel = cur, tram_after
            h1, h2 = st.columns([4, 2])
            h1.radio("업종", IND_LIST, key="ind_panel", horizontal=True, on_change=_ind_cb)
            h2.toggle("트램 건설 후 (2028 개통 반영)", key="tram_after_panel", on_change=_tram_cb,
                      help="건설 후 = '트램 효과' 항목(10점)을 넣고 나머지 항목을 90점에 맞춰 다시 계산")
            B, wb = ind_scores(False)
            A, wa = ind_scores(True)
            T = B[B.industry == cur][["code", "name", "n_stores", "growth", "lq", f"tram_effect_{SCEN_KEY}", "flag"]].copy()
            T["before"], T["after"] = B.loc[T.index, "score"], A.loc[T.index, "score"]
            T["change"] = (T.after - T.before).round(1)
            rb, ra = T.before.rank(ascending=False, method="min"), T.after.rank(ascending=False, method="min")
            T["move"] = [("–" if pd.isna(x) or pd.isna(y) else ("▲" + str(int(x - y)) if x > y else
                          ("▼" + str(int(y - x)) if y > x else "="))) for x, y in zip(rb, ra)]
            now_col = "after" if tram_after else "before"
            T = T.sort_values(now_col, ascending=False, na_position="last").reset_index(drop=True)
            T.insert(0, "rank", T[now_col].rank(ascending=False, method="min").values)
            T["score_now"] = T[now_col]
            T.insert(1, "선택", T.code.eq(sel).map({True: "▶", False: ""}))
            top = T.dropna(subset=[now_col]).head(3)
            st.markdown(f"#### {cur} 점수 순위 · {'트램 건설 후' if tram_after else '트램 건설 전'} 기준 정렬")
            st.caption("점수 = 업종 안에서 20개 상권을 줄 세운 상대 점수(100점). 1위: " +
                       ", ".join(f"{n.split('(')[0]} {v:.0f}" for n, v in zip(top.name, top[now_col])) +
                       " · 행을 누르면 그 상권의 점수 근거가 아래에 나옴")
            CC = st.column_config
            cfg = {"rank": CC.NumberColumn("순위", format="%d"), "code": "코드", "name": "상권",
                   "score_now": CC.ProgressColumn(f"점수 ({'건설 후' if tram_after else '건설 전'})", min_value=0,
                                                  max_value=100, format="%.0f"),
                   "before": CC.NumberColumn("건설 전", format="%.0f"), "after": CC.NumberColumn("건설 후", format="%.0f"),
                   "change": CC.NumberColumn("변화", format="%+.1f"), "move": "순위 변화",
                   "n_stores": CC.NumberColumn(f"{cur} 점포 수", format="%d"),
                   "growth": CC.NumberColumn("대전 내 비중 5년 변화", format="%+.1f%%"),
                   "lq": CC.NumberColumn("특화도", format="%.2f", help="1보다 크면 대전 평균보다 이 업종이 많이 모인 상권"),
                   f"tram_effect_{SCEN_KEY}": CC.NumberColumn(f"트램 효과 ({scen})", format="%.2f%%", help=TRAM_DEF),
                   "flag": "비고"}
            show = ["rank", "선택", "code", "name", "score_now", "before", "after", "change", "move", "n_stores", "growth", "lq",
                    f"tram_effect_{SCEN_KEY}", "flag"]
            try:
                ev = st.dataframe(T[show], hide_index=True, use_container_width=True, column_config=cfg, height=420,
                                  on_select="rerun", selection_mode="single-row", key="ind_tbl")
                rws = ev.selection.rows if ev is not None else []
            except TypeError:
                st.dataframe(T[show], hide_index=True, use_container_width=True, column_config=cfg); rws = []
            if rws and T.code.iloc[rws[0]] != sel:
                ss.sel_area = T.code.iloc[rws[0]]; ss._last_area = ss.sel_area; st.rerun()

            # 건설 전 → 후 비교 (덤벨 차트)
            g1, g2 = st.columns([3, 2])
            dd = T.dropna(subset=["before"]).assign(short=lambda d: d.name.str.split("(").str[0])
            order_y = list(dd.short)
            base = alt.Chart(dd).encode(y=alt.Y("short:N", sort=order_y, title=None))
            rule = base.mark_rule(color="#b9bec5", strokeWidth=2).encode(
                x=alt.X("before:Q", title="점수 (100점)", scale=alt.Scale(domain=[0, 100])), x2="after:Q")
            pb = base.mark_circle(size=70, color="#9aa0a6").encode(x="before:Q", tooltip=["name", alt.Tooltip("before:Q", title="건설 전")])
            pa = base.mark_circle(size=90, color="#1f4fa3").encode(x="after:Q", tooltip=["name", alt.Tooltip("after:Q", title="건설 후"),
                                                                                         alt.Tooltip("change:Q", title="변화")])
            g1.markdown(f"**{cur}: 트램 건설 전(회색) → 후(파랑)**")
            g1.altair_chart((rule + pb + pa).properties(height=max(260, 22 * len(dd))), use_container_width=True)
            g1.caption("트램 정거장 500m 안 비율이 높고 트램에 민감한 업종(음식·소매)일수록 오르고, 트램이 닿지 않는 상권은 내려감")

            # 상권 × 업종 한눈에 (지금 기준)
            Cur = A if tram_after else B
            hm = Cur.assign(short=Cur.name.str.split("(").str[0])
            ordr = list(hm.groupby("short").score.mean().sort_values(ascending=False).index)
            heat = alt.Chart(hm).mark_rect().encode(
                x=alt.X("industry:N", sort=IND_LIST, title=None, axis=alt.Axis(orient="top", labelAngle=0)),
                y=alt.Y("short:N", sort=ordr, title=None),
                color=alt.Color("score:Q", scale=alt.Scale(domain=[0, 100], range=["#f3f6f4", "#1d7a46"]), legend=None),
                tooltip=["name", "industry", alt.Tooltip("score:Q", format=".0f"), "flag"])
            txt = alt.Chart(hm).mark_text(fontSize=11).encode(
                x=alt.X("industry:N", sort=IND_LIST), y=alt.Y("short:N", sort=ordr),
                text=alt.Text("score:Q", format=".0f"),
                color=alt.condition(alt.datum.score > 60, alt.value("white"), alt.value("#333")))
            g2.markdown(f"**20개 상권 × 6개 업종 ({'건설 후' if tram_after else '건설 전'})**")
            g2.altair_chart((heat + txt).properties(height=max(260, 22 * len(ordr))), use_container_width=True)

            # 선택 상권의 점수 근거
            row_b = B[(B.industry == cur) & (B.code == sel)]
            if len(row_b):
                rb_ = row_b.iloc[0]
                w_now = wa if tram_after else wb
                pr = info.loc[sel]
                raw = {"growth": f"{rb_.growth:+.1f}%" if pd.notna(rb_.growth) else "–",
                       "size": f"{int(rb_.n_stores):,}개" if pd.notna(rb_.n_stores) else "–",
                       "lq": f"{rb_.lq:.2f}" if pd.notna(rb_.lq) else "–",
                       "survival": f"분기 폐업률 {pr.close_rate_q_pct:.1f}%" if pd.notna(pr.get("close_rate_q_pct")) and pd.notna(rb_.survival) else "–",
                       "land": f"{rb_.land:+.1f}%" if pd.notna(rb_.land) else "–",
                       "tram": f"500m 안 {rb_.in500 * 100:.0f}% · 효과 {rb_[f'tram_effect_{SCEN_KEY}']:.2f}%"}
                ITEM = ISW.set_index("key").item.to_dict()
                ws = sum(v for k, v in w_now.items() if pd.notna(rb_[f"s_{k}"]))
                br = pd.DataFrame([{"항목": ITEM.get(k, k), "이 상권 값": raw[k],
                                    "항목 점수": rb_[f"s_{k}"], "가중치": round(v, 1),
                                    "기여 점수": round(rb_[f"s_{k}"] * v / ws, 1) if pd.notna(rb_[f"s_{k}"]) else None}
                                   for k, v in w_now.items()])
                tot_ = (A if tram_after else B).loc[row_b.index[0], "score"]
                st.markdown(f"**{names[sel]} · {cur} 점수 {tot_:.0f}점의 근거** "
                            f"({'트램 건설 후' if tram_after else '트램 건설 전'})" if pd.notna(tot_) else
                            f"**{names[sel]} · {cur}**: {rb_.flag}")
                st.dataframe(br, hide_index=True, use_container_width=True, column_config={
                    "항목 점수": CC.ProgressColumn("항목 점수 (20개 중 상대)", min_value=0, max_value=100, format="%.0f"),
                    "기여 점수": CC.NumberColumn("기여 점수", format="%.1f",
                                               help="항목 점수 × 가중치 ÷ (값이 있는 항목 가중치 합). 다 더하면 총점")})
                if isinstance(rb_.flag, str) and rb_.flag:
                    st.caption(f"비고: {rb_.flag}")

            # 가중치와 근거 + 직접 조정
            with st.expander("가중치와 근거 · 직접 조정"):
                wt = ISW.rename(columns={"item": "항목", "weight_before": "건설 전", "weight_after": "건설 후",
                                         "data": "데이터", "method": "계산", "rationale": "근거", "limit": "한계"})
                st.dataframe(wt.drop(columns=["key"]), hide_index=True, use_container_width=True)
                st.caption("항목 점수는 업종마다 20개 상권을 줄 세운 백분위(0~100). 트램 효과만 절대 척도"
                           "(정거장 500m 안 비율 × 업종 민감도). 업종 점포가 5개 미만인 상권은 점수를 매기지 않음. "
                           "도룡동은 신세계 입점 등록 왜곡으로 성장·생존 항목 제외")
                st.markdown("**가중치 직접 조정** (건설 전 기준, 합이 100이 아니어도 비율로 맞춤 · 건설 후는 트램 10점 + 나머지 90점)")
                cols = st.columns(len(W_DEF))
                new_w = {}
                for c_, (k, v) in zip(cols, ss.ind_w.items()):
                    new_w[k] = float(c_.slider(ITEM.get(k, k), 0, 50, int(v), 5))
                b1, b2 = st.columns([1, 5])
                if b1.button("기본값으로", key="ind_w_reset"):
                    new_w = dict(W_DEF)
                if new_w != ss.ind_w:
                    ss.ind_w = new_w
                    st.rerun()
                if ss.ind_w != W_DEF:
                    b2.caption("지금 조정한 가중치로 지도·순위가 계산되고 있음 (기본: " +
                               ", ".join(f"{ITEM.get(k, k)} {v:.0f}" for k, v in W_DEF.items()) + ")")

# ================================================================ 격자 보기 (실험용)
else:
    st.warning("격자 보기는 실험용입니다. '월평균 매출'은 실제 매출이 아니라 점포 수로 만든 합성값이니 발표·판단에 쓰지 마세요.")
    df["tram_sel"] = df[SCEN[scen]] if SCEN[scen] in df.columns else df["tram_effect"]
    LABEL = {"tram_sel": f"트램 효과(%, {scen})", "resid_pct": "입지 대비 잔차(%)"}
    if "land_price" in df.columns:
        LABEL.update({"land_price": "공시지가(원/㎡)", "land_growth_5y": "공시지가 5년 상승률(%)"})
    LABEL["sales"] = "월평균 매출 (합성값·실험용)"
    cats = box.multiselect("업종", sorted(df.category.unique()), default=["음식", "소매"])
    metric = box.radio("지표", list(LABEL), format_func=LABEL.get,
                       help="입지 대비 잔차 = 버스·인구 등 입지 조건으로 예상한 값보다 실제가 얼마나 높은지(%)")
    style = box.radio("표현 방식", ["격자 색칠", "히트맵"])
    agg = dict(lat=("lat", "first"), lon=("lon", "first"), dong=("dong", "first"), zone=("zone", "first"),
               sales=("sales", "sum"), tram_sel=("tram_sel", "mean"), resid_pct=("resid_pct", "first"))
    if "land_price" in df.columns:
        agg.update(land_price=("land_price", "first"), land_growth_5y=("land_growth_5y", "first"))
    d = df[df.category.isin(cats)].groupby("cell_id").agg(**agg).reset_index()
    d["tram_sel"] = d.tram_sel.round(2)
    v = d[metric]
    if v.notna().any():
        kd = "div0" if metric in ("resid_pct", "land_growth_5y") else ("seq_tram" if metric == "tram_sel" else "seq_neutral")
        d["color"], (stops, lo, hi) = colorize(v, kd)
        d["norm"] = ((v - v.min()) / (v.max() - v.min() + 1e-9)).fillna(0)
        st.markdown(legend_bar(LABEL[metric], stops, lo, hi, kd), unsafe_allow_html=True)
    else:
        d["color"], d["norm"] = [[200, 200, 200, 90]] * len(d), 0.0
        st.warning(f"'{LABEL[metric]}' 값이 map_data.csv 에 없습니다.")
    if style == "격자 색칠":
        main = pdk.Layer("ScatterplotLayer", d, get_position=["lon", "lat"], get_radius=120,
                         get_fill_color="color", pickable=True)
    else:
        main = pdk.Layer("HeatmapLayer", d, get_position=["lon", "lat"], get_weight="norm", radius_pixels=60)
    show_map(deck([main] + lay_route + [lay_stop],
                  {"text": "{zone} · {dong} {cell_id}\n트램효과 {tram_sel}%\n잔차 {resid_pct}%\n매출(합성) {sales}"}), select=False)
    st.subheader(f"{LABEL[metric]} 상위 격자")
    st.dataframe(d.sort_values(metric, ascending=False).head(20).drop(columns=["color", "norm"]),
                 hide_index=True, use_container_width=True)

    @st.cache_data(show_spinner=False)
    def ai_comment(row_text, cats_text, scen_text):
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        return client.models.generate_content(
            model="gemini-3.8-flash",
            contents=(f"대전 트램 상권 분석 격자 데이터야: {row_text}. 선택 업종: {cats_text}. "
                      f"트램 효과(tram_sel)는 '{scen_text}' 시나리오의 {TRAM_DEF}야. "
                      "sales 는 합성값이니 해석에 쓰지 마. "
                      "창업자 관점에서 장점, 위험, 추천 업종을 5줄로 정리하고 추정은 추정이라고 표시해줘.")).text

    st.subheader("AI 격자 해설")
    gsel = st.selectbox("해설 볼 격자", d.sort_values(metric, ascending=False).cell_id)
    ss.setdefault("ai_grid", {})
    if st.button("해설 받기"):
        row = d[d.cell_id == gsel].drop(columns=["color", "norm"]).iloc[0].to_dict()
        with st.spinner("AI가 분석 중..."):
            try:
                ss.ai_grid[gsel] = ai_comment(str(row), str(cats), scen)
            except Exception as e:
                st.error(f"AI 호출 실패: {e}")
    if gsel in ss.ai_grid:
        st.write(ss.ai_grid[gsel])
