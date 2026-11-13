// 글 대신 보여 주는 작은 시각 부품 (2026-11-12 개편): 숫자 올라가기, 나타나기, 2x2 위치, 막대, 범위, 점 줄
import { useEffect, useState } from "react";
import { QC, QORDER, OUTSIDE, rgb, short } from "./lib.js";

const still = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** 0에서 값까지 올라가는 숫자 */
export function CountUp({ value, digits = 0, sign = false, suffix = "", dur = 700 }) {
  const [v, setV] = useState(still() ? value : 0);
  useEffect(() => {
    if (value == null || isNaN(value)) return;
    if (still()) { setV(value); return; }
    let raf, t0;
    const from = 0;
    const step = t => {
      t0 ??= t;
      const k = Math.min(1, (t - t0) / dur);
      setV(from + (value - from) * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  if (value == null || isNaN(value)) return <span>-</span>;
  const s = sign && value > 0 ? "+" : value < 0 ? "−" : "";
  return <span className="num">{s}{Math.abs(v).toFixed(digits)}{suffix}</span>;
}

/** 처음 그려질 때 살짝 떠오르며 나타남 (CSS 애니메이션, 화면 밖이어도 내용은 항상 보임) */
export function Reveal({ children, className = "", delay = 0, as: Tag = "div", style, ...rest }) {
  return <Tag className={`reveal ${className}`} style={{ ...style, animationDelay: `${delay}ms` }} {...rest}>{children}</Tag>;
}

/** 2x2: 가로 = 상대 위험 점수(0~100, 50 선), 세로 = 업종 변화 %p(가운데값 선). 속 빈 점 = 절대 쇠퇴 신호 없음 */
export function Quad2x2({ points, sel, median, onPick, big = false, label = "지금 위험과 업종 변화 위치" }) {
  const W = big ? 520 : 300, H = big ? 320 : 190, m = { l: 30, r: 10, t: 10, b: 26 };
  const ymax = Math.max(median * 2, ...points.map(p => p.y || 0)) * 1.08 || 1;
  const X = v => m.l + (Math.max(0, Math.min(100, v)) / 100) * (W - m.l - m.r);
  const Y = v => H - m.b - (Math.max(0, v) / ymax) * (H - m.t - m.b);
  const xc = X(50), yc = Y(median);
  const tint = q => `rgba(${QC[q].join(",")},0.10)`;
  const order = [...points].sort((a, b) => (a.key === sel) - (b.key === sel));
  return (
    <svg className="q2" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <rect x={m.l} y={m.t} width={xc - m.l} height={yc - m.t} fill={tint("변화 관찰")} />
      <rect x={xc} y={m.t} width={W - m.r - xc} height={yc - m.t} fill={tint("먼저 지원")} />
      <rect x={m.l} y={yc} width={xc - m.l} height={H - m.b - yc} fill={tint("정기 점검")} />
      <rect x={xc} y={yc} width={W - m.r - xc} height={H - m.b - yc} fill={tint("기존 지원 연계")} />
      <line x1={xc} x2={xc} y1={m.t} y2={H - m.b} className="q2-cut" />
      <line x1={m.l} x2={W - m.r} y1={yc} y2={yc} className="q2-cut" />
      {big && <>
        <text x={W - m.r - 4} y={m.t + 14} textAnchor="end" className="q2-q">먼저 지원</text>
        <text x={m.l + 4} y={m.t + 14} className="q2-q">변화 관찰</text>
        <text x={W - m.r - 4} y={H - m.b - 6} textAnchor="end" className="q2-q">기존 지원 연계</text>
        <text x={m.l + 4} y={H - m.b - 6} className="q2-q">정기 점검</text>
      </>}
      <text x={(m.l + W - m.r) / 2} y={H - 6} textAnchor="middle" className="q2-ax">지금 위험 → (50점 선)</text>
      <text x={10} y={(m.t + H - m.b) / 2} textAnchor="middle" className="q2-ax" transform={`rotate(-90 10 ${(m.t + H - m.b) / 2})`}>업종 변화 →</text>
      {order.map(p => {
        const on = p.key === sel, c = rgb(QC[p.q] || QC[OUTSIDE]);
        return (
          <g key={p.key} className={"q2-pt" + (on ? " on" : "")} style={{ transform: `translate(${X(p.x)}px,${Y(p.y)}px)` }}
            onClick={onPick ? () => onPick(p.key) : undefined} role={onPick ? "button" : undefined} aria-label={onPick ? p.name : undefined}>
            <title>{`${p.name} · 위험 ${Math.round(p.x)}점 · 업종 +${(p.y || 0).toFixed(2)}%p · ${p.q}`}</title>
            {on && <circle r={big ? 13 : 10} fill="none" stroke={c} strokeWidth="1.5" className="q2-ring" />}
            <circle r={on ? (big ? 7 : 6) : (big ? 5 : 3.6)} fill={p.hollow ? "#fff" : c} stroke={c} strokeWidth={p.hollow ? 1.6 : 0} />
            {(on || (big && p.label)) && <text x={9} y={-8} className={"q2-lb" + (on ? " on" : "")}>{short(p.name)}</text>}
          </g>
        );
      })}
    </svg>
  );
}

/** 가로 막대 + 기준선 */
export function Meter({ value, max = 100, cut, color = "var(--ink)", cutLabel }) {
  const w = v => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  return (
    <div className="meter" aria-hidden="true">
      <div className="meter-f" style={{ width: w(value ?? 0), background: color }} />
      {cut != null && <div className="meter-c" style={{ left: w(cut) }} title={cutLabel} />}
    </div>
  );
}

/** 범위 막대: 낮음~높음 띠 + 가운데 점 + 0 선 (확신 등급 '방향만'을 그림으로) */
export function RangeBar({ lo, mid, hi, min, max, unit = "%", labels = ["낮음", "기본", "높음"] }) {
  const a = Math.min(min ?? Math.min(lo, 0), lo), b = Math.max(max ?? Math.max(hi, 0), hi);
  const P = v => `${((v - a) / (b - a || 1)) * 100}%`;
  const fmt = v => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}${unit}`;
  const zeroIn = lo <= 0 && hi >= 0;
  return (
    <div className="rbar">
      <div className="rbar-track">
        {a < 0 && <div className="rbar-zero" style={{ left: P(0) }}><span>0</span></div>}
        <div className={"rbar-band" + (zeroIn ? " weak" : "")} style={{ left: P(lo), width: `calc(${P(hi)} - ${P(lo)})` }} />
        <div className="rbar-mid" style={{ left: P(mid) }} />
      </div>
      <div className="rbar-l">
        <span style={{ left: P(lo) }}>{labels[0]} {fmt(lo)}</span>
        <span style={{ left: P(mid) }} className="b">{labels[1]} {fmt(mid)}</span>
        <span style={{ left: P(hi) }}>{labels[2]} {fmt(hi)}</span>
      </div>
    </div>
  );
}

/** 점 n개 중 k개 채움 (절대 쇠퇴 신호 4가지 등) */
export function DotRow({ items }) {
  return (
    <ul className="dotrow">
      {items.map(([t, on]) => <li key={t} className={on ? "on" : ""}><i aria-hidden="true" />{t}</li>)}
    </ul>
  );
}

/** 등급 계단 (낮음·보통·높음 중 하나 강조) */
export function Steps({ steps, value, colors }) {
  return (
    <div className="steps" role="img" aria-label={`${value}`}>
      {steps.map((s, i) => <span key={s} className={s === value ? "on" : ""} style={s === value ? { background: colors?.[i], color: i === steps.length - 1 ? "#fff" : undefined } : undefined}>{s}</span>)}
    </div>
  );
}

/** 4칸 개수 카드 (누르면 지도 거르기) */
export function QCards({ counts, active, onPick, outside, desc }) {
  return (
    <div className="qcards" role="group" aria-label="진단 칸으로 거르기">
      {QORDER.map((q, i) => (
        <Reveal key={q} delay={i * 60} as="button" type="button" className="qcard" aria-pressed={active === q}
          onClick={() => onPick(active === q ? null : q)} style={{ "--qc": rgb(QC[q]) }}>
          <span className="qcard-n"><CountUp value={counts[q] || 0} /></span>
          <span className="qcard-t">{q}</span>
          {desc && <span className="qcard-d">{desc[q]}</span>}
        </Reveal>
      ))}
      {outside > 0 && <span className="qcard-out">비교 지역 {outside}</span>}
    </div>
  );
}
