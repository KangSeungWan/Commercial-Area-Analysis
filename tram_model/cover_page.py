"""앱 첫 화면(커버). 시안 D '아침에서 저녁' (cover_drafts/d_morning_to_evening.html).

- 그림: 언덕 다섯 겹 + 하늘에 걸린 트램 2호선 노선(실제 정거장 좌표, tram_route 순서). 언덕 위로 트램이 달림
- 움직임: 커서를 따라 언덕이 겹겹이 움직이고(패럴랙스), 스크롤하면 하늘이 새벽 → 한낮 → 노을 → 저녁으로 바뀜
  그동안 제목은 왼쪽으로 빠지고 세 가지 분석 → 분석 네 단계 → 마무리(지도 열기, 자료 출처) 가 차례로 들어옴
- 색·글꼴: DESIGN.md (리넨 바탕, 숲색 잉크, 세이지, 제목만 Newsreader / Noto Serif KR 300). 글꼴은 앱 전체에서 이미 불러옴
- 구현: Streamlit 커스텀 컴포넌트 v2 (iframe 없이 페이지 안에 그려짐 → 스크롤은 Streamlit 페이지 하나뿐)
  그림은 320vh 높이 상자 안에서 sticky 로 화면에 붙음 (fixed 는 휠 스크롤이 Streamlit 스크롤 상자로 전달되지 않음)
  GSAP·ScrollTrigger 는 cover_assets/ 의 파일을 읽어 그대로 넣음 (CDN 없음)
- '지도 열기'·'분석 방법 보기' 는 컴포넌트 트리거 → 같은 세션에서 다시 실행 (페이지 새로고침 없음 → 세션 상태 유지)
app.py 에서 render_cover(...) 가 '지도 열기' 를 누르면 True 를 돌려줌.
"""
from pathlib import Path

import streamlit as st

from tram_route import LOOP, BRANCH

_ASSETS = Path(__file__).with_name("cover_assets")
# 라이브러리는 이미 있으면 다시 실행하지 않음 (커버로 여러 번 돌아와도 한 번만).
# UMD 묶음은 전역(this.window)에 붙는데, 모듈(엄격 모드)에선 window.window 에 쓸 수 없어서
# { window } 를 this 로 넘겨 실행 → 결과(gsap, ScrollTrigger)는 그대로 window 에 붙음
_LIBS = "\n".join(
    f"if (!window.{name}) (function () {{\n{(_ASSETS / file).read_text(encoding='utf-8')}\n}}).call({{ window }});"
    for name, file in [("gsap", "gsap.min.js"), ("ScrollTrigger", "ScrollTrigger.min.js")])

_HTML = """
<div class="cv-wrap">
<section class="cv-stage">
  <svg class="cv-svg" role="img" aria-label="언덕 위로 트램이 달리는 대전 트램 2호선 풍경, 아침에서 저녁까지">
    <defs>
      <linearGradient id="cvSky" x1="0" y1="0" x2="0" y2="1"><stop class="skyTop" offset="0"/><stop class="skyBot" offset="1"/></linearGradient>
      <radialGradient id="cvSunGlow"><stop class="glowIn" offset="0" stop-color="#fbf6e9" stop-opacity=".9"/><stop class="glowOut" offset="1" stop-color="#fbf6e9" stop-opacity="0"/></radialGradient>
      <radialGradient id="cvHorizonGlow"><stop offset="0" stop-color="#f29a62" stop-opacity=".75"/><stop offset=".55" stop-color="#f2ae7c" stop-opacity=".3"/><stop offset="1" stop-color="#f2ae7c" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#cvSky)"/>
    <ellipse class="horizon" fill="url(#cvHorizonGlow)" opacity="0"/>
    <g class="sun"><circle class="sunHalo" r="120" fill="url(#cvSunGlow)"/><circle class="sunDisc" r="34" fill="#fbf6e9"/></g>
    <g class="moon" opacity="0"><circle r="20" fill="#f8f9f5"/><circle class="moonCut" r="20" cx="9" cy="-5"/></g>
    <g class="route"><path class="routeLine" fill="none" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/><g class="routeStops"></g></g>
    <g class="hillWrap"></g>
  </svg>
  <header class="cv-nav">
    <span class="cv-mark"><i></i>대전 트램 상권 지도</span>
    <button type="button" class="cv-cta cv-nav-cta" data-act="open">지도 열기</button>
  </header>

  <!-- 1. 첫 화면: 스크롤하면 왼쪽으로 빠짐 -->
  <div class="cv-copy cv-hero">
    <span class="cv-tag">대전 트램 2호선 · 2030년 개통</span>
    <h1><span class="line"><span>트램이 지날 길 위의</span></span><span class="line"><span>스무 상권</span></span></h1>
    <div class="cv-actions">
      <button type="button" class="cv-cta" data-act="open">지도 열기</button>
      <button type="button" class="cv-ghost" data-act="about">분석 방법 보기</button>
    </div>
  </div>

  <!-- 2. 무엇을 보나: 세 가지 분석 (오른쪽에서 들어와 왼쪽으로 빠짐) -->
  <div class="cv-panel cv-p1">
    <div class="cv-card cv-rows">
      <div class="cv-row"><h3>상권 진단</h3><p>땅값·점포 흐름과 정거장 거리로 20개 상권을 네 가지 상태로 나눕니다. 진단이 흔들리는 상권은 따로 표시합니다.</p>
        <div class="cv-num"><b data-stat="rebound"></b>곳이 트램 반등 기회</div></div>
      <div class="cv-row"><h3>상권 가치(땅값) 기준 트램 효과</h3><p>2006년 대전 1호선 개통 전후의 땅값 변화로 트램 정거장 500m 안의 효과를 추정합니다. 숫자 하나가 아니라 범위로 보여 줍니다.</p>
        <div class="cv-num"><b data-stat="base"></b>기본 시나리오 (<span data-stat="low"></span> ~ <span data-stat="high"></span>)</div></div>
      <div class="cv-row"><h3>업종 점수</h3><p>음식·소매 등 6개 업종을 상권마다 100점으로 매기고, 트램 건설 전과 후의 순위를 나란히 비교합니다.</p>
        <div class="cv-num"><b data-stat="n_scores"></b>개 상권·업종 점수</div></div>
    </div>
  </div>

  <!-- 3. 어떻게 분석했나: 네 단계 -->
  <div class="cv-panel cv-p2">
    <div class="cv-card cv-steps">
      <div class="cv-step"><b><span>1</span>자료 모으기</b>공시지가 1990~2026, 상가정보 42분기, 정거장 45곳 좌표</div>
      <div class="cv-step"><b><span>2</span>효과 추정</b>1호선 역 500m 안과 1~3km 밖 같은 필지의 개통 전후 비교</div>
      <div class="cv-step"><b><span>3</span>진단과 점수</b>상권 4분류, 업종별 100점, 땅값 예측</div>
      <div class="cv-step"><b><span>4</span>지도에서 보기</b>상권·정거장을 눌러 근거와 AI 해설 확인</div>
    </div>
  </div>

  <!-- 4. 마무리 (저녁): 지도로 -->
  <div class="cv-panel cv-p3">
    <div class="cv-close">
      <h2>지도에서 직접 눌러 보세요</h2>
      <p>상권을 누르면 진단 근거가, 정거장을 누르면 500m 영향권이 열립니다.</p>
      <div class="cv-actions">
        <button type="button" class="cv-cta" data-act="open">지도 열기</button>
        <button type="button" class="cv-ghost" data-act="about">분석 방법 보기</button>
      </div>
    </div>
    <div class="cv-foot">자료: 국토교통부 개별공시지가, 소상공인시장진흥공단 상가(상권)정보, 대전시 트램 2호선 정거장 자료,
      2021 대전 소상공인 실태조사. 상권 가치(땅값) 기준 트램 효과는 추정값이며 매출 변화가 아닙니다.</div>
  </div>
</section>
</div>
"""

_CSS = """
.cv-wrap, .cv-wrap * { box-sizing: border-box; }       /* 그림자 DOM 은 Streamlit 의 box-sizing 을 물려받지 않음 */
.cv-wrap { position: relative; height: 560vh; }       /* 이 높이만큼 페이지가 스크롤되고, 그동안 그림은 화면에 붙어 있음 */
.cv-stage {
  --fg: #0a1d08; --tag-fg: #4a6d47; --tag-bg: rgba(239, 242, 232, .9); --tag-line: #e1e6df;
  --btn-bg: #0a1d08; --btn-fg: #f8f9f5; --sage: #4a6d47;
  --gutter: clamp(16px, 5vw, 88px);
  position: sticky; top: 0; height: 100vh; height: 100dvh; overflow: hidden; background: #f8f9f5; color: var(--fg);
  font-family: Pretendard, "Apple SD Gothic Neo", sans-serif; font-weight: 500;
}
.cv-svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.cv-nav { position: absolute; inset: 0 0 auto 0; height: 68px; display: flex; align-items: center; justify-content: space-between;
          padding: 0 var(--gutter); font-size: 15px; letter-spacing: -0.01em; color: var(--fg); z-index: 2; }
.cv-mark i { display: inline-block; width: 10px; height: 10px; border: 2px solid currentColor; border-radius: 50%; margin-right: 10px; }
.cv-nav-cta { padding: 8px 18px !important; font-size: 14px !important; visibility: hidden; opacity: 0; }

.cv-copy { position: absolute; left: var(--gutter); top: clamp(110px, 20vh, 220px); max-width: 620px; color: var(--fg); }
.cv-tag { display: inline-block; font-size: 13px; color: var(--tag-fg); background: var(--tag-bg); border: 1px solid var(--tag-line);
          border-radius: 999px; padding: 5px 13px; margin-bottom: 26px; }
.cv-copy h1 { font-family: "Newsreader", "Noto Serif KR", serif; font-weight: 300; font-size: clamp(40px, 4.6vw, 80px); line-height: 1.1;
              letter-spacing: -0.025em; word-break: keep-all; margin: 0 0 34px 0; padding: 0; color: var(--fg); }
.cv-copy h1 .line { display: block; overflow: hidden; padding: 0.14em 0 0.06em 0; margin-top: -0.14em; }   /* 한글 세리프 글자 위가 잘리지 않게 */
.cv-copy h1 .line > span { display: block; }
@media (min-width: 768px) { .cv-copy h1 .line { white-space: nowrap; } }
.cv-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.cv-cta, .cv-ghost { font: inherit; font-size: 15px; border-radius: 20px; padding: 11px 24px; cursor: pointer; white-space: nowrap;
                     transition: transform .25s cubic-bezier(.16,1,.3,1), filter .25s cubic-bezier(.16,1,.3,1); }
.cv-cta { color: var(--btn-fg); background: var(--btn-bg); border: 1px solid var(--btn-bg); }
.cv-ghost { color: var(--fg); background: transparent; border: 1px solid var(--tag-line); }
.cv-cta:hover { filter: brightness(1.25); }
.cv-ghost:hover { border-color: var(--fg); }
.cv-cta:active, .cv-ghost:active { transform: scale(0.98); }
.cv-cta:focus-visible, .cv-ghost:focus-visible { outline: 2px solid var(--sage); outline-offset: 2px; }

/* 스크롤하면 차례로 들어오는 내용: 바탕 없이 글자만 하늘 위에 (구분은 가는 선 하나) */
.cv-panel { position: absolute; left: var(--gutter); right: var(--gutter); top: clamp(120px, 20vh, 220px); bottom: 32px; display: flex;
            flex-direction: column; justify-content: flex-start; visibility: hidden; opacity: 0; pointer-events: none; }
.cv-panel > * { pointer-events: auto; }
.cv-card { width: min(1120px, 100%); color: var(--fg); }
.cv-rows { display: grid; grid-template-columns: repeat(3, 1fr); }
.cv-row, .cv-step { padding: 2px 28px 4px 28px; border-left: 1px solid rgba(10, 29, 8, .16); }
.cv-row:first-child, .cv-step:first-child { padding-left: 0; border-left: none; }
.cv-row h3 { font-size: 18px; font-weight: 600; margin: 0 0 6px 0; padding: 0; color: #0a1d08; font-family: inherit; }
.cv-row p { font-size: 15px; line-height: 1.6; color: #2a332a; margin: 0 0 10px 0; word-break: keep-all; }
.cv-num { font-size: 15px; color: #4a6d47; }
.cv-num b { font-family: "Newsreader", "Noto Serif KR", serif; font-weight: 300; font-size: 34px; color: #0a1d08; margin-right: 6px;
            letter-spacing: -0.02em; }
.cv-steps { display: grid; grid-template-columns: repeat(4, 1fr); }
.cv-step { font-size: 15px; line-height: 1.6; color: #2a332a; word-break: keep-all; }
.cv-step b { display: block; font-size: 17px; color: #0a1d08; margin-bottom: 4px; font-weight: 600; }
.cv-step span { color: #4a6d47; margin-right: 8px; font-variant-numeric: tabular-nums; }
.cv-close { max-width: 620px; color: var(--fg); }
.cv-close h2 { font-family: "Newsreader", "Noto Serif KR", serif; font-weight: 300; font-size: clamp(32px, 3.4vw, 52px); letter-spacing: -0.02em;
               line-height: 1.15; margin: 0 0 12px 0; padding: 0; color: var(--fg); word-break: keep-all; }
.cv-close p { font-size: 17px; line-height: 1.6; margin: 0 0 28px 0; color: var(--fg); opacity: .85; word-break: keep-all; }
.cv-foot { position: absolute; left: 0; right: 0; bottom: 0; max-width: 760px; font-size: 13px; line-height: 1.7; color: var(--fg); opacity: .7;
           word-break: keep-all; }

@media (max-width: 767px) {
  .cv-copy { right: var(--gutter); top: 96px; }
  .cv-tag { margin-bottom: 18px; }
  .cv-copy h1 { margin-bottom: 24px; }
  .cv-rows, .cv-steps { grid-template-columns: 1fr; }
  .cv-row, .cv-step { padding: 14px 0 12px 0; border-left: none; border-top: 1px solid rgba(10, 29, 8, .16); }
  .cv-row:first-child, .cv-step:first-child { padding-top: 0; border-top: none; }
  .cv-panel { top: 92px; }
  .cv-row p { font-size: 14px; }
  .cv-num b { font-size: 28px; }
  .cv-foot { display: none; }
}
"""

_JS = _LIBS + """

// ---------------------------------------------------------------- 커버 (시안 D)
const inst = new WeakMap();            // parentElement → 정리 함수 (다시 그려져도 한 번만 시작)

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  if (inst.has(parentElement)) return inst.get(parentElement);
  const cleanup = start(parentElement, data.route, data.stats || {}, setTriggerValue);
  const done = () => { cleanup(); inst.delete(parentElement); };
  inst.set(parentElement, done);
  return done;
}

function start(rootEl, ROUTE, stats, setTriggerValue) {
  const gsap = window.gsap, ScrollTrigger = window.ScrollTrigger;
  gsap.registerPlugin(ScrollTrigger);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const NS = "http://www.w3.org/2000/svg";
  const q = sel => rootEl.querySelector(sel);
  const svg = q(".cv-svg"), stage = q(".cv-stage"), wrap = q(".cv-wrap");
  const lerp = gsap.utils.interpolate;

  // 하늘 시간표 (스크롤 0 → 1): 새벽, 한낮(지금 커버 색), 늦은 오후, 노을, 해 진 직후, 저녁. 아침은 짧게, 노을·저녁은 길게
  // warm = 노을빛 세기 (해 색, 지평선 빛, 언덕에 비치는 빛)
  const SKY = [
    { p: 0,   top: "#d6ddd8", bot: "#f2e9df", night: 0,   warm: .1 },
    { p: .17, top: "#f8f9f5", bot: "#eff2e8", night: 0,   warm: 0 },
    { p: .4,  top: "#eef0e6", bot: "#f4e4c6", night: 0,   warm: .25 },
    { p: .63, top: "#b7a79b", bot: "#f2ae7c", night: .05, warm: 1 },
    { p: .8,  top: "#4c5552", bot: "#d27f58", night: .55, warm: .75 },
    { p: 1,   top: "#16241b", bot: "#3e5a3c", night: 1,   warm: 0 },
  ];
  function sky(p) {
    let i = 1; while (i < SKY.length - 1 && SKY[i].p < p) i++;
    const a = SKY[i - 1], b = SKY[i], t = Math.min(1, Math.max(0, (p - a.p) / (b.p - a.p)));
    return { top: lerp(a.top, b.top, t), bot: lerp(a.bot, b.bot, t), night: lerp(a.night, b.night, t), warm: lerp(a.warm, b.warm, t) };
  }
  // 해의 위치 (0 뜸 → .5 가장 높음 → 1 짐): 한낮에 가장 높고, 노을 무렵 언덕 바로 위, 해 진 직후 넘어감
  const SUN = [[0, 0], [.17, .5], [.63, .81], [.82, 1]];
  function sunPath(p) {
    let i = 1; while (i < SUN.length - 1 && SUN[i][0] < p) i++;
    const [p0, t0] = SUN[i - 1], [p1, t1] = SUN[i];
    return t0 + (t1 - t0) * Math.min(1, Math.max(0, (p - p0) / (p1 - p0)));
  }

  // 언덕 다섯 겹 (예전 커버 능선 식 + 맨 뒤 먼 산 한 겹). depth 가 클수록 앞쪽, 더 많이 움직임
  const HILLS = [
    { base: 215, amp: [12, 6, 3],  waves: [0.7, 2.2, 4.6], phase: [1.4, 0.2, 2.2], fill: "#dde3da", depth: .12 },
    { base: 250, amp: [16, 9, 5],  waves: [1.3, 3.1, 6.2], phase: [0.4, 1.2, 2.0], fill: "#c9d5c5", depth: .25 },
    { base: 290, amp: [22, 10, 6], waves: [0.9, 2.4, 5.1], phase: [2.1, 0.3, 1.1], fill: "#c5ccb6", depth: .45, tram: true },
    { base: 330, amp: [18, 12, 4], waves: [1.6, 2.9, 7.3], phase: [1.0, 2.6, 0.2], fill: "#a5ac9f", depth: .7 },
    { base: 372, amp: [14, 7, 3],  waves: [1.1, 3.7, 8.0], phase: [0.7, 1.9, 2.8], fill: "#4a6d47", depth: 1 },
  ];

  let W, H, PAD = 80, layers = [], ridge = null, tram, stopsEls = [];

  function project(box) {
    const all = ROUTE.loop.concat(ROUTE.branch);
    const lons = all.map(p => p[0]), lats = all.map(p => p[1]);
    const lo0 = Math.min(...lons), lo1 = Math.max(...lons), la0 = Math.min(...lats), la1 = Math.max(...lats);
    const kx = Math.cos((la0 + la1) / 2 * Math.PI / 180);
    const k = Math.min(box.w / ((lo1 - lo0) * kx), box.h / (la1 - la0));
    const ox = box.x + (box.w - (lo1 - lo0) * kx * k) / 2, oy = box.y + (box.h - (la1 - la0) * k) / 2;
    return ([lon, lat]) => ({ x: ox + (lon - lo0) * kx * k, y: oy + (la1 - lat) * k });
  }

  function build() {
    W = stage.clientWidth; H = stage.clientHeight;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const mobile = W < 768;
    // 하늘에 옅게 걸린 노선 (밤이 되면 정거장이 불빛처럼 켜짐)
    const P = project(mobile ? { x: W * .3, y: H * .4, w: W * .6, h: H * .14 } : { x: W * .55, y: H * .1, w: W * .36, h: H * .4 });
    const loop = ROUTE.loop.map(P), branch = ROUTE.branch.map(P);
    const pd = pts => "M" + pts.map(p => p.x.toFixed(1) + "," + p.y.toFixed(1)).join(" L");
    q(".routeLine").setAttribute("d", pd(loop.concat([loop[0]])) + " " + pd(branch));
    const rs = q(".routeStops"); rs.textContent = "";
    stopsEls = loop.concat(branch.slice(1)).map(p => {
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", p.x); c.setAttribute("cy", p.y); c.setAttribute("r", 2.6); c.setAttribute("stroke-width", 1.2);
      rs.appendChild(c); return c;
    });
    const s = H * (mobile ? .38 : .5) / 160, hillWrap = q(".hillWrap"); hillWrap.textContent = ""; layers = [];
    for (const h of HILLS) {
      const g = document.createElementNS(NS, "g"), path = document.createElementNS(NS, "path");
      const pts = [], w = W + PAD * 2;
      for (let i = 0; i <= 160; i++) {
        const x = -PAD + w * i / 160;
        pts.push([x, H - (400 - h.base) * s - h.amp.reduce((a, A, j) => a + A * s * Math.sin(2 * Math.PI * ((x + PAD) / w) * h.waves[j] + h.phase[j]), 0)]);
      }
      path.setAttribute("d", "M" + pts.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L") + ` L${W + PAD},${H + PAD} L${-PAD},${H + PAD} Z`);
      g.appendChild(path); hillWrap.appendChild(g);
      layers.push({ ...h, g, path });
      if (h.tram) {                                         // 트램은 이 언덕 능선 위를 달림 (능선 바로 뒤에 두어 바퀴가 땅에 묻힌 듯)
        ridge = pts; tram = makeTram(); g.insertBefore(tram, path);
      }
    }
  }

  function makeTram() {                                     // 둥근 차체 + 창 + 집전 장치
    const g = document.createElementNS(NS, "g");
    g.innerHTML = `
      <g transform="translate(0,-15)">
        <path d="M-2,-26 L8,-34 L14,-26" fill="none" stroke="#0a1d08" stroke-width="1.6"/>
        <rect x="-46" y="-24" width="92" height="26" rx="9" fill="#0a1d08"/>
        <g class="tramWin" fill="#eff2e8">
          <rect x="-38" y="-18" width="14" height="9" rx="2"/><rect x="-20" y="-18" width="14" height="9" rx="2"/>
          <rect x="-2" y="-18" width="14" height="9" rx="2"/><rect x="16" y="-18" width="14" height="9" rx="2"/>
        </g>
        <circle cx="44" cy="-6" r="2.4" fill="#f2e9cf"/>
        <path class="tramBeam" d="M46,-6 L130,-22 L130,10 Z" fill="#f2e9cf" opacity="0"/>
      </g>`;
    return g;
  }

  function onRidge(x) {                                     // 능선 위 x 위치 → 좌표·기울기
    const w = W + PAD * 2, f = (x + PAD) / w * (ridge.length - 1), i = Math.max(0, Math.min(ridge.length - 2, Math.floor(f))), t = f - i;
    const a = ridge[i], b = ridge[i + 1];
    return { x, y: a[1] + (b[1] - a[1]) * t, ang: Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI };
  }

  const S = { p: 0, mx: 0, my: 0, tx: 0, ty: 0, run: 0, intro: 0 };
  const INK = { d: 0, want: 0 };                            // 글자색 전환 상태 (0 먹색, 1 리넨)
  const el = {
    skyTop: q(".skyTop"), skyBot: q(".skyBot"), sun: q(".sun"), sunDisc: q(".sunDisc"), sunHalo: q(".sunHalo"),
    glowIn: q(".glowIn"), glowOut: q(".glowOut"), horizon: q(".horizon"), moon: q(".moon"), moonCut: q(".moonCut"),
    routeLine: q(".routeLine"), route: q(".route"),
  };

  function render() {
    const P = reduce ? .17 : S.p;                           // 하늘·풍경의 시각 (움직임 줄이기: 한낮 고정)
    const sk = sky(P), n = sk.night, wm = sk.warm;
    el.skyTop.setAttribute("stop-color", sk.top); el.skyBot.setAttribute("stop-color", sk.bot);
    // 해: 왼쪽 아래에서 떠서 가운데 위를 지나, 노을 무렵 오른쪽 언덕 바로 위로 낮게 내려와 짐
    const a = Math.PI * (1 - sunPath(P));
    const hz = H * .62, sx = W * .5 + Math.cos(a) * W * .42, sy = hz - Math.sin(a) * H * .5;
    gsap.set(el.sun, { x: sx, y: sy, opacity: 1 - Math.max(0, (P - .75) / .07) });
    el.sunDisc.setAttribute("fill", lerp("#fbf6e9", "#f08a52", wm));
    el.sunDisc.setAttribute("r", 34 + wm * 14);
    el.sunHalo.setAttribute("r", 120 + wm * 110);
    el.glowIn.setAttribute("stop-color", lerp("#fbf6e9", "#f4a06a", wm));
    el.glowOut.setAttribute("stop-color", lerp("#fbf6e9", "#f4a06a", wm));
    // 지평선 노을빛: 해가 지는 쪽 언덕 위로 넓게 번짐
    el.horizon.setAttribute("cx", sx); el.horizon.setAttribute("cy", H * .5);
    el.horizon.setAttribute("rx", W * .75); el.horizon.setAttribute("ry", H * .32);
    el.horizon.setAttribute("opacity", wm * (1 - n * .6));
    gsap.set(el.moon, { x: W * .3, y: H * .16, opacity: Math.max(0, (n - .55) / .45) });
    el.moonCut.setAttribute("fill", sk.top);
    // 노선: 낮엔 먹선, 밤엔 정거장이 불빛처럼
    el.routeLine.setAttribute("stroke", lerp("#0a1d08", "#c9d5c5", n));
    // 하늘의 노선은 내용 글자가 나와 있는 동안 옅게 (겹쳐 읽히지 않게). 휴대폰은 마무리 글자와도 겹쳐서 끝까지 옅게
    const c01 = v => Math.min(1, Math.max(0, v));
    const textOn = c01((S.p - .12) / .06) * (W < 768 ? 1 : 1 - c01((S.p - .64) / .06));
    el.route.style.opacity = (.5 + n * .3) * (1 - .8 * textOn);
    for (const c of stopsEls) {
      c.setAttribute("fill", lerp("#f8f9f5", "#f2e9cf", n)); c.setAttribute("stroke", lerp("#0a1d08", "#f2e9cf", n)); c.setAttribute("r", 2.6 + n * 1.2);
    }
    // 언덕: 패럴랙스(커서·스크롤) + 노을빛 + 저녁엔 어두워짐
    for (const L of layers) {
      gsap.set(L.g, { x: -S.mx * L.depth * 34, y: -S.my * L.depth * 14 - P * L.depth * 46 + (1 - S.intro) * (120 + L.depth * 220) });
      const lit = lerp(L.fill, "#e3a07a", wm * (.38 - L.depth * .26));             // 노을빛은 먼 언덕일수록 진하게
      L.path.setAttribute("fill", lerp(lit, "#0e1a12", n * (.62 + L.depth * .3)));  // 밤엔 하늘보다 어둡게 (글자 대비)
    }
    // 트램: 시간이 흐르며 달리고, 스크롤하면 더 멀리 감. 오른쪽 끝을 지나면 왼쪽에서 다시 나옴
    if (ridge) {
      const span = W + 260, x = ((S.run + P * W * 1.4) % span + span) % span - 130;
      const r = onRidge(x);
      tram.setAttribute("transform", `translate(${r.x.toFixed(1)},${(r.y + 2).toFixed(1)}) rotate(${r.ang.toFixed(2)})`);
      tram.querySelector(".tramWin").setAttribute("fill", lerp("#eff2e8", "#f2e9cf", n));
      tram.querySelector(".tramBeam").setAttribute("opacity", n * .35);
    }
    // 글자·버튼 색: 하늘이 어두워지면 리넨으로. 중간 회색에 머물지 않도록 문턱을 넘으면 짧게 전환
    const wantDark = P > .73 ? 1 : 0;
    if (wantDark !== INK.want) {
      INK.want = wantDark;
      if (reduce) INK.d = wantDark; else gsap.to(INK, { d: wantDark, duration: .5, ease: "power2.inOut", overwrite: true });
    }
    const d = INK.d;
    stage.style.setProperty("--fg", lerp("#0a1d08", "#f8f9f5", d));
    stage.style.setProperty("--tag-fg", lerp("#4a6d47", "#e1e6df", d));
    stage.style.setProperty("--tag-bg", lerp("rgba(239,242,232,.9)", "rgba(248,249,245,.08)", d));
    stage.style.setProperty("--tag-line", lerp("#e1e6df", "rgba(248,249,245,.25)", d));
    stage.style.setProperty("--btn-bg", lerp("#0a1d08", "#f8f9f5", d));
    stage.style.setProperty("--btn-fg", lerp("#f8f9f5", "#0a1d08", d));
    scenes.time(S.p);                                       // 스크롤 장면 (제목 → 세 가지 분석 → 네 단계 → 마무리)
  }

  // 버튼 → Python (트리거: 한 번의 재실행에만 값이 실림, 페이지 새로고침 없음)
  const onClick = e => {
    const b = e.target.closest("[data-act]");
    if (b) setTriggerValue(b.dataset.act, true);
  };
  stage.addEventListener("click", onClick);

  // 분석 수치 (app.py 에서 계산해 넘김)
  for (const b of rootEl.querySelectorAll("[data-stat]")) b.textContent = String(stats[b.dataset.stat] ?? "-");

  // 스크롤 장면: 길이 1 의 멈춘 타임라인을 스크롤 위치(S.p)로 감음. 제목은 왼쪽으로 빠지고, 내용은 오른쪽에서 들어옴
  const T = reduce ? .0001 : 1;                             // 움직임 줄이기: 이동 없이 바로 바뀜
  const hero = q(".cv-hero"), navCta = q(".cv-nav-cta"), p1 = q(".cv-p1"), p2 = q(".cv-p2"), p3 = q(".cv-p3");
  const slideIn = (el, at) => scenes.fromTo(el, { autoAlpha: 0, x: reduce ? 0 : 140 }, { autoAlpha: 1, x: 0, duration: .07 * T, ease: "power3.out" }, at);
  const slideOut = (el, at) => scenes.to(el, { autoAlpha: 0, x: reduce ? 0 : -140, duration: .06 * T, ease: "power2.in" }, at);
  const scenes = gsap.timeline({ paused: true });
  slideOut(hero, .1);                                                       // 새벽~한낮: 제목
  scenes.fromTo(navCta, { autoAlpha: 0 }, { autoAlpha: 1, duration: .03 * T }, .13);   // 제목이 빠지면 '지도 열기' 는 위쪽 줄에
  slideIn(p1, .18);                                                         // 한낮~오후: 세 가지 분석
  scenes.from(p1.querySelectorAll(".cv-row"), { autoAlpha: 0, y: reduce ? 0 : 26, duration: .05 * T, stagger: .02 * T, ease: "power3.out" }, .2);
  slideOut(p1, .4);
  slideIn(p2, .45);                                                         // 오후~노을: 네 단계
  scenes.from(p2.querySelectorAll(".cv-step"), { autoAlpha: 0, y: reduce ? 0 : 20, duration: .05 * T, stagger: .015 * T, ease: "power3.out" }, .47);
  slideOut(p2, .63);
  scenes.to(navCta, { autoAlpha: 0, duration: .03 * T }, .7);              // 마무리엔 큰 '지도 열기' 가 있으므로 위쪽 줄 버튼은 숨김
  slideIn(p3, .7);                                                          // 해 진 뒤~밤: 마무리
  scenes.set({}, {}, 1);                                                    // 타임라인 길이 = 1 (스크롤 끝)

  // Streamlit 페이지의 스크롤 상자 (커버 스크롤 = 페이지 스크롤 하나)
  function findScroller() {
    let n = rootEl;
    while (n) {
      n = n.parentNode || n.host;
      if (!n || n === document) break;
      if (n.nodeType === 1) {
        const oy = getComputedStyle(n).overflowY;
        if ((oy === "auto" || oy === "scroll") && n.scrollHeight > n.clientHeight + 1) return n;
      }
    }
    return document.scrollingElement || document.documentElement;
  }

  build();
  const tweens = [], offs = [];
  let tick = null, st = null;
  if (reduce) {
    S.intro = 1; S.run = W * .18; render();                               // 하늘은 한낮 고정, 내용만 스크롤로 바뀜 (이동 없음)
    requestAnimationFrame(() => {
      const scroller = findScroller();
      scroller.scrollTop = 0;
      st = ScrollTrigger.create({ trigger: wrap, scroller, start: "top top", end: "bottom bottom", onUpdate: self => { S.p = self.progress; render(); } });
    });
  } else {
    render();
    tweens.push(gsap.from(rootEl.querySelectorAll(".cv-hero h1 .line > span"), { yPercent: 115, duration: 1.3, ease: "expo.out", stagger: .12, delay: .4 }));
    tweens.push(gsap.from([q(".cv-hero .cv-tag"), q(".cv-hero .cv-actions")], { opacity: 0, y: 14, duration: .9, ease: "power3.out", stagger: .5, delay: .6 }));
    tweens.push(gsap.to(S, { intro: 1, duration: 1.8, ease: "expo.out" }));     // 언덕이 아래에서 솟아오름
    // 레이아웃이 자리 잡은 뒤 스크롤 상자를 찾아 연결 (지도에서 돌아오면 맨 위부터)
    requestAnimationFrame(() => {
      const scroller = findScroller();
      scroller.scrollTop = 0;
      const tw = gsap.to(S, { p: 1, ease: "none", scrollTrigger: { trigger: wrap, scroller, start: "top top", end: "bottom bottom", scrub: 1 } });
      tweens.push(tw); st = tw.scrollTrigger;
    });
    const move = e => { S.tx = e.clientX / innerWidth * 2 - 1; S.ty = e.clientY / innerHeight * 2 - 1; };
    const leave = () => { S.tx = S.ty = 0; };
    stage.addEventListener("pointermove", move); stage.addEventListener("pointerleave", leave);
    offs.push(() => { stage.removeEventListener("pointermove", move); stage.removeEventListener("pointerleave", leave); });
    tick = (time, dt) => {
      const k = Math.min(1, dt * .005);
      S.mx += (S.tx - S.mx) * k; S.my += (S.ty - S.my) * k;
      S.run += dt * .07;                                                    // 기본 주행 속도 (px/ms)
      render();
    };
    gsap.ticker.add(tick);
  }
  let rz;
  const onResize = () => { clearTimeout(rz); rz = setTimeout(() => { build(); render(); if (!reduce) ScrollTrigger.refresh(); }, 150); };
  addEventListener("resize", onResize);
  offs.push(() => { removeEventListener("resize", onResize); clearTimeout(rz); });

  return () => {                                                            // 커버를 떠나면 모두 정리
    if (tick) gsap.ticker.remove(tick);
    if (st) st.kill();
    tweens.forEach(t => t.kill());
    scenes.kill();
    gsap.killTweensOf(INK);
    stage.removeEventListener("click", onClick);
    offs.forEach(f => f());
  };
}
"""

_COVER = st.components.v2.component("tram_cover", html=_HTML, css=_CSS, js=_JS)

# 커버에서만: Streamlit 머리줄·사이드바 숨기고 여백 없앰 (그림이 화면 전체를 덮음)
_PAGE_CSS = """<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], header[data-testid="stHeader"] { display: none; }
[data-testid="stMainBlockContainer"], .block-container { padding: 0 !important; max-width: none !important; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { gap: 0; }   /* 위쪽 스타일 요소와의 16px 틈 */
</style>"""


def _route(stations, route_paths):
    """정거장 표 → 노선 좌표 [lon, lat, 번호] (순환선 LOOP 순서, 지선은 route_paths 가 고른 순환선 정거장에서 시작)."""
    pos = {int(r.station_no): (round(float(r.lon), 6), round(float(r.lat), 6)) for r in stations.itertuples()}
    loop = [n for n in LOOP if n in pos]
    paths = route_paths(stations)
    branch = []
    if len(paths) > 1:
        b0 = tuple(round(v, 6) for v in paths[1][0])
        start = next((n for n in loop if pos[n] == b0), loop[0])
        branch = [start] + [n for n in BRANCH if n in pos]
    return {"loop": [[*pos[n], n] for n in loop], "branch": [[*pos[n], n] for n in branch]}


def render_cover(st, stations, route_paths, stats, open_about):
    """커버 화면. '지도 열기' 를 누르면 True. '분석 방법 보기' 는 분석 방법 창을 엶.
    stats: 스크롤하면 나오는 세 가지 분석의 수치 {rebound, base, low, high, n_scores}."""
    st.html(_PAGE_CSS)
    res = _COVER(key="cover", data={"route": _route(stations, route_paths), "stats": stats},
                 on_open_change=lambda: None, on_about_change=lambda: None)
    if res.about:
        open_about()
    return bool(res.open)
