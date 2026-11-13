

// ---------------------------------------------------------------- 커버 (시안 D)
const inst = new WeakMap();            // parentElement → 정리 함수 (다시 그려져도 한 번만 시작)

export function mountCover(rootEl, route, stats, onAct) {
  return start(rootEl, route, stats, (k) => onAct(k));
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
    const all = ROUTE.loop.concat(ROUTE.branch, ...(ROUTE.spurs || []));
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
    const loop = ROUTE.loop.map(P), branch = ROUTE.branch.map(P), spurs = (ROUTE.spurs || []).map(s => s.map(P));
    const pd = pts => "M" + pts.map(p => p.x.toFixed(1) + "," + p.y.toFixed(1)).join(" L");
    q(".routeLine").setAttribute("d", pd(loop.concat([loop[0]])) + " " + pd(branch) + spurs.map(s => " " + pd(s)).join(""));
    const rs = q(".routeStops"); rs.textContent = "";
    stopsEls = loop.concat(branch.slice(1), ...spurs.map(s => s.slice(1))).map(p => {
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
    tweens.push(gsap.from([q(".cv-hero .cv-tag"), q(".cv-hero .cv-sub"), q(".cv-hero .cv-actions")], { opacity: 0, y: 14, duration: .9, ease: "power3.out", stagger: .5, delay: .6 }));
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
