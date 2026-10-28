// 관광지·관문 그림 표시: 이름·종류로 그림 종류를 고르고, 둥근 배지 안에 흰 그림(SVG)을 그림.
// 지도(deck.gl IconLayer)와 범례가 같은 그림을 씀.

const W = 'fill="#fff"';
const S = 'fill="none" stroke="#fff" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"';

// viewBox 0 0 24 24, 가운데 (12,12) 근처 14px 안
export const KINDS = {
  train: { label: "기차역", g: `<rect x="7" y="5.5" width="10" height="10.5" rx="2.2" ${W}/><rect x="8.6" y="7.3" width="6.8" height="3.4" rx=".6" fill="currentColor"/><circle cx="9.6" cy="13.3" r=".95" fill="currentColor"/><circle cx="14.4" cy="13.3" r=".95" fill="currentColor"/><path d="M9 16l-1.6 2.6M15 16l1.6 2.6" ${S}/>` },
  bus: { label: "버스터미널", g: `<rect x="6" y="5.5" width="12" height="11" rx="2" ${W}/><rect x="7.6" y="7.2" width="8.8" height="3.8" rx=".5" fill="currentColor"/><circle cx="8.8" cy="13.6" r=".9" fill="currentColor"/><circle cx="15.2" cy="13.6" r=".9" fill="currentColor"/><rect x="7.4" y="16.3" width="2" height="2" rx=".5" ${W}/><rect x="14.6" y="16.3" width="2" height="2" rx=".5" ${W}/>` },
  mountain: { label: "산·숲·휴양림", g: `<path d="M3.8 17.5l5.4-8.6 3 4.6 2.2-3.2 5.8 7.2z" ${W}/><path d="M9.2 8.9l1.4 2.2-1.4-.6-1.3.8z" fill="currentColor"/>` },
  park: { label: "공원·수목원·호수", g: `<circle cx="12" cy="9.6" r="4.8" ${W}/><rect x="11" y="13" width="2" height="5.4" rx=".6" ${W}/><path d="M7 18.6h10" ${S}/>` },
  museum: { label: "박물관·과학관·미술관", g: `<path d="M5 9.2L12 5.2l7 4z" ${W}/><rect x="6.6" y="10.2" width="2" height="6" ${W}/><rect x="11" y="10.2" width="2" height="6" ${W}/><rect x="15.4" y="10.2" width="2" height="6" ${W}/><rect x="5" y="16.8" width="14" height="1.8" rx=".4" ${W}/>` },
  heritage: { label: "문화재·옛집", g: `<path d="M3.6 10.6c3 .9 5.6-.8 8.4-3.8 2.8 3 5.4 4.7 8.4 3.8l-1.8 1.6H5.4z" ${W}/><rect x="7" y="12.6" width="10" height="5.6" ${W}/><rect x="10.8" y="14.2" width="2.4" height="4" fill="currentColor"/>` },
  shop: { label: "시장·빵집·거리", g: `<path d="M6.6 9.2h10.8l.9 9H5.7z" ${W}/><path d="M9.4 9.2V7.8a2.6 2.6 0 0 1 5.2 0v1.4" ${S}/>` },
  festival: { label: "축제·경기장", g: `<path d="M12 4.6l2.2 4.6 5 .6-3.7 3.4 1 5-4.5-2.5-4.5 2.5 1-5-3.7-3.4 5-.6z" ${W}/>` },
  spa: { label: "온천", g: `<path d="M5.6 14.2h12.8a6.4 3.6 0 0 1-12.8 0z" ${W}/><path d="M9 12c-1.1-1.4 1.1-2.4 0-4M12 12c-1.1-1.4 1.1-2.4 0-4M15 12c-1.1-1.4 1.1-2.4 0-4" ${S}/>` },
  camp: { label: "캠핑장", g: `<path d="M12 5.4l7.4 12.4H4.6z" ${W}/><path d="M12 11l2.6 6.8H9.4z" fill="currentColor"/>` },
  fun: { label: "테마파크·아쿠아리움", g: `<circle cx="12" cy="10.4" r="5.2" ${S}/><path d="M12 5.2v10.4M6.8 10.4h10.4M8.3 6.7l7.4 7.4M15.7 6.7l-7.4 7.4" ${S} stroke-width="1"/><path d="M12 10.4l-3.4 8.2M12 10.4l3.4 8.2M7.6 18.6h8.8" ${S}/>` },
  science: { label: "대학·연구단지", g: `<circle cx="12" cy="12" r="1.7" ${W}/><ellipse cx="12" cy="12" rx="7" ry="2.8" ${S} stroke-width="1.3"/><ellipse cx="12" cy="12" rx="7" ry="2.8" ${S} stroke-width="1.3" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="7" ry="2.8" ${S} stroke-width="1.3" transform="rotate(-60 12 12)"/>` },
};

const RULES = [
  ["fun", /아쿠아리움|오-월드|오월드|테마파크|어린이회관|로파크/],
  ["spa", /온천|스파|족욕/],
  ["camp", /캠핑/],
  ["festival", /축제장|볼파크|0시/],
  ["shop", /시장|빵집|성심당|거리|스카이로드|신세계|카페|5일장/],
  ["science", /카이스트|KAIST|연구원|발명/],
  ["museum", /박물관|미술관|과학관|전시관|천문대|기념물센터|예술의전당|헤레디움|체험관|생태관|기념구역/],
  ["heritage", /민속마을|사적공원/],
  ["mountain", /산성|산 |산$|휴양림|수통골|전망대|황톳길|계족산|식장산|보문산|장태산|만인산/],
  ["park", /공원|수목원|호수|유원지|정원|마을|하늘공원/],
  ["heritage", /서원|향교|당|고택|사$|사 |사당|천단|민속|생가|형무소|도청|공관|테미오래|사적|관사촌|원$|루$|성지|현충원/],
];

export function poiKind(p) {
  if (p.gateway) return /터미널/.test(p.name) ? "bus" : "train";
  const n = p.name || "";
  for (const [k, re] of RULES) if (re.test(n)) return k;
  if (p.type === "문화재(소규모)") return "heritage";
  if (p.type === "축제장") return "festival";
  if (p.type === "체험시설") return "museum";
  return "park";
}

export const BADGE = { poi: "#7f4f24", gate: "#23272e", minor: "#9a7b5c" };

export function badgeColor(p) {
  if (p.gateway) return BADGE.gate;
  return p.type === "문화재(소규모)" ? BADGE.minor : BADGE.poi;
}

export function iconSvg(kind, bg, size = 48) {
  const g = (KINDS[kind] || KINDS.park).g;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" color="${bg}">` +
    `<circle cx="12" cy="12" r="11" fill="${bg}" stroke="#fff" stroke-width="1.4"/>${g}</svg>`;
}

const cache = {};
export function iconUrl(kind, bg) {
  const k = kind + bg;
  if (!cache[k]) cache[k] = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(iconSvg(kind, bg));
  return cache[k];
}

// 지도용 그림 묶음(public/img/poi-atlas.png, 64px 칸) — icons.js 의 그림으로 미리 그려 둔 PNG (scripts: 빌드 때 다시 그리려면 /web/tools 참고)
export const ATLAS_URL = "./img/poi-atlas.png";
export const ATLAS_MAP = {"train#7f4f24":{"x":0,"y":0,"width":64,"height":64,"anchorY":32},"bus#7f4f24":{"x":64,"y":0,"width":64,"height":64,"anchorY":32},"mountain#7f4f24":{"x":128,"y":0,"width":64,"height":64,"anchorY":32},"park#7f4f24":{"x":192,"y":0,"width":64,"height":64,"anchorY":32},"museum#7f4f24":{"x":256,"y":0,"width":64,"height":64,"anchorY":32},"heritage#7f4f24":{"x":320,"y":0,"width":64,"height":64,"anchorY":32},"shop#7f4f24":{"x":384,"y":0,"width":64,"height":64,"anchorY":32},"festival#7f4f24":{"x":448,"y":0,"width":64,"height":64,"anchorY":32},"spa#7f4f24":{"x":512,"y":0,"width":64,"height":64,"anchorY":32},"camp#7f4f24":{"x":576,"y":0,"width":64,"height":64,"anchorY":32},"fun#7f4f24":{"x":640,"y":0,"width":64,"height":64,"anchorY":32},"science#7f4f24":{"x":704,"y":0,"width":64,"height":64,"anchorY":32},"train#23272e":{"x":0,"y":64,"width":64,"height":64,"anchorY":32},"bus#23272e":{"x":64,"y":64,"width":64,"height":64,"anchorY":32},"mountain#23272e":{"x":128,"y":64,"width":64,"height":64,"anchorY":32},"park#23272e":{"x":192,"y":64,"width":64,"height":64,"anchorY":32},"museum#23272e":{"x":256,"y":64,"width":64,"height":64,"anchorY":32},"heritage#23272e":{"x":320,"y":64,"width":64,"height":64,"anchorY":32},"shop#23272e":{"x":384,"y":64,"width":64,"height":64,"anchorY":32},"festival#23272e":{"x":448,"y":64,"width":64,"height":64,"anchorY":32},"spa#23272e":{"x":512,"y":64,"width":64,"height":64,"anchorY":32},"camp#23272e":{"x":576,"y":64,"width":64,"height":64,"anchorY":32},"fun#23272e":{"x":640,"y":64,"width":64,"height":64,"anchorY":32},"science#23272e":{"x":704,"y":64,"width":64,"height":64,"anchorY":32},"train#9a7b5c":{"x":0,"y":128,"width":64,"height":64,"anchorY":32},"bus#9a7b5c":{"x":64,"y":128,"width":64,"height":64,"anchorY":32},"mountain#9a7b5c":{"x":128,"y":128,"width":64,"height":64,"anchorY":32},"park#9a7b5c":{"x":192,"y":128,"width":64,"height":64,"anchorY":32},"museum#9a7b5c":{"x":256,"y":128,"width":64,"height":64,"anchorY":32},"heritage#9a7b5c":{"x":320,"y":128,"width":64,"height":64,"anchorY":32},"shop#9a7b5c":{"x":384,"y":128,"width":64,"height":64,"anchorY":32},"festival#9a7b5c":{"x":448,"y":128,"width":64,"height":64,"anchorY":32},"spa#9a7b5c":{"x":512,"y":128,"width":64,"height":64,"anchorY":32},"camp#9a7b5c":{"x":576,"y":128,"width":64,"height":64,"anchorY":32},"fun#9a7b5c":{"x":640,"y":128,"width":64,"height":64,"anchorY":32},"science#9a7b5c":{"x":704,"y":128,"width":64,"height":64,"anchorY":32}};
