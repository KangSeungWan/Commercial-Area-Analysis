import { useState } from "react";
import MapView from "../MapView.jsx";
import { Loading, Tabs, Seg } from "../ui.jsx";
import { useData, pct, short } from "../lib.js";

export default function TourismPage() {
  const { data, error } = useData(["tourism", "meta", "geo_dongs"]);
  const [tab, setTab] = useState("dj");
  if (!data) return <Loading error={error} />;
  return (
    <div className="page">
      <div className="page-h">
        <h1 className="page-t">트램과 관광</h1>
        <p className="page-sub">관광은 트램의 부수 효과입니다. 트램이 관광객을 늘렸다는 인과 측정은 세계적으로 없어서, 이 화면은 '이런 효과도 기대할 수 있다' 수준으로만 보여 주고 상권 진단·점수에는 넣지 않습니다.</p>
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[["dj", "대전 기대 효과"], ["world", "해외 사례"], ["kr", "국내 개통 예정"], ["how", "근거와 방법"]]} />
      {tab === "dj" && <Daejeon D={data} />}
      {tab === "world" && <World T={data.tourism} />}
      {tab === "kr" && <Korea T={data.tourism} />}
      {tab === "how" && <How T={data.tourism} />}
    </div>
  );
}

function Daejeon({ D }) {
  const T = D.tourism;
  const A = T.layer.filter(r => r.kind === "area");
  const on = A.filter(r => r.tourism_type === "관광자원형");
  const S = T.station;
  const maxB = Math.max(...on.map(r => r.visit_base_pct || 0)), maxH = Math.max(...on.map(r => r.visit_high_pct || 0));
  return <>
    <div className="rows3">
      <div className="stat"><span className="v">{on.length} / {A.length}</span><span className="l">관광지가 가까운 상권</span><span className="d">그중 관광지 많은 곳 {on.filter(r => r.tour_level === "강").length}</span></div>
      <div className="stat"><span className="v">{S.filter(s => s.n_poi > 0).length} / {S.length}</span><span className="l">관광지가 있는 정거장</span><span className="d">500m 안 (큰 공원 1km)</span></div>
      <div className="stat"><span className="v">0 ~ +{Math.round(maxB)}%</span><span className="l">방문 증가 (기본)</span><span className="d">관문 → 상권 이동 시간 변화로 계산</span></div>
      <div className="stat"><span className="v">최대 +{Math.round(maxH)}%</span><span className="l">방문 증가 (상한)</span><span className="d">버스가 느린 경우 · 탄력성 1.0</span></div>
    </div>
    <div className="split" style={{ marginTop: 0 }}>
      <div className="mapbox">
        <div className="maphead"><div className="lg"><span className="it">정거장에 마우스를 올리거나 누르면 500m 안 관광지가 보입니다</span></div>
          <div className="sym"><span><span className="ln" />트램 2호선</span><span><span className="st" />정거장</span></div></div>
        <MapView keyProp="dong_id" polys={D.geo_dongs} polyAlpha={60} fill={{}} fillKey="t" stations={D.meta.stations} route={D.meta.route} tramAfter
          stationTip={s => { const t = S.find(x => x.station_no === s.no); return `<b>${s.no}번 ${s.name}</b><br/>${t?.pois || "500m 안 관광지 없음"}`; }}
          ariaLabel="관광지와 트램 정거장 지도" />
      </div>
      <div>
        <div className="box">
          <h2>기대할 수 있는 것, 조심할 것</h2>
          <ul className="list" style={{ color: "var(--moss)" }}>
            <li><b>만년동·과학관·엑스포 일대(정거장 220·221)</b>: 수목원·과학관·신세계·한빛탑이 모여 트램이 가장 의미 있는 곳. 다만 대전역에서는 지금 버스가 더 빨라 기본 시나리오 효과는 작습니다.</li>
            <li><b>대전역·원도심</b>(성심당·중앙시장·으능정이): 관광 수요는 가장 크지만 역에서 걸어가는 거리라 트램으로 달라지는 것이 거의 없습니다.</li>
            <li><b>알기 쉬운 이동 수단</b>: 땅 위로 다니고 노선이 보여 처음 온 관광객이 쓰기 쉽습니다(히로시마·나가사키 관광객 37~40% 이용). 이 장점은 숫자로 넣지 못했습니다.</li>
            <li><b>축제 수송</b>: 0시 축제(중앙로) 때 대전역·중앙로 정거장 이용이 늘 것으로 봅니다(에든버러 축제 주간 13.7만 명 참고).</li>
            <li><b>조심할 점</b>: 관광객이 몰리면 주민 혼잡(리스본·하코다테). 순환선이라 먼 관광지는 오히려 버스보다 느립니다.</li>
          </ul>
        </div>
      </div>
    </div>
    <div className="grid2" style={{ marginTop: 18 }}>
      <div className="tablewrap"><table className="t"><thead><tr><th>상권</th><th>관광지</th><th>가까운 관광지</th><th>방문 증가 범위 (시나리오)</th></tr></thead>
        <tbody>{on.sort((a, b) => b.visit_high_pct - a.visit_high_pct).map(r => <tr key={r.id}><td>{short(r.name)}</td><td>{r.tour_level === "강" ? "많음" : "조금"}</td>
          <td className="small">{r.top_poi}</td><td className="num">{r.visit_high_pct > 0.05 ? (r.visit_base_pct >= 0.05 ? `0 ~ ${pct(r.visit_base_pct)} (상한 ${pct(r.visit_high_pct)})` : `기본 0, 상한 ${pct(r.visit_high_pct)}`) : "변화 거의 없음"}</td></tr>)}</tbody></table></div>
      <div className="tablewrap"><table className="t"><thead><tr><th>정거장</th><th>관광지 (거리)</th></tr></thead>
        <tbody>{S.filter(s => s.n_poi > 0).sort((a, b) => b.tour_score - a.tour_score).map(s => <tr key={s.station_no}><td>{s.station_no} {s.station_name}</td><td className="small">{s.pois}</td></tr>)}</tbody></table></div>
    </div>
    <p className="src">관광지 위치 점은 공개 사이트에 싣지 않습니다(좌표 자료 이용 조건). 관광지 이름과 거리는 정거장 표에서 볼 수 있습니다. 시나리오: 관문 4곳(대전역·대전복합터미널·서대전역·유성복합터미널, 하루 이용객 비율로 가중)에서 상권까지 이동 시간이 트램으로 줄어드는 만큼 방문이 는다고 가정(해외 고속철 탄력성 0~1.0 차용). 이동 시간은 근사(환승 제외). 효과는 개통 후 2년쯤에 절반. 자료: 관광 접근성 시나리오 · 정거장별 관광지</p>
  </>;
}

function World({ T }) {
  return <>
    <p className="lead" style={{ marginBottom: 12 }}>관광지를 <b>바로 잇는 노선</b>일수록 관광객이 많이 탑니다(히로시마·나가사키 37~40%). 통근형 신설 노선은 5% 안팎입니다. 숫자는 '이용 비율'이며 '트램 때문에 관광객이 늘었다'는 인과가 아닙니다.</p>
    <div className="tablewrap"><table className="t"><thead><tr><th>도시·노선</th><th>무엇을 봤나</th><th>숫자</th><th>읽는 법</th><th>등급</th><th>원문</th></tr></thead>
      <tbody>{T.good.map(r => <tr key={r.city} className={r.grade === "하" ? "dim" : ""}><td><b style={{ fontWeight: 600 }}>{r.city}</b></td><td>{r.what}</td><td className="num">{r.num}</td><td className="small">{r.read}</td><td>{r.grade}</td>
        <td><a href={r.url} target="_blank" rel="noopener noreferrer">원문</a></td></tr>)}</tbody></table></div>
    <h2 style={{ fontSize: 16, margin: "18px 0 6px" }}>같이 봐야 할 사례 (효과 없음·부작용)</h2>
    <ul className="list">{T.caution.map(r => <li key={r.city}><b>{r.city}</b>: {r.text} · 등급 {r.grade} · <a href={r.url} target="_blank" rel="noopener noreferrer">원문</a></li>)}</ul>
  </>;
}

function Korea({ T }) {
  return <>
    <div className="tablewrap"><table className="t"><thead><tr><th>노선</th><th>구간</th><th>규모</th><th>개통 목표</th><th>지금</th><th>관광과의 관계</th><th>기사</th></tr></thead>
      <tbody>{T.domestic.map(r => <tr key={r.line}><td><b style={{ fontWeight: 600 }}>{r.line}</b></td><td>{r.section}</td><td className="small">{r.size}</td><td>{r.open}</td><td className="small">{r.status}</td>
        <td className="small">{r.tourism.replace(/\*\*/g, "")}</td><td><a href={r.url} target="_blank" rel="noopener noreferrer">기사</a></td></tr>)}</tbody></table></div>
    <p className="src">기사 기준 ({T.checked} 확인). 국내에는 아직 개통한 현대 트램이 없어 관광 효과를 잰 사례가 없습니다. 위례선(2026-12)이 첫 비교 대상입니다.</p>
  </>;
}

function How({ T }) {
  const [g, setG] = useState("상중");
  const grade = x => (["상", "중", "하"].includes(String(x)[0]) ? String(x)[0] : "중");
  const rows = T.literature.filter(r => g.includes(grade(r.reliability)));
  return <>
    <div className="grid2">
      <div className="box"><h2>이 화면이 말하지 않는 것</h2>
        <ul className="list small"><li>'트램이 관광객을 몇 명 늘린다', '관광 매출 몇 억 원' 같은 확정 숫자</li><li>해외 관광도시 수치를 대전에 그대로 적용</li>
          <li>카드 매출의 외지인 비율 (자료에 거주지 구분이 없음)</li><li>개통 후 실제 효과 (2030년 이후 자료로 검증해야 함)</li></ul></div>
      <div className="box"><h2>쓸 수 있는 숫자 (시나리오 재료)</h2>
        <ul className="list small">{T.params.slice(0, 9).map(p => <li key={p.param_id}>{p.paper}: <b>{p.value}</b> {p.unit}</li>)}</ul></div>
    </div>
    <div className="ctl" style={{ marginTop: 18 }}><div className="ctl-g"><span className="ctl-l">문헌 {T.literature.length}건 · 신뢰도</span>
      <Seg label="신뢰도" options={[["상중", "상·중"], ["상중하", "전체 (하 포함)"]]} value={g} onChange={setG} /></div></div>
    <div className="tablewrap"><table className="t"><thead><tr><th>등급</th><th>분야</th><th>출처</th><th>도시·노선</th><th>결과</th><th>원문</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r.id} className={grade(r.reliability) === "하" ? "dim" : ""}><td>{grade(r.reliability)}</td><td className="small">{r.group}</td><td className="small">{r.source}</td>
        <td className="small">{r.city_system}</td><td className="small">{r.finding}</td><td>{r.url && <a href={r.url} target="_blank" rel="noopener noreferrer">원문</a>}</td></tr>)}</tbody></table></div>
    <p className="src">자세한 근거: 트램 관광 효과 문헌 90건 · 관광지 67곳 인터넷 대조 검증</p>
  </>;
}
