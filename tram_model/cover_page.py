"""앱 첫 화면(커버). adaline.ai 처럼 차분한 세이지 톤 · 세리프 제목 하나 · 풍경 그림.

- 색: 리넨 바탕, 숲색 잉크(글자·주 버튼), 세이지 계열(언덕·보조)
- 글꼴: 제목만 Newsreader / Noto Serif KR (300), 나머지는 Pretendard
- 그림: 겹겹의 언덕 위에 실제 정거장 좌표로 그린 트램 2호선 노선 (원본 그림, 외부 이미지 없음)
app.py 에서 render_cover(...) 가 '지도 열기' 를 누르면 True 를 돌려줌.
"""
import math

INK, LINEN, BONE, MIST, EUCA, LICHEN, SAGE_MIST, SAGE, SAGE_GRAY = (
    "#0a1d08", "#f8f9f5", "#eff2e8", "#e1e6df", "#c9d5c5", "#c5ccb6", "#a5ac9f", "#4a6d47", "#6b7860")

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,300&family=Noto+Serif+KR:wght@300&display=swap');
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], header[data-testid="stHeader"] {{ display: none; }}
.stApp {{ background: {LINEN}; }}
.stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp div {{ word-break: keep-all; }}
.block-container {{ max-width: 1120px; padding-top: 1.2rem; padding-bottom: 3rem; }}
.stApp, .stApp p, .stApp div, .stApp button {{ font-family: Pretendard, 'Apple SD Gothic Neo', sans-serif; color: {INK}; }}
.cv-nav {{ display:flex; justify-content:space-between; align-items:center; padding: 6px 0 0 0; font-size: 15px; }}
.cv-nav .mark {{ font-weight: 600; letter-spacing: -0.01em; }}
.cv-nav .mark i {{ display:inline-block; width:9px; height:9px; border-radius:50%; border:2px solid {INK}; margin-right:8px;
                   vertical-align: 1px; }}
.cv-nav .meta {{ color: {SAGE_GRAY}; font-size: 14px; }}
.cv-hero {{ text-align:center; padding: 9vh 0 2.2rem 0; }}
.cv-hero .tag {{ display:inline-block; font-size: 13px; color: {SAGE}; background: {BONE}; border: 1px solid {MIST};
                 border-radius: 999px; padding: 4px 12px; margin-bottom: 26px; }}
.cv-hero h1 {{ font-family: 'Newsreader', 'Noto Serif KR', serif !important; font-weight: 300 !important;
               font-size: clamp(40px, 6.6vw, 88px) !important; line-height: 1.08 !important; letter-spacing: -0.025em;
               color: {INK} !important; margin: 0 auto 22px auto; max-width: 14em; padding: 0; }}
.cv-hero p {{ font-size: 18px; line-height: 1.6; color: #2a332a; max-width: 36em; margin: 0 auto; }}
.stButton > button {{ border-radius: 20px; padding: 10px 22px; font-size: 15px; font-weight: 500; box-shadow: none; }}
.stButton > button[kind="primary"] {{ background: {INK}; color: {LINEN}; border: 1px solid {INK}; }}
.stButton > button[kind="primary"] p {{ color: {LINEN}; }}
.stButton > button[kind="primary"]:hover {{ background: #2b390a; border-color: #2b390a; }}
.stButton > button[kind="secondary"] {{ background: transparent; color: {INK}; border: 1px solid {SAGE_MIST}; }}
.stButton > button[kind="secondary"]:hover {{ border-color: {INK}; color: {INK}; }}
.stButton > button:focus-visible {{ outline: 2px solid {SAGE}; outline-offset: 2px; }}
.cv-land {{ margin: 34px calc(50% - 50vw) 0 calc(50% - 50vw); width: 100vw; line-height: 0; }}
.cv-land svg {{ width: 100%; height: auto; display:block; }}
.cv-rows {{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 0; border-top: 1px solid {MIST}; margin-top: 0; }}
.cv-rows > div {{ padding: 26px 24px 30px 0; border-right: 1px solid {MIST}; }}
.cv-rows > div + div {{ padding-left: 24px; }}
.cv-rows > div:last-child {{ border-right: none; }}
.cv-rows h3 {{ font-size: 18px !important; font-weight: 600 !important; margin: 0 0 8px 0 !important; padding:0 !important;
               color: {INK} !important; }}
.cv-rows p {{ font-size: 15px; line-height: 1.6; color: #2a332a; margin: 0 0 14px 0; }}
.cv-rows .num {{ font-size: 15px; color: {SAGE}; }}
.cv-rows .num b {{ font-family: 'Newsreader', 'Noto Serif KR', serif; font-weight: 300; font-size: 34px; color: {INK};
                   margin-right: 6px; letter-spacing: -0.02em; }}
.cv-steps {{ background: {BONE}; border: 1px solid {MIST}; border-radius: 10px; padding: 22px 24px; margin: 40px 0 0 0;
             display:grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }}
.cv-steps div {{ font-size: 14px; line-height: 1.55; color: #2a332a; }}
.cv-steps b {{ display:block; font-size: 15px; color: {INK}; margin-bottom: 4px; font-weight: 600; }}
.cv-steps span {{ color: {SAGE}; margin-right: 6px; font-variant-numeric: tabular-nums; }}
.cv-close {{ text-align:center; padding: 64px 0 18px 0; }}
.cv-close h2 {{ font-family: 'Newsreader', 'Noto Serif KR', serif !important; font-weight: 300 !important; font-size: 36px !important;
                color: {INK} !important; margin: 0 0 6px 0 !important; padding: 0 !important; letter-spacing: -0.02em; }}
.cv-close p {{ color: {SAGE_GRAY}; font-size: 15px; margin: 0; }}
.cv-foot {{ border-top: 1px solid {MIST}; margin-top: 54px; padding-top: 18px; font-size: 13px; color: {SAGE_GRAY}; line-height: 1.7; }}
@media (max-width: 760px) {{
  .cv-rows, .cv-steps {{ grid-template-columns: 1fr; }}
  .cv-rows > div, .cv-rows > div + div {{ border-right: none; border-bottom: 1px solid {MIST}; padding-left: 0; }}
  .cv-nav .meta {{ display:none; }}
}}
</style>
"""


def _hill(w, base, amp, waves, phase):
    """부드러운 언덕 능선 (사인파 합) → SVG path."""
    pts = []
    for i in range(0, 121):
        x = w * i / 120
        y = base - sum(a * math.sin(2 * math.pi * (x / w) * f + p) for a, f, p in zip(amp, waves, phase))
        pts.append((x, y))
    d = f"M0,{pts[0][1]:.1f} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in pts[1:])
    return d + f" L{w},400 L0,400 Z"


def landscape_svg(paths, stops):
    """언덕 4겹 + 실제 좌표로 그린 트램 2호선 노선(평면 모양을 하늘에 옅게 겹침)."""
    W, H = 1440, 400
    hills = [
        (EUCA, 0.9, _hill(W, 250, [16, 9, 5], [1.3, 3.1, 6.2], [0.4, 1.2, 2.0])),
        (LICHEN, 0.95, _hill(W, 290, [22, 10, 6], [0.9, 2.4, 5.1], [2.1, 0.3, 1.1])),
        (SAGE_MIST, 0.9, _hill(W, 330, [18, 12, 4], [1.6, 2.9, 7.3], [1.0, 2.6, 0.2])),
        (SAGE, 0.85, _hill(W, 372, [14, 7, 3], [1.1, 3.7, 8.0], [0.7, 1.9, 2.8])),
    ]
    # 노선 평면도를 화면 가운데 위쪽에 맞춤
    xs = [p[0] for path in paths for p in path]
    ys = [p[1] for path in paths for p in path]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    k = 250 / max(y1 - y0, 1e-9)                         # 세로 250px 안에, 아래쪽은 언덕에 걸치게
    kx = k * math.cos(math.radians((y0 + y1) / 2))
    cx = W / 2 - (x1 - x0) * kx / 2

    def P(lon, lat):
        return cx + (lon - x0) * kx, 70 + (y1 - lat) * k

    route = "".join(
        "M" + " L".join(f"{P(lon, lat)[0]:.1f},{P(lon, lat)[1]:.1f}" for lon, lat in path) + " " for path in paths)
    dots = "".join(f'<circle cx="{P(lo, la)[0]:.1f}" cy="{P(lo, la)[1]:.1f}" r="2.6" fill="{LINEN}" stroke="{INK}" '
                   f'stroke-width="1.2"/>' for lo, la in stops)
    g = "".join(f'<path d="{d}" fill="{c}" fill-opacity="{o}"/>' for c, o, d in hills)
    return (f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMax slice" role="img" '
            f'aria-label="대전 트램 2호선 노선과 언덕 풍경">'
            f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{LINEN}"/>'
            f'<stop offset="1" stop-color="{BONE}"/></linearGradient></defs>'
            f'<rect width="{W}" height="{H}" fill="url(#sky)"/>{g}'
            f'<path d="{route}" fill="none" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round" '
            f'stroke-linecap="round" opacity="0.85"/>{dots}</svg>')


def render_cover(st, stations, route_paths, stats, open_about):
    """커버 화면. '지도 열기' 를 누르면 True."""
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="cv-nav"><span class="mark"><i></i>대전 트램 상권 지도</span>'
                '<span class="meta">공공데이터 분석 프로젝트</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="cv-hero"><span class="tag">대전 트램 2호선 · 2030년 개통</span>'
                '<h1>트램이 지날 길 위의<br/>스무 상권</h1>'
                '<p>트램 2호선이 개통하면 정거장 주변 상권은 어떻게 달라질까요. 37년치 공시지가와 '
                '10년치 상가 기록으로 20개 상권의 지금과 트램 이후를 살펴봅니다.</p></div>',
                unsafe_allow_html=True)
    go = False
    _, b1, b2, _ = st.columns([3, 1.3, 1.3, 3])
    if b1.button("지도 열기", type="primary", use_container_width=True, key="cv_open"):
        go = True
    if b2.button("분석 방법 보기", use_container_width=True, key="cv_about"):
        open_about()

    paths = route_paths(stations)
    stops = list(zip(stations.lon, stations.lat))
    st.markdown(f'<div class="cv-land">{landscape_svg(paths, stops)}</div>', unsafe_allow_html=True)

    s = stats
    st.markdown(
        '<div class="cv-rows">'
        f'<div><h3>상권 진단</h3><p>땅값·점포 흐름과 정거장 거리로 20개 상권을 네 가지 상태로 나눕니다. '
        f'진단이 흔들리는 상권은 따로 표시합니다.</p>'
        f'<div class="num"><b>{s["rebound"]}</b>곳이 트램 반등 기회</div></div>'
        f'<div><h3>땅값 기준 트램 효과</h3><p>2006년 대전 1호선 개통 전후의 땅값 변화로 트램 정거장 500m 안의 효과를 추정합니다. '
        f'숫자 하나가 아니라 범위로 보여 줍니다.</p>'
        f'<div class="num"><b>{s["base"]}</b>기본 시나리오 ({s["low"]} ~ {s["high"]})</div></div>'
        f'<div><h3>업종 점수</h3><p>음식·소매 등 6개 업종을 상권마다 100점으로 매기고, 트램 건설 전과 후의 순위를 '
        f'나란히 비교합니다.</p>'
        f'<div class="num"><b>{s["n_scores"]}</b>개 상권·업종 점수</div></div>'
        '</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="cv-steps">'
        '<div><b><span>1</span>자료 모으기</b>공시지가 1990~2026, 상가정보 42분기, 정거장 45곳 좌표</div>'
        '<div><b><span>2</span>효과 추정</b>1호선 역 500m 안과 1~3km 밖 같은 필지의 개통 전후 비교</div>'
        '<div><b><span>3</span>진단과 점수</b>상권 4분류, 업종별 100점, 땅값 예측</div>'
        '<div><b><span>4</span>지도에서 보기</b>상권·정거장을 눌러 근거와 AI 해설 확인</div>'
        '</div>', unsafe_allow_html=True)

    st.markdown('<div class="cv-close"><h2>지도에서 직접 눌러 보세요</h2>'
                '<p>상권을 누르면 진단 근거가, 정거장을 누르면 500m 영향권이 열립니다.</p></div>',
                unsafe_allow_html=True)
    _, c, _ = st.columns([3, 1.3, 3])
    if c.button("지도 열기", type="primary", use_container_width=True, key="cv_open2"):
        go = True
    st.markdown('<div class="cv-foot">자료: 국토교통부 개별공시지가, 소상공인시장진흥공단 상가(상권)정보, 대전시 트램 2호선 정거장 자료, '
                '2021 대전 소상공인 실태조사. 땅값 기준 트램 효과는 추정값이며 매출 변화가 아닙니다.</div>',
                unsafe_allow_html=True)
    return go
