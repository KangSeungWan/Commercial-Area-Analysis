import { useMemo, useState, useEffect } from "react";
import MapView, { centroid } from "../MapView.jsx";
import { Controls, Seg, Help, QBadge, Tabs, ForecastChart, LineChart, StoreChart, CompChart, Loading } from "../ui.jsx";
import { useData, useApp, setState, go, useRoute, view, METRICS, metricLabel, colorize, QC, QHEX, RENT_C, rgb, pct, pp, int, eok, short,
  scenLabel, TRAM_DEF, HELP, ruleText, f1 } from "../lib.js";

const NEED = ["meta", "areas", "dongs", "geo_core", "geo_regions", "geo_dongs", "series_area", "series_dong", "composition"];

export default function MapPage() {
  const { data, error } = useData(NEED);
  if (!data) return <Loading error={error} />;
  return <MapInner D={data} />;
}

function MapInner({ D }) {
  const st = useApp();
  const { q } = useRoute();
  const { meta, areas, dongs } = D;
  const dong = st.unit === "dong";
  const sl = scenLabel(meta, st.scen);
  const A = useMemo(() => Object.fromEntries(areas.map(a => [a.code, a])), [areas]);
  const DG = useMemo(() => Object.fromEntries(dongs.map(d => [d.dong_id, d])), [dongs]);
  const rows = dong ? dongs : areas;
  const keyOf = r => (dong ? r.dong_id : r.code);
  const V = useMemo(() => Object.fromEntries(rows.map(r => [keyOf(r), view(r, st)])), [rows, st.tramAfter, st.scen, dong]);
  const reb = rows.filter(r => r.quadrant_after === "트램 반등 기회").sort((a, b) => b.risk_score - a.risk_score).map(keyOf);

  // 처음 선택: 주소 → 저장값 → 반등 기회 위험 1위
  useEffect(() => {
    if (q.area && A[q.area] && q.area !== st.sel) setState({ sel: q.area, unit: "area" });
    else if (!st.sel || !A[st.sel]) {
      const r0 = areas.filter(a => a.quadrant_after === "트램 반등 기회").sort((a, b) => b.risk_score - a.risk_score)[0];
      setState({ sel: (r0 || areas[0]).code });
    }
    if (!st.selDong || !DG[st.selDong]) {
      const d0 = dongs.filter(a => a.quadrant_after === "트램 반등 기회").sort((a, b) => b.risk_score - a.risk_score)[0];
      setState({ selDong: (d0 || dongs[0]).dong_id });
    }
  }, [q.area]);
  const selKey = dong ? st.selDong : st.sel;
  const pick = k => setState(dong ? { selDong: k } : { sel: k });

  // ── 색 ──
  const m = st.metric in METRICS ? st.metric : "quadrant";
  const M = METRICS[m];
  const keys = rows.map(keyOf);
  let fill = {}, legend;
  if (M.kind === "cat") {
    keys.forEach(k => { fill[k] = QC[V[k].quadrant] || [200, 200, 200]; });
    legend = <CatLegend label={metricLabel(m, st, sl)} items={Object.entries(QC).filter(([k]) => st.tramAfter || k !== "트램 반등 기회")} />;
  } else if (M.tram && !st.tramAfter) {
    keys.forEach(k => { fill[k] = [215, 218, 222]; });
    legend = <div className="lg"><b>{M.short}</b>&nbsp;트램이 생겨야 나타나는 변화라 건설 전에는 없음 (위에서 건설 후를 고르면 곳별 예상)</div>;
  } else if (M.kind === "cat_rent") {
    keys.forEach(k => { fill[k] = RENT_C[V[k].rent] || RENT_C["해당 없음"]; });
    legend = <CatLegend label={metricLabel(m, st, sl)} items={Object.entries(RENT_C)} />;
  } else {
    const vals = keys.map(k => (m in V[k] ? V[k][m] : (dong ? DG[k] : A[k])[m]));
    let center = null, span = null;
    if (M.kind === "divavg") center = meta.city.land_5y_pct;
    if (m === "land_fc") span = q95abs(rows.flatMap(r => [r.land_fc?.none, r.land_fc?.[st.scen]]));
    const c = colorize(vals, M.kind, center, span);
    keys.forEach((k, i) => { fill[k] = c.cols[i]; });
    legend = <BarLegend label={metricLabel(m, st, sl)} c={c} kind={M.kind} center={center} />;
  }
  const fillKey = `${m}|${st.tramAfter}|${st.scen}|${dong}`;

  // ── 지도 라벨 (상권 이름) ──
  const labels = useMemo(() => {
    if (dong) return null;
    return D.geo_core.features.map(f => {
      const k = f.properties.code, a = A[k];
      return { key: k, text: short(a.name), pos: centroid(f), pri: (k === st.sel ? 1e9 : 0) + (reb.includes(k) ? 1e6 : 0) + (a.n_stores || 0) };
    });
  }, [dong, st.sel, D.geo_core]);

  const tooltip = k => {
    const r = dong ? DG[k] : A[k]; if (!r) return null;
    const v = V[k];
    const val = m in v ? v[m] : r[m];
    const shown = typeof val === "string" ? val : val == null ? "-" : (+val).toFixed(1);
    const near = r.nearest_tram ? `가까운 트램 ${r.nearest_tram}번 정거장 · ${int(r.nearest_tram_m)}m` : "";
    return `<b>${dong ? r.name : r.code + " " + r.name}</b><br/><span style="color:${QHEX[v.quadrant] || "#666"}">●</span> ${v.quadrant || ""}<br/>${METRICS[m].short} <b>${shown}</b><br/><span style="color:#777">${near}</span>`;
  };
  const stationTip = s => `<b>${s.no}번 ${s.name}</b><br/>500m 안 점포 ${int(s.n_stores)}개<br/><span style="color:#777">누르면 500m 영향권 표시</span>`;

  return (
    <div className="page">
      <Controls meta={meta} unit />
      <Verdict D={D} st={st} dong={dong} reb={reb} V={V} A={A} DG={DG} rows={rows} selKey={selKey} pick={pick} />

      <div className="split">
        <div className="mapbox">
          <div className="metricsel">
            <span className="ctl-l">지도에 칠할 것</span>
            <Seg label="지도에 칠할 것" options={["quadrant", "tram_sel", "comp", "rent"].map(k => [k, METRICS[k].short])} value={m} onChange={v => setState({ metric: v })} />
            <span className="sep" aria-hidden="true" />
            <Seg label="참고 지표" options={["land_fc", "land_chg_5y_pct", "store_share_chg_5y_pct"].map(k => [k, METRICS[k].short])} value={m} onChange={v => setState({ metric: v })} />
          </div>
          <div className="maphead">
            {legend}
            <div className="sym">
              <span><span className={"ln" + (st.tramAfter ? "" : " plan")} />트램 2호선{st.tramAfter ? "" : " (계획)"}</span>
              <span><span className="st" />정거장</span>
              <span><span className="ln l1" />1호선</span>
            </div>
          </div>
          <MapView key={dong ? "dong" : "area"} keyProp={dong ? "dong_id" : "code"} base={dong ? null : D.geo_dongs}
            regions={dong ? null : D.geo_regions} showRegion={!dong && st.region} fitTo={D.geo_core} polys={dong ? D.geo_dongs : D.geo_core} polyAlpha={dong ? 200 : 225}
            fill={fill} fillKey={fillKey} sel={selKey} onPick={pick} stations={meta.stations} route={meta.route} line1={meta.line1}
            tramAfter={st.tramAfter} station={st.station} onStation={no => setState({ station: no })} tooltip={tooltip} stationTip={stationTip}
            labels={labels} showLabels={st.labels} ariaLabel={dong ? "행정동 82개 지도" : "핵심 상권 20개 지도"} />
          <div className="mapnote">
            {dong ? "행정동을 누르면 오른쪽에 진단 근거가 열립니다. " : "상권(진한 칸 = 점포가 모인 핵심 영역, 옅은 칸 = 그 상권 권역)을 누르면 오른쪽에 진단 근거가 열립니다. "}
            정거장을 누르면 500m 영향권이 표시됩니다.
            {!dong && <> <label style={{ marginLeft: 8 }}><input type="checkbox" checked={st.region} onChange={e => setState({ region: e.target.checked })} /> 권역 칠하기</label>
              <label style={{ marginLeft: 8 }}><input type="checkbox" checked={st.labels} onChange={e => setState({ labels: e.target.checked })} /> 이름</label></>}
          </div>
        </div>
        <div>
          {st.station != null && <StationCard D={D} no={st.station} A={A} pick={k => setState({ sel: k, unit: "area" })} />}
          {dong ? <DongPanel D={D} d={DG[st.selDong]} v={V[st.selDong]} st={st} /> : <AreaPanel D={D} a={A[st.sel]} v={V[st.sel]} st={st} />}
        </div>
      </div>
    </div>
  );
}

function q95abs(arr) {
  const v = arr.filter(x => x != null).map(Math.abs).sort((a, b) => a - b);
  return v.length ? v[Math.floor((v.length - 1) * .95)] : 1;
}
function CatLegend({ label, items }) {
  return <div className="lg"><b>{label}</b>{items.map(([n, c]) => <span key={n} className="it"><span className="dot" style={{ background: rgb(c) }} />{n}</span>)}</div>;
}
function BarLegend({ label, c, kind, center }) {
  const fmt = v => (Math.abs(c.hi) < 10 ? v.toFixed(1) : v.toFixed(0));
  let l, r;
  if (kind === "divavg") { l = `평균보다 낮음 ${pct(c.lo, 0)}`; r = `높음 ${pct(c.hi, 0)} · 흰색 = 대전 평균 ${pct(center)}`; }
  else if (kind.startsWith("div")) { l = `감소 ${pct(c.lo, 0)}`; r = `증가 ${pct(c.hi, 0)}`; }
  else { l = `낮음 ${fmt(c.lo)}`; r = `높음 ${fmt(c.hi)}+`; }
  return <div className="lg"><b>{label}</b><span>{l}</span><span className="bar" style={{ background: `linear-gradient(90deg,${c.stops.join(",")})` }} /><span>{r}</span></div>;
}

function Story({ D, st, dong, rows }) {
  const { meta } = D;
  if (!st.tramAfter) return <div className="story">트램 없이 흘러갈 때의 진단입니다. 위에서&nbsp;<b>건설 후</b>를 고르면 트램이 바꾸는 것(상권 가치 → 업종 → 임대료)을 볼 수 있습니다.</div>;
  const eff = pct(meta.scen[st.scen]?.effect_pct);
  const cafe = meta.city.cafe_add?.[st.scen];
  const reb = rows.filter(r => r.quadrant_after === "트램 반등 기회");
  const nhi = reb.filter(r => r.rent?.grade === "높음").length;
  const ar = <span className="ar" aria-hidden="true">→</span>;
  return (
    <div className="story">
      <span>① 트램은 <b>상권 가치</b>를 올리고(정거장 500m 땅값 {eff})</span>{ar}
      <span>② <b>업종</b>을 카페 쪽으로 바꾸지만{cafe != null && ` (2034 대전 카페 +${Math.round(cafe)}곳)`}</span>{ar}
      <span>③ <b>점포당 매출</b>은 덜 오릅니다{meta.sales_ratio != null && `(땅값 효과의 ${meta.sales_ratio.toFixed(2)}배)`}</span>{ar}
      <span>④ 반등 기회 {reb.length}곳 중 <b>{nhi}곳은 임대료 부담</b> 위험</span>{ar}
      <span>⑤ 시: 공사 중 매출 보전 → 개통 초 빈 점포 채우기 → 땅값 오른 뒤 상인 보호 · 상인: 계약 갱신을 개통(2030) 전후로</span>
    </div>
  );
}

function Verdict({ D, st, dong, reb, V, A, DG, rows, selKey, pick }) {
  const { meta } = D;
  const name = k => (dong ? DG[k].dong : short(A[k].name));
  const hi = st.tramAfter ? reb.filter(k => (dong ? DG[k] : A[k]).rent?.grade === "높음") : [];
  let head;
  if (st.tramAfter) head = `트램이 상권 가치를 올릴 위치의 쇠퇴 ${dong ? "행정동" : "상권"}(반등 기회) ${reb.length}곳`;
  else {
    const cnt = {}; reb.forEach(k => { const b = (dong ? DG[k] : A[k]).quadrant_before; cnt[b] = (cnt[b] || 0) + 1; });
    const e = Object.entries(cnt);
    head = e.length === 1 ? `트램이 없으면 이 ${reb.length}곳은 모두 ${e[0][0]}` : `트램이 없으면 이 ${reb.length}곳은 ` + e.map(([k, v]) => `${k} ${v}곳`).join(", ");
  }
  const cnt = {}; rows.forEach(r => { const k = V[dong ? r.dong_id : r.code].quadrant; cnt[k] = (cnt[k] || 0) + 1; });
  const avg = st.tramAfter && !dong ? rows.reduce((s, r) => s + (V[r.code].tram_sel || 0), 0) / rows.length : null;
  const moneyAll = dong ? rows.reduce((s, r) => s + (r.money?.[st.scen] || 0), 0) : meta.money_all?.[st.scen];
  const sens = dong ? rows.filter(r => r.sens).map(r => r.dong) : [];
  const dev = dong ? rows.filter(r => r.dev?.[0] === "개발지").map(r => r.dong) : [];
  return (
    <section aria-label="결론">
      <h1 className="verdict">{head}</h1>
      <div className="chips">
        {reb.map(k => (
          <button key={k} type="button" className="chip" aria-pressed={k === selKey} onClick={() => pick(k)}>
            {name(k)}{hi.includes(k) && <span className="warn" title="임대료 부담 신호 높음">⚠</span>}
          </button>
        ))}
      </div>
      <div className="kpi">
        {Object.keys(QC).filter(q => cnt[q]).map(q => <span key={q}><span className="dot" style={{ background: QHEX[q] }} />{q} <b>{cnt[q]}</b>곳</span>)}
        <span className="muted symkey">⚠ 임대료 신호 높음{dong && " · ⚑ 가정에 민감 · ⌂ 개발지"} · <span className="help" aria-hidden="true">?</span> 누르면 설명</span>
      </div>
      <details className="more">
        <summary>이야기 순서 ①~⑤ · 숫자 읽는 법</summary>
        <div className="more-in">
          <Story D={D} st={st} dong={dong} rows={rows} />
          {hi.length > 0 && (
        <p className="rentnote"><span className="dot" style={{ background: rgb(RENT_C["높음"]) }} />그중 <b>{hi.length}곳</b>은 임대료 부담 신호가 높음(⚠) = <b>조건부 기회</b>.
          땅값은 오르지만 점포당 매출은 거의 그대로일 곳이라, 건물주의 기회가 기존 상인의 기회가 되려면 개통 뒤 보호 장치가 필요합니다.</p>
      )}
          <div className="kpi">
            {avg != null && <span>상권 전체로 펴면 평균 <b>{pct(avg)}</b> (500m 안 {pct(meta.scen[st.scen].effect_pct)} × 500m 안 점포 비율)</span>}
            {st.tramAfter && moneyAll > 0 && <span>정거장 500m 안 땅값 <b>+{eok(moneyAll)}</b> (공시지가 기준, 개통 1~4년{dong ? ", 82개 동 합계" : ""})</span>}
            <button type="button" className="linkbtn" onClick={() => go("/about", { tab: "evidence" })}>트램 효과 근거 보기</button>
          </div>
      {sens.length > 0 && <p className="src">⚑ 정거장 추정 좌표에 따라 진단이 바뀔 수 있는 동: {sens.join(", ")} (좌표를 0~300m 옮겨 300번 다시 계산) · 핵심 상권 20곳은 모두 안정</p>}
      {dev.length > 0 && <p className="src">⌂ 신도시·택지 개발로 트램 없어도 오르는 동: {dev.join(", ")}{meta.city.dev_money != null && ` — 트램 효과 금액(기본)의 ${Math.round(meta.city.dev_money)}%가 이 동들에 있음`}{meta.city.dev_l1 != null && `. 1호선 효과는 개발지를 빼고 다시 계산해도 +${meta.city.dev_l1.toFixed(1)}%`}</p>}
      <p className="src">자료: {dong ? "행정동 진단·지표 (82개 동 안 상대 순위)" : "상권 진단·지표 (20개 상권 안 상대 순위)"} · 트램 효과 수준</p>
        </div>
      </details>
    </section>
  );
}

function WhyBox({ title, q, quadAfter, i5, r, extraFoot }) {
  const rows = [
    ["상대 쇠퇴 위험", `${Math.round(r.risk_score)}점`, r.risk_drivers, HELP.risk],
    ["상대 성장 가능", `${Math.round(r.growth_score)}점`, r.growth_drivers, HELP.growth],
  ];
  if (r.nearest_tram) rows.push(["가까운 정거장", `${int(r.nearest_tram_m)}m`, `${r.nearest_tram}번 정거장 · 점포의 ${i5 == null ? "-" : Math.round(i5 * 100) + "%"}가 500m 안`]);
  if (r.abs_decline && r.abs_decline !== "판단 안 함")
    rows.push(["절대 쇠퇴 신호", r.abs_decline + (r.abs_decline_n != null ? ` (${r.abs_decline_n}/4)` : ""), (r.abs_decline_why || "해당 없음") + " · 대전 전체 기준", HELP.abs]);
  const stab = r.quadrant_stability;
  return (
    <div className="why">
      <div className="why-h">{title}</div>
      <div className="why-rule">{ruleText(q, quadAfter, i5)}</div>
      {rows.map(([l, v, d, h]) => (
        <div className="why-r" key={l}><span className="l">{l}{h && <> <Help tip={h} /></>}</span><b>{v}</b><span>{d}</span></div>
      ))}
      {(stab != null || extraFoot) && (
        <div className="why-f">
          {stab != null && <p>진단 안정도 {Math.round(stab * 100)}% (15가지 계산 변형 중 같은 진단 비율){r.quadrant_alt && stab < 1 ? `, 바뀔 때는 '${r.quadrant_alt}'` : ""}</p>}
          {extraFoot}
        </div>
      )}
    </div>
  );
}

function Metric({ l, v, d, h, txt }) {
  return (
    <div className="m">
      <div className="m-l">{l}{h && <Help tip={h} />}</div>
      <div className={"m-v" + (txt ? " txt" : "")}>{v}</div>
      {d && <div className="m-d">{d}</div>}
    </div>
  );
}

function rentMetric(r, v, st) {
  const g = v.rent;
  const drv = r.rent?.drivers;
  const stab = r.rent?.stab;
  const warn = stab != null && stab < 0.6;
  return <Metric l="임대료 부담 신호" txt v={g + (warn && st.tramAfter && g !== "해당 없음" ? " ⚑" : "")} h={HELP.rent}
    d={st.tramAfter ? (g === "해당 없음" ? "트램 효과가 거의 없는 곳" : `${drv ? "높은 요소: " + drv + " · " : ""}상대 순위, 금액 아님${stab != null ? ` · 가중치 8변형 중 ${Math.round(stab * 100)}% 같은 등급` : ""}`) : "건설 후에만"} />;
}
function compMetric(v, st, sl) {
  const c = v.compInfo;
  if (!c) return <Metric l="업종 변화 (카페)" v="-" />;
  return <Metric l="업종 변화 (카페·빵집)" h={HELP.comp} v={st.tramAfter ? pp(c.pp) : "없음"}
    d={st.tramAfter ? `비중 ${(c.now * 100).toFixed(1)}→${(c.y34 * 100).toFixed(1)}% · 카페 +${Math.round(c.add_cafe)}곳 (2034)` : `건설 후 ${pp(c.pp)} (${sl})`} />;
}

function AreaPanel({ D, a, v, st }) {
  const [tab, setTab] = useState("fc");
  if (!a) return null;
  const { meta } = D;
  const sl = scenLabel(meta, st.scen);
  const ser = D.series_area;
  const comp = D.composition.data[`상권|${a.code}`];
  const foot = <>{a.sens && <p><b>⚑ 정거장 위치에 민감</b>: {a.sens}</p>}</>;
  return (
    <section className="panel" aria-label="선택한 상권">
      <div className="pick">
        <select aria-label="상권 선택" value={a.code} onChange={e => setState({ sel: e.target.value })}>
          {D.areas.map(x => <option key={x.code} value={x.code}>{x.code} {x.name}</option>)}
        </select>
      </div>
      <div className="area-h"><span className="code">{a.code}</span><h2 className="t">{a.name}</h2></div>
      <div className="badges">
        <QBadge q={v.quadrant} />
        {a.quadrant_uncertain && <span className="badge warn">불확실 {Math.round(a.quadrant_stability * 100)}%</span>}
        {a.type_name && <span className="badge gray" title="K-means 4유형, 안정성 ARI 0.49 (참고)">{a.type_name} <small>참고</small></span>}
        <span className="where">{a.gu} · {a.type}</span>
      </div>
      <WhyBox title="진단 근거 · 20개 상권 안 순위" q={v.quadrant} quadAfter={a.quadrant_after} i5={a.in500} r={a} extraFoot={a.sens ? foot : null} />
      <div className="mgrid">
        <div className="mgroup">트램 개통 뒤 (상권 가치 → 업종 → 임대료)</div>
        <Metric l="상권 가치 효과" h={TRAM_DEF} v={st.tramAfter ? pct(v.tram_sel) : "없음"}
          d={st.tramAfter ? `${v.money > 0 ? `500m 안 땅값 +${eok(v.money)} · ` : ""}낮음 ${pct(a.tram_effect_low)} ~ 높음 ${pct(a.tram_effect_high)}` : `건설 후 ${pct(v.tram)} (${sl})`} />
        {compMetric(v, st, sl)}
        {rentMetric(a, v, st)}
        <Metric l={`땅값 전망 2026→2034`} v={pct(v.land_fc)} d={st.tramAfter ? `트램 없으면 ${pct(a.land_fc?.none)}` : "트램 없는 추세"} />
        <div className="mgroup">지금 상태</div>
        <Metric l="점포 수 (2026-06)" v={int(a.n_stores)} d={`대전 내 비중 5년 ${pct(a.store_share_chg_5y_pct)}`} />
        <Metric l="땅값 5년 상승률" v={pct(a.land_chg_5y_pct)} d={a.close_rate_q_pct != null ? `분기 폐업률 ${a.close_rate_q_pct.toFixed(2)}%` : null} />
      </div>
      <p className="notes">
        {a.top3_mid && <>주요 업종: {a.top3_mid}. </>}
        {a.rent_market && <>임대 시장(한국부동산원 '{a.rent_market.region}' {a.rent_market.kind} 상가): 공실률 {f1(a.rent_market.vac)}%, 임대가격지수 2022→2026 {pct(a.rent_market.idx)}. </>}
        {a.bad_pct != null && <>2021 실태조사({a.survey_dong}): 매출·이익 감소 {Math.round(a.decline_pct)}%, 폐업·전환 고려 {Math.round(a.closing_pct)}%(대전 평균 74%·7%, 코로나 시기). </>}
      </p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", margin: "12px 0 6px" }}>
        <button type="button" className="btn ghost" onClick={() => go("/ai", { area: a.code })}>이 상권 AI 해설 보기</button>
        <button type="button" className="btn ghost" onClick={() => go("/3d", { area: a.code })}>3D로 보기</button>
      </div>
      <div style={{ marginTop: 14 }}>
        <Tabs value={tab} onChange={setTab} tabs={[["fc", "땅값 전망"], ["comp", "업종 구성"], ["land", "땅값 흐름"], ["store", "점포 수"]]} />
        {tab === "fc" && <>
          <p className="chart-cap">회색 띠 = 트램 없는 추세 전망(ARIMA)의 80% 범위(넓으므로 상권끼리 비교용) · 남색 선 = 거기에 트램 효과를 더한 시나리오 · 남색 띠 = 트램 몫</p>
          <ForecastChart hist={ser.land[a.code]} fc={ser.fc[a.code]} scen={st.scen} after={st.tramAfter} />
          <p className="src">자료: 상권 땅값 예측 · 상권 땅값 지수 (국토교통부 개별공시지가)</p></>}
        {tab === "comp" && <CompTab comp={comp} groups={D.composition.groups} st={st} name={short(a.name)} sl={sl} />}
        {tab === "land" && <>
          <p className="chart-cap">대전 전체와 비교 · 회색 점선 = 이 상권의 주요 사건(마우스를 올리면 내용)</p>
          <LineChart yLabel="지수 (2015=100)" series={[{ name: short(a.name), color: "var(--chart-blue)", data: ser.land[a.code] || [] }, { name: "대전 전체", color: "#9aa0a6", data: ser.land.ALL || [] }]}
            events={(a.events || []).map(e => ({ x: +e.date.slice(0, 4) + (+e.date.slice(5, 7)) / 12, text: `${e.date} ${e.text}` }))} />
          {a.events?.length > 0 && <ul className="list small muted">{a.events.map(e => <li key={e.date + e.text}>{e.date} {e.text}</li>)}</ul>}</>}
        {tab === "store" && <>
          <p className="chart-cap">회색 점선 = 자료 수집 기준이 바뀐 분기 (그때의 급변은 자료 탓일 수 있음)</p>
          <StoreChart data={ser.store[a.code]} breaks={ser.breaks} />
          <p className="src">자료: 소상공인시장진흥공단 상가(상권)정보 42개 분기</p></>}
      </div>
    </section>
  );
}

function CompTab({ comp, groups, st, name, sl }) {
  if (!comp) return <p className="muted small">업종 구성 결과가 없습니다.</p>;
  const tot = comp.n_stores;
  const now = Object.fromEntries(groups.map(g => [g, (comp.n[g] || 0) / tot * 100]));
  const ad = comp.add?.[st.scen] || { cafe: 0, bakery: 0 };
  const tot34 = tot + ad.cafe + ad.bakery;
  const later = st.tramAfter ? Object.fromEntries(groups.map(g => [g, ((comp.n[g] || 0) + (g === "카페" ? ad.cafe : g === "빵·과자" ? ad.bakery : 0)) / tot34 * 100])) : null;
  return <>
    <p className="chart-cap">대전 1호선 근거: 역 500m 안 카페 수 +25%, 음식점 중 카페 비중 +1.4%p(1단계)·+4.0%p(2단계 따로 재현). 다른 업종은 근거가 약해 그대로 둠 → 바뀌는 것은 카페 몫. 식사 음식점 비중은 −5%p(1호선 실측)라 기존 식당에는 경쟁·전환 압력</p>
    <CompChart groups={groups} now={now} later={later} />
    {st.tramAfter && <p className="small" style={{ marginTop: 6 }}><b>{name}</b>: 카페 {comp.n["카페"]}곳 중 {Math.round((comp.near500_cafe || 0) * 100)}%가 정거장 500m 안 → 2034년까지 카페 약 <b>{Math.round(ad.cafe)}곳</b> 상대 증가 ({sl})</p>}
    <p className="src">자료: 업종 구성 (상가정보 2026-06) · 업종 변화 예측</p>
  </>;
}

function DongPanel({ D, d, v, st }) {
  const [tab, setTab] = useState("fc");
  if (!d) return null;
  const { meta } = D;
  const sl = scenLabel(meta, st.scen);
  const ser = D.series_dong;
  const comp = D.composition.data[`행정동|${d.dong_id}`];
  const order = [...D.dongs].sort((a, b) => (a.si + a.dong).localeCompare(b.si + b.dong, "ko"));
  const foot = <>{d.sens && <p><b>⚑ 정거장 위치에 민감</b>: {d.sens}</p>}
    {d.dev && <p><b>⌂ 트램 없어도 오르는 곳</b> ({d.dev[0]}): {d.dev[1]} → {d.dev[0] === "개발지" ? "땅값 전망에 신도시·택지 개발 효과가 섞임" : "트램 확정(2019) 전부터 대전보다 더 오르던 곳"}</p>}</>;
  return (
    <section className="panel" aria-label="선택한 행정동">
      <div className="pick">
        <select aria-label="행정동 선택" value={d.dong_id} onChange={e => setState({ selDong: e.target.value })}>
          {order.map(x => <option key={x.dong_id} value={x.dong_id}>{x.name}</option>)}
        </select>
      </div>
      <div className="area-h"><span className="code">{d.si}</span><h2 className="t">{d.dong}</h2></div>
      <div className="badges">
        <QBadge q={v.quadrant} />
        {d.quadrant_uncertain && <span className="badge warn">불확실 {Math.round(d.quadrant_stability * 100)}%</span>}
        {d.type_name && <span className="badge gray">{d.type_name} <small>참고</small></span>}
        {d.small ? <span className="badge gray">점포 적음</span> : null}
        <span className="where">{d.tram_group}</span>
      </div>
      <WhyBox title="진단 근거 · 82개 동 안 순위" q={v.quadrant} quadAfter={d.quadrant_after} i5={d.tram500_share} r={d} extraFoot={(d.sens || d.dev) ? foot : null} />
      <div className="mgrid">
        <div className="mgroup">트램 개통 뒤</div>
        <Metric l="상권 가치 효과" h={TRAM_DEF} v={st.tramAfter ? pct(v.tram_sel) : "없음"}
          d={st.tramAfter ? `${v.money > 0 ? `500m 안 땅값 +${eok(v.money)} · ` : ""}낮음 ${pct(d.tram_effect_low)} ~ 높음 ${pct(d.tram_effect_high)}` : `건설 후 ${pct(v.tram)} (${sl})`} />
        {compMetric(v, st, sl)}
        {rentMetric(d, v, st)}
        <Metric l="카드매출 2025→2026" v={pct(d.s89_sales_yoy_pct)} h={"출처: " + meta.sources.s8989 + ". 1~8월 같은 달끼리 비교. 금액보다 비율·증감으로 해석"}
          d={d.s89_market_caveat ? "현금·비카드 거래 영향 가능" : "8989 추정매출, 같은 달 비교"} />
        <div className="mgroup">지금 상태</div>
        <Metric l="점포 수 (2026-06)" v={int(d.n_stores)} d={d.store_share_chg_5y_pct != null ? `비중 5년 ${pct(d.store_share_chg_5y_pct)}` : null} />
        <Metric l="땅값 5년 상승률" v={pct(d.land_chg_5y_pct)} d={d.land_rel_idx != null ? `대전 평균 대비 ${Math.round(d.land_rel_idx)}` : null} />
      </div>
      <p className="notes">{d.top3 && <>주요 업종: {d.top3}. </>}{d.areas && <>겹치는 핵심 상권: {d.areas}. </>}{d.survey_bad_pct != null && <>2021 실태조사 어려움 응답 {Math.round(d.survey_bad_pct)}% (대전 평균 약 81%). </>}{d.score_note}</p>
      <div style={{ marginTop: 14 }}>
        <Tabs value={tab} onChange={setTab} tabs={[["fc", "땅값 전망"], ["comp", "업종 구성"], ["land", "땅값 흐름"], ["store", "점포 수"]]} />
        {tab === "fc" && <ForecastChart hist={ser.land[d.dong_id]} fc={ser.fc[d.dong_id]} scen={st.scen} after={st.tramAfter} />}
        {tab === "comp" && <CompTab comp={comp} groups={D.composition.groups} st={st} name={d.dong} sl={sl} />}
        {tab === "land" && <LineChart yLabel="지수 (2015=100)" series={[{ name: d.dong, color: "var(--chart-blue)", data: ser.land[d.dong_id] || [] }, { name: "대전 전체", color: "#9aa0a6", data: D.series_area.land.ALL || [] }]} />}
        {tab === "store" && <StoreChart data={ser.store[d.dong_id]} breaks={D.series_area.breaks} />}
        <p className="src">자료: 행정동 진단·지표 · 행정동 땅값 예측 · 행정동 연도별 지표 · 점포 수</p>
      </div>
    </section>
  );
}

function StationCard({ D, no, A, pick }) {
  const s = D.meta.stations.find(x => x.no === no);
  if (!s) return null;
  return (
    <section className="stn" aria-label="선택한 정거장">
      <div className="stn-t"><span>{s.no}번 {s.name}</span><button type="button" className="xbtn" onClick={() => setState({ station: null })}>닫기 ✕</button></div>
      <p className="small">500m 안 점포 <b>{int(s.n_stores)}</b>개{s.top && ` · ${s.top}`}</p>
      {s.areas.length > 0 && <ul>{s.areas.map(x => <li key={x.code}><button type="button" className="linkbtn" onClick={() => pick(x.code)}>{short(A[x.code]?.name)}</button> — 상권 점포 {x.n}개({Math.round(x.share)}%)가 이 정거장 500m 안</li>)}</ul>}
      {s.areas.length === 0 && <p className="small muted">핵심 상권 20곳 중 500m 안에 드는 곳은 없습니다.</p>}
      {s.dongs?.length > 0 && <p className="small muted" style={{ marginTop: 6 }}>걸치는 행정동: {s.dongs.map(d => d.name).join(", ")}</p>}
    </section>
  );
}
