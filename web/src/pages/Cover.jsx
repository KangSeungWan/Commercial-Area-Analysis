import { useEffect, useRef } from "react";
import html from "../cover/cover.html";
import "../cover/cover.css";
import { mountCover } from "../cover/cover.js";
import { useData, go, pct, QORDER, QHEX, QTXT, QDO } from "../lib.js";

const LOOP = Array.from({ length: 40 }, (_, i) => 201 + i), BRANCH = [241, 242, 243, 244], SPURS = [[233, [245]]];

function coverRoute(meta) {
  const pos = Object.fromEntries(meta.stations.map(s => [s.no, [s.lon, s.lat]]));
  const loop = LOOP.filter(n => pos[n]);
  let branch = [];
  if (meta.route.length > 1) {
    const b0 = meta.route[1][0];
    const start = loop.find(n => Math.abs(pos[n][0] - b0[0]) < 1e-6 && Math.abs(pos[n][1] - b0[1]) < 1e-6) || loop[0];
    branch = [start, ...BRANCH.filter(n => pos[n])];
  }
  const spurs = SPURS.filter(([a]) => pos[a]).map(([a, ns]) => [[...pos[a], a], ...ns.filter(n => pos[n]).map(n => [...pos[n], n])]);
  return { loop: loop.map(n => [...pos[n], n]), branch: branch.map(n => [...pos[n], n]), spurs };
}


// 2026-11-13 첫 화면 그림 장면: 숫자는 모두 결과 파일(about·meta·areas·dongs)에서 읽음
const num = v => (v == null ? NaN : parseFloat(String(v).replace(/[−–]/g, "-").replace(/[^\d.\-+]/g, "")));
const GR = { "확실": ["#1e7d4a", "#fff"], "방향만": ["#eb8214", "#0a1d08"], "확인 안 됨": ["#9aa196", "#0a1d08"] };
const esc = t => String(t).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

function forestRows(about) {
  const N = about.numbers, S = i => about.story.find(s => s.what.startsWith("①②③④⑤"[i])) || {};
  const ci = String(N.base_ci || "").split("~").map(num);
  const cafe = (S(1).result || "").match(/카페 수 ([+\-−]?[\d.]+)% \[([\-−]?[\d.]+), ([\-−]?[\d.]+)\]/);
  const sales = (S(2).result || "").match(/땅값 \+?([\d.]+)% 차이 vs 점포당 매출 \+?([\d.]+)% \(95% ([\-−]?[\d.]+)~\+?([\d.]+)%\)/);
  const con = (about.construction || []).find(c => c["결과"] === "전체 카드매출");
  const rows = [];
  if (cafe) rows.push({ name: "업종 구성(카페 수)", sub: "트램이 바꿈", g: "확실", v: num(cafe[1]), lo: num(cafe[2]), hi: num(cafe[3]) });
  if (ci.length === 2 && !isNaN(ci[0])) rows.push({ name: "상권 가치(땅값)", sub: "오르는 방향", g: "방향만", v: num(N.pool), lo: ci[0], hi: ci[1] });
  if (sales) rows.push({ name: "점포당 매출", sub: "", g: "방향만", v: num(sales[2]), lo: num(sales[3]), hi: num(sales[4]), land: num(sales[1]) });
  if (con) rows.push({ name: "공사 기간 카드매출", sub: `공사 구간 ${con["처리_동"]}개 동`, g: "확인 안 됨", v: +con["효과_퍼센트"], lo: +con["하한"], hi: +con["상한"] });
  rows.push({ name: "임대료 부담 신호", sub: "'지켜볼 곳'으로만 씀", g: "확인 안 됨", text: "임대료 상승을 미리 알려 주지 못함 (전국 53개 상권 검사)" });
  const MIN = -10, MAX = 50, X = v => `${((Math.min(MAX, Math.max(MIN, v)) - MIN) / (MAX - MIN)) * 100}%`;
  const W = (a, b) => `${((Math.min(MAX, b) - Math.max(MIN, a)) / (MAX - MIN)) * 100}%`;
  return rows.map(r => {
    const [bg, fg] = GR[r.g];
    let track = `<span class="z" style="left:${X(0)}"></span>`;
    if (r.text) track = `<span class="txt">${esc(r.text)}</span>`;
    else if (r.land != null) track += `<span class="pair" style="left:${X(0)};width:${W(0, r.land)};background:#4a6d47" title="땅값"></span>`
      + `<span class="pair b" style="left:${X(0)};width:${W(0, r.v)};background:${bg}" title="점포당 매출"></span>`;
    else track += `<span class="bar" style="left:${X(r.lo)};width:${W(r.lo, r.hi)};background:${bg}"></span><span class="pt" style="left:${X(r.v)};background:${bg}"></span>`;
    const val = r.text ? "—" : r.land != null ? pct(r.v, 0) : pct(r.v);
    const sub = r.land != null ? `<i class="sw" style="background:#4a6d47"></i>땅값 ${pct(r.land, 0)} vs <i class="sw" style="background:${bg}"></i>매출 ${pct(r.v, 0)}` : esc(r.sub);
    return `<div class="cv-fi"><div class="cv-fl"><b>${esc(r.name)}</b><small>${sub}</small></div><div class="cv-ft">${track}</div>`
      + `<div class="cv-fv"><b>${val}</b><span class="cv-g" style="background:${bg};color:${fg}">${r.g}</span></div></div>`;
  }).join("");
}

function quadCells(areas, dongs) {
  const near = areas.filter(a => a.policy_target), dn = dongs.filter(d => d.policy_target);
  const cnt = (L, q) => L.filter(x => x.quadrant_after === q).length;
  const pos = { "변화 관찰": 0, "먼저 지원": 1, "정기 점검": 2, "기존 지원 연계": 3 };          // 왼위·오른위·왼아래·오른아래
  const cells = [...QORDER].sort((a, b) => pos[a] - pos[b]).map(q =>
    `<div class="cv-qc" style="background:${QHEX[q]};color:${QTXT[q]}"><div><span class="n">${cnt(near, q)}<small>곳</small></span><span class="d">동 ${cnt(dn, q)}곳</span></div>`
    + `<div><div class="nm">${esc(q)}</div><div class="do">${esc(QDO[q])}</div></div></div>`).join("");
  const nOut = areas.length - near.length;
  const split = `<span style="width:${near.length / areas.length * 100}%;background:#0a1d08"></span><span style="width:${nOut / areas.length * 100}%;background:#c8cac6"></span>`;
  const lab = `<span><b>${near.length}</b>곳 트램 근처 → 네 칸으로 진단</span><span><b>${nOut}</b>곳 노선 밖 비교 지역</span>`;
  return { cells, split, lab, nNear: near.length, nDong: dn.length };
}

export default function Cover() {
  const { data } = useData(["meta", "areas", "dongs", "about"]);
  const el = useRef(null);
  useEffect(() => {
    document.body.classList.add("on-cover");
    return () => document.body.classList.remove("on-cover");
  }, []);
  useEffect(() => {
    if (!data || !el.current || !window.gsap) return;
    const { meta, areas, dongs, about } = data;
    const Q = quadCells(areas, dongs);
    const put = (sel, h) => { const n = el.current.querySelector(sel); if (n) n.innerHTML = h; };
    put(".cv-forest", forestRows(about));
    put(".cv-quad", Q.cells); put(".cv-split-bar", Q.split); put(".cv-split-lab", Q.lab);
    const N = about.numbers || {};
    const stats = { n_area: Q.nNear, n_dong: Q.nDong, reg_n: N.reg_n ?? "-", reg_q: N.reg_q ?? "-", n_src: (about.data || []).length || "-" };
    window.scrollTo(0, 0);
    const stop = mountCover(el.current, coverRoute(meta), stats, act => {
      if (act === "open") go("/map");
      else if (act === "about") go("/about");
    });
    return () => stop && stop();
  }, [data]);
  return <div ref={el} className="cover-root" dangerouslySetInnerHTML={{ __html: html }} />;
}
