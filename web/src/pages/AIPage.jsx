import { useState, useEffect } from "react";
import { Loading, MD, QBadge } from "../ui.jsx";
import { useData, useApp, useRoute, setState, go, view, short } from "../lib.js";

const EXAMPLES = ["이 상권에서 카페를 열려는데 2030년 개통 전후 어느 시점이 나을까?",
  "임대료 부담 신호가 높다는데, 임차인은 계약할 때 무엇을 확인해야 해?",
  "공사 기간(2025~2028)에 매출 변화를 기록해 두려면 무엇을 어떻게 적어 두면 좋을까?",
  "이 상권과 옆 상권 중 소매업에 더 유리한 곳은 어디야?"];

export default function AIPage() {
  const { data, error } = useData(["ai", "areas"]);
  const st = useApp();
  const { q } = useRoute();
  const [asked, setAsked] = useState(null);
  useEffect(() => { if (q.area) setState({ sel: q.area, unit: "area" }); }, [q.area]);
  if (!data) return <Loading error={error} />;
  const { ai, areas } = data;
  const code = ai.areas[st.sel] ? st.sel : areas[0].code;
  const a = areas.find(x => x.code === code);
  const e = ai.areas[code];
  const v = view(a, { ...st, tramAfter: true, scen: "base" });
  const prompt = e.prompt + (asked ? `\n\n[이용자의 추가 질문]\n${asked}\n위 1~6번을 다 쓴 뒤 '7. 질문에 대한 답'을 덧붙여 3~5줄로 답해. 답도 위 정보와 지표 설명 안에서만 하고, 정보에 없는 것은 "이 분석에는 없는 내용"이라고 말해. 투자·매매 권유처럼 들리는 확정 표현은 쓰지 마.` : "");
  return (
    <div className="page">
      <div className="page-h">
        <h1 className="page-t">AI 상권 해설</h1>
        <p className="page-sub">진단·땅값 전망·업종 점수·임대료 신호를 AI에게 보내 받은 해설입니다. 숫자는 모두 이 분석의 결과이고, AI는 그것을 설명하는 역할만 합니다. 상권 담당자가 상인에게 설명할 때 쓸 수 있는 쉬운 말로 씁니다.</p>
      </div>
      <div className="ctl">
        <div className="ctl-g" style={{ minWidth: "min(420px,100%)" }}>
          <label className="ctl-l" htmlFor="ai-area">상권</label>
          <select id="ai-area" className="pick" style={{ border: "1px solid var(--mist)", borderRadius: 8, padding: "8px 10px", background: "#fff" }}
            value={code} onChange={ev => { setState({ sel: ev.target.value }); setAsked(null); }}>
            {areas.map(x => <option key={x.code} value={x.code}>{x.code} {x.name}</option>)}
          </select>
        </div>
        <div className="small" style={{ paddingBottom: 6 }}><QBadge q={v.quadrant} /> 상대 쇠퇴 위험 {Math.round(a.risk_score)}점 · 성장 가능 {Math.round(a.growth_score)}점
          {a.abs_decline && <> · 절대 쇠퇴 신호 {a.abs_decline}</>}</div>
      </div>

      <div className="split split-ai">
        <section className="panel" aria-label="해설">
          <div className="badges" style={{ marginTop: 0 }}>
            <span className="badge gray">기본 해설 {e.generated_at ? `(${String(e.generated_at).slice(0, 10)} 작성)` : ""}</span>
            <span className="where">기준: {ai.scenario} 시나리오 · 기본 업종 가중치</span>
          </div>
          {e.text ? <MD text={e.text} /> : <p className="muted">이 상권의 해설이 아직 없습니다.</p>}
          {asked && (
            <div className="notice warn" style={{ marginTop: 14 }}>
              <b>질문에 대한 맞춤 답은 실시간 연결 때만 받을 수 있습니다.</b> 이 공개 사이트에서는 AI 키를 보호하려고 실시간 호출을 열어 두지 않았습니다.
              발표 시연 앱에서는 아래 '보내는 글' 그대로 AI에게 보내 7번 항목으로 답을 받습니다.
            </div>
          )}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16 }}>
            <button type="button" className="btn ghost" onClick={() => go("/map", { area: code })}>지도에서 {short(a.name)} 보기</button>
          </div>
        </section>
        <aside className="box bone">
          <h2>추가 질문은 발표용 앱에서</h2>
          <p className="small" style={{ margin: "2px 0 8px" }}>이 공개 사이트는 AI에 실시간으로 질문을 보내지 않습니다. 위 기본 해설은 미리 써 두고 숫자를 대조한 글입니다. 발표용 앱에서는 아래 같은 질문을 덧붙여 AI의 답을 받을 수 있습니다.</p>
          <p className="small muted" style={{ margin: "0 0 6px" }}>예시를 누르면 AI에게 보내는 글에 어떻게 붙는지 아래 '보내는 정보와 글 보기'에서 볼 수 있습니다.</p>
          <div className="pills">{EXAMPLES.map(x => <button key={x} type="button" aria-pressed={asked === x} onClick={() => setAsked(x)}>{x}</button>)}</div>
          <p className="small muted" style={{ marginTop: 8 }}>AI 답은 참고용이며, 지원·보상이나 법률·계약에 관한 판단을 대신하지 않습니다.</p>
        </aside>
      </div>
      <details className="more">
        <summary>AI에게 보내는 정보와 글 보기</summary>
        <div>
          <p className="small muted">상권 정보 묶음(JSON)과 지표 설명·작성 형식이 한 글로 보내집니다{asked ? " (추가 질문 포함)" : ""}.</p>
          <pre className="prompt">{prompt}</pre>
        </div>
      </details>
      <p className="src">AI 해설은 분석 결과를 설명하는 참고 자료이며 투자·계약 판단의 근거가 아닙니다. 추정치는 '추정'으로 표시됩니다. 기본 해설은 앱이 보내는 것과 같은 글로 사전 작성한 뒤 숫자를 기계로 대조했습니다(보낸 정보에 없는 숫자 0개, 2026-11-06).</p>
    </div>
  );
}
