import { useMemo, useState, useRef, useId, useEffect } from "react";
import { marked } from "marked";
import { scaleLinear, scaleTime, scaleBand } from "d3-scale";
import { line as d3line, area as d3area } from "d3-shape";
import { useApp, setState, SCEN_ORDER, scenLabel, QHEX, QTXT } from "./lib.js";

marked.setOptions({ gfm: true, breaks: false });
export function MD({ text, inline = false, className = "md" }) {
  // '2009~2011' 같은 물결표를 지움줄(GFM ~) 로 읽지 않게
  const html = useMemo(() => { if (!text) return ""; const t = String(text).replace(/~/g, "\\~"); return inline ? marked.parseInline(t) : marked.parse(t); }, [text, inline]);
  return inline ? <span className={className} dangerouslySetInnerHTML={{ __html: html }} />
    : <div className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}

/** ? 설명: 누르거나(터치) 마우스를 올리거나 키보드로 고르면 화면 안에 맞춰 뜸. Esc 로 닫힘 */
export function Help({ tip }) {
  const [pos, setPos] = useState(null);
  const ref = useRef(null), id = useId();
  const open = () => {
    const b = ref.current.getBoundingClientRect(), w = Math.min(300, innerWidth - 24);
    const left = Math.max(12, Math.min(b.left + b.width / 2 - w / 2, innerWidth - w - 12));
    const below = b.bottom + 8, up = innerHeight - b.top + 8;
    setPos(b.bottom > innerHeight * 0.66 ? { left, bottom: up, width: w } : { left, top: below, width: w });
  };
  const close = () => setPos(null);
  useEffect(() => {
    if (!pos) return;
    const k = e => e.key === "Escape" && close();
    const out = e => { if (!ref.current?.contains(e.target)) close(); };
    addEventListener("keydown", k); addEventListener("scroll", close, true); addEventListener("pointerdown", out);
    return () => { removeEventListener("keydown", k); removeEventListener("scroll", close, true); removeEventListener("pointerdown", out); };
  }, [pos]);
  return (
    <>
      <button type="button" ref={ref} className="help" aria-label={"설명: " + tip} aria-expanded={!!pos} aria-describedby={pos ? id : undefined}
        onClick={e => { e.stopPropagation(); open(); }} onMouseEnter={open} onMouseLeave={close} onFocus={open} onBlur={close}>?</button>
      {pos && <span role="tooltip" id={id} className="tip" style={pos}>{tip}</span>}
    </>
  );
}

export function Seg({ options, value, onChange, big, disabled, label }) {
  return (
    <div className={"seg" + (big ? " big" : "")} role="group" aria-label={label}>
      {options.map(([k, t]) => (
        <button key={k} type="button" aria-pressed={value === k} disabled={disabled} onClick={() => onChange(k)}>{t}</button>
      ))}
    </div>
  );
}

/** 모든 분석 화면 맨 위: (보기 단위) · 트램 건설 전/후 · 시나리오 */
export function Controls({ meta, unit = false }) {
  const st = useApp();
  return (
    <div className="ctl">
      {unit && (
        <div className="ctl-g">
          <span className="ctl-l">보기 단위</span>
          <Seg label="보기 단위" options={[["area", "핵심 상권 20"], ["dong", "행정동 82"]]} value={st.unit} onChange={v => setState({ unit: v })} />
        </div>
      )}
      <div className="ctl-g">
        <span className="ctl-l">트램 2호선</span>
        <div className={"tramsw" + (st.tramAfter ? " after" : "")} role="group" aria-label="트램 2호선 건설 전·후">
          <button type="button" aria-pressed={!st.tramAfter} onClick={() => setState({ tramAfter: false })}>건설 전</button>
          <span className="rail" aria-hidden="true" />
          <button type="button" aria-pressed={st.tramAfter} onClick={() => setState({ tramAfter: true })}>건설 후</button>
        </div>
      </div>
      <div className="ctl-g">
        <span className="ctl-l">상권 가치 효과 시나리오 {!st.tramAfter && "· 건설 후에만"}</span>
        <Seg label="시나리오" options={SCEN_ORDER.map(s => [s, scenLabel(meta, s)])} value={st.scen} disabled={!st.tramAfter}
          onChange={v => setState({ scen: v })} />
      </div>
    </div>
  );
}

export function QBadge({ q }) {
  if (!q) return null;
  // 글자 대비 4.5:1 이상이 되도록 배지 바탕만 조금 진하게 (지도 색은 그대로)
  const bg = QHEX[q] || "#999";
  return <span className="badge" style={{ background: bg, color: QTXT[q] || "#fff" }}>{q}</span>;
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([k, t]) => <button key={k} role="tab" type="button" aria-selected={value === k} onClick={() => onChange(k)}>{t}</button>)}
    </div>
  );
}

// ── 차트 (SVG, d3 눈금) ──
const W = 560, H = 250, M = { t: 10, r: 14, b: 26, l: 40 };
function Axes({ x, y, xTicks, yTicks, xfmt = d => d, yfmt = d => d }) {
  return (
    <g className="ax">
      {yTicks.map(t => (
        <g key={"y" + t} transform={`translate(0,${y(t)})`}>
          <line x1={M.l} x2={W - M.r} strokeDasharray="2 3" />
          <text x={M.l - 6} dy="0.32em" textAnchor="end">{yfmt(t)}</text>
        </g>
      ))}
      {xTicks.map(t => <text key={"x" + t} x={x(t)} y={H - 8} textAnchor="middle">{xfmt(t)}</text>)}
    </g>
  );
}
export function Legend({ items }) {
  return (
    <div className="chart-lg">
      {items.map(([t, c, dash]) => <span key={t} style={{ color: c }}><i className={dash ? "dash" : ""} style={{ background: c }} /><span style={{ color: "var(--moss)" }}>{t}</span></span>)}
    </div>
  );
}

/** 땅값 전망: 실제(검정) + 추세(회색 점선) + 80% 띠 + 시나리오(남색) */
export function ForecastChart({ hist, fc, scen, after, openYear = 2030, showShare = true }) {
  if (!hist?.length || !fc?.length) return <p className="muted small">이 곳의 땅값 전망 결과가 없습니다.</p>;
  const h = hist.filter(d => d[0] >= 2015);
  const b = hist[hist.length - 1][1] / 100;
  const col = { low: 4, base: 5, high: 6 }[scen];
  const rows = fc.map(d => ({ y: d[0], base: d[1] * b, lo: d[2] * b, hi: d[3] * b, tram: d[col] * b }));
  const ys = [...h.map(d => d[1]), ...rows.flatMap(r => [r.lo, r.hi, r.tram])];
  const x = scaleLinear().domain([2015, rows[rows.length - 1].y]).range([M.l, W - M.r]);
  const y = scaleLinear().domain([Math.min(...ys), Math.max(...ys)]).nice().range([H - M.b, M.t]);
  const L = d3line().x(d => x(d[0])).y(d => y(d[1]));
  const A = d3area().x(d => x(d.y)).y0(d => y(d.lo)).y1(d => y(d.hi));
  const last = [h[h.length - 1][0], h[h.length - 1][1]];
  const end = rows[rows.length - 1];
  const share = after && end.base ? (end.tram / end.base - 1) * 100 : null;
  const T = d3area().x(d => x(d.y)).y0(d => y(d.base)).y1(d => y(d.tram));
  return (
    <div className="chart">
      <Legend items={[["실제", "#222"], ["추세 전망 (트램 없음)", "#9aa0a6", true], ...(after ? [["시나리오 (트램 건설 후)", "var(--tram-ink)"]] : [])]} />
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="땅값 지수 실제와 전망 (2015=100)">
        <Axes x={x} y={y} xTicks={x.ticks(6)} yTicks={y.ticks(5)} xfmt={d => d} />
        <path d={A(rows)} fill="#9aa0a6" opacity=".14" />
        {after && <path d={T(rows)} fill="var(--tram-ink)" opacity=".22" />}
        <path d={L([last, ...rows.map(r => [r.y, r.base])])} fill="none" stroke="#9aa0a6" strokeWidth="2.2" strokeDasharray="5 4" />
        {after && <path d={L([last, ...rows.map(r => [r.y, r.tram])])} fill="none" stroke="var(--tram-ink)" strokeWidth="2.5" />}
        <path d={L(h)} fill="none" stroke="#222" strokeWidth="2.5" />
        <line x1={x(openYear)} x2={x(openYear)} y1={M.t} y2={H - M.b} stroke="var(--route)" strokeDasharray="2 2" />
        <text x={x(openYear) + 4} y={M.t + 10} fontSize="12" fill="var(--route)">트램 개통</text>
        <text x={M.l} y={M.t - 1} fontSize="12" fill="var(--sage-gray)">지수 (2015=100)</text>
        {showShare && share != null && <text x={x(end.y)} y={y(end.tram) - 8} fontSize="12.5" fontWeight="600" textAnchor="end" fill="var(--tram-ink)">트램 몫 {share >= 0 ? "+" : ""}{share.toFixed(1)}% ({end.y})</text>}
      </svg>
    </div>
  );
}

/** 여러 선 (연도) */
export function LineChart({ series, events = [], yLabel }) {
  const all = series.flatMap(s => s.data);
  if (!all.length) return <p className="muted small">자료가 없습니다.</p>;
  const xs = all.map(d => d[0]), ys = all.map(d => d[1]);
  const x = scaleLinear().domain([Math.min(...xs), Math.max(...xs)]).range([M.l, W - M.r]);
  const y = scaleLinear().domain([Math.min(...ys), Math.max(...ys)]).nice().range([H - M.b, M.t]);
  const L = d3line().x(d => x(d[0])).y(d => y(d[1]));
  return (
    <div className="chart">
      <Legend items={series.map(s => [s.name, s.color])} />
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={yLabel}>
        <Axes x={x} y={y} xTicks={x.ticks(7).filter(Number.isInteger)} yTicks={y.ticks(5)} />
        {events.map((e, i) => (
          <g key={i}>
            <line x1={x(e.x)} x2={x(e.x)} y1={M.t} y2={H - M.b} stroke="#888" strokeDasharray="3 3"><title>{e.text}</title></line>
          </g>
        ))}
        {series.map(s => <path key={s.name} d={L(s.data)} fill="none" stroke={s.color} strokeWidth="2.5" />)}
        <text x={M.l} y={M.t - 1} fontSize="10.5" fill="var(--sage-gray)">{yLabel}</text>
      </svg>
    </div>
  );
}

/** 점포 수 (분기) + 수집 기준 변경 선 */
export function StoreChart({ data, breaks = [] }) {
  if (!data?.length) return <p className="muted small">자료가 없습니다.</p>;
  const pts = data.map(([p, n]) => [new Date(+p.slice(0, 4), +p.slice(4, 6) - 1, 1), n]);
  const x = scaleTime().domain([pts[0][0], pts[pts.length - 1][0]]).range([M.l, W - M.r]);
  const y = scaleLinear().domain([Math.min(...pts.map(d => d[1])), Math.max(...pts.map(d => d[1]))]).nice().range([H - M.b, M.t]);
  const L = d3line().x(d => x(d[0])).y(d => y(d[1]));
  const yt = x.ticks(8);
  return (
    <div className="chart">
      <Legend items={[["점포 수", "var(--chart-blue)"], ["수집 기준 변경", "#6b7860", true]]} />
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="분기별 점포 수">
        <Axes x={x} y={y} xTicks={yt} yTicks={y.ticks(5)} xfmt={d => d.getFullYear()} yfmt={d => d.toLocaleString("ko-KR")} />
        {breaks.map(b => { const d = new Date(+b.slice(0, 4), +b.slice(5, 7) - 1, 1); return <line key={b} x1={x(d)} x2={x(d)} y1={M.t} y2={H - M.b} stroke="#6b7860" strokeDasharray="4 3"><title>수집 기준 변경 (급변은 자료 탓일 수 있음)</title></line>; })}
        <path d={L(pts)} fill="none" stroke="var(--chart-blue)" strokeWidth="2.5" />
        {pts.map((d, i) => <circle key={i} cx={x(d[0])} cy={y(d[1])} r="2.2" fill="var(--chart-blue)"><title>{`${d[0].getFullYear()}-${String(d[0].getMonth() + 1).padStart(2, "0")}: ${d[1]}개`}</title></circle>)}
      </svg>
    </div>
  );
}

/** 업종 구성: 지금 vs 2034 (묶음 막대) */
export function CompChart({ groups, now, later }) {
  const x = scaleBand().domain(groups).range([M.l, W - M.r]).padding(0.25);
  const xi = scaleBand().domain(later ? ["now", "later"] : ["now"]).range([0, x.bandwidth()]).padding(0.08);
  const y = scaleLinear().domain([0, Math.max(...groups.map(g => Math.max(now[g] || 0, later?.[g] || 0)))]).nice().range([H - M.b, M.t]);
  return (
    <div className="chart">
      <Legend items={[["지금 (2026-06)", "#b8bfb3"], ...(later ? [["2034 (트램 건설 후)", "#7f4f24"]] : [])]} />
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="업종 구성 비중">
        <g className="ax">
          {y.ticks(5).map(t => <g key={t} transform={`translate(0,${y(t)})`}><line x1={M.l} x2={W - M.r} strokeDasharray="2 3" /><text x={M.l - 6} dy="0.32em" textAnchor="end">{t}%</text></g>)}
          {groups.map(g => <text key={g} x={x(g) + x.bandwidth() / 2} y={H - 8} textAnchor="middle">{g}</text>)}
        </g>
        {groups.map(g => (
          <g key={g} transform={`translate(${x(g)},0)`}>
            <rect x={xi("now")} width={xi.bandwidth()} y={y(now[g] || 0)} height={H - M.b - y(now[g] || 0)} fill="#b8bfb3" rx="2"><title>{`${g} 지금 ${(now[g] || 0).toFixed(1)}%`}</title></rect>
            {later && <rect x={xi("later")} width={xi.bandwidth()} y={y(later[g] || 0)} height={H - M.b - y(later[g] || 0)} fill="#7f4f24" rx="2"><title>{`${g} 2034 ${(later[g] || 0).toFixed(1)}%`}</title></rect>}
          </g>
        ))}
      </svg>
    </div>
  );
}

export function Loading({ error }) {
  return <div className="loading">{error ? `자료를 불러오지 못했습니다 (${error.message}). 새로 고쳐 주세요.` : "자료를 불러오는 중…"}</div>;
}
