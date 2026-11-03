# 대전 트램 상권 지도 — 공개 웹사이트 (React)

Streamlit 앱(`app.py`)과 같은 분석 결과를 보여 주는 정적 사이트. 서버 없이 `dist/` 폴더만 올리면 됨 (Netlify·GitHub Pages 등).

## 구조
- `src/` React 19 (JSX) — 화면: 커버 · 지도 · 3D 지도 · 업종 점수 · 비교 · AI 해설 · 트램과 관광 · 분석 방법
  - `lib.js` 데이터 읽기·상태·색·시나리오 규칙 (app.py 와 같은 규칙), `ui.jsx` 조작 줄·차트, `MapView.jsx` deck.gl 지도
  - `cover/` 커버(시안 D) — `tram_model/cover_page.py` 의 HTML·CSS·JS 그대로
- `public/vendor/` GSAP (커버 애니메이션, CDN 없이)
- 자료: `python tram_model/export_web.py` → 프로젝트 폴더 `web_data/` (JSON·그림·3D 지도) → 빌드 때 `dist/data/` 로 복사
- 외부: deck.gl 9.1.14 (jsdelivr), 바탕 지도 CARTO, 글꼴 Pretendard·Newsreader

## 빌드
```bash
cd web && node build.mjs --prod      # esbuild 필요 (npm i -D esbuild react react-dom d3-scale d3-shape marked)
```

## 공개 원칙
- 8989 원자료·월별 매출·금액은 넣지 않음. 행정동 카드매출 증감(%)만 출처와 함께
- Gemini 키 없음: AI 해설은 미리 만든 기본 해설 20곳. 맞춤 질문은 안내만 — 실시간은 발표용 Streamlit 앱에서
