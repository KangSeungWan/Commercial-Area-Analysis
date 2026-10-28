// 공통: 데이터 읽기, 색, 숫자 형식, 시나리오 규칙 (app.py 와 같은 규칙)
import { useEffect, useState, useSyncExternalStore } from "react";

// ── 데이터 ──
const cache = {};
export function load(name) {
  if (!cache[name]) cache[name] = fetch(`./data/${name}.json`).then(r => {
    if (!r.ok) throw new Error(`${name}.json ${r.status}`);
    return r.json();
  });
  return cache[name];
}
export function useData(names) {
  const [st, setSt] = useState({ data: null, error: null });
  const key = names.join(",");
  useEffect(() => {
    let live = true;
    Promise.all(names.map(load)).then(v => live && setSt({ data: Object.fromEntries(names.map((n, i) => [n, v[i]])), error: null }))
      .catch(e => live && setSt({ data: null, error: e }));
    return () => { live = false; };
  }, [key]);
  return st;
}

// ── 주소(해시) 라우터: #/map?area=A06 ──
function parseHash() {
  const h = location.hash.replace(/^#/, "") || "/";
  const [path, qs] = h.split("?");
  return { path: path || "/", q: Object.fromEntries(new URLSearchParams(qs || "")) };
}
let route = parseHash();
const subs = new Set();
addEventListener("hashchange", () => { route = parseHash(); subs.forEach(f => f()); });
export function useRoute() {
  return useSyncExternalStore(f => { subs.add(f); return () => subs.delete(f); }, () => route);
}
export function go(path, q) {
  const s = q ? "?" + new URLSearchParams(Object.entries(q).filter(([, v]) => v != null && v !== "")).toString() : "";
  location.hash = path + s;
}

// ── 앱 상태 (화면을 옮겨도 남음) ──
const S = { tramAfter: true, scen: "base", unit: "area", metric: "quadrant", sel: null, selDong: null, station: null,
  weights: null, region: true, labels: true };
try { Object.assign(S, JSON.parse(sessionStorage.getItem("tram-state") || "{}")); } catch { /* 저장 공간 없음 */ }
const ssubs = new Set();
let snap = { ...S };
export function setState(p) {
  Object.assign(S, p); snap = { ...S };
  try { sessionStorage.setItem("tram-state", JSON.stringify(S)); } catch { /* 무시 */ }
  ssubs.forEach(f => f());
}
export function useApp() {
  return useSyncExternalStore(f => { ssubs.add(f); return () => ssubs.delete(f); }, () => snap);
}

// ── 색 (DESIGN.md: 진단 4분류·지표 색 단계는 뜻 고정) ──
export const QC = { "성장 지속": [34, 139, 84], "트램 반등 기회": [235, 130, 20], "쇠퇴 우려": [200, 50, 50], "정체·안정": [140, 140, 140] };
export const QHEX = Object.fromEntries(Object.entries(QC).map(([k, v]) => [k, rgb(v)]));
export const QTXT = { "성장 지속": "#ffffff", "트램 반등 기회": "#0a1d08", "쇠퇴 우려": "#ffffff", "정체·안정": "#0a1d08" };
export const RENT_C = { "높음": [106, 42, 140], "보통": [166, 120, 198], "낮음": [221, 208, 234], "해당 없음": [228, 230, 233] };
export const RAMP = {
  bad: ["#fff4d6", "#f2a65a", "#b8322a"], good: ["#eef7ee", "#83c58f", "#1d7a46"], tram: ["#eef1fb", "#8ea2e6", "#2c3fa8"],
  neutral: ["#f1f3f5", "#9aa5b1", "#2f3b48"], cafe: ["#f7f0e8", "#d4a373", "#7f4f24"], div: ["#6b4c9a", "#f4f4f2", "#1f7a7a"],
};
export const ROUTE_C = [35, 39, 46];
export function rgb(c) { return `rgb(${c[0]},${c[1]},${c[2]})`; }
const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
function interp(stops, t) {
  const n = stops.length - 1, i = Math.min(Math.floor(t * n), n - 1), f = t * n - i;
  const a = hex(stops[i]), b = hex(stops[i + 1]);
  return a.map((x, j) => Math.round(x + (b[j] - x) * f));
}
function q95(arr) {
  const v = arr.filter(x => x != null && !isNaN(x)).sort((a, b) => a - b);
  if (!v.length) return 0;
  const p = (v.length - 1) * .95, lo = Math.floor(p), hi = Math.ceil(p);
  return v[lo] + (v[hi] - v[lo]) * (p - lo);
}
/** 숫자 → 색. kind: seq_bad/good/tram/neutral/cafe, div0, divavg(center) */
export function colorize(values, kind, center = null, span = null) {
  if (kind.startsWith("div")) {
    const c = center ?? 0;
    const m = span || q95(values.map(v => v == null ? null : Math.abs(v - c))) || 1;
    return { cols: values.map(v => v == null ? [210, 210, 210] : interp(RAMP.div, (Math.max(-m, Math.min(m, v - c)) / m + 1) / 2)),
      stops: RAMP.div, lo: c - m, hi: c + m };
  }
  const ok = values.filter(v => v != null && !isNaN(v));
  const lo = Math.min(...ok), hi = q95(values);
  const stops = RAMP[kind.split("_")[1]];
  return { cols: values.map(v => v == null ? [210, 210, 210] : interp(stops, Math.max(0, Math.min(1, (Math.min(v, hi) - lo) / (hi - lo + 1e-9))))),
    stops, lo, hi };
}

// ── 숫자 ──
export const f1 = v => v == null || isNaN(v) ? "-" : (+v).toFixed(1);
export const pct = (v, d = 1) => v == null || isNaN(v) ? "-" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}%`;
export const pp = (v, d = 1) => v == null || isNaN(v) ? "-" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}%p`;
export const int = v => v == null || isNaN(v) ? "-" : Math.round(v).toLocaleString("ko-KR");
export function eok(v) {
  if (v == null || isNaN(v)) return "-";
  return Math.abs(v) >= 1e4 ? `${(v / 1e4).toFixed(2)}조 원` : `${Math.round(v).toLocaleString("ko-KR")}억 원`;
}
export const short = n => (n || "").split("(")[0];

// ── 시나리오 규칙 ──
export const SCEN_ORDER = ["low", "base", "high"];
export const effCol = s => s === "base" ? "tram_effect" : `tram_effect_${s}`;
/** 상권·행정동 한 곳의 '지금 조작 상태' 값 */
export function view(r, st) {
  const after = st.tramAfter, s = st.scen;
  const comp = r.comp?.[s];
  return {
    quadrant: after ? r.quadrant_after : r.quadrant_before,
    tram: r[effCol(s)],
    tram_sel: after ? r[effCol(s)] : 0,
    land_fc: r.land_fc ? r.land_fc[after ? s : "none"] : null,
    comp: after ? (comp?.pp ?? null) : 0,
    compInfo: comp,
    rent: after ? (r.rent?.grade || "해당 없음") : "해당 없음",
    money: r.money?.[s],
  };
}
export const METRICS = {
  quadrant: { short: "진단", kind: "cat" },
  tram_sel: { short: "상권 가치 효과", kind: "seq_tram", tram: true },
  comp: { short: "업종 변화", kind: "seq_cafe", tram: true },
  rent: { short: "임대료 신호", kind: "cat_rent", tram: true },
  land_fc: { short: "땅값 전망", kind: "div0", ref: true },
  land_chg_5y_pct: { short: "땅값 5년", kind: "divavg", ref: true },
  store_share_chg_5y_pct: { short: "점포 비중", kind: "div0", ref: true },
};
export function metricLabel(m, st, scenLabel) {
  const mode = st.tramAfter ? "건설 후" : "건설 전";
  return {
    quadrant: `진단 (트램 ${mode})`, tram_sel: `상권 가치(땅값) 기준 트램 효과 (%, ${scenLabel}, 개통 초기 1~4년)`,
    comp: `업종 변화: 2034 카페·빵집 비중 증가 (%p, ${scenLabel})`, rent: "임대료 부담 신호 (상대 순위, 건설 후)",
    land_fc: `땅값 전망 2026→2034 (%, 트램 ${mode})`, land_chg_5y_pct: "땅값 5년 상승률 (%)", store_share_chg_5y_pct: "대전 내 점포 비중 5년 변화 (%)",
  }[m];
}
export const TRAM_DEF = "상권 가치(땅값) 기준 효과: 개통 초기 1~4년, 정거장 500m 안 땅값으로 추정한 %. 점포당 매출 변화가 아님(대전 실측상 매출 차이는 작음)";
export const HELP = {
  quadrant: "상대 쇠퇴 위험 50점 이상 + 상권 점포 절반 이상이 정거장 500m 안 → 트램 반등 기회, 500m 밖 → 쇠퇴 우려. 위험 50 미만은 성장 점수로 성장 지속·정체·안정. 15가지 변형에서 80% 미만으로 같으면 '불확실'. '반등 기회'는 트램이 땅값을 올릴 위치라는 뜻이며 가게 생존은 임대료 신호와 함께 봐야 함",
  comp: "트램 개통 4년 뒤(2034) 음식점 중 카페·빵집 비중이 몇 %p 늘지. 대전 1호선 근거: 역 500m 안 카페 수 +25%, 음식점 중 카페 비중 +1.4%p(1단계)·+4.0%p(2단계에서 따로 재현)",
  rent: "측정한 임대료가 아니라 '밀려날 위험 신호'를 상대 순위로 매긴 것. ① 매출로 뒷받침되지 않는 땅값 상승 × 개인 점포 비율 ② 폐업률 ③ 카페 증가(업종 교체) — 같은 무게로 백분위 평균. 지금 대전 상가 임대료는 13년째 하락·공실 많음 → '공실이 채워지고 땅값이 오른 뒤 생길 수 있는 부담'",
  risk: "땅값 상대 하락·점포 비중 감소·폐업률을 20개 상권(또는 82개 동) 안 순위로 합친 점수. 언제나 약 절반이 50 이상",
  growth: "상권 가치 기준 트램 효과·개업률·최근 점포 비중을 순위로 합친 점수",
  abs: "대전 전체 기준(상대 점수 보조): 최근 3년 점포 비중 감소 + 폐업률 대전 평균 초과면 '있음', 10년 비중 감소·폐업 > 개업까지 4가지 모두면 '강함'",
};
export function ruleText(q, quadAfter, i5) {
  const t = i5 == null ? "-" : `${Math.round(i5 * 100)}%`;
  if (q === "트램 반등 기회") return `위험 50점 이상, 점포 ${t}가 정거장 500m 안(절반 이상)이라 트램 반등 기회`;
  if (q === "쇠퇴 우려") return quadAfter === "트램 반등 기회" ? "위험 50점 이상, 트램이 없으면 정거장 500m 기준이 사라져 쇠퇴 우려" : `위험 50점 이상, 정거장 500m 안 점포 ${t}(절반 미만)라 쇠퇴 우려`;
  if (q === "성장 지속") return "위험 50점 미만, 성장 50점 이상이라 성장 지속";
  return "위험·성장 모두 50점 미만이라 정체·안정";
}
export function scenLabel(meta, s) { const t = meta.scen[s]; return t ? `${t.label} ${pct(t.effect_pct)}` : s; }
