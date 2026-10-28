# Commercial-Area-Analysis

대전 트램 2호선(2030 하반기 개통 예정) 정거장 주변 상권 분석 — 팀 공모전 프로젝트.

## 구성
- `app.py` — Streamlit 앱 (발표·시연용. Gemini 실시간 AI 해설 포함). 실행: `streamlit run app.py`
- `tram_model/` — 분석 코드·자료·결과. 전체 재실행: `python tram_model/run_all.py`, 진행 상황은 `PROGRESS.md`
- `web/` — 공개 웹사이트 (React 정적 사이트). 자세한 내용은 `web/README.md`
- `web_data/` — 웹사이트용 자료 (`python tram_model/export_web.py` 로 만듦)

## 공개 웹사이트 배포
1. `python tram_model/export_web.py` → `web_data/` 갱신
2. `cd web && node build.mjs --prod` → `web/dist/`
3. `web/dist/` 폴더를 Netlify Drop(app.netlify.com/drop)에 끌어다 놓기

## 자료 사용 조건
- 8989 상권분석(대전신용보증재단): 활용 허가(2026-10), 재배포 금지·출처 명시. 원자료는 저장소에 넣지 않음
- 이 저장소는 비공개로 유지. 공개는 `web/dist` 빌드 결과만
