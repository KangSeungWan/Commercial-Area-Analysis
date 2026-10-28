import { createRoot } from "react-dom/client";
import { lazy, Suspense, useEffect } from "react";
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
  useEffect(() => { document.title = path === "/" ? "대전 트램 상권 지도" : `${TITLES[path] || ""} · 대전 트램 상권 지도`; window.scrollTo(0, 0); }, [path]);
  const Page = { "/": Cover, "/map": MapPage, "/3d": Map3D, "/industry": IndustryPage, "/compare": ComparePage, "/ai": AIPage, "/tourism": TourismPage, "/about": AboutPage }[path] || MapPage;
  return (
    <>
      <header className="top">
        <div className="top-in">
          <a className="mark" href="#/" aria-label="처음 화면으로"><i /><span>대전 트램 상권 지도</span></a>
          <nav className="nav" aria-label="화면">
            {NAV.map(([p, t]) => <a key={p} href={"#" + p} aria-current={path === p ? "page" : undefined}>{t}</a>)}
          </nav>
          <span className="top-src">2030 개통 트램 2호선 · 공공데이터 분석</span>
        </div>
      </header>
      <main><Page /></main>
      <footer className="foot">
        <div className="foot-in">
          <p>자료: 국토교통부 개별공시지가, 소상공인시장진흥공단 상가(상권)정보, 대전시 트램 2호선 정거장 자료, 2021 대전 소상공인 실태조사, 한국부동산원 임대동향,
            대전신용보증재단 '대전 소상공인 상권분석 서비스'(8989.daejeon.go.kr) 상권 정보(재단 활용 허가, 재배포 금지), 문화체육관광부 주요관광지점 입장객 통계.</p>
          <p>땅값 기준 트램 효과는 추정값이며 매출 변화가 아닙니다. 정거장 좌표 일부는 공개 도면 기준 추정값입니다.</p>
        </div>
      </footer>
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
