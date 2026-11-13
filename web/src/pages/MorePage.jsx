// '더 보기': 자주 안 쓰는 화면을 한곳에 (2026-11-12 메뉴 4개 개편)
import { Reveal } from "../viz.jsx";

export const MORE = [
  { path: "/ai", title: "AI 쉬운 해설", desc: "상권마다 담당자가 상인에게 설명할 말", g: "M5 6h14v9H9l-4 3z" },
  { path: "/compare", title: "비교 표", desc: "상권·행정동을 한 표에서 정렬", g: "M4 6h16M4 12h16M4 18h16M9 4v16" },
  { path: "/industry", title: "업종 점수", desc: "업종별 100점 점수, 트램 전·후", g: "M6 18V11M12 18V6M18 18v-4" },
  { path: "/3d", title: "3D 지도", desc: "2026→2034 변화를 기둥으로 재생", g: "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5" },
  { path: "/tourism", title: "트램과 관광", desc: "부수 효과, 해외 사례", g: "M12 21s-6-5.5-6-10a6 6 0 0 1 12 0c0 4.5-6 10-6 10zM12 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4z" },
  { path: "/about", title: "분석 방법", desc: "데이터·모델·논문·한계 전체", g: "M6 4h9l3 3v13H6zM9 11h6M9 15h6" },
];

export default function MorePage() {
  return (
    <div className="page">
      <div className="page-h"><h1 className="page-t">더 보기</h1></div>
      <div className="more-grid">
        {MORE.map((m, i) => (
          <Reveal key={m.path} as="a" delay={i * 50} className="more-card" href={"#" + m.path}>
            <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><path d={m.g} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
            <span className="more-t">{m.title}</span>
            <span className="more-d">{m.desc}</span>
          </Reveal>
        ))}
      </div>
    </div>
  );
}
