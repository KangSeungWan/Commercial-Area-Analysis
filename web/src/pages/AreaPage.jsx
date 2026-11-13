// 상권 상세 (2026-11-12 새 화면): 숫자 타일 → 왜 이 칸인가(2x2) → 트램 뒤 업종·땅값 → 지켜볼 신호 → 흐름 그래프. 긴 글은 접어 둠
import { useMemo, useState, useEffect } from "react";
import { QBadge, Tabs, ForecastChart, LineChart, StoreChart, CompChart, Loading, MD, Help } from "../ui.jsx";
import { CountUp, Reveal, Quad2x2, Meter, RangeBar, DotRow, Steps } from "../viz.jsx";
import { TopControls } from "./MapPage.jsx";
import { useData, useApp, setState, go, useRoute, view, QC, QDESC, QDO, QNOTE, rgb, pct, int, short, ruleText, HELP, TRAM_DEF } from "../lib.js";

const NEED = ["meta", "areas", "dongs", "series_area", "series_dong", "composition", "ai"];
const ABS = ["점포 비중 10년 감소", "점포 비중 최근 3년 감소", "폐업률 대전 평균보다 높음", "폐업 > 개업"];
const ABS_SHORT = ["점포 비중 10년 ↓", "점포 비중 3년 ↓", "폐업률 > 대전 평균", "폐업 > 개업"];

export default function AreaPage() {
  const { data, error } = useData(NEED);
  if (!data) return <Loading error={error} />;
  return <AreaInner D={data} />;
}

function AreaInner({ D }) {
  const st = useApp();
  const { q } = useRoute();
  const dong = q.dong ? true : q.area ? false : st.unit === "dong";
  const rows = dong ? D.dongs : D.areas;
  const keyOf = r => (dong ? r.dong_id : r.code);
  const M = useMemo(() => Object.fromEntries(rows.map(r => [keyOf(r), r])), [rows]);
  const key = (dong ? q.dong : q.area) || (dong ? st.selDong : st.sel) || keyOf(rows.find(r => r.quadrant_after === "먼저 지원") || rows[0]);
  const r = M[key] || rows[0];
  const k = keyOf(r);
  useEffect(() => { setState(dong ? { selDong: k, unit: "dong" } : { sel: k, unit: "area" }); }, [k, dong]);
  const v = view(r, st);
  const name = dong ? r.dong : short(r.name);
  const pts = rows.filter(x => x.policy_target).map(x => ({ key: keyOf(x), name: dong ? x.dong : x.name, x: x.risk_score, y: x.change_pp,
    q: view(x, st).quadrant, hollow: !["있음", "강함"].includes(x.abs_decline), label: x.quadrant_after === "먼저 지원" }));
  const ser = dong ? D.series_dong : D.series_area;
  const comp = D.composition.data[`${dong ? "행정동" : "상권"}|${k}`];
  const order = dong ? [...rows].sort((a, b) => (a.si + a.dong).localeCompare(b.si + b.dong, "ko")) : rows;
  const absWhy = r.abs_decline_why || "";
  const ai = !dong ? D.ai.areas?.[k] : null;
  const [tab, setTab] = useState("fc");

  return (
    <div className="page area">
      <div className="area-top">
        <button type="button" className="linkbtn" onClick={() => go("/map")}>← 지도</button>
        <select aria-label="곳 고르기" value={k} onChange={e => go("/area", dong ? { dong: e.target.value } : { area: e.target.value })}>
          {order.map(x => <option key={keyOf(x)} value={keyOf(x)}>{dong ? x.name : `${x.code} ${x.name}`}</option>)}
        </select>
        <TopControls unit={false} />
      </div>

      <Reveal as="header" className="area-hero" style={{ "--qc": rgb(QC[v.quadrant] || QC["비교 지역"]) }}>
        <div className="area-hero-l">
          <span className="code">{dong ? r.si : `${r.code} · ${r.gu}`}</span>
          <h1 className="area-name">{name}</h1>
          <div className="badges"><QBadge q={v.quadrant} />{r.quadrant_uncertain && r.policy_target && <span className="badge warn">불확실 {Math.round(r.quadrant_stability * 100)}%</span>}</div>
        </div>
        <div className="area-hero-r">
          <p className="hero-desc">{QDESC[v.quadrant]}</p>
          {r.policy_target && <p className="hero-do">할 일 · <b>{QDO[v.quadrant]}</b></p>}
        </div>
      </Reveal>

      <div className="tiles">
        <Reveal className="tile" delay={0}><span className="l">지금 위험 <Help tip={HELP.risk} /></span><b><CountUp value={r.risk_score} /></b><span className="u">/ 100점</span>
          <Meter value={r.risk_score} cut={50} color={r.risk_high ? rgb(QC["먼저 지원"]) : "var(--sage-mist)"} /><span className="s">50점 선</span></Reveal>
        <Reveal className="tile" delay={60}><span className="l">절대 쇠퇴 신호 <Help tip={HELP.abs} /></span><b><CountUp value={r.abs_decline_n ?? 0} /></b><span className="u">/ 4 · {r.abs_decline}</span>
          <div className="pips" aria-hidden="true">{ABS.map(t => <i key={t} className={absWhy.includes(t) ? "on" : ""} />)}</div></Reveal>
        <Reveal className="tile" delay={120}><span className="l">업종 변화 (2034 추정) <Help tip={HELP.comp} /></span><b><CountUp value={st.tramAfter ? r.change_pp : 0} digits={2} sign /></b><span className="u">%p</span>
          <Meter value={st.tramAfter ? r.change_pp : 0} max={Math.max(3.5, r.change_pp || 0)} cut={st.tramAfter ? r.change_median : null} color={rgb(QC["변화 관찰"])} /><span className="s">세로선 = 가운데값</span></Reveal>
        <Reveal className="tile" delay={180}><span className="l">가까운 정거장</span><b><CountUp value={r.nearest_tram_m} /></b><span className="u">m · {r.nearest_tram ? `${r.nearest_tram}번` : "-"}</span>
          <Meter value={(dong ? r.tram500_share : r.in500) * 100} color="var(--route)" /><span className="s">점포 {Math.round((dong ? r.tram500_share : r.in500) * 100)}%가 500m 안</span></Reveal>
      </div>

      <div className="cards2">
        <Reveal className="card">
          <h2 className="card-h">왜 이 칸인가</h2>
          {r.policy_target ? <Quad2x2 big points={pts} sel={k} median={r.change_median ?? 0} onPick={x => go("/area", dong ? { dong: x } : { area: x })} />
            : <p className="muted">트램 노선 밖이라 분류하지 않는 비교 지역입니다.</p>}
          <p className="cap">{ruleText(r, st.tramAfter)}</p>
          {r.policy_target && <p className="cap muted">속 빈 점 = 절대 쇠퇴 신호 없음(위험 점수가 높아도 '낮음'으로 봄) · 점을 누르면 그곳으로</p>}
        </Reveal>
        <Reveal className="card" delay={80}>
          <h2 className="card-h">트램 뒤 가게 종류 <span className="tag">추정</span></h2>
          {comp ? <CompBlock comp={comp} groups={D.composition.groups} st={st} /> : <p className="muted">자료 없음</p>}
          <p className="cap muted">1호선 역 주변에서 확실히 바뀐 것은 카페 → 이 곳에 같은 비율을 적용</p>
        </Reveal>
        <Reveal className="card">
          <h2 className="card-h">땅값 <span className="tag">방향만</span> <Help tip={TRAM_DEF} /></h2>
          <RangeBar lo={r.tram_effect_low ?? 0} mid={r.tram_effect ?? 0} hi={r.tram_effect_high ?? 0} min={0} />
          <p className="cap muted">개통 초기 1~4년, 상권 전체로 편 값 · 기본값의 95% 구간이 0을 포함</p>
        </Reveal>
        <Reveal className="card" delay={80}>
          <h2 className="card-h">지켜볼 신호</h2>
          <div className="sig">
            <span className="l">임대료 부담 신호 <Help tip={HELP.rent} /></span>
            <Steps steps={["낮음", "보통", "높음"]} value={v.rent} colors={["#ddd0ea", "#a678c6", "#6a2a8c"]} />
            {v.rent === "해당 없음" && <span className="s">트램 효과가 거의 없는 곳</span>}
          </div>
          <div className="sig"><span className="l">절대 쇠퇴 신호</span><DotRow items={ABS.map((t, i) => [ABS_SHORT[i], absWhy.includes(t)])} /></div>
          {(r.sens || (!dong && ["A03", "A04"].includes(r.code)) || r.dev) && <ul className="flags">
            {r.sens && <li>⚑ 정거장 위치에 민감</li>}
            {!dong && ["A03", "A04"].includes(r.code) && <li>■ 전통시장 — 카드매출로 측정 부족</li>}
            {r.dev && <li>⌂ 개발지 — 트램 없어도 오르는 곳</li>}
          </ul>}
        </Reveal>
      </div>

      <Reveal className="card wide">
        <Tabs value={tab} onChange={setTab} tabs={[["fc", "땅값 전망"], ["land", "땅값 흐름"], ["store", "점포 수"]]} />
        {tab === "fc" && <ForecastChart hist={ser.land[k]} fc={ser.fc[k]} scen={st.scen} after={st.tramAfter} showShare={false} />}
        {tab === "land" && <LineChart yLabel="지수 (2015=100)" series={[{ name, color: "var(--chart-blue)", data: ser.land[k] || [] }, { name: "대전 전체", color: "#9aa0a6", data: D.series_area.land.ALL || [] }]}
          events={(r.events || []).map(e => ({ x: +e.date.slice(0, 4) + (+e.date.slice(5, 7)) / 12, text: `${e.date} ${e.text}` }))} />}
        {tab === "store" && <StoreChart data={ser.store[k]} breaks={D.series_area.breaks} />}
      </Reveal>

      <div className="folds">
        {ai && <details className="fold"><summary>AI 쉬운 해설 <span className="muted small">AI가 쓴 참고 글</span></summary><div className="fold-in"><MD text={ai.text} /></div></details>}
        {r.events?.length > 0 && <details className="fold"><summary>과거 사건 {r.events.length}개</summary>
          <ol className="timeline">{r.events.map(e => <li key={e.date + e.text}><time>{e.date.slice(0, 7)}</time><span>{e.text}</span></li>)}</ol></details>}
        <details className="fold"><summary>숫자 더 보기</summary>
          <dl className="kv">
            <dt>점포 수 (2026-06)</dt><dd>{int(r.n_stores)}</dd>
            <dt>대전 내 점포 비중 5년</dt><dd>{pct(r.store_share_chg_5y_pct)}</dd>
            <dt>땅값 5년 상승률</dt><dd>{pct(r.land_chg_5y_pct)}</dd>
            {(r.top3_mid || r.top3) && <><dt>주요 업종</dt><dd>{r.top3_mid || r.top3}</dd></>}
            {r.rent_market && <><dt>임대 시장(부동산원)</dt><dd>공실률 {r.rent_market.vac?.toFixed(1)}% · 임대가격지수 2022→2026 {pct(r.rent_market.idx)}</dd></>}
            {r.bad_pct != null && <><dt>2021 실태조사</dt><dd>매출·이익 감소 {Math.round(r.decline_pct)}% (대전 평균 74%, 코로나 시기)</dd></>}
            <dt>진단 안정도</dt><dd>{Math.round((r.quadrant_stability ?? 1) * 100)}% (10가지 계산 변형 중 같은 칸)</dd>
          </dl>
        </details>
      </div>
      <p className="src">{QNOTE} 투자·임대·계약 판단의 근거로 쓰지 마세요.</p>
    </div>
  );
}

function CompBlock({ comp, groups, st }) {
  const tot = comp.n_stores;
  const now = Object.fromEntries(groups.map(g => [g, (comp.n[g] || 0) / tot * 100]));
  const ad = comp.add?.[st.scen] || { cafe: 0, bakery: 0 };
  const tot34 = tot + ad.cafe + ad.bakery;
  const later = st.tramAfter ? Object.fromEntries(groups.map(g => [g, ((comp.n[g] || 0) + (g === "카페" ? ad.cafe : g === "빵·과자" ? ad.bakery : 0)) / tot34 * 100])) : null;
  return <>
    <div className="bignum">카페 <b>+<CountUp value={st.tramAfter ? ad.cafe : 0} /></b>곳 <span className="muted small">2034, 트램 없을 때보다</span></div>
    <CompChart groups={groups} now={now} later={later} />
  </>;
}
