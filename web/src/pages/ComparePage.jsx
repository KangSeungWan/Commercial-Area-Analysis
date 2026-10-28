import { useState } from "react";
import { Controls, Loading, QBadge, Help } from "../ui.jsx";
import { useData, useApp, setState, go, view, short, pct, pp, int, HELP } from "../lib.js";

const R_ORD = { "높음": 3, "보통": 2, "낮음": 1, "해당 없음": 0 };
const A_ORD = { "강함": 3, "있음": 2, "없음": 1, "판단 안 함": 0 };

export default function ComparePage() {
  const { data, error } = useData(["meta", "areas", "dongs"]);
  const st = useApp();
  const [sort, setSort] = useState(["risk", -1]);
  if (!data) return <Loading error={error} />;
  const { meta } = data;
  const dong = st.unit === "dong";
  const rows = (dong ? data.dongs : data.areas).map(r => {
    const v = view(r, st);
    return { key: dong ? r.dong_id : r.code, name: dong ? r.name : short(r.name), r, v,
      quadrant: v.quadrant, stab: r.quadrant_stability, risk: r.risk_score, growth: r.growth_score, abs: r.abs_decline,
      tram: v.tram_sel, comp: v.comp, rent: v.rent, rentScore: (R_ORD[v.rent] || 0) * 1000 + (r.rent?.score || 0),
      land5: r.land_chg_5y_pct, share: r.store_share_chg_5y_pct, extra: dong ? r.s89_sales_yoy_pct : r.close_rate_q_pct, n: r.n_stores };
  });
  const [k, dir] = sort;
  const val = r => (k === "rent" ? r.rentScore : k === "abs" ? (A_ORD[r.abs] ?? -1) : k === "name" ? r.name : r[k]);
  rows.sort((a, b) => { const x = val(a), y = val(b); if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * dir; });
  const H = ({ id, children, r, tip }) => (
    <th className={r ? "r" : ""} aria-sort={k === id ? (dir > 0 ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => setSort([id, k === id ? -dir : -1])}>{children}{k === id ? (dir > 0 ? " ▲" : " ▼") : ""}</button>{tip && <> <Help tip={tip} /></>}
    </th>
  );
  const open = r => { setState(dong ? { selDong: r.key, unit: "dong" } : { sel: r.key, unit: "area" }); go("/map"); };
  return (
    <div className="page">
      <Controls meta={meta} unit />
      <div className="page-h">
        <h1 className="page-t">{dong ? "82개 행정동" : "20개 상권"} 비교</h1>
        <p className="page-sub">머리글을 누르면 정렬됩니다. 행을 누르면 지도에서 그 곳이 열립니다. 점수는 {dong ? "82개 동" : "20개 상권"} 안 상대 순위입니다.</p>
      </div>
      <div className="tablewrap">
        <table className="t">
          <thead><tr>
            <H id="name">{dong ? "행정동" : "상권"}</H><H id="quadrant">진단</H><H id="stab" r>안정도</H>
            <H id="risk" r tip={HELP.risk}>상대 위험</H><H id="growth" r tip={HELP.growth}>상대 성장</H><H id="abs" tip={HELP.abs}>절대 쇠퇴 신호</H>
            <H id="tram" r>상권 가치 효과</H><H id="comp" r tip={HELP.comp}>업종 변화</H><H id="rent" tip={HELP.rent}>임대료 신호</H>
            <H id="land5" r>땅값 5년</H><H id="share" r>점포 비중 5년</H><H id="extra" r>{dong ? "카드매출 증감" : "분기 폐업률"}</H><H id="n" r>점포 수</H>
          </tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.key} className="click" onClick={() => open(r)} tabIndex={0} onKeyDown={e => e.key === "Enter" && open(r)}>
                <td><b style={{ fontWeight: 600 }}>{r.name}</b></td>
                <td><QBadge q={r.quadrant} />{r.r.quadrant_uncertain && <span className="small" style={{ color: "var(--q-decline)", marginLeft: 6 }}>불확실</span>}</td>
                <td className="r">{r.stab != null ? Math.round(r.stab * 100) + "%" : "-"}</td>
                <td className="r">{Math.round(r.risk)}</td><td className="r">{Math.round(r.growth)}</td>
                <td>{r.abs || "-"}</td>
                <td className="r">{st.tramAfter ? pct(r.tram) : "-"}</td>
                <td className="r">{st.tramAfter && r.comp != null ? pp(r.comp) : "-"}</td>
                <td>{r.rent}</td>
                <td className="r">{pct(r.land5)}</td><td className="r">{r.share != null && Math.abs(r.share) > 200 ? <span title="2021 대형 쇼핑몰 입점 점포가 한꺼번에 등록된 왜곡 — 점포 지표는 해석하지 말 것">{pct(r.share)}*</span> : pct(r.share)}</td>
                <td className="r">{dong ? pct(r.extra) : r.extra != null ? r.extra.toFixed(2) + "%" : "-"}</td>
                <td className="r">{int(r.n)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="src">{!dong && "* 도룡동 점포 비중은 2021 대형 쇼핑몰 입점 점포가 한꺼번에 등록된 왜곡이라 해석하지 않습니다. "}출처: {dong ? "outputs/dong_map_profile.csv · 카드매출 증감: " + meta.sources.s8989 : "outputs/area_profile.csv"} · outputs/tram_scenarios.csv · composition_forecast.csv · rent_pressure.csv</p>
    </div>
  );
}
