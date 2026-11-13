// 지도 화면 (2026-11-12 개편): 결론 한 줄 + 4칸 카드(거르기) + 지도 + 선택 카드. 긴 설명은 '상권 상세'·'근거' 화면으로
import { useMemo, useState, useEffect } from "react";
import MapView, { centroid } from "../MapView.jsx";
import { Seg, Help, QBadge, Loading } from "../ui.jsx";
import { CountUp, QCards, Quad2x2, Meter, Steps, Reveal } from "../viz.jsx";
import { useData, useApp, setState, go, useRoute, view, colorize, QC, QHEX, QORDER, OUTSIDE, QDESC, QDO, QNOTE, RENT_C, rgb, int, short, HELP } from "../lib.js";

const NEED = ["meta", "areas", "dongs", "geo_core", "geo_regions", "geo_dongs", "geo_gu"];
const FADE = [228, 230, 226];

export default function MapPage() {
  const { data, error } = useData(NEED);
  if (!data) return <Loading error={error} />;
  return <MapInner D={data} />;
}

export function TopControls({ unit = true }) {
  const st = useApp();
  return (
    <div className="ctl slim">
      {unit && <Seg label="보기 단위" options={[["area", "상권 20"], ["dong", "행정동 82"]]} value={st.unit} onChange={v => setState({ unit: v })} />}
      <div className={"tramsw" + (st.tramAfter ? " after" : "")} role="group" aria-label="트램 2호선 건설 전·후">
        <button type="button" aria-pressed={!st.tramAfter} onClick={() => setState({ tramAfter: false })}>건설 전</button>
        <span className="rail" aria-hidden="true" />
        <button type="button" aria-pressed={st.tramAfter} onClick={() => setState({ tramAfter: true })}>건설 후</button>
      </div>
    </div>
  );
}

function MapInner({ D }) {
  const st = useApp();
  const { q } = useRoute();
  const { meta, areas, dongs } = D;
  const dong = st.unit === "dong";
  const [only, setOnly] = useState(null);
  const A = useMemo(() => Object.fromEntries(areas.map(a => [a.code, a])), [areas]);
  const DG = useMemo(() => Object.fromEntries(dongs.map(d => [d.dong_id, d])), [dongs]);
  const rows = dong ? dongs : areas;
  const keyOf = r => (dong ? r.dong_id : r.code);
  const byKey = dong ? DG : A;
  const V = useMemo(() => Object.fromEntries(rows.map(r => [keyOf(r), view(r, st)])), [rows, st.tramAfter, st.scen, dong]);

  useEffect(() => {
    const first = list => [...list].filter(r => r.quadrant_after === "먼저 지원").sort((a, b) => b.risk_score - a.risk_score)[0] || list.find(r => r.policy_target) || list[0];
    if (q.area && A[q.area]) setState({ sel: q.area, unit: "area" });
    else if (!st.sel || !A[st.sel]) setState({ sel: first(areas).code });
    if (!st.selDong || !DG[st.selDong]) setState({ selDong: first(dongs).dong_id });
  }, [q.area]);
  useEffect(() => setOnly(null), [dong, st.tramAfter]);
  const selKey = dong ? st.selDong : st.sel;
  const pick = k => setState(dong ? { selDong: k } : { sel: k });

  const counts = {};
  rows.forEach(r => { const k = V[keyOf(r)].quadrant; counts[k] = (counts[k] || 0) + 1; });
  const nTarget = rows.filter(r => r.policy_target).length;

  // 지도 색
  const m = ["quadrant", "comp", "rent"].includes(st.metric) ? st.metric : "quadrant";
  const keys = rows.map(keyOf);
  const fill = {};
  let legend;
  if (m === "quadrant") {
    keys.forEach(k => { const qq = V[k].quadrant; fill[k] = only && qq !== only ? FADE : (QC[qq] || QC[OUTSIDE]); });
    const items = [...QORDER, OUTSIDE].filter(x => counts[x]);
    legend = <div className="lg">{items.map(n => <span key={n} className="it"><span className="dot" style={{ background: rgb(QC[n]) }} />{n}</span>)}<Help tip={HELP.quadrant} /></div>;
  } else if (!st.tramAfter) {
    keys.forEach(k => { fill[k] = [215, 218, 222]; });
    legend = <div className="lg">트램이 생겨야 나타나는 변화라 건설 전에는 없음</div>;
  } else if (m === "rent") {
    keys.forEach(k => { fill[k] = RENT_C[V[k].rent] || RENT_C["해당 없음"]; });
    legend = <div className="lg">{["높음", "보통", "낮음"].map(n => <span key={n} className="it"><span className="dot" style={{ background: rgb(RENT_C[n]) }} />{n}</span>)}<Help tip={HELP.rent} /></div>;
  } else {
    const c = colorize(keys.map(k => V[k].comp), "seq_cafe");
    keys.forEach((k, i) => { fill[k] = c.cols[i]; });
    legend = <div className="lg"><span>낮음</span><span className="bar" style={{ background: `linear-gradient(90deg,${c.stops.join(",")})` }} /><span>높음 +{c.hi.toFixed(1)}%p</span><Help tip={HELP.comp} /></div>;
  }
  const fillKey = `${m}|${st.tramAfter}|${st.scen}|${dong}|${only}`;

  const labels = useMemo(() => {
    if (dong) return null;
    return D.geo_core.features.map(f => {
      const k = f.properties.code, a = A[k];
      return { key: k, text: short(a.name), pos: centroid(f), pri: (k === st.sel ? 1e9 : 0) + (a.quadrant_after === "먼저 지원" ? 1e6 : 0) + (a.policy_target ? 1e5 : 0) + (a.n_stores || 0) };
    });
  }, [dong, st.sel, D.geo_core]);

  const tooltip = k => {
    const r = byKey[k]; if (!r) return null;
    const qq = V[k].quadrant;
    return `<b>${dong ? r.name : short(r.name)}</b><br/><span style="color:${QHEX[qq] || "#666"}">●</span> ${qq || ""}`;
  };
  const stationTip = s => `<b>${s.no}번 ${s.name}</b><br/>500m 안 점포 ${int(s.n_stores)}개`;

  return (
    <div className="page">
      <section className="mtop" aria-label="결론">
        <div className="mtop-h">
          <h1 className="mtitle">트램 근처 <CountUp value={nTarget} />{dong ? "개 동" : "곳"}, 담당자가 할 일</h1>
          <TopControls />
        </div>
        <QCards counts={counts} active={only} onPick={setOnly} outside={counts[OUTSIDE] || 0} desc={QDO} />
      </section>

      <div className="split">
        <div className="mapbox">
          <div className="maphead">
            <Seg label="지도에 칠할 것" options={[["quadrant", "진단"], ["comp", "업종 변화"], ["rent", "임대료 신호"]]} value={m} onChange={v => setState({ metric: v })} />
            {legend}
          </div>
          <MapView key={dong ? "dong" : "area"} keyProp={dong ? "dong_id" : "code"} base={dong ? null : D.geo_dongs}
            gu={D.geo_gu} regions={dong ? null : D.geo_regions} showRegion={!dong && st.region} fitTo={D.geo_core} polys={dong ? D.geo_dongs : D.geo_core} polyAlpha={dong ? 200 : 225}
            fill={fill} fillKey={fillKey} sel={selKey} onPick={pick} stations={meta.stations} route={meta.route} line1={meta.line1}
            tramAfter={st.tramAfter} station={st.station} onStation={no => setState({ station: no })} tooltip={tooltip} stationTip={stationTip}
            labels={labels} showLabels={st.labels} ariaLabel={dong ? "행정동 82개 지도" : "핵심 상권 20개 지도"} />
          <p className="mapnote">{QNOTE}</p>
        </div>
        <div>
          {st.station != null && <StationCard D={D} no={st.station} A={A} pick={k => setState({ sel: k, unit: "area" })} />}
          <SelCard r={byKey[selKey]} v={V[selKey]} rows={rows} V={V} keyOf={keyOf} dong={dong} pick={pick} st={st} />
        </div>
      </div>
    </div>
  );
}

function SelCard({ r, v, rows, V, keyOf, dong, pick, st }) {
  if (!r || !v) return null;
  const k = keyOf(r);
  const name = dong ? r.name : r.name;
  const pts = rows.filter(x => x.policy_target).map(x => ({ key: keyOf(x), name: dong ? x.dong : x.name, x: x.risk_score, y: x.change_pp,
    q: V[keyOf(x)].quadrant, hollow: !["있음", "강함"].includes(x.abs_decline) }));
  const med = r.change_median ?? 0;
  const rent = v.rent;
  return (
    <Reveal key={k} as="section" className="panel selcard" aria-label="선택한 곳">
      <div className="sel-h">
        <h2 className="t">{dong ? r.dong : short(name)}</h2>
        <QBadge q={v.quadrant} />
        {r.quadrant_uncertain && r.policy_target && <span className="badge warn">불확실</span>}
      </div>
      <p className="sel-d">{QDESC[v.quadrant]}{r.policy_target && <> · <b>{QDO[v.quadrant]}</b></>}</p>
      {r.policy_target ? <>
        <Quad2x2 points={pts} sel={k} median={med} onPick={pick} />
        <div className="sel-m">
          <div><span className="l">지금 위험</span><b><CountUp value={r.risk_score} /></b><span className="u">점</span>
            <Meter value={r.risk_score} cut={50} color={r.risk_high ? rgb(QC["먼저 지원"]) : "var(--sage-mist)"} /></div>
          <div><span className="l">업종 변화</span><b><CountUp value={st.tramAfter ? r.change_pp : 0} digits={2} sign /></b><span className="u">%p</span>
            <Meter value={st.tramAfter ? r.change_pp : 0} max={Math.max(3.5, r.change_pp || 0)} cut={med} color={rgb(QC["변화 관찰"])} /></div>
          <div><span className="l">임대료 신호</span><Steps steps={["낮음", "보통", "높음"]} value={rent} colors={["#ddd0ea", "#a678c6", "#6a2a8c"]} /></div>
        </div>
      </> : <p className="muted small">가까운 정거장 {r.nearest_tram ? `${r.nearest_tram}번 · ${int(r.nearest_tram_m)}m` : "-"}</p>}
      <div className="sel-b">
        <button type="button" className="btn" onClick={() => go("/area", dong ? { dong: k } : { area: k })}>자세히 보기 →</button>
        {!dong && <button type="button" className="btn ghost" onClick={() => go("/ai", { area: k })}>AI 쉬운 해설</button>}
      </div>
    </Reveal>
  );
}

function StationCard({ D, no, A, pick }) {
  const s = D.meta.stations.find(x => x.no === no);
  if (!s) return null;
  return (
    <section className="stn" aria-label="선택한 정거장">
      <div className="stn-t"><span>{s.no}번 {s.name}</span><button type="button" className="xbtn" onClick={() => setState({ station: null })}>닫기 ✕</button></div>
      <div className="stn-n"><b><CountUp value={s.n_stores} /></b> 점포가 500m 안{s.dem && <> · 2030 하루 승차 예측 <b>{s.dem.b.toLocaleString()}</b>명</>}</div>
      {s.areas.length > 0 && <div className="chips">{s.areas.map(x => <button key={x.code} type="button" className="chip" onClick={() => pick(x.code)}>{short(A[x.code]?.name)} {Math.round(x.share)}%</button>)}</div>}
    </section>
  );
}
