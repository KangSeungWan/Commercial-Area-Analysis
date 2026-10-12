import json, os, sys
import numpy as np
import streamlit as st, pandas as pd, pydeck as pdk, altair as alt

st.set_page_config(page_title="대전 트램 상권 지도", layout="wide", page_icon=":material/tram:")
sys.path.insert(0, "tram_model")
from tram_route import route_paths
from about_page import show_about                                      # 분석 방법 팝업
import ai_comment as ac                                                # AI 상권 해설 (실시간 + 저장본)

OUT, DATA = "tram_model/outputs", "tram_model/data"
OPEN_YEAR = 2030                                           # 트램 2호선 개통 예정 연도
ss = st.session_state


# ── 파일 읽기 (한 번 읽고 캐시 → 클릭 반응 빠르게) ──
@st.cache_data
def read_csv(path, **kw):
    return pd.read_csv(path, encoding="utf-8-sig", **kw) if os.path.exists(path) else None


@st.cache_data
def read_json(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


def setting(name, default=None):
    """secrets.toml → 환경변수 순서로 설정값을 찾음. 파일이 없거나 깨져도 오류 없이 default."""
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return v or os.environ.get(name) or default


@st.cache_data
def load_ai_saved(mtime):                                  # 파일이 바뀌면(mtime) 다시 읽음
    return ac.load_saved()


stations = read_csv(f"{DATA}/tram_stations.csv")
if stations is None:
    stations = read_csv(f"{DATA}/tram_stations_approx.csv")
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
money = read_csv(f"{OUT}/tram_impact_money.csv")             # 트램 효과 금액 (analyze_tram_impact, 공시지가 기준)

# 핵심 파일이 없으면 파이썬 오류 대신 안내를 띄우고 멈춤
_miss = [k for k, v in {"상권 정보 (outputs/area_profile.csv)": prof, "트램 정거장 좌표 (data/tram_stations.csv)": stations,
                        "상권 경계 (outputs/sangkwon_polygons.geojson)": gj}.items() if v is None]
if _miss:
    st.title("대전 트램 상권 지도")
    st.error("앱을 여는 데 필요한 분석 결과 파일이 없습니다: " + ", ".join(_miss))
    st.markdown("프로젝트 폴더에서 `python tram_model/run_all.py` 를 실행해 결과 파일을 만든 뒤 이 페이지를 새로 고치세요.")
    st.stop()
stations = stations.sort_values("station_no")

# ── 색 (진단 4분류 색은 지도·배지·요약·표에서 똑같이 사용) ──
QC = {"성장 지속": [34, 139, 84], "트램 반등 기회": [235, 130, 20], "쇠퇴 우려": [200, 50, 50], "정체·안정": [140, 140, 140]}
QHEX = {k: "#%02x%02x%02x" % tuple(v) for k, v in QC.items()}
# 진단 배지 글자색: 바탕 밝기에 맞춤 (주황·회색 위 흰 글자는 대비 2.7·3.4:1 → 숲색 잉크 6.5·5.2:1)
QTXT = {"성장 지속": "#ffffff", "트램 반등 기회": "#0a1d08", "쇠퇴 우려": "#ffffff", "정체·안정": "#0a1d08"}
TRAM_INK = "#2c3fa8"                                       # 트램 효과 = 남색 (색 단계 끝 · 예측 차트 '건설 후' 선)
PAL = [[52, 110, 190], [235, 130, 20], [34, 139, 84], [200, 50, 50], [128, 90, 180]]       # 상권 유형 1~5
ROUTE_C = [35, 39, 46]                                     # 트램 노선·정거장: 짙은 먹색 (지표 색과 겹치지 않게)
REG_A, CORE_A = 95, 225                                     # 권역은 옅게, 점포가 모인 핵심 영역은 진하게
RAMP = {"bad": ["#fff4d6", "#f2a65a", "#b8322a"],          # 높을수록 나쁨 (위험·폐업률)
        "good": ["#eef7ee", "#83c58f", "#1d7a46"],         # 높을수록 좋음 (성장)
        "tram": ["#eef1fb", "#8ea2e6", "#2c3fa8"],         # 트램 효과
        "neutral": ["#f1f3f5", "#9aa5b1", "#2f3b48"],      # 좋고 나쁨 없음 (점포 수)
        "div": ["#6b4c9a", "#f4f4f2", "#1f7a7a"]}          # 증감: 감소 보라 · 0 흰색 · 증가 청록 (진단 4색과 겹치지 않게)
BREAKS = ["2023-03", "2024-12", "2026-06"]                 # 점포 자료 수집 기준이 바뀐 분기

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,300&family=Noto+Serif+KR:wght@300&display=swap');
/* DESIGN.md 토큰: ink #0a1d08 · moss #2a332a · linen #f8f9f5 · bone #eff2e8 · mist #e1e6df · sage #4a6d47 · sage-gray #6b7860 */
.block-container{padding-top:2.4rem;padding-left:2.5rem;padding-right:2.5rem}
.stMarkdown p,.stMarkdown div,.stCaption{word-break:keep-all}
::selection{background:#c9d5c5;color:#0a1d08}
.serif{font-family:'Newsreader','Noto Serif KR',serif;font-weight:300;letter-spacing:-0.02em}
h1.page-t{font-family:'Newsreader','Noto Serif KR',serif;font-weight:300;font-size:36px;letter-spacing:-0.02em;color:#0a1d08;
  padding:4px 0 6px 0;margin:0}
[data-testid="stMetricValue"]{font-family:'Newsreader','Noto Serif KR',serif;font-weight:300;letter-spacing:-0.02em}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:13px;font-weight:600;color:#fff;margin-left:6px;vertical-align:middle}
.badge.gray{background:#eff2e8;color:#0a1d08;border:1px solid #e1e6df}
.verdict{font-size:20px;font-weight:600;color:#0a1d08;letter-spacing:-0.01em;margin:0 0 2px 0}
.kpi{display:flex;flex-wrap:wrap;align-items:center;gap:4px 16px;font-size:14px;color:#2a332a;margin:0 0 6px 0}
.kpi .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
.kpi b{font-size:16px;color:#0a1d08}.kpi .sep{color:#6b7860}
.area-h{line-height:1.2}.area-h .code{color:#6b7860;font-size:14px;margin-right:8px;font-variant-numeric:tabular-nums}
.area-h .t{font-family:'Newsreader','Noto Serif KR',serif;font-weight:300;font-size:30px;letter-spacing:-0.02em;color:#0a1d08}
.area-b{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:8px 0 2px 0}.area-b .badge{margin-left:0}
.area-b .where{font-size:13px;color:#6b7860;margin-left:4px}
.why{background:#eff2e8;border:1px solid #e1e6df;border-radius:10px;padding:12px 16px;margin:4px 0 6px 0;color:#2a332a}
.why-h{font-size:13px;font-weight:600;color:#4a6d47;margin-bottom:4px}
.why-rule{font-size:15px;font-weight:600;color:#0a1d08;margin-bottom:8px;line-height:1.45}
.why-r{display:grid;grid-template-columns:7.2em 3.6em 1fr;gap:8px;font-size:13.5px;line-height:1.45;padding:3px 0}
.why-r .l{color:#6b7860}.why-r b{color:#0a1d08;text-align:right;font-variant-numeric:tabular-nums}
.why-f{font-size:12.5px;color:#6b7860;margin-top:8px;padding-top:7px;border-top:1px solid #e1e6df}
.stn-t{font-size:16px;font-weight:600;color:#0a1d08}
.st-key-stnpanel{background:#fff;border-left:4px solid #23272e !important}   /* DESIGN Station Card: 노선 위의 한 점 */
.ai-saved{display:inline-block;padding:2px 10px;border-radius:6px;font-size:13px;font-weight:600;color:#2a332a;background:#eff2e8;border:1px solid #c9d5c5}
.lg{display:flex;align-items:center;gap:8px;font-size:13px;color:#2a332a;margin:2px 0 4px 0;flex-wrap:wrap}
.lg .bar{width:180px;height:10px;border-radius:3px}.lg .dot{width:11px;height:11px;border-radius:50%;display:inline-block;margin:0 4px 0 10px}
.maphead{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px 18px;
  border:1px solid #e1e6df;border-bottom:none;border-radius:10px 10px 0 0;padding:8px 12px;background:#fff;margin-bottom:-2px}
.maphead .lg{margin:0}
.sym{display:flex;align-items:center;gap:6px;font-size:12.5px;color:#6b7860;flex-wrap:wrap}
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


def colorize(values, kind, center=None, span=None):
    """숫자 → 색. kind: seq_bad / seq_good / seq_tram / seq_neutral / div0(0 기준 증감) / div100(100 기준)
    / divavg(center = 대전 평균 기준)."""
    v = pd.to_numeric(values, errors="coerce")
    if kind.startswith("div"):
        c = center if center is not None else (100 if kind == "div100" else 0)
        m = span or float((v - c).abs().quantile(.95)) or 1.0
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


TIP_STYLE = {"backgroundColor": "#ffffff", "color": "#0a1d08", "fontSize": "12.5px", "lineHeight": "1.5",
             "borderRadius": "8px", "border": "1px solid #e1e6df", "boxShadow": "0 4px 14px rgba(0,0,0,.14)",
             "padding": "8px 11px", "fontFamily": "Pretendard, 'Apple SD Gothic Neo', sans-serif"}
# 첫 화면: 트램 노선 전체가 꽉 차게 (대전 전체가 아니라 분석 대상에 초점)
VIEW0 = dict(latitude=float((stations.lat.min() + stations.lat.max()) / 2),
             longitude=float((stations.lon.min() + stations.lon.max()) / 2), zoom=12.0)


MPP0 = 78271.517       # deck.gl·Mapbox 지도(512px 타일)에서 줌 0, 적도 1픽셀 = 몇 m (256px 타일 값 156543 의 절반)
LABEL_PX = 12.5         # 지도 위 상권 이름 글자 높이 (실제 화면 픽셀)


def fit_view(lons, lats, w_px, h_px, pad=0.07):
    """경위도 범위가 w×h 픽셀 지도에 여백 pad 를 두고 꽉 차는 중심·줌."""
    import math
    lat0, lon0 = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
    c = math.cos(math.radians(lat0))
    mpp = max((max(lons) - min(lons)) * 111320 * c / (w_px * (1 - 2 * pad)),
              (max(lats) - min(lats)) * 111320 / (h_px * (1 - 2 * pad)))
    return dict(latitude=lat0, longitude=lon0, zoom=round(math.log2(MPP0 * c / mpp), 2))


def _bbox(geo):
    xs, ys = [], []
    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)
    for f in geo["features"]:
        walk(f["geometry"]["coordinates"])
    return xs, ys


# 지도 화면: 지도가 화면 왼쪽 약 60%로 줄어듦 → 20개 상권 핵심 영역 + 정거장 전체가 들어가게 맞춤
# (상권은 남북 약 17km로 세로가 김 → 높이가 줌을 정함. 폭은 1440px 화면의 지도 칸 약 560px 기준)
MAP_H, MAP_W = 600, 560
_xs, _ys = _bbox(gj)
VIEW_MAP = fit_view(_xs + stations.lon.tolist(), _ys + stations.lat.tolist(), MAP_W, MAP_H)
IND_H = 460                                                # 업종 점수 화면 지도 (본문 폭 약 1000px)
VIEW_IND = fit_view(_xs + stations.lon.tolist(), _ys + stations.lat.tolist(), 900, IND_H)


def deck(layers, tooltip, view=None):
    if isinstance(tooltip, dict):
        tooltip = {**tooltip, "style": TIP_STYLE}
    return pdk.Deck(layers=layers, map_style="light", tooltip=tooltip,
                    initial_view_state=view or pdk.ViewState(**VIEW0, min_zoom=10, max_zoom=16))


def px(lon, lat, view=VIEW0):
    """경위도 → 첫 화면 기준 픽셀 좌표 (라벨 겹침 계산용)."""
    import math
    m = MPP0 * math.cos(math.radians(view["latitude"])) / 2 ** view["zoom"]
    return ((lon - view["longitude"]) * 111320 * math.cos(math.radians(view["latitude"])) / m,
            (lat - view["latitude"]) * 111320 / m)


def show_map(d, select=True, key="map", height=620):
    """지도 + 클릭 선택. 오래된 Streamlit이면 가능한 기능만 사용."""
    tries = ([dict(on_select="rerun", selection_mode="single-object", key=key, height=height),
              dict(on_select="rerun", selection_mode="single-object", key=key)] if select else []) + \
            [dict(height=height), dict()]
    for kw in tries:
        try:
            return st.pydeck_chart(d, **kw)
        except TypeError:
            continue



LABEL_FONTS = ["/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
               "/Library/Fonts/AppleGothic.ttf", "C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf",
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
               "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]


@st.cache_data(show_spinner=False)
def label_shapes(texts, lons, lats, offs, sels, px_h=LABEL_PX, view=None):
    """상권 이름 → (배경 상자, 글자 모양) GeoJSON. 첫 화면(zoom 12)에서 글자 높이 약 px_h 픽셀.
    글꼴의 글자 윤곽(matplotlib TextPath)을 경위도 다각형으로 바꾸고, 구멍(ㅇ·ㅁ 안쪽)은 바깥 윤곽에 묶어 둠."""
    import math
    from matplotlib.font_manager import FontProperties
    from matplotlib.path import Path
    from matplotlib.textpath import TextPath
    font = next((f for f in LABEL_FONTS if os.path.exists(f)), None)
    if font is None:
        return None, None
    fp = FontProperties(fname=font)
    lat0, zoom = view or (VIEW0["latitude"], VIEW0["zoom"])
    mpp = MPP0 * math.cos(math.radians(lat0)) / 2 ** zoom               # 첫 화면 1픽셀 = 몇 m
    em = px_h * mpp / 0.72                                             # 글자 크기(em) → 한글 높이 약 0.72em
    bg_f, tx_f = [], []
    for text, lon, lat, (dx, dy), sel in zip(texts, lons, lats, offs, sels):
        tp = TextPath((0, 0), text, size=1, prop=fp)
        rings = [r for r in tp.to_polygons() if len(r) >= 3]
        if not rings:
            continue
        allp = [p for r in rings for p in r]
        x0, x1 = min(p[0] for p in allp), max(p[0] for p in allp)
        y0, y1 = min(p[1] for p in allp), max(p[1] for p in allp)
        cx_, cy_ = (x0 + x1) / 2, (y0 + y1) / 2
        k = 111320 * math.cos(math.radians(lat))
        ox, oy = dx * mpp, -dy * mpp                                   # off 는 화면 기준(아래 +) → 지도 기준(위 +)

        def ll(x, y):
            return [round(lon + ((x - cx_) * em + ox) / k, 6), round(lat + ((y - cy_) * em + oy) / 111320, 6)]

        # 바깥 윤곽과 구멍 나누기: 넓이 부호가 많은 쪽 = 바깥
        def area(r):
            return sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r))) / 2
        A = [area(r) for r in rings]
        outer_sign = 1 if sum(a > 0 for a in A) >= sum(a < 0 for a in A) else -1
        outers = [i for i, a in enumerate(A) if a * outer_sign > 0]
        polys = {i: [rings[i]] for i in outers}
        for i, a in enumerate(A):
            if a * outer_sign > 0:
                continue
            host = [j for j in outers if Path(rings[j]).contains_point(rings[i][0])]
            if host:
                polys[min(host, key=lambda j: abs(A[j]))].append(rings[i])
        fg = [255, 255, 255, 255] if sel else [25, 28, 32, 255]
        bg = [35, 39, 46, 235] if sel else [255, 255, 255, 220]
        tx_f.append({"type": "Feature", "properties": {"fill": fg},
                     "geometry": {"type": "MultiPolygon",
                                  "coordinates": [[[ll(*p) for p in list(r) + [r[0]]] for r in rs] for rs in polys.values()]}})
        px_, py_ = 0.32, 0.26                                          # 상자 여백 (em)
        bx0, bx1, by0, by1 = x0 - px_, x1 + px_, y0 - py_, y1 + py_
        rr = min(0.3, (by1 - by0) / 2)
        box = []
        for ccx, ccy, a0 in [(bx1 - rr, by0 + rr, -90), (bx1 - rr, by1 - rr, 0), (bx0 + rr, by1 - rr, 90), (bx0 + rr, by0 + rr, 180)]:
            for t in range(0, 91, 15):
                ang = math.radians(a0 + t)
                box.append(ll(ccx + rr * math.cos(ang), ccy + rr * math.sin(ang)))
        box.append(box[0])
        bg_f.append({"type": "Feature", "properties": {"fill": bg}, "geometry": {"type": "Polygon", "coordinates": [box]}})
    return ({"type": "FeatureCollection", "features": bg_f}, {"type": "FeatureCollection", "features": tx_f})


# ================================================================ 기본 정보
NM = dict(zip(prof.code, prof.name))
names = {c: f"{c} {n}" for c, n in NM.items()}
order = list(prof.code)
STN = dict(zip(stations.station_no.astype(int), stations.station_no.astype(str) + " " + stations.get("station_name", "")))
TRAM_DEF = ac.TRAM_DEF
SRC_AREA = "outputs/area_profile.csv"                      # 화면 숫자의 출처 (tram_model/ 아래 결과 파일)
SRC_TRAM = "outputs/tram_scenarios.csv"                    # 수준(낮음·기본·높음). 원 추정은 landprice_effects.csv


def src(*files):
    return "출처: " + ", ".join(files)


def eok(v):
    """억 원 → '4,349억 원' / '1.40조 원'."""
    return f"{v / 1e4:,.2f}조 원" if abs(v) >= 1e4 else f"{v:,.0f}억 원"


def money_of(code, key):
    """상권(또는 ALL)의 정거장 500m 안 땅값 증가액(억 원). 없으면 None."""
    if money is None or code not in set(money.code):
        return None
    v = money.set_index("code").loc[code, f"gain_{key}_eok"]
    return float(v) if pd.notna(v) else None


def tram_range(row, lo="tram_effect_low", hi="tram_effect_high"):
    """낮음~높음 범위 문구. 값이 없으면 빈 문자열."""
    a, b = row.get(lo), row.get(hi)
    return f"낮음 {a:+.1f} ~ 높음 {b:+.1f}%" if pd.notna(a) and pd.notna(b) else ""

# 트램 시나리오 (이름·설명은 결과 파일 tram_scenarios.csv 에서 → 실제 값과 항상 일치)
_ts = read_csv(f"{OUT}/tram_scenarios.csv")
SCEN, SCEN_HELP, _TS = ac.scenarios(_ts, prof.columns)

# 업종 점수 (score_industry.py)
IS = read_csv(f"{OUT}/industry_scores.csv")
ISW = read_csv(f"{OUT}/industry_score_weights.csv")
IND_LIST = ac.ind_list(IS)
W_DEF = ac.default_weights(ISW)
ITEM = ISW.set_index("key").item.to_dict() if ISW is not None else {}
ss.setdefault("ind_w", dict(W_DEF))


def ind_scores(after, w=None):
    """업종 점수 (계산은 ai_comment.score_industries, AI 해설과 같은 식)."""
    return ac.score_industries(IS, w or ss.ind_w, after, globals().get("SCEN_KEY", "base"))


# ================================================================ 커버 화면 (처음 들어오면)
from cover_page import render_cover
from about_page import open_about

_qp = st.query_params if hasattr(st, "query_params") else {}
if "page" not in ss:
    ss.page = "map" if (_qp.get("view") == "map" or _qp.get("area")) else "cover"
if ss.page == "cover":
    _stats = {"rebound": int((prof.quadrant == "트램 반등 기회").sum()) if "quadrant" in prof else "-",
              "base": f"{_TS['base'].effect_pct:+.1f}%" if "base" in _TS else "-",
              "low": f"{_TS['low'].effect_pct:+.1f}%" if "low" in _TS else "-",
              "high": f"{_TS['high'].effect_pct:+.1f}%" if "high" in _TS else "-",
              "n_scores": int(IS.score_before.notna().sum()) if IS is not None else "-"}
    if render_cover(st, stations, route_paths, _stats, lambda: open_about(st)):
        ss.page = "map"
        try:
            st.query_params["view"] = "map"
        except Exception:
            pass
        st.rerun()
    st.stop()

# ================================================================ 사이드바
PAGES = {"map": "지도", "industry": "업종 점수", "compare": "20개 상권 비교"}
if ss.page not in PAGES:
    ss.page = "map"
st.sidebar.title("대전 트램 상권 지도")
st.sidebar.caption(f"{OPEN_YEAR}년 개통 트램 2호선 주변 20개 상권 진단")


def _nav_cb():
    ss.page = {v: k for k, v in PAGES.items()}[ss.nav]


ss.nav = PAGES[ss.page]
st.sidebar.radio("화면", list(PAGES.values()), key="nav", on_change=_nav_cb)
PAGE = ss.page
TRAM_MODES = ["건설 전", "건설 후"]
MAPM = {"quadrant": "진단 (4분류)", "land_fc": f"땅값 전망 (2026→{int(fc.year.max()) if fc is not None else 2034})",
        "tram_sel": "땅값 기준 트램 효과", "land_chg_5y_pct": "땅값 5년 상승률",
        "store_share_chg_5y_pct": "점포 비중 5년 변화"}     # 업종 점수 색칠은 '업종 점수' 화면의 지도에서
MAPM_SHORT = {"quadrant": "진단", "land_fc": "땅값 전망", "tram_sel": "땅값 기준 트램 효과", "land_chg_5y_pct": "땅값 5년",
              "store_share_chg_5y_pct": "점포 비중"}
# 조작 값은 위젯 키(_w)와 따로 저장 → 화면을 옮겨 위젯이 사라져도 값이 남음
if ss.get("mm") not in MAPM:
    ss.mm = "quadrant"
ss.setdefault("tram_saved", "건설 후")
ss.setdefault("scen_saved", list(SCEN)[0])
ss.setdefault("show_region", True)
ss.setdefault("show_label", True)
if ss.scen_saved not in SCEN:
    ss.scen_saved = list(SCEN)[0]


def _keep(saved, widget):                                  # 위젯 값 → 저장 값 (콜백은 스크립트보다 먼저 실행)
    return lambda: ss.update({saved: ss[widget]})


show_about(st)
if st.sidebar.button("처음 화면으로", use_container_width=True, key="to_cover"):
    ss.page = "cover"
    try:
        st.query_params.clear()
    except Exception:
        pass
    st.rerun()

# ================================================================ 조작 줄 (모든 화면 맨 위, 지도 화면은 결론 띠 아래)
top = st.container() if PAGE == "map" else None           # 지도 화면: 결론 띠 자리 (값이 정해진 뒤 채움)
ss.tram_w, ss.mm_w, ss.scen_w = ss.tram_saved, ss.mm, ss.scen_saved
with st.container(horizontal=True, vertical_alignment="bottom", gap="medium", key="ctlbar"):
    st.segmented_control("트램 2호선", TRAM_MODES, key="tram_w", required=True, on_change=_keep("tram_saved", "tram_w"),
                         help="건설 전: 트램이 없을 때의 진단·전망, 노선은 옅은 계획선 / "
                              "건설 후: 땅값 기준 트램 효과를 넣은 진단·전망·업종 점수(트램이 닿는 상권만 오름)")
    if PAGE == "map":
        st.segmented_control("지도에 칠할 것", list(MAPM), key="mm_w", required=True, format_func=MAPM_SHORT.get,
                             on_change=_keep("mm", "mm_w"), help="업종별 점수 지도는 '업종 점수' 화면에 있음")
    with st.popover(f"땅값 기준 트램 효과 {ss.scen_saved}", icon=":material/tune:",
                    help="땅값 기준 트램 효과 시나리오(낮음·기본·높음)" + (" · 지도 표시 설정" if PAGE == "map" else "")):
        st.segmented_control("땅값 기준 트램 효과 시나리오", list(SCEN), key="scen_w", required=True,
                             on_change=_keep("scen_saved", "scen_w"),
                             help=" / ".join(SCEN_HELP) + " · 효과 = 수준 × 업종 비율 × 상권 중 500m 안 비율")
        st.caption(f"땅값 기준 트램 효과 = {TRAM_DEF} · {src(SRC_TRAM, 'outputs/landprice_effects.csv (대전 1호선 원 추정)')}")
        if PAGE == "map":
            st.divider()
            ss.show_region = rg is not None and st.toggle("대전 전체를 상권 권역으로 채우기", value=ss.show_region)
            ss.show_label = st.toggle("상권 이름 표시", value=ss.show_label)
tram_mode = ss.tram_saved
tram_after = tram_mode == "건설 후"
am = ss.mm
scen, show_region, show_label = ss.scen_saved, ss.show_region and rg is not None, ss.show_label
SCEN_KEY = {"tram_effect": "base", "tram_effect_low": "low", "tram_effect_high": "high"}[SCEN[scen]]
prof["tram_sel"] = prof[SCEN[scen]]
# 트램 건설 전/후에 따라 달라지는 값
prof["quadrant_after"] = prof.quadrant
if "quadrant" in prof:                                    # 트램이 없으면 '반등 기회'의 근거(정거장 500m)가 사라짐
    _reb = prof.quadrant == "트램 반등 기회"               # → score_areas.py 분류 규칙을 정거장 없이 다시 적용
    prof["quadrant_before"] = prof.quadrant.where(~_reb, np.select(
        [prof.risk_score >= 50, prof.growth_score >= 50], ["쇠퇴 우려", "성장 지속"], "정체·안정"))
    if not tram_after:
        prof["quadrant"] = prof.quadrant_before
if fc is not None:
    _y = fc.year.max()
    _f = fc[fc.year == _y].set_index("code")
    _tcol = {"base": "tram_base", "low": "tram_low", "high": "tram_high"}[SCEN_KEY]
    prof["land_fc"] = prof.code.map((_f[_tcol] if tram_after else _f.base_path) - 100).round(1)

# ================================================================ 지도 색
LABEL = {"quadrant": f"진단 (트램 {tram_mode})", "land_fc": f"땅값 전망 2026→2034 (%, 트램 {tram_mode})",
         "tram_sel": f"땅값 기준 트램 효과 (%, {scen}, 개통 초기 1~4년)", "land_chg_5y_pct": "땅값 5년 상승률 (%)",
         "store_share_chg_5y_pct": "대전 내 점포 비중 5년 변화 (%)",
         "risk_score": "상대 쇠퇴 위험", "growth_score": "상대 성장 가능"}
HELP = {"quadrant": "상대 쇠퇴 위험 50점 이상 + 상권 점포 절반 이상이 정거장 500m 안 → 트램 반등 기회, 500m 밖 → 쇠퇴 우려 / "
                    "위험 50 미만은 성장 점수로 성장 지속·정체·안정. 15가지 변형에서 80% 미만으로 같으면 '불확실'",
        "tram_sel": TRAM_DEF,
        "land_chg_5y_pct": "2021→2026 같은 필지 공시지가 변화의 중앙값",
        "store_share_chg_5y_pct": "대전 전체 점포 중 이 상권 몫이 5년간 늘었는지(+) 줄었는지(-)",
        "risk_score": "땅값 상대 하락·점포 비중 감소·폐업률을 20개 상권 안 순위로 합친 점수 (언제나 약 절반이 50 이상)",
        "growth_score": "땅값 기준 트램 효과·개업률·최근 점포 비중을 20개 상권 안 순위로 합친 점수",
        "close_rate_q_pct": "최근 3년 분기마다 문 닫은 점포 비율의 평균"}
if am.startswith("ind:") and IS is not None:
    ind_now = am[4:]
    _cur, _ = ind_scores(tram_after)
    prof["map_val"] = prof.code.map(_cur[_cur.industry == ind_now].set_index("code").score)
    LABEL["map_val"] = f"{ind_now} 점수 (100점, 트램 {tram_mode})"
    col_key, kind = "map_val", "seq_good"
else:
    ind_now = None
    col_key = am
    kind = {"quadrant": "cat", "land_fc": "div0", "tram_sel": "seq_tram", "land_chg_5y_pct": "divavg",
            "store_share_chg_5y_pct": "div0"}[am]
info = prof.set_index("code")

if kind == "cat":
    colors = {c: QC.get(q, [200, 200, 200]) + [190] for c, q in zip(prof.code, prof.quadrant)}
    legend = legend_cat(LABEL["quadrant"], [(k, v) for k, v in QC.items() if tram_after or k != "트램 반등 기회"])
elif am == "tram_sel" and not tram_after:                 # 건설 전에는 트램 효과가 없음
    colors = {c: [215, 218, 222, 170] for c in prof.code}
    legend = '<div class="lg"><b>땅값 기준 트램 효과</b>&nbsp;건설 전에는 효과 없음 (위에서 건설 후를 고르면 상권별 예상 효과)</div>'
else:
    cen = None
    if kind == "divavg":                                   # 대전 전체 5년 상승률을 기준(흰색)으로
        if lp is not None:
            a_ = lp[lp.code == "ALL"].set_index("year").idx
            cen = float((a_.iloc[-1] / a_.loc[a_.index.max() - 5] - 1) * 100)
        else:
            cen = float(prof[col_key].median())
    span = None
    if col_key == "land_fc" and fc is not None:          # 건설 전·후 같은 색 눈금 → 색 차이 = 트램 효과
        _ff = fc[fc.year == fc.year.max()]
        span = float(pd.concat([_ff.base_path, _ff[_tcol]]).sub(100).abs().quantile(.95))
    cl, (stops, lo, hi) = colorize(prof[col_key], kind, cen, span)
    colors = dict(zip(prof.code, cl))
    legend = legend_bar(LABEL[col_key], stops, lo, hi, kind, cen)

# ================================================================ 선택 상태
qp = st.query_params if hasattr(st, "query_params") else {}
if "inited" not in ss:
    ss.inited = True
    a = qp.get("area")
    _reb0 = prof[prof.quadrant_after == "트램 반등 기회"].sort_values("risk_score", ascending=False).code \
        if "quadrant_after" in prof else pd.Series(dtype=str)
    ss.sel_area = a if a in order else (_reb0.iloc[0] if len(_reb0) else order[0])
    s = qp.get("station")
    ss.sel_station = int(s) if s and str(s).isdigit() and int(s) in STN else None
    ss.ai = {}
for _mk in ("map", "map_ind"):                            # 지도 페이지·업종 점수 페이지 지도 클릭
    _m = ss.get(_mk)
    sel_obj = (_m or {}).get("selection", {}) if isinstance(_m, dict) else (getattr(_m, "selection", None) or {})
    objs = sel_obj.get("objects", {}) if sel_obj else {}
    _hit = objs.get("core") or objs.get("areas")               # 핵심 영역·권역 어느 쪽을 눌러도 같은 상권
    click_area = (_hit or [{}])[0].get("properties", {}).get("code") if _hit else None
    click_stn = (objs.get("stations") or [{}])[0].get("station_no") if objs.get("stations") else None
    if click_area and click_area != ss.get(f"_last_area_{_mk}"):
        ss[f"_last_area_{_mk}"] = click_area; ss.sel_area = click_area
    if click_stn is not None and click_stn != ss.get("_last_stn"):
        ss._last_stn = click_stn; ss.sel_station = int(click_stn)
sel = ss.sel_area

# 트램 노선·정거장 (지도 두 곳에서 같이 씀)
route = [{"path": p} for p in route_paths(stations)]
_rc, _rw = (ROUTE_C + [255], 3) if tram_after else ([140, 146, 154, 200], 2)     # 건설 전 = 옅은 계획선
lay_route = [pdk.Layer("PathLayer", route, id="route_case", get_path="path", get_color=[255, 255, 255, 235],
                       width_min_pixels=_rw + 3, cap_rounded=True, joint_rounded=True),
             pdk.Layer("PathLayer", route, id="route", get_path="path", get_color=_rc,
                       width_min_pixels=_rw, cap_rounded=True, joint_rounded=True)]
stop_df = stations.merge(st_sum[["station_no", "n_stores"]], on="station_no", how="left") if st_sum is not None \
    else stations.assign(n_stores=None)
stop_df = stop_df.assign(name=stop_df.station_no.astype(str) + "번 " + stop_df.get("station_name", ""), type="트램 정거장",
                         qcolor="#23272e",
                         val_label="500m 안 점포 " + stop_df.n_stores.fillna(0).astype(int).astype(str) + "개 · 클릭하면 영향권 표시")
lay_stop = pdk.Layer("ScatterplotLayer", stop_df, id="stations", get_position=["lon", "lat"], get_radius=55,
                     radius_min_pixels=4.5, radius_max_pixels=9, get_fill_color=[255, 255, 255, 255],
                     get_line_color=_rc, stroked=True, line_width_min_pixels=1.8 if tram_after else 1.2, pickable=True,
                     auto_highlight=True, highlight_color=[35, 39, 46, 255])

def land_chart(code):
    t = lp[lp.code.isin([code, "ALL"])].copy()
    t["상권"] = t.code.map(lambda c: "대전 전체" if c == "ALL" else NM.get(c, c))
    dom = [NM[code], "대전 전체"]
    ch = alt.Chart(t).mark_line(strokeWidth=2.5).encode(
        x=alt.X("year:Q", title=None, axis=alt.Axis(format="d")),
        y=alt.Y("idx:Q", title="지수 (2015=100)", scale=alt.Scale(zero=False)),
        color=alt.Color("상권:N", scale=alt.Scale(domain=dom, range=["#1f4fa3", "#9aa0a6"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["상권", "year", alt.Tooltip("idx:Q", format=".1f")])
    if events is not None:
        ev = events[events.area_codes.fillna("").str.contains(code)].copy()
        if len(ev):
            ev["year"] = pd.to_datetime(ev.date).dt.year + pd.to_datetime(ev.date).dt.month / 12
            ch = ch + alt.Chart(ev).mark_rule(color="#888", strokeDash=[3, 3]).encode(x="year:Q", tooltip=["date", "description"])
    return ch.properties(height=280)


def store_chart(code):
    s = sp[sp.code == code].copy()
    s["date"] = pd.to_datetime(s.period, format="%Y%m")
    br = pd.DataFrame({"date": pd.to_datetime(BREAKS), "설명": "수집 기준 변경 (급변은 자료 탓일 수 있음)"})
    line = alt.Chart(s).mark_line(strokeWidth=2.5, color="#1f4fa3", point=alt.OverlayMarkDef(size=18)).encode(
        x=alt.X("date:T", title=None), y=alt.Y("n_stores:Q", title="점포 수", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("date:T", format="%Y-%m"), "n_stores"])
    rule = alt.Chart(br).mark_rule(color="#6b7860", strokeDash=[4, 3]).encode(x="date:T", tooltip=["설명"])
    return (line + rule).properties(height=280)


def forecast_chart(code, with_tram):
    f = fc[fc.code == code].set_index("year")
    h = lp[lp.code == code].set_index("year").idx
    b = h.iloc[-1] / 100
    band = pd.DataFrame({"year": f.index, "lo": f.lo80 * b, "hi": f.hi80 * b})
    parts = [pd.DataFrame({"year": h.loc[2015:].index, "v": h.loc[2015:].values, "구분": "실제"}),
             pd.DataFrame({"year": f.index, "v": f.base_path.values * b, "구분": "예측 (트램 없음)"})]
    dom, rng, dash = ["실제", "예측 (트램 없음)"], ["#222222", "#9aa0a6"], [[1, 0], [5, 4]]
    if with_tram:
        parts.append(pd.DataFrame({"year": f.index, "v": f.tram_base.values * b, "구분": "예측 (트램 건설 후)"}))
        dom, rng, dash = dom + ["예측 (트램 건설 후)"], rng + [TRAM_INK], dash + [[1, 0]]
    ln = pd.concat(parts)
    a_ = alt.Chart(band).mark_area(opacity=.22, color="#9aa0a6").encode(
        x=alt.X("year:Q", axis=alt.Axis(format="d"), title=None),
        y=alt.Y("lo:Q", title="지수 (2015=100)", scale=alt.Scale(zero=False)), y2="hi:Q")
    l_ = alt.Chart(ln).mark_line(strokeWidth=2.5).encode(
        x="year:Q", y="v:Q", color=alt.Color("구분:N", scale=alt.Scale(domain=dom, range=rng),
                                             legend=alt.Legend(orient="top", title=None)),
        strokeDash=alt.StrokeDash("구분:N", scale=alt.Scale(domain=dom, range=dash), legend=None),
        tooltip=["구분", "year", alt.Tooltip("v:Q", format=".1f")])
    op = alt.Chart(pd.DataFrame({"year": [OPEN_YEAR], "t": ["트램 개통"]}))
    return (a_ + l_ + op.mark_rule(color="#23272e", strokeDash=[2, 2]).encode(x="year:Q")
            + op.mark_text(align="left", dx=4, color="#23272e").encode(x="year:Q", y=alt.value(10), text="t")).properties(height=280)


# ================================================================ 페이지 1: 지도 (상권 상세)
if PAGE == "map":
    REB = (prof[prof.quadrant_after == "트램 반등 기회"].sort_values("risk_score", ascending=False).code.tolist()
           if "quadrant_after" in prof else [])
    short = lambda c: NM[c].split("(")[0]

    def _pick(widget):                                    # 칩·선택 상자 → 선택 상권 (지도 클릭과 같은 값)
        def cb():
            if ss.get(widget):
                ss.sel_area = ss[widget]
        return cb

    def _pick_stn():
        ss.sel_station = ss.stn_w or None
        ss._last_stn = ss.sel_station

    # ================================================================ ① 결론 띠 (조작 줄보다 위)
    with top:
        if REB:
            n_ = len(REB)
            if tram_after:
                head = f"트램이 지나면 반등을 기대할 수 있는 상권 {n_}곳"
            else:                                          # 문구는 데이터에서: 이 상권들의 '건설 전' 진단을 그대로 셈
                bq = prof.set_index("code").loc[REB, "quadrant_before"].value_counts()
                head = (f"트램이 없으면 이 {n_}곳은 모두 {bq.index[0]}" if len(bq) == 1 else
                        f"트램이 없으면 이 {n_}곳은 " + ", ".join(f"{k} {v}곳" for k, v in bq.items()))
            st.markdown(f'<div class="verdict">{head}</div>', unsafe_allow_html=True)
            ss.chip_w = sel if sel in REB else None
            st.pills("트램 반등 기회 상권", REB, key="chip_w", format_func=short, on_change=_pick("chip_w"),
                     label_visibility="collapsed")
        if "quadrant" in prof:
            cnt = prof.quadrant.value_counts()
            st.markdown('<div class="kpi">' + "".join(
                f'<span><span class="dot" style="background:{QHEX[q]}"></span>{q} <b>{cnt.get(q, 0)}</b>곳</span>'
                for q in QC if cnt.get(q, 0))
                + (f'<span class="sep">땅값 기준 트램 효과({scen}) 상권 평균 <b>{prof.tram_sel.mean():+.1f}%</b> '
                     f'({tram_range(prof[["tram_effect_low", "tram_effect_high"]].mean())})</span>'
                   if tram_after else "")
                + (f'<span class="sep">정거장 500m 안 땅값 <b>+{eok(money_of("ALL", SCEN_KEY))}</b> '
                   f'(공시지가 기준, 개통 1~4년)</span>' if tram_after and money_of("ALL", SCEN_KEY) else "")
                + '</div>', unsafe_allow_html=True)
            st.caption(src(f"{SRC_AREA} (진단·상권 값)", f"{SRC_TRAM} (트램 효과 수준)"))

    # ================================================================ ③ 지도 | 선택 상권
    left, right = st.columns([3, 2], gap="medium")
    with left:
        for f in gj["features"] + (rg["features"] if rg else []):
            c = f["properties"]["code"]
            r = info.loc[c]
            val = r[col_key]
            val = "-" if pd.isna(val) else (val if isinstance(val, str) else f"{float(val):,.1f}")
            near = f"가까운 트램 {int(r.nearest_tram)}번 정거장 · {int(r.nearest_tram_m)}m" if pd.notna(r.get("nearest_tram")) else ""
            q = r.quadrant if "quadrant" in r and pd.notna(r.quadrant) else ""
            f["properties"].update({"fill": colors[c][:3] + [REG_A], "fill_core": colors[c][:3] + [CORE_A],
                                    "name": r["name"], "type": q, "qcolor": QHEX.get(q, "#999"),
                                    "val_label": f"{LABEL[col_key]} <b>{val}</b><br/><span style='color:#777'>{near}</span>"})
        fill_src = rg if show_region else gj
        HL = dict(auto_highlight=True, highlight_color=[255, 255, 255, 90])
        layers = []
        if show_region:
            layers.append(pdk.Layer("GeoJsonLayer", rg, id="areas", pickable=True, stroked=True, filled=True,
                                    get_fill_color="properties.fill", get_line_color=[255, 255, 255, 255],
                                    line_width_min_pixels=1.2, **HL))
        layers.append(pdk.Layer("GeoJsonLayer", gj, id="core", pickable=True, stroked=True, filled=True,
                                get_fill_color="properties.fill_core", get_line_color=[255, 255, 255, 255],
                                line_width_min_pixels=1, **HL))
        sel_gj = {"type": "FeatureCollection", "features": [f for f in fill_src["features"] if f["properties"]["code"] == sel]}
        layers += [pdk.Layer("GeoJsonLayer", sel_gj, id="sel_halo", pickable=False, stroked=True, filled=False,
                             get_line_color=[255, 255, 255, 255], line_width_min_pixels=8),
                   pdk.Layer("GeoJsonLayer", sel_gj, id="sel_area", pickable=False, stroked=True, filled=False,
                             get_line_color=ROUTE_C + [255], line_width_min_pixels=3.5)]
        layers += lay_route
        if ss.sel_station is not None:
            srow = stations[stations.station_no == ss.sel_station]
            layers.append(pdk.Layer("ScatterplotLayer", srow, id="buffer", get_position=["lon", "lat"], get_radius=500,
                                    filled=True, get_fill_color=ROUTE_C + [28], stroked=True,
                                    get_line_color=ROUTE_C + [240], line_width_min_pixels=2.5, pickable=False))
        layers.append(lay_stop)
        if ss.sel_station is not None:
            layers.append(pdk.Layer("ScatterplotLayer", srow, id="sel_stop", get_position=["lon", "lat"], get_radius=90,
                                    radius_min_pixels=7, get_fill_color=ROUTE_C + [255], get_line_color=[255, 255, 255, 255],
                                    stroked=True, line_width_min_pixels=2, pickable=False))
        if show_label:                                        # 상권 이름: 점포 많은 순, 겹치면 위·아래·옆으로, 자리 없으면 생략
            cen_xy = {}
            for f in gj["features"]:
                g = f["geometry"]
                ring = g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len)
                cen_xy[f["properties"]["code"]] = (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
            pri = prof.assign(p=prof.n_stores.fillna(0) + 1e6 * prof.code.isin(REB)    # 선택 > 반등 기회 > 점포 많은 순
                              + 1e9 * (prof.code == sel)).sort_values("p", ascending=False).code
            boxes, lab = [], []
            for c in pri:
                if c not in cen_xy:
                    continue
                t = NM[c].split("(")[0]
                x, y = px(*cen_xy[c], view=VIEW_MAP)
                em = LABEL_PX / 0.72                       # 한글 높이 약 0.72em, 한 글자 폭 약 1em
                w, h = len(t) * em + 0.64 * em + 4, 1.24 * em + 3   # 이름 상자 (글자 + 여백) 픽셀 크기
                for dx, dy in [(0, 0), (0, h), (0, -h), (w / 2 + 6, 0), (-w / 2 - 6, 0), (w / 2 + 6, h), (-w / 2 - 6, h),
                               (w / 2 + 6, -h), (-w / 2 - 6, -h), (0, 1.9 * h), (0, -1.9 * h)]:
                    bx = (x + dx - w / 2, y + dy - h / 2, x + dx + w / 2, y + dy + h / 2)
                    inside = -MAP_W / 2 + 6 < bx[0] and bx[2] < MAP_W / 2 - 6 and -MAP_H / 2 + 6 < bx[1] and bx[3] < MAP_H / 2 - 26
                    if inside and (c == sel or not any(not (bx[2] < o[0] or bx[0] > o[2] or bx[3] < o[1] or bx[1] > o[3])
                                                       for o in boxes)):
                        break                              # 지도 틀 안(아래는 지도 출처 표기 자리 비움)이고 안 겹치는 첫 자리
                else:
                    continue
                boxes.append(bx)
                lab.append({"text": t, "lon": cen_xy[c][0], "lat": cen_xy[c][1], "sel": c == sel, "off": [dx, -dy]})
            lab = pd.DataFrame(lab)
            # 상권 이름: 이 Streamlit 의 지도에서는 글자(TextLayer)·그림(IconLayer) 층이 그려지지 않음 →
            # 글자 모양을 다각형으로 바꿔 GeoJsonLayer 로 그림 (확대하면 글자도 함께 커짐)
            lab_bg, lab_txt = label_shapes(tuple(lab.text), tuple(lab.lon), tuple(lab.lat),
                                           tuple(map(tuple, lab.off)), tuple(lab.sel),
                                           view=(VIEW_MAP["latitude"], VIEW_MAP["zoom"])) if len(lab) else (None, None)
            if lab_bg:
                layers.append(pdk.Layer("GeoJsonLayer", lab_bg, id="label_bg", filled=True, stroked=False, pickable=False,
                                        get_fill_color="properties.fill"))
                layers.append(pdk.Layer("GeoJsonLayer", lab_txt, id="label_txt", filled=True, stroked=False, pickable=False,
                                        get_fill_color="properties.fill"))

        st.markdown(f'<div class="maphead">{legend}<div class="sym">'
                    + (f'<span class="ln"></span>트램 2호선' if tram_after else
                       '<span class="ln" style="background:#8c929a;height:2px"></span>트램 2호선(계획)')
                    + f'<span class="st"></span>정거장'
                    f'<span class="sq strong"></span>상권 핵심(점포 밀집)'
                    + ('<span class="sq weak"></span>영향 권역' if show_region else "")
                    + '</div></div>', unsafe_allow_html=True)
        show_map(deck(layers, {"html": "<div style='font-weight:700;font-size:14px'>{name}</div>"
                                       "<div><span style='color:{qcolor}'>●</span> {type}</div>{val_label}"},
                      view=pdk.ViewState(**VIEW_MAP, min_zoom=10, max_zoom=16)), height=MAP_H)
        stn_opts = [0] + list(STN)                         # 0 = 선택 안 함 (None 이면 빈 칸으로 보여서)
        ss.stn_w = ss.sel_station if ss.sel_station in STN else 0
        c_cap, c_stn = st.columns([3, 2], vertical_alignment="center")
        c_cap.caption("상권을 누르면 오른쪽에 진단이, 정거장 점을 누르면 아래에 500m 영향권이 나옵니다  \n"
                      + src("outputs/forecast_land.csv" if am == "land_fc" else SRC_AREA,
                            "outputs/sangkwon_polygons.geojson (상권 경계)"))
        c_stn.selectbox("정거장 선택", stn_opts, key="stn_w", on_change=_pick_stn,
                        format_func=lambda v: STN[v] if v else "정거장 고르기", label_visibility="collapsed")

        if ss.sel_station is not None and st_sum is not None and ss.sel_station in set(st_sum.station_no):
            t = st_sum.set_index("station_no").loc[ss.sel_station]
            with st.container(border=True, key="stnpanel"):
                s1, s2 = st.columns([6, 1], vertical_alignment="center")
                s1.markdown(f'<div class="stn-t">{ss.sel_station}번 {t.station_name} 정거장 · 500m 영향권</div>',
                            unsafe_allow_html=True)
                if s2.button("닫기", key="stn_close", icon=":material/close:", type="tertiary"):
                    ss.sel_station = None; ss._last_stn = None; st.rerun()
                k1, k2 = st.columns(2)                     # 지도 칸이 좁아 4칸이면 숫자가 잘림 → 2×2
                k3, k4 = st.columns(2)
                k1.metric("점포 수 (2026-06)", f"{int(t.n_stores):,}")
                k2.metric("음식 / 소매", f"{t.food_pct:.0f}% / {t.retail_pct:.0f}%", f"체인점 {t.branch_pct:.0f}%",
                          delta_color="off", delta_arrow="off")
                k3.metric("공시지가 중앙값", f"{t.land_price / 1e4:,.0f}만원/㎡" if pd.notna(t.get("land_price")) else "-",
                          f"5년 {t.land_growth_5y_pct:+.1f}%" if pd.notna(t.get("land_growth_5y_pct")) else None,
                          delta_color="off", delta_arrow="off")
                te = t.get(f"tram_effect_{SCEN_KEY}")
                k4.metric("땅값 기준 트램 효과", ("없음 (건설 전)" if not tram_after else f"{te:+.1f}%") if pd.notna(te)
                          else "분석 상권 밖", tram_range(t, "tram_effect_low", "tram_effect_high") or None,
                          delta_color="off", delta_arrow="off", help=TRAM_DEF)
                a = st_areas[st_areas.station_no == ss.sel_station] if st_areas is not None else pd.DataFrame()
                if len(a):
                    cols = {"code": "코드", "name": "영향권에 걸친 상권", "stores_in_500m": "영향권 안 점포",
                            "share_of_area_pct": "상권 점포 중 비율(%)", "quadrant": "진단"}
                    a = a.assign(quadrant=a.code.map(info.quadrant))   # 진단은 지금 고른 건설 전/후 기준
                    tb = a[[c for c in cols if c in a.columns]].rename(columns=cols).round(1).reset_index(drop=True)
                    ev = st.dataframe(tb, hide_index=True, on_select="rerun", selection_mode="single-row", key="stn_tbl")
                    rows = ev.selection.rows if ev is not None else []
                    if rows and tb["코드"].iloc[rows[0]] != sel:
                        ss.sel_area = tb["코드"].iloc[rows[0]]; ss._last_area_map = ss.sel_area
                        st.rerun()
                else:
                    st.caption(f"이 정거장 500m 안에는 20개 분석 상권이 없습니다 · 주요 업종: {t.top3_mid}")
                st.caption(src("outputs/station_summary.csv", "outputs/station_areas.csv"))

    r = info.loc[sel]                                      # (지도 레이어 반복문이 r 을 덮어쓰므로 여기서 다시)
    with right, st.container(border=True, key="areapanel"):
        ss.area_w = sel
        st.selectbox("상권 선택", order, key="area_w", format_func=names.get, on_change=_pick("area_w"))
        q = r.get("quadrant")
        st.markdown(f'<div class="area-h"><span class="code">{sel}</span><span class="t">{r["name"]}</span></div>'
                    '<div class="area-b">'
                    + (f'<span class="badge" style="background:{QHEX.get(q, "#999")};color:{QTXT.get(q, "#fff")}">{q}</span>' if pd.notna(q) else "")
                    + (f'<span class="badge" style="background:#fff;color:{QHEX['쇠퇴 우려']};border:1px solid {QHEX['쇠퇴 우려']}">불확실 '
                       f'{r.quadrant_stability * 100:.0f}%</span>' if bool(r.get("quadrant_uncertain", False)) else "")
                    + (f'<span class="badge gray">{r.type_name}</span>' if pd.notna(r.get("type_name")) else "")
                    + f'<span class="where">{r.gu} · {r.type}</span></div>', unsafe_allow_html=True)

        # 진단 근거 상자: 규칙 한 줄 → 숫자 근거 → 안정도
        if pd.notna(r.get("risk_score")):
            rs, gs, i5 = r.risk_score, r.growth_score, r.get("in500")
            i5t = f"{i5 * 100:.0f}%" if pd.notna(i5) else "-"
            if q == "트램 반등 기회":
                rule = f"위험 50점 이상, 점포 {i5t}가 정거장 500m 안(절반 이상)이라 트램 반등 기회"
            elif q == "쇠퇴 우려":
                rule = (f"위험 50점 이상, 트램이 없으면 정거장 500m 기준이 사라져 쇠퇴 우려"
                        if r.get("quadrant_after") == "트램 반등 기회" else
                        f"위험 50점 이상, 정거장 500m 안 점포 {i5t}(절반 미만)라 쇠퇴 우려")
            elif q == "성장 지속":
                rule = "위험 50점 미만, 성장 50점 이상이라 성장 지속"
            else:
                rule = "위험·성장 모두 50점 미만이라 정체·안정"
            rows_ = [("상대 쇠퇴 위험", f"{rs:.0f}점", r.risk_drivers),
                     ("상대 성장 가능", f"{gs:.0f}점", r.growth_drivers)]
            if pd.notna(r.get("nearest_tram")):
                rows_.append(("가까운 정거장", f"{int(r.nearest_tram_m)}m",
                              f"{int(r.nearest_tram)}번 정거장 · 상권 점포의 {i5t}가 500m 안"))
            stab = r.get("quadrant_stability")
            foot = ""
            if pd.notna(stab):
                alt_q = r.get("quadrant_alt") if isinstance(r.get("quadrant_alt"), str) and r.get("quadrant_alt") else ""
                foot = f"진단 안정도 {stab * 100:.0f}% (15가지 계산 변형 중 같은 진단 비율)" + (
                    f", 바뀔 때는 '{alt_q}'" if alt_q and stab < 1 else "")
            st.markdown('<div class="why"><div class="why-h">진단 근거</div>'
                        f'<div class="why-rule">{rule}</div>'
                        + "".join(f'<div class="why-r"><span class="l">{l}</span><b>{v}</b><span class="d">{d}</span></div>'
                                  for l, v, d in rows_)
                        + (f'<div class="why-f">{foot}</div>' if foot else "") + '</div>', unsafe_allow_html=True)

        m1, m2 = st.columns(2)
        m3, m4 = st.columns(2)
        m1.metric("점포 수 (2026-06)", f"{int(r.n_stores):,}" if pd.notna(r.n_stores) else "-",
                  f"비중 5년 {r.store_share_chg_5y_pct:+.1f}%" if pd.notna(r.get("store_share_chg_5y_pct")) else None,
                  delta_color="off", delta_arrow="off", help=HELP["store_share_chg_5y_pct"])
        m2.metric("땅값 5년 상승률", f"{r.land_chg_5y_pct:+.1f}%" if pd.notna(r.get("land_chg_5y_pct")) else "-",
                  f"대전 평균 대비 {r.land_rel_idx:.0f}" if pd.notna(r.get("land_rel_idx")) else None,
                  delta_color="off", delta_arrow="off", help=HELP["land_chg_5y_pct"])
        m3.metric("분기 폐업률", f"{r.close_rate_q_pct:.1f}%" if pd.notna(r.get("close_rate_q_pct")) else "-",
                  help=HELP["close_rate_q_pct"])
        _mv = money_of(sel, SCEN_KEY)
        m4.metric("땅값 기준 트램 효과", f"{r.tram_sel:+.1f}%" if tram_after else "없음",
                  ((f"500m 안 땅값 +{eok(_mv)} · " if _mv else "") + tram_range(r)) if tram_after
                  else f"건설 후 {r.tram_sel:+.1f}% ({scen})" + (f" · +{eok(_mv)}" if _mv else ""),
                  delta_color="off", delta_arrow="off",
                  help=TRAM_DEF + f" · 지금 시나리오: {scen}"
                       + (" · 금액 = 이 상권 안 정거장 500m 필지의 2026 공시지가 총액 × 효과 % (공공 시설 땅 제외, 시세로는 더 큼)"
                          if _mv else ""))
        notes = [f"주요 업종: {r.top3_mid}"]
        if pd.notna(r.get("bad_pct")):
            notes.append(f"2021 실태조사({r.survey_dong}): 매출·이익 감소 {r.decline_pct:.0f}%, "
                         f"폐업·전환 고려 {r.closing_pct:.0f}% (대전 평균 74% / 7%, 코로나 시기)")
        if sel == "A12":
            notes.append("도룡동 점포 수 급증은 2021년 대전신세계 입점 매장이 등록된 영향")
        st.caption(" · ".join(notes))
        st.caption(src(f"{SRC_AREA} (진단 근거·지표)", f"{SRC_TRAM} (트램 효과 수준)"))

    try:                                                   # 공유 링크: 지금 선택이 주소창에 남음
        st.query_params["area"] = sel
        if ss.sel_station is not None:
            st.query_params["station"] = str(ss.sel_station)
        elif "station" in st.query_params:
            del st.query_params["station"]
    except Exception:
        pass

    # ================================================================ ④ 상세 탭 (이름 고정 → 다시 그려도 보던 탭 유지)
    t_fc, t_land, t_store, t_ai = st.tabs(["땅값 예측", "땅값 흐름", "점포 수", "AI 해설"], key="detail_tab")
    with t_fc:
        if fc is not None and lp is not None and sel in set(fc.code):
            st.caption("회색 띠 = 트램 없는 예측의 80% 범위(넓으므로 상권끼리 비교용) · 남색 선 = 트램 건설 후 · "
                       + ("땅값 기준 트램 효과는 대전 1호선처럼 개통 1~4년에 가장 크고 이후 줄어듦" if tram_after
                          else "위에서 '건설 후'를 고르면 땅값 기준 트램 효과 경로가 함께 나옴"))
            st.altair_chart(forecast_chart(sel, tram_after))
            st.caption(src("outputs/forecast_land.csv", "outputs/landprice_area_panel.csv (실제 값)"))
        else:
            st.info("이 상권의 땅값 예측 결과가 없습니다.")
    with t_land:
        if lp is not None:
            st.caption("대전 전체와 비교 · 회색 점선 = 이 상권의 주요 사건(마우스를 올리면 내용)")
            st.altair_chart(land_chart(sel))
            st.caption(src("outputs/landprice_area_panel.csv", "data/area_events.csv (사건)"))
        else:
            st.info("땅값 흐름 결과 파일이 없습니다.")
    with t_store:
        if sp is not None:
            st.caption("회색 점선 = 자료 수집 기준이 바뀐 분기 (그때의 급변은 자료 탓일 수 있음)")
            st.altair_chart(store_chart(sel))
            st.caption(src("outputs/store_panel.csv"))
        else:
            st.info("점포 수 결과 파일이 없습니다.")

    def area_context(code):
        """AI 해설용 상권 정보 묶음 (지금 화면의 시나리오·업종 가중치 기준)."""
        return ac.area_context(code, info, fc, IS, ss.ind_w, ind_area, events, st_areas, SCEN_KEY)

    @st.cache_data(show_spinner=False)
    def ai_area(ctx_text, scen_text, nonce=0):
        return ac.generate(ac.build_prompt(ctx_text, scen_text, SCEN_HELP),
                           setting("GEMINI_API_KEY"), setting("GEMINI_MODEL", ac.DEFAULT_MODEL))

    def ai_error_box(err):
        with st.expander("오류 내용 보기 (발표자용)"):
            st.code(err, language=None)

    @st.fragment
    def ai_panel():                                        # 해설 버튼은 이 부분만 다시 그림 (지도는 그대로)
        key = (sel, scen)
        ss.setdefault("ai", {})
        res = ss.ai.get(key)
        saved = ac.saved_entry(load_ai_saved(ac.SAVED_PATH.stat().st_mtime if ac.SAVED_PATH.exists() else 0), sel)
        if st.button("AI 해설 다시 받기" if res else "AI 해설 받기", key="ai_btn"):
            n = ss.get("_ai_n", 0) + (1 if res else 0)
            with st.spinner("AI가 해설을 쓰는 중입니다. 10초쯤 걸립니다."):
                try:
                    res = {"src": "live", "text": ai_area(ac.context_text(area_context(sel)), scen, n)}
                    ss._ai_n = n
                except Exception as e:
                    k_ = setting("GEMINI_API_KEY")
                    err = f"{type(e).__name__}: {e}"
                    err = err.replace(k_, "****") if k_ else err          # 오류 원문에 키가 섞여도 화면에 나오지 않게
                    why = "API 키가 설정되어 있지 않습니다." if isinstance(e, ac.NoApiKey) else "인터넷 연결이나 AI 서비스에 문제가 있습니다."
                    if res and res["src"] == "live":                       # 앞서 받은 실시간 해설은 그대로 둠
                        res = {**res, "err": err, "why": why}
                    else:
                        res = {"src": "saved" if saved else "none", "err": err, "why": why}
            ss.ai[key] = res

        if res and res["src"] == "live":
            if res.get("err"):
                st.caption(f"새 해설을 받지 못해 앞서 받은 해설을 그대로 보여 드립니다. {res['why']}")
            st.markdown(res["text"])
            if res.get("err"):
                ai_error_box(res["err"])
            with st.expander("AI에게 보낸 정보 보기"):
                st.json(area_context(sel))
        elif res and res["src"] == "saved" and saved:
            st.markdown(f'<span class="ai-saved">미리 만들어 둔 해설({saved["generated_at"][:10]})</span>',
                        unsafe_allow_html=True)
            st.caption(f"지금은 AI 해설을 실시간으로 불러올 수 없어 미리 만들어 둔 해설을 보여 드립니다. {res['why']}"
                       + (f" 이 해설은 '{saved['scenario']}' 시나리오와 기본 업종 가중치를 기준으로 만들었습니다."
                          if saved["scenario"] else ""))
            st.markdown(saved["text"])
            ai_error_box(res["err"])
            with st.expander("이 해설을 만들 때 쓴 정보 보기"):
                st.json(ac.area_context(sel, info, fc, IS, W_DEF, ind_area, events, st_areas, "base"))
        elif res:
            st.warning(f"지금은 AI 해설을 불러올 수 없습니다. {res['why']} 잠시 뒤 'AI 해설 다시 받기'를 눌러 주세요.")
            st.caption("미리 만들어 둔 해설도 없습니다. 발표 전에 python tram_model/make_ai_comments.py 를 실행해 두세요.")
            ai_error_box(res["err"])
        else:
            st.caption("진단·예측·땅값 기준 트램 효과·업종 점수를 근거로 해설을 만듭니다. 받은 해설은 다른 상권을 보고 와도 남아 있습니다."
                       + (" 실시간 호출이 안 되면 미리 만들어 둔 해설을 보여 드립니다." if saved else ""))

    with t_ai:
        ai_panel()

# ================================================================ 페이지 2: 업종 점수
elif PAGE == "industry":
    if IS is None:
        st.info("업종 점수 결과가 없습니다. python tram_model/run_all.py --from score_industry 를 실행하세요.")
    else:
        cur = ss.get("ind_last", IND_LIST[0])
        if cur not in IND_LIST:
            cur = IND_LIST[0]

        def _ind_cb():                                 # 업종 선택은 이 화면 안에서만 (지도 화면 색칠은 그대로)
            ss.ind_last = ss.ind_panel

        ss.ind_panel = cur
        st.markdown('<h1 class="page-t">업종 점수</h1>', unsafe_allow_html=True)
        st.radio("업종", IND_LIST, key="ind_panel", horizontal=True, on_change=_ind_cb, label_visibility="collapsed")
        B, wb = ind_scores(False)
        A, wa = ind_scores(True)

        # 업종 점수 지도 (색칠만, 이름표 없음) — 누르면 그 상권의 점수 근거가 아래에
        _sc = (A if tram_after else B)
        _sc = _sc[_sc.industry == cur].set_index("code").score
        _cl, (_stops, _lo, _hi) = colorize(prof.code.map(_sc), "seq_good")
        _col = dict(zip(prof.code, _cl))
        _src = rg if rg is not None else gj
        _fc = {"type": "FeatureCollection", "features": []}
        for f in _src["features"]:
            c_ = f["properties"]["code"]
            v_ = _sc.get(c_)
            _fc["features"].append({"type": "Feature", "geometry": f["geometry"], "properties": {
                "code": c_, "name": NM[c_], "fill": _col[c_][:3] + [200 if c_ == sel else 165],
                "val_label": f"{cur} 점수 <b>{v_:.0f}</b> (트램 {tram_mode})" if pd.notna(v_) else f"{cur}: 점포 부족"}})
        _sel_fc = {"type": "FeatureCollection", "features": [f for f in _fc["features"] if f["properties"]["code"] == sel]}
        _lay = [pdk.Layer("GeoJsonLayer", _fc, id="areas", pickable=True, stroked=True, filled=True,
                          get_fill_color="properties.fill", get_line_color=[255, 255, 255, 255], line_width_min_pixels=1,
                          auto_highlight=True, highlight_color=[255, 255, 255, 90]),
                pdk.Layer("GeoJsonLayer", _sel_fc, id="sel_halo", stroked=True, filled=False,
                          get_line_color=[255, 255, 255, 255], line_width_min_pixels=7),
                pdk.Layer("GeoJsonLayer", _sel_fc, id="sel_area", stroked=True, filled=False,
                          get_line_color=ROUTE_C + [255], line_width_min_pixels=3)] + lay_route
        st.markdown(f'<div class="maphead">{legend_bar(f"{cur} 점수 (100점, 트램 {tram_mode})", _stops, _lo, _hi, "seq_good")}'
                    f'<div class="sym"><span class="ln"></span>트램 2호선</div></div>', unsafe_allow_html=True)
        show_map(deck(_lay, {"html": "<div style='font-weight:700;font-size:14px'>{name}</div>{val_label}"},
                      view=pdk.ViewState(**VIEW_IND, min_zoom=10, max_zoom=16)), key="map_ind", height=IND_H)
        T = B[B.industry == cur][["code", "name", "n_stores", "growth", "lq", f"tram_effect_{SCEN_KEY}", "flag"]].copy()
        T["flag"] = T.flag.where(T.flag.notna(), "")             # 비고 없는 행은 빈칸 ('None' 표시 방지)
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
        st.markdown(f"**{cur} 점수 순위** · 트램 {tram_mode} 기준 (위의 트램 2호선에서 전·후 전환) · 1위 " +
                    ", ".join(f"{n.split('(')[0]} {v:.0f}" for n, v in zip(top.name, top[now_col])))
        st.caption(src("outputs/industry_scores.csv (항목 점수)", "outputs/industry_score_weights.csv (가중치)",
                       f"{SRC_TRAM} (건설 후 트램 효과 수준)"))
        CC = st.column_config
        cfg = {"rank": CC.NumberColumn("순위", format="%d"), "선택": "", "code": "코드", "name": "상권",
               "score_now": CC.ProgressColumn(f"점수 (트램 {tram_mode})", min_value=0, max_value=100, format="%.0f"),
               "before": CC.NumberColumn("건설 전", format="%.0f"), "after": CC.NumberColumn("건설 후", format="%.0f"),
               "move": "순위 변화", "n_stores": CC.NumberColumn(f"{cur} 점포", format="%d"),
               "growth": CC.NumberColumn("대전 내 비중 5년", format="%+.1f%%"),
               "flag": "비고"}
        show = ["rank", "선택", "name", "score_now", "before", "after", "move", "n_stores", "growth", "flag"]
        try:
            ev = st.dataframe(T[show + ["code"]], hide_index=True, use_container_width=True, column_config=cfg | {"code": None},
                              height=420, on_select="rerun", selection_mode="single-row", key="ind_tbl")
            rws = ev.selection.rows if ev is not None else []
        except TypeError:
            st.dataframe(T[show], hide_index=True, use_container_width=True, column_config=cfg); rws = []
        if rws and T.code.iloc[rws[0]] != sel:
            ss.sel_area = T.code.iloc[rws[0]]; ss._last_area_map = ss.sel_area; st.rerun()

        t1, t2, t3, t4 = st.tabs([f"{NM[sel].split('(')[0]} 점수 근거", "트램 전·후 비교", "6개 업종 한눈에", "가중치와 근거"])
        with t1:
            row_b = B[(B.industry == cur) & (B.code == sel)]
            if len(row_b):
                rb_ = row_b.iloc[0]
                ra_ = (A if tram_after else B).loc[row_b.index[0]]
                w_now = wa if tram_after else wb
                pr = info.loc[sel]
                _ga, _la = rb_.get(f"growth_after_{SCEN_KEY}"), rb_.get(f"land_after_{SCEN_KEY}")
                raw = {"growth": ("–" if pd.isna(rb_.growth) else f"{rb_.growth:+.1f}%" +
                                  (f" → {_ga:+.1f}%" if tram_after and pd.notna(_ga) and _ga != rb_.growth else "")),
                       "size": f"{int(rb_.n_stores):,}개" if pd.notna(rb_.n_stores) else "–",
                       "lq": f"{rb_.lq:.2f}" if pd.notna(rb_.lq) else "–",
                       "survival": f"분기 폐업률 {pr.close_rate_q_pct:.1f}%" if pd.notna(pr.get("close_rate_q_pct")) and pd.notna(rb_.survival) else "–",
                       "land": ("–" if pd.isna(rb_.land) else f"{rb_.land:+.1f}%" +
                                (f" → {_la:+.1f}%" if tram_after and pd.notna(_la) and _la != rb_.land else ""))}
                ws = sum(v for k, v in w_now.items() if pd.notna(ra_[f"sa_{k}"]))
                br = pd.DataFrame([{"항목": ITEM.get(k, k), "이 상권 값": raw[k], "항목 점수": ra_[f"sa_{k}"],
                                    "가중치": round(v, 1),
                                    "기여 점수": round(ra_[f"sa_{k}"] * v / ws, 1) if pd.notna(ra_[f"sa_{k}"]) else None}
                                   for k, v in w_now.items()])
                tot_ = (A if tram_after else B).loc[row_b.index[0], "score"]
                st.markdown(f"**{names[sel]} · {cur} {tot_:.0f}점** (트램 {tram_mode})" if pd.notna(tot_)
                            else f"**{names[sel]} · {cur}**: {rb_.flag}")
                st.dataframe(br, hide_index=True, use_container_width=True, column_config={
                    "항목 점수": CC.ProgressColumn("항목 점수 (20개 중 상대)", min_value=0, max_value=100, format="%.0f"),
                    "기여 점수": CC.NumberColumn("기여 점수", format="%.1f", help="항목 점수 × 가중치 ÷ 가중치 합. 다 더하면 총점")})
                st.caption(f"트램: 이 상권 점포의 {rb_.in500 * 100:.0f}%가 정거장 500m 안 · {cur} 땅값 기준 트램 효과 "
                           f"{rb_[f'tram_effect_{SCEN_KEY}']:.2f}% ({scen}) · 건설 후에는 이 효과를 성장·땅값 흐름에 더해 다시 매김"
                           + (f" · 비고: {rb_.flag}" if isinstance(rb_.flag, str) and rb_.flag else ""))
        with t2:
            dd = T.dropna(subset=["before"]).assign(short=lambda d: d.name.str.split("(").str[0])
            base = alt.Chart(dd).encode(y=alt.Y("short:N", sort=list(dd.short), title=None))
            rule = base.mark_rule(color="#b9bec5", strokeWidth=2).encode(
                x=alt.X("before:Q", title="점수 (100점)", scale=alt.Scale(domain=[0, 100])), x2="after:Q")
            pb = base.mark_circle(size=70, color="#9aa0a6").encode(x="before:Q", tooltip=["name", alt.Tooltip("before:Q", title="건설 전")])
            pa = base.mark_circle(size=90, color=TRAM_INK).encode(x="after:Q", tooltip=["name", alt.Tooltip("after:Q", title="건설 후"),
                                                                                         alt.Tooltip("change:Q", title="변화")])
            st.caption("회색 = 건설 전, 남색 = 건설 후 · 정거장 500m 안 비율이 높고 트램에 민감한 업종(음식·소매)일수록 오르고, "
                       "트램이 닿지 않는 상권은 점수가 그대로 (순위는 다른 상권이 오르면서 밀릴 수 있음)")
            st.altair_chart((rule + pb + pa).properties(height=max(260, 22 * len(dd))), use_container_width=True)
        with t3:
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
            st.caption(f"20개 상권 × 6개 업종 점수 (트램 {tram_mode}) · 빈칸 = 업종 점포 5개 미만")
            st.altair_chart((heat + txt).properties(height=max(260, 22 * len(ordr))), use_container_width=True)
        with t4:
            wt = ISW.rename(columns={"item": "항목", "weight_before": "건설 전", "weight_after": "건설 후",
                                     "data": "데이터", "method": "계산", "rationale": "근거", "limit": "한계"})
            st.dataframe(wt.drop(columns=["key"]), hide_index=True, use_container_width=True)
            st.caption("항목 점수는 업종마다 20개 상권을 줄 세운 백분위(0~100). 건설 후에는 성장·땅값 흐름에 트램 예상 효과를 "
                       "더한 값을 건설 전 분포에 대어 다시 매김 → 트램이 닿는 상권만 오르고 나머지는 그대로. "
                       "업종 점포 5개 미만은 점수 없음, 도룡동은 성장·생존 제외")
            st.markdown("**가중치 직접 조정** · 비율로 맞춤 (건설 전·후 같은 가중치)")
            cols = st.columns(len(W_DEF))
            new_w = {k: float(c_.slider(ITEM.get(k, k), 0, 50, int(v), 5)) for c_, (k, v) in zip(cols, ss.ind_w.items())}
            b1, b2 = st.columns([1, 5])
            if b1.button("기본값으로", key="ind_w_reset"):
                new_w = dict(W_DEF)
            if new_w != ss.ind_w:
                ss.ind_w = new_w
                st.rerun()
            if ss.ind_w != W_DEF:
                b2.caption("조정한 가중치로 지도·순위를 계산 중 (기본: " +
                           ", ".join(f"{ITEM.get(k, k)} {v:.0f}" for k, v in W_DEF.items()) + ")")

# ================================================================ 페이지 3: 20개 상권 비교
else:
    st.markdown('<h1 class="page-t">20개 상권 비교</h1>', unsafe_allow_html=True)
    keep = ["code", "name", "quadrant", "quadrant_stability", "risk_score", "growth_score", "tram_sel",
            "land_chg_5y_pct", "store_share_chg_5y_pct", "close_rate_q_pct", "n_stores"]   # 유형은 지도 화면 상권 패널에
    tb = prof[[c for c in keep if c in prof.columns]].copy()
    tb["name"] = [("▶ " if c == sel else "") + n.split("(")[0] for c, n in zip(tb.code, tb.name)]   # 표 폭: 괄호 설명 생략
    tb.insert(tb.columns.get_loc("tram_sel") + 1, "tram_range",
              [tram_range(x).replace("낮음 ", "").replace("높음 ", "") for _, x in prof.iterrows()])
    if ind_now:
        tb.insert(3, "map_val", prof.map_val)
    sort_col = "map_val" if ind_now else (am if am != "quadrant" else "risk_score")
    tb = tb.sort_values(sort_col, ascending=False).reset_index(drop=True)
    st.markdown(f"**20개 상권** · '{LABEL.get(sort_col, sort_col)}' 순 정렬 (지도에 칠한 지표) · 행을 누르면 상세로 이동")
    CC = st.column_config
    cfg = {"code": None, "name": CC.TextColumn("상권", width=150, help="▶ = 지금 지도 화면에서 고른 상권"),
           "quadrant": CC.TextColumn("진단", width=100),
           "quadrant_stability": CC.NumberColumn("진단 안정도", format="percent",
                                                 help="15가지 변형 중 같은 진단 비율. 80% 미만 = 불확실"),
           "risk_score": CC.ProgressColumn("상대 위험", min_value=0, max_value=100, format="%.0f", width=100,
                                           help=HELP["risk_score"]),
           "growth_score": CC.ProgressColumn("상대 성장", min_value=0, max_value=100, format="%.0f", width=100,
                                             help=HELP["growth_score"]),
           "tram_sel": CC.NumberColumn("땅값 기준 트램 효과", format="%+.1f%%",
                                       help=TRAM_DEF + f" · 지금 시나리오: {scen}"),
           "tram_range": CC.TextColumn("낮음 ~ 높음", help="같은 상권의 낮음·높음 시나리오 값 (%)"),
           "land_chg_5y_pct": CC.NumberColumn("땅값 5년", format="%+.1f%%"),
           "store_share_chg_5y_pct": CC.NumberColumn("점포 비중", format="%+.1f%%",
                                                     help="5년 변화 · " + HELP["store_share_chg_5y_pct"]),
           "close_rate_q_pct": CC.NumberColumn("분기 폐업률", format="%.1f%%"),
           "n_stores": CC.NumberColumn("점포 수", format="%d")}
    if ind_now:
        cfg["map_val"] = CC.ProgressColumn(f"{ind_now} 점수", min_value=0, max_value=100, format="%.0f")
    try:
        ev = st.dataframe(tb, hide_index=True, use_container_width=True, column_config=cfg, height=740,
                          on_select="rerun", selection_mode="single-row", key="cmp_tbl")
        rws = ev.selection.rows if ev is not None else []
    except TypeError:
        st.dataframe(tb, hide_index=True, use_container_width=True, column_config=cfg); rws = []
    if rws and tb.code.iloc[rws[0]] != sel:
        ss.sel_area = tb.code.iloc[rws[0]]; ss._last_area_map = ss.sel_area
        ss.page = "map"; st.rerun()
    st.caption(src(f"{SRC_AREA} (진단·점수·지표)", f"{SRC_TRAM} (트램 효과 수준)"))
