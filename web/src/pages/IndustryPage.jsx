import { useMemo, useState } from "react";
import { Controls, Seg, Loading, QBadge } from "../ui.jsx";
import { useData, useApp, setState, go, view, short, scenLabel } from "../lib.js";

/** ai_comment.score_industries 와 같은 식: 항목 점수(0~100) 가중 평균, 건설 후는 성장·땅값 항목을 트램 반영 값으로 */
export function scoreIndustries(rows, weights, after, scen) {
  const w = Object.fromEntries(Object.entries(weights).filter(([k]) => k !== "tram"));
  const tot = Object.values(w).reduce((a, b) => a + b, 0) || 1;
  return rows.map(r => {
    let num = 0, den = 0;
    for (const [k, wk] of Object.entries(w)) {
      const col = after && r[`s_${k}_after_${scen}`] != null ? `s_${k}_after_${scen}` : `s_${k}`;
      const v = r[col];
      if (v != null && !isNaN(v)) { num += v * wk / tot * 100; den += wk / tot * 100; }
    }
    return { ...r, score: r.score_before == null || den === 0 ? null : Math.round(num / den * 10) / 10 };
  });
}

export default function IndustryPage() {
  const { data, error } = useData(["meta", "industry", "areas"]);
  if (!data) return <Loading error={error} />;
  return <Inner D={data} />;
}

function Inner({ D }) {
  const st = useApp();
  const { meta, industry, areas } = D;
  const W0 = useMemo(() => Object.fromEntries(industry.weights.filter(w => w.key !== "tram").map(w => [w.key, w.weight_before])), [industry]);
  const weights = st.weights && Object.keys(st.weights).length ? st.weights : W0;
  const [ind, setInd] = useState(industry.order[0]);
  const A = Object.fromEntries(areas.map(a => [a.code, a]));
  const before = scoreIndustries(industry.rows, weights, false, st.scen);
  const after = scoreIndustries(industry.rows, weights, true, st.scen);
  const B = Object.fromEntries(before.filter(r => r.industry === ind).map(r => [r.code, r.score]));
  const list = (st.tramAfter ? after : before).filter(r => r.industry === ind)
    .map(r => ({ code: r.code, name: A[r.code]?.name || r.name, now: B[r.code], score: r.score, n: r.n_stores }))
    .sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  const items = industry.weights.filter(w => w.key !== "tram");
  const changed = JSON.stringify(weights) !== JSON.stringify(W0);
  return (
    <div className="page">
      <Controls meta={meta} />
      <div className="page-h">
        <h1 className="page-t">업종 점수</h1>
        <p className="page-sub">업종마다 20개 상권을 100점으로 매겼습니다. 성장·규모·특화도·생존·땅값 흐름을 합친 상대 점수이고, 건설 후에는 트램이 닿는 상권만 성장·땅값 항목이 오릅니다.</p>
      </div>
      <div className="ctl">
        <div className="ctl-g"><span className="ctl-l">업종</span>
          <Seg label="업종" options={industry.order.map(i => [i, i])} value={ind} onChange={setInd} /></div>
      </div>
      <div className="split" style={{ gridTemplateColumns: "minmax(0,3fr) minmax(300px,1.3fr)" }}>
        <div className="tablewrap">
          <table className="t">
            <thead><tr><th>순위</th><th>상권</th><th>진단</th><th className="r">점포</th><th>{ind} 점수 {st.tramAfter ? `(건설 전 → 후, ${scenLabel(meta, st.scen)})` : "(건설 전)"}</th></tr></thead>
            <tbody>
              {list.map((r, i) => (
                <tr key={r.code} className={"click" + (r.score == null ? " dim" : "")} onClick={() => { setState({ sel: r.code, unit: "area" }); go("/map"); }}>
                  <td className="r">{r.score == null ? "-" : i + 1}</td>
                  <td>{short(r.name)}</td>
                  <td><QBadge q={view(A[r.code], st).quadrant} /></td>
                  <td className="r">{r.n ?? "-"}</td>
                  <td>{r.score == null ? <span className="muted small">점포 부족</span> : (
                    <div className="cellbar">
                      <span className="track" aria-hidden="true"><span className="b" style={{ width: `${(r.now || 0) * 1.4}px` }} />
                      {st.tramAfter && r.score > r.now && <span className="b after" style={{ width: `${(r.score - r.now) * 1.4}px` }} />}</span>
                      <span className="num">{Math.round(r.now)}{st.tramAfter && <> → <b>{Math.round(r.score)}</b></>}</span>
                    </div>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <aside className="box bone">
          <h3>가중치 바꿔 보기</h3>
          <p className="small muted" style={{ marginBottom: 10 }}>항목 비중을 바꾸면 순위가 바로 다시 계산됩니다. AI 해설 화면도 같은 가중치를 씁니다.</p>
          {items.map(w => (
            <div className="slider" key={w.key} title={`${w.method} — ${w.rationale}`}>
              <label htmlFor={"w-" + w.key}>{w.item}</label>
              <input id={"w-" + w.key} type="range" min="0" max="50" step="5" value={weights[w.key] ?? 0}
                onChange={e => setState({ weights: { ...weights, [w.key]: +e.target.value } })} />
              <span className="num">{weights[w.key] ?? 0}</span>
            </div>
          ))}
          <button type="button" className="btn ghost" style={{ marginTop: 12 }} disabled={!changed} onClick={() => setState({ weights: null })}>기본값으로</button>
          <details className="more" style={{ background: "transparent" }}>
            <summary>항목은 어떻게 계산하나</summary>
            <div><ul className="list small">{items.map(w => <li key={w.key}><b>{w.item}</b>: {w.method}. {w.limit && <span className="muted">한계: {w.limit}</span>}</li>)}</ul></div>
          </details>
        </aside>
      </div>
      <p className="src">출처: outputs/industry_scores.csv, industry_score_weights.csv · 행을 누르면 지도에서 그 상권이 열립니다</p>
    </div>
  );
}
