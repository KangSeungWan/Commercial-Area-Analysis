// 근거 (2026-11-12 새 화면): 다섯 가지 결과를 확신 등급 카드 + 범위 그림으로. 글은 접어 둠, 전체는 '분석 방법'
import { Loading, MD } from "../ui.jsx";
import { CountUp, Reveal, RangeBar } from "../viz.jsx";
import { useData, go } from "../lib.js";

const GRADE = { "확실": ["#1e7d4a", "#fff"], "방향만": ["#eb8214", "#0a1d08"], "확인 안 됨": ["#c9cec4", "#0a1d08"] };
const num = s => (s == null ? null : parseFloat(String(s).replace(/[−–]/g, "-").replace(/[^\d.\-+]/g, "")));

export default function EvidencePage() {
  const { data, error } = useData(["about", "meta"]);
  if (!data) return <Loading error={error} />;
  const B = data.about, N = B.numbers;
  const S = i => B.story.find(s => s.what.startsWith("①②③④⑤"[i])) || {};
  const ci = String(N.base_ci || "").split("~").map(num);
  const cafe = (S(1).result || "").match(/카페 수 ([+\-−]?[\d.]+)% \[([\-−]?[\d.]+), ([\-−]?[\d.]+)\]/);
  const sales = (S(2).result || "").match(/땅값 \+?([\d.]+)% 차이 vs 점포당 매출 \+?([\d.]+)%/);
  const con = (B.construction || []).find(c => c["결과"] === "전체 카드매출");
  const vis = [
    ci.length === 2 && !isNaN(ci[0]) ? { big: num(N.pool), unit: "%", rb: [ci[0], num(N.pool), ci[1]], lab: ["하한", "합산", "상한"], cap: "1호선 역 500m 땅값 · 95% 구간이 0을 지남" } : null,
    cafe ? { big: num(cafe[1]), unit: "%", rb: [num(cafe[2]), num(cafe[1]), num(cafe[3])], lab: ["하한", "효과", "상한"], cap: "1호선 역 500m 카페 수 · 구간 전체가 0보다 큼" } : null,
    sales ? { pair: [["땅값", num(sales[1])], ["점포당 매출", num(sales[2])]], cap: "1호선 역세권, 같은 곳의 차이" } : null,
    { text: "지켜볼 곳", cap: "임대료 상승을 미리 알려 주지 못함(전국 53개 상권 검사)" },
    con ? { big: con["효과_퍼센트"], unit: "%", rb: [con["하한"], con["효과_퍼센트"], con["상한"]], lab: ["하한", "효과", "상한"], cap: `공사 구간 ${con["처리_동"]}개 동 카드매출 · 0을 지남` } : null,
  ];
  return (
    <div className="page">
      <div className="page-h">
        <h1 className="page-t">근거</h1>
        <p className="page-sub">대전 1호선(2006) 전후를 재서 확실한 것만 확실하다고 표시합니다.</p>
      </div>
      <div className="grades">{Object.entries(GRADE).map(([g, [bg, fg]]) => <span key={g} className="grade" style={{ background: bg, color: fg }}>{g}</span>)}
        <span className="muted small">확실 = 여러 검사 통과 · 방향만 = 95% 구간이 0을 포함 · 확인 안 됨 = 유의하지 않음</span></div>
      <div className="ev-grid">
        {B.story.map((s, i) => {
          const g = GRADE[s.grade] || GRADE["확인 안 됨"], x = vis[i];
          return (
            <Reveal key={s.what} className={"ev" + (s.grade === "확실" ? " sure" : "")} delay={i * 70} style={{ "--gc": g[0] }}>
              <div className="ev-h"><span className="ev-what">{s.what.replace(/^[①-⑤]\s*/, "")}</span><span className="grade" style={{ background: g[0], color: g[1] }}>{s.grade}</span></div>
              <div className="ev-verdict">트램은 <b>{s.verdict}</b></div>
              {x?.big != null && <div className="ev-big"><CountUp value={x.big} digits={1} sign suffix={x.unit} /></div>}
              {x?.rb && <RangeBar lo={x.rb[0]} mid={x.rb[1]} hi={x.rb[2]} labels={x.lab} />}
              {x?.pair && <div className="pair">{x.pair.map(([t, val], j) => (
                <div key={t} className="pair-r"><span>{t}</span><div className="pair-b"><div style={{ width: `${(val / Math.max(...x.pair.map(p => p[1]))) * 100}%`, background: j ? "#c9cec4" : "var(--tram-ink)" }} /></div><b>+<CountUp value={val} />%</b></div>))}</div>}
              {x?.text && <div className="ev-big txt">{x.text}</div>}
              {x?.cap && <p className="cap muted">{x.cap}</p>}
              <details className="fold mini"><summary>어떻게 쟀나 · 반대 결과 · 한계</summary>
                <dl className="kv"><dt>어떻게</dt><dd><MD inline text={s.how} /></dd><dt>결과</dt><dd><MD inline text={s.result} /></dd>
                  {s.counter && <><dt>반대·약화</dt><dd><MD inline text={s.counter} /></dd></>}<dt>한계</dt><dd><MD inline text={s.limit} /></dd></dl>
              </details>
            </Reveal>
          );
        })}
      </div>
      <div className="ev-more">
        <figure><img src="./data/img/line1_permits_sector.png" alt="대전 1호선 역 주변 업종별 인허가 변화 그림" loading="lazy" /><figcaption>업종별 변화 — 카페가 가장 큼</figcaption></figure>
        <figure><img src="./data/img/landprice_line1_es.png" alt="대전 1호선 개통 전후 역 500m 땅값 사건연구 그림" loading="lazy" /><figcaption>개통 전후 역 500m 땅값</figcaption></figure>
      </div>
      <button type="button" className="btn ghost" onClick={() => go("/about")}>분석 방법 전체 보기 →</button>
    </div>
  );
}
