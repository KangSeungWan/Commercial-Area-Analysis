import { Loading, Tabs, MD } from "../ui.jsx";
import { useData, useRoute, go, pct } from "../lib.js";

const TABS = [["story", "트램이 바꾸는 것"], ["evidence", "트램 효과 근거"], ["data", "데이터"], ["models", "분석·모델"], ["papers", "참고 논문"], ["limits", "검증·한계"]];

export default function AboutPage() {
  const { data, error } = useData(["about", "meta"]);
  const { q } = useRoute();
  const tab = TABS.some(t => t[0] === q.tab) ? q.tab : "story";
  if (!data) return <Loading error={error} />;
  const { about: B, meta } = data;
  return (
    <div className="page">
      <div className="page-h">
        <h1 className="page-t">분석 방법</h1>
        <p className="page-sub">대전 트램 2호선(2030 개통 예정) 상권 분석 — 공공데이터로 과거 30년 변화를 학습하고, 대전 1호선 개통 전후 땅값으로 상권 가치(땅값) 기준 트램 효과 범위를 추정했습니다.</p>
      </div>
      <div className="rows3">
        <div className="stat"><span className="v">{pct(meta.scen.base.effect_pct)}</span><span className="l">상권 가치(땅값) 기준 트램 효과, 기본</span><span className="d">낮음 {pct(meta.scen.low.effect_pct)} · 높음 {pct(meta.scen.high.effect_pct)}</span></div>
        <div className="stat"><span className="v">{B.numbers.land_rmse || "-"}</span><span className="l">땅값 1년 예측 오차</span><span className="d">{B.numbers.land_best || ""}</span></div>
        <div className="stat"><span className="v">{B.numbers.k || "-"}개</span><span className="l">상권 유형 (K-means)</span><span className="d">안정성 ARI {B.numbers.ari}</span></div>
        <div className="stat"><span className="v">20 · 82</span><span className="l">핵심 상권 · 행정동</span><span className="d">격자 293개</span></div>
      </div>
      <Tabs value={tab} onChange={k => go("/about", { tab: k })} tabs={TABS} />
      {tab === "story" && <section>
        <p className="lead" style={{ marginBottom: 6 }}><b>1호선 주변에서 확실히 달라진 것은 카페였습니다.</b> 땅값은 오르는 방향이지만 크기는 불확실하고, 가게당 매출이 땅값만큼 따라 오른 증거는 없었습니다. 임대료 상승과 공사 피해는 아직 확인되지 않았습니다.</p>
        <p className="small muted">확신 등급 — 확실: p&lt;0.01이고 두 가지 이상 검사를 통과, 다중 검정 보정 뒤에도 남음 · 방향만: 방향은 같지만 크기의 95% 구간이 0을 포함 · 확인 안 됨: 유의하지 않거나 과거 자료와 맞지 않음. 반대·약화 결과는 늘 같은 자리에 둠.</p>
        {B.story.map(s => (
          <article className="card-story" key={s.what}>
            <div><h3>{s.what}</h3><span className="vd">{s.verdict}</span>{s.grade && <span className="vd">확신 등급: {s.grade}</span>}</div>
            <dl><dt>어떻게</dt><dd><MD inline text={s.how} /></dd><dt>결과</dt><dd><MD inline text={s.result} /></dd>
              {s.counter && <><dt>반대·약화 결과</dt><dd><MD inline text={s.counter} /></dd></>}
              <dt>한계</dt><dd className="muted"><MD inline text={s.limit} /></dd></dl>
          </article>
        ))}
      </section>}
      {tab === "evidence" && <section>
        {B.meta && <p className="lead" style={{ marginBottom: 12 }}>해외 트램·경전철 땅값 효과 메타분석 {B.meta.k}곳: 평균 <b>{pct(B.meta.mu)}</b> (95% {B.meta.lo.toFixed(1)}~{B.meta.hi.toFixed(1)}%). 비교군이 있는 연구는 부동산 +3~12%, 점포 수보다 업종 구성·가게 수명이 바뀌고, 효과는 몇 년 뒤 커지며, 공사 기간 손실은 거의 모든 도시에서 확인됩니다.</p>}
        <div className="grid2" style={{ marginBottom: 18 }}>
          <figure><img src="./data/img/tram_meta_forest.png" alt="해외 트램·경전철 개통 효과와 대전 값 비교 그림" loading="lazy" /><figcaption>해외 트램·경전철 개통 효과와 대전 값 비교</figcaption></figure>
          <figure><img src="./data/img/landprice_line1_es.png" alt="대전 1호선 개통 전후 역 500m 땅값 사건연구 그림" loading="lazy" /><figcaption>대전 1호선 개통 전후 역 500m 안 땅값 (사건연구)</figcaption></figure>
          <figure><img src="./data/img/line1_permits_sector.png" alt="대전 1호선 역 주변 업종별 인허가 변화 그림" loading="lazy" /><figcaption>대전 1호선 역 주변 업종별 인허가 (카페가 가장 큼)</figcaption></figure>
          <figure><img src="./data/img/tram_distance_bands.png" alt="역에서 거리별 땅값 효과 그림" loading="lazy" /><figcaption>역에서 거리별 효과 (가까울수록 큼)</figcaption></figure>
        </div>
        <div className="tablewrap"><table className="t"><thead><tr><th>분야</th><th>사례</th><th>무엇을 쟀나</th><th>결과</th><th>비교군</th><th>출처</th></tr></thead>
          <tbody>{B.overseas.map((r, i) => <tr key={i}><td className="small">{r.kind}</td><td><b style={{ fontWeight: 600 }}>{r.case}</b></td><td className="small">{r.what}</td><td className="small">{r.result}</td><td className="small">{r.control}</td>
            <td className="small">{r.url ? <a href={r.url} target="_blank" rel="noopener noreferrer">{r.source}</a> : r.source}</td></tr>)}</tbody></table></div>
      </section>}
      {tab === "data" && <Table cols={[["name", "데이터"], ["source", "출처"], ["period", "기간"], ["size", "규모"], ["use", "쓰인 곳"]]} rows={B.data} />}
      {tab === "models" && <>
        <Table cols={[["goal", "목적"], ["method", "방법·모델"], ["result", "핵심 결과"], ["check", "검증"]]} rows={B.models} />
        <p className="src">흐름: 원본 → 상권·행정동·격자 패널 → 효과 추정(이중차분) → 유형(K-means) → 예측(ARIMA 등) → 트램 시나리오 → 진단 점수 → 지도</p>
        <h3 style={{ fontSize: 16, margin: "18px 0 6px" }}>쓴 도구</h3>
        <Table cols={[["use", "용도"], ["fw", "프레임워크"], ["where", "쓴 곳"]]} rows={B.frameworks} />
        <p className="src">{B.why}</p>
      </>}
      {tab === "papers" && <Table cols={[["tag", ""], ["paper", "논문"], ["use", "이 분석에서 쓴 내용"]]} rows={B.papers} />}
      {tab === "limits" && <section className="box"><ul className="list">{B.limits.map((x, i) => <li key={i}><MD inline text={x} /></li>)}</ul>
        <p className="src" style={{ marginTop: 12 }}>{B.other_sectors}</p></section>}
      <p className="src">코드: tram_model/ (run_all.py 로 전체 재현) · 웹 자료: tram_model/export_web.py</p>
    </div>
  );
}

function Table({ cols, rows }) {
  return (
    <div className="tablewrap"><table className="t"><thead><tr>{cols.map(([k, t]) => <th key={k}>{t}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{cols.map(([k]) => <td key={k} className={k === "name" || k === "goal" || k === "tag" ? "" : "small"}>
        {k === "name" || k === "goal" ? <b style={{ fontWeight: 600 }}>{r[k]}</b> : <MD inline text={r[k]} />}</td>)}</tr>)}</tbody></table></div>
  );
}
