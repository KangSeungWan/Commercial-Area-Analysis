import { createRoot } from "react-dom/client";
import { lazy, Suspense, useEffect, useRef } from "react";
import "./app.css";
import { useRoute, useApp, go } from "./lib.js";
import Cover from "./pages/Cover.jsx";
import MapPage from "./pages/MapPage.jsx";
import IndustryPage from "./pages/IndustryPage.jsx";
import ComparePage from "./pages/ComparePage.jsx";
import AIPage from "./pages/AIPage.jsx";
import TourismPage from "./pages/TourismPage.jsx";
import AboutPage from "./pages/AboutPage.jsx";

const NAV = [["/map", "지도"], ["/3d", "3D 지도"], ["/industry", "업종 점수"], ["/compare", "비교"], ["/ai", "AI 해설"], ["/tourism", "트램과 관광"], ["/about", "분석 방법"]];
const TITLES = { "/map": "지도", "/3d": "3D 지도", "/industry": "업종 점수", "/compare": "비교", "/ai": "AI 해설", "/tourism": "트램과 관광", "/about": "분석 방법" };

function Map3D() {
  const { q } = useRoute();
  const st = useApp();
  return (
    <div className="page">
      <div className="page-h">
        <h1 className="page-t">3D 지도</h1>
        <p className="page-sub">상권 20곳을 기둥으로 세워 2026→2034 땅값·업종(카페) 변화와 2030 개통 후 트램 운행을 재생합니다. 기둥을 누르면 상권 카드가 뜹니다. 트램 운행 모습은 연출이며 실제 배차와 다릅니다.</p>
      </div>
      <iframe className="frame3d" title="3D 지도" src={`./map3d.html#sel=${q.area || st.sel || ""}`} loading="lazy" />
    </div>
  );
}

function App() {
  const { path } = useRoute();
  const mainRef = useRef(null), first = useRef(true);
  useEffect(() => {
    document.title = path === "/" ? "대전 트램 상권 지도" : `${TITLES[path] || ""} · 대전 트램 상권 지도`; window.scrollTo(0, 0);
    // 화면이 바뀌면 본문으로 초점 이동(화면 읽기 프로그램), 좁은 화면에서는 고른 메뉴가 보이게
    if (!first.current) mainRef.current?.focus({ preventScroll: true });
    first.current = false;
    document.querySelector('.nav a[aria-current="page"]')?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [path]);
  const Page = { "/": Cover, "/map": MapPage, "/3d": Map3D, "/industry": IndustryPage, "/compare": ComparePage, "/ai": AIPage, "/tourism": TourismPage, "/about": AboutPage }[path] || MapPage;
  return (
    <>
      <a className="skip" href="#main" onClick={e => { e.preventDefault(); mainRef.current?.focus(); }}>본문으로 건너뛰기</a>
      <header className="top">
        <div className="top-in">
          <a className="mark" href="#/" aria-label="처음 화면으로"><i /><span>대전 트램 상권 지도</span></a>
          <nav className="nav" aria-label="화면">
            {NAV.map(([p, t]) => <a key={p} href={"#" + p} aria-current={path === p ? "page" : undefined}>{t}</a>)}
          </nav>
          <span className="top-src">2030 개통 트램 2호선 · 공공데이터 분석</span>
        </div>
      </header>
      <main id="main" ref={mainRef} tabIndex={-1}><Page /></main>
      <footer className="foot">
        <div className="foot-in">
          <p>자료: 국토교통부 개별공시지가·전국 버스정류장, 소상공인시장진흥공단 상가(상권)정보, 행정안전부 지방행정 인허가(LOCALDATA), 통계청 행정동 경계,
            한국부동산원 임대동향(R-ONE), 대전광역시 대전트램 누리집 정거장 위치도·노선도(좌표 보정 참고), 2021 소상공인 실태조사, 한국철도공사 역별 승하차(공공데이터포털), 대전교통공사·대전복합터미널 발표 자료,
            문화체육관광부 주요관광지점 입장객 통계, 대전광역시 자치구별 신용카드(KB국민카드) 매출액·온통대전 업종별 매출액(공공데이터포털), 서울 열린데이터광장 상권분석·개별공시지가(비교 분석), 국가공간정보포털 연속지적도(비교 분석),
            대전광역시·대전신용보증재단, 「대전 소상공인 상권분석 서비스」(https://8989.daejeon.go.kr)(활용 허가, 분석 결과 요약만 표시, 재배포 금지).</p>
          <p>※ 상권분석 서비스의 일부 통계를 활용하여 충남대학교 학생 연구팀이 자체 분석·가공한 결과이며, 대전광역시 또는 대전신용보증재단의 공식 분석이나 전망은 아님.</p>
          <p>땅값 기준 트램 효과와 모든 진단·점수는 공개 자료로 만든 추정값이며 매출 변화가 아닙니다. 정거장 좌표 일부는 공개 도면 기준 추정값입니다.
            투자·임대·계약 판단의 근거로 쓰지 마세요. AI 해설은 AI가 쓴 참고 글입니다. <a href="./THIRD_PARTY_NOTICES.txt">오픈소스 라이선스</a></p>
        </div>
      </footer>
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
