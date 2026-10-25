# 대전 트램 2호선 상권 모델 — 데이터 구축 · 학습 · 분석

## 실행
```bash
python -m pip install -r requirements.txt
# data/raw/ 에 원본 6종을 config.py 의 RAW 파일명으로 넣기
python build_dataset.py     # → outputs/ 데이터셋·피처
python train_analyze.py     # → outputs/ 지표·벤치마크·시나리오
```

## 파일
| 파일 | 내용 |
|---|---|
| `config.py` | 원본 경로, 격자(250m)·구역 반경(1km), 구역 유형, 환승 정거장 |
| `literature_params.csv` | 논문 7편에서 뽑은 41개 수치 (출처·쪽·표 번호 포함). 코드는 이 파일에서 값을 읽음 |
| `data/tram_stations_approx.csv` | 2호선 45개 정거장 추정 좌표 (버스정류장 기준 근사, ±100~300m) |
| `build_dataset.py` | 학습용 9개 컬럼 + 논문 기반 추가 피처 생성 |
| `train_analyze.py` | 타깃 진단 → ML(공간 CV) → 논문 계수 벤치마크 → 개통 효과 시나리오 |

## 논문이 코드에 들어간 위치
| 논문 | 쓰인 곳 | 값 |
|---|---|---|
| P2 Lan 외 2025 (영국 LRT, DID) | 시나리오 효과 크기·버스밀도 조절·시차, 500m 권역 피처 | 음식 POI +0.106, 소매 +0.092, 부동산 +0.108, 기타 +0.026(ns) / 버스 고밀 +0.119, 저밀 +0.009(ns) / 개통 6년 후부터 유의 |
| P3 김용래 외 2016 (수도권 30개 역) | 500m·1km 상권 피처, 대형상업시설·브랜드지수 대용, 승하차 탄력성(선택) | 매출←승하차 0.109 (탄력성 ≈0.32), 임대료←승하차 0.043, 임대료 매개효과 없음 |
| P4 정은애·성현곤 2018 (서울 블록 SEM) | 버스 300m 집수권 피처, OLS 벤치마크 | 매출←대중교통 0.157(전체)/0.091(주거)/0.040(상업, ns), 매출←사업체 0.114 |
| P5 Reyes-Schade 외 2025 (바르셀로나) | 500m 정거장 권역 정의 | 효과 크기 없음. 가로망 통합도·선택도 피처는 도로망 데이터 확보 시 추가 권장 |
| P6 Kakutani·Hiramatsu 2025 (고베 시뮬레이션) | 구역 유형 가중치, 효과 상한 | 방문객 중심 +4.9% / 2차 +8.1% / 주변 +15.0%, 주변 소비 +23.6%(상한) |
| P7 양충헌·김진국 2020 (수원 트램 LUTI) | 환승 정거장 플래그 | 총량 변화 ±0.02%: 창출보다 재배치. 소매는 환승·종점으로 |
| P1 이경미·김명수 2017 (대전 2호선 VISSIM) | literature_params 에만 기록 | 한밭대로 차량속도 13.3→5.5km/h, 계백로 7.5→3.2. 간선 피처는 도로 데이터 필요 |

## 시나리오 규칙 (`scenario()`)
- 대상: 정거장 500m 이내 셀 (P2 처리군 정의). 500m 밖은 0 (P2 Table 5: 인접지 파급 없음)
- **low** = P2 버스 저밀 계수 0.0089 (사실상 효과 없음)
- **base** = 버스 고밀 셀은 P2 업종별 계수, 저밀 셀은 0.0089 → × P6 구역 가중치 (중심 0.65 / 2차 1.08 / 주변 2.0)
- **high** = 버스 고밀 셀은 P2 고밀 계수 0.1193, 저밀 셀은 업종별 계수 → × 구역 가중치, 상한 log(1.236)
- 시차: 개통 후 1~5년은 0→50% 선형, 6년차부터 100% (P2 이벤트 스터디)
- 기준 매출: 2019년 3~7월 평균 (코로나 이전)
- 정거장 일 승하차 예측치가 생기면 `scenario(df, lit, tram_riders={정거장번호: 인원})` 로 P3 탄력성 항목이 추가됨

## 현재 결과를 읽는 법 (중요)
- `metrics.json` 의 `target_synthetic: true` — 지금 `sales` 는 구 단위 KB 매출을 점포 수로 나눈 값이라 log(sales) 의 99.8% 가 `n_same_type` 하나로 설명됨. ML R²·벤치마크 계수는 **파이프라인 검증용**이며 해석하면 안 됨.
- 위치별 실측 매출(예: 소상공인 상권분석 추정매출, 카드사 상권 단위 매출)로 `sales` 를 바꾸면 진단이 자동으로 꺼지고 같은 코드가 실제 분석을 수행함.
- 시나리오는 대전 데이터로 추정한 효과가 아니라 **해외·수도권 논문 효과를 대전 셀에 적용한 사전 추정치**임.

## 대전 20개 상권 (build_areas.py)
```bash
python -m pip install scikit-image   # 폴리곤 경계 추출용 (처음 한 번)
python tram_model/build_areas.py
```
- 정의: `data/sangkwon_areas.csv` — 상권 코드·이름·구·원도심/신도심·반경·기준점(여러 개면 `;`로 구분). 이 파일만 고치고 다시 실행하면 됨
- 기준점은 실행 시 점포 밀집 중심으로 최대 150m 보정되고, 이웃 상권과 겹치지 않게 나눔
- 출력: `outputs/sangkwon_polygons.geojson`(지도 클릭용), `sangkwon_summary.csv`(상권 요약), `sangkwon_anchors.csv`(보정 전후 기준점)

## 상가정보 과거 패널 (build_store_panel.py → analyze_store_panel.py)
```bash
# data/raw/상가_과거/ 에 소상공인시장진흥공단_상가(상권)정보_대전_YYYYMM.csv 여러 분기를 넣고
python tram_model/build_store_panel.py     # → outputs/store_panel.csv (20개 상권 × 42분기)
python tram_model/analyze_store_panel.py   # → panel_trend.png, panel_events.png, panel_event_effects.csv
```
- 2025-03 파일은 좌표가 강원도로 잘못 들어 있어 앞뒤 분기 같은 점포 좌표로 자동 복원
- 자료 단절 분기(2023-03, 2024-12, 2026-06)를 기준으로 구간(regime A/B/C)을 나누고, 사건 효과는 같은 구간 안에서만 추정
- 2016년 분기들은 폐업이 기록되지 않아 폐업률 결측

## 개별공시지가 1990~2026 (build_landprice.py → analyze_landprice.py)
```bash
# data/raw/공시지가/ 에 국가공간정보포털 '개별공시지가정보' 대전 파일을 받은 이름 그대로 넣기
#   AL_*D151*.csv / AL_*D151*_csv.zip (연도별 가격), AL_*D150*.shp·.shx·.dbf·.prj (필지 위치)
python tram_model/build_landprice.py      # → landprice_parcels.csv.gz, landprice_long.pkl, landprice_area_panel.csv, landprice_cells.csv
python tram_model/analyze_landprice.py    # → landprice_effects.csv, landprice_area_events.csv, 그림 2장
python tram_model/build_dataset.py        # 공시지가 격자 피처(land_price, land_growth_5y/10y)가 자동으로 추가됨
```
- 핵심 파일은 `AL_30_D151_20200925_csv.zip` (1990~2020 전 연도). 2021~2026 은 2025·2026년 공시분 dbf 안의 5년치에서 가져옴
- 필지 위치는 최신 shp 우선, 그 사이 분할·합병돼 없어진 필지는 옛 shp(2020: EPSG:5174, 2016: EPSG:2097)에서 보충
- 지목 '대'만 사용(도룡동처럼 '대'가 30필지 미만인 상권은 전체 지목). 지수는 같은 필지 전년 대비 변화 중앙값을 이은 값(2015=100)
- 2006년은 시가지 필지 27% 누락 → 지수·분석에서 기준연도로 쓰지 않음
- 1호선 역 좌표 `data/line1_stations.csv`: 역명 버스정류장(출구) 평균, ±100m

## 20개 상권 기준으로 전환 (2026-10-11)
- 학습 데이터·시나리오·지도 모두 예전 4개 구역(Z1~Z4) 대신 20개 상권(A01~A20) 기준. `zone` 컬럼 = 상권 코드
- 셀 선택: 250m 격자 중심이 상권 기준점에서 (반경 + 125m) 안 → 293개 격자
- `data/sangkwon_areas.csv` 에 `p6_zone`(core/secondary/periphery: 트램 효과 가중), `rent_area`(부동산원 하위상권) 열 추가
- 트램 시나리오: 기본 = 대전 1호선 1단계 역세권 지가 효과(`landprice_effects.csv`, 없으면 literature_params 의 `DJ_line1_land_500m`) × P2 업종 비율,
  높음 = P2 영국 LRT 업종별 계수(예전 기본), 낮음 = P2 버스 저밀 계수
- `make_map_data.py` 가 `outputs/area_profile.csv`(상권 요약: 점포·폐업률·지가·트램 효과)도 만듦 → `app.py` 상권 보기에서 사용
- 실행 순서: build_areas → build_landprice → analyze_landprice → build_dataset → train_analyze → make_map_data

## 지도 앱 (app.py, folium)
```bash
python -m pip install folium streamlit-folium
python tram_model/build_dong_layer.py     # 행정동 82개 경계 + 지표 → outputs/dong_polygons.geojson
python tram_model/make_map_data.py
streamlit run app.py
```
- 보기 3가지: 상권 20개 / 행정동 82개(통계청 2023-01 경계, `data/daejeon_dong_2023.geojson`) / 격자 250m
- 경계 클릭 → 오른쪽 패널에 상세·추이·AI 해설. 1호선(파란선), 트램 2호선(주황 점선 순환)

## 한 번에 실행 (run_all.py)
```bash
python tram_model/run_all.py              # 무거운 단계(상가 과거·공시지가)는 결과 있으면 건너뜀, 약 1~2분
python tram_model/run_all.py --full       # 전부 다시
python tram_model/run_all.py --from train_analyze
```
- `tram_route.py`: 트램 노선 순서 (번호 ≠ 노선: 245 진잠네거리는 231~232 사이, 241~244 는 연축 지선)
- `analyze_robustness.py`: 1호선 효과 강건성(비교군 거리·처리 반경·같은 구·가짜 개통연도·가짜 역) + 정거장 반경 400/500/600m 민감도
- `cluster_areas.py`: 부트스트랩·특징 빼기·시작값 안정성(ARI), 상권별 안정도 → `area_type_stability.csv`

## D. 예측 모델 비교 (forecast_areas.py)
- 대상: 상권 지가 지수(연, 1·2·3년 뒤), 점포 비중 지수(분기, 4·8분기 뒤). 매출은 합성값이라 제외
- 모델: naive / drift / ARIMA(p,1,0)(직접 구현) / LightGBM(없으면 sklearn GBM), 시간 순서 검증 + 상권 분할 검증
- 출력: forecast_backtest.csv/.png, forecast_land.csv, forecast_store.csv(도룡동 제외), forecast_paths.png
- statsmodels·lightgbm 설치 불필요. LightGBM 을 쓰려면 `python -m pip install lightgbm`

## E. 쇠퇴 위험 · 성장 가능 점수 (score_areas.py)
- 위험: 점포 비중 10년·최근 3년(↓), 폐업률(↑), 지가 대전 대비 10년·최근 4년(↓), 2034 지가 예측(트램 없음, ↓) 의 백분위 평균
- 성장: 2034 지가 예측(트램 기본), 트램 기본 효과, 개업률, 점포 비중 최근 3년 의 백분위 평균
- 진단: 위험 ≥ 50 이고 트램 효과 ≥ 3p → 트램 반등 기회 / 아니면 쇠퇴 우려, 위험 < 50 → 성장 지속(성장 ≥ 50)·정체·안정
- 출력: area_scores.csv, area_scores_sensitivity.csv, area_scores.png → area_profile.csv → app.py (색칠 기준·상세·예측 그래프)

## 보강 분석 (2026-10-11)
| 스크립트 | 내용 | 출력 |
|---|---|---|
| analyze_line1_trend.py | 1호선 효과 개통 전 추세 보정·사전 성장 매칭 + 가짜 개통연도 | line1_trend_adjusted.csv/.png |
| analyze_tram_benchmark.py | 대전 추정 vs 국내외 LRT·트램 문헌 (`literature_tram_benchmarks.csv`) | tram_benchmark.csv/.png |
| build_dong_panel.py | 행정동 82개 지가 지수·점포 패널 (상가 42분기 읽음, 약 1분) | dong_panel_land.csv, dong_panel_store.csv |
| analyze_dong_events.py | 사건 효과를 행정동 단위로 (비교 62개, 가짜 처리군 p) | dong_event_effects.csv/.png |
| analyze_factors.py | 요인 분석 (회귀+VIF, RF 순열 중요도) | factors_ols.csv, factors_rf.csv, factors.png |
| analyze_industry.py | 업종 구성 변화·지역 이동·상권별·업종별 트램 효과 | industry_*.csv, industry.png |
- 트램 시나리오 '높음'(지가) = 대전 1호선 추세 보정+매칭 9.3% (`DJ_line1_land_trendadj`)

## 실태조사·업종 매출 (analyze_survey_sales.py)
- `data/raw/매출/` 에 csv 를 넣으면 열 이름으로 자동 구분 (파일 이름 무관, cp949)
  - 2021 소상공인 실태조사(행정동) → 행정동별 매출 감소·폐업 고려 응답률, 우리 지표와 순위 상관(외부 검증)
  - 월별 업종 매출(2020-05~2021-09, 186업종) → 대분류 10개 구성비·점포당 월 매출
- 위치별 매출 금액은 없어 격자 매출 합성값은 그대로 (실태조사는 응답률, 업종 매출은 대전 전체)

## 지도 앱 개선 (2026-10-11)
- 상권 클릭 → 파란 굵은 테두리로 선택 표시 (pydeck 선택 레이어), 아래 선택 상자와 연동
- 트램 정거장 점 클릭(또는 '정거장 선택') → 500m 영향권 원 + 영향권 점포·업종·공시지가·트램 효과·포함 상권 표 (`build_station_summary.py` → station_summary.csv, station_areas.csv)
- AI 해설: 진단·위험/성장 점수와 원인·유형·2034 예측·실태조사·업종 변화·과거 사건·정거장 영향권을 묶어 전달, 6항목 형식으로 답변. 'AI 에게 보낸 정보 보기'로 확인 가능
- Streamlit 1.39 이상 필요 (클릭 선택). 낮으면 선택 상자로 사용
- 색칠 기준을 주제 5개로 묶음: 종합 진단(진단·위험·성장) / 트램 효과 / 땅값 / 점포(비중·폐업률·수) / 상권 유형
- `build_area_regions.py`: 대전 행정구역 전체를 20개 상권 권역으로 빈틈없이 나눈 폴리곤(가중 보로노이, 40m 격자) → 지도 색칠. 상권 핵심 영역은 회색 윤곽으로 함께 표시, 사이드바에서 끄기 가능
- `about_page.py`: 사이드바 '📘 분석 방법 한눈에 보기' 버튼 → 팝업(st.dialog, Streamlit 1.37+) 탭 4개(데이터·분석/모델·참고 논문·검증/한계). 핵심 수치는 outputs 결과 파일에서 자동으로 읽음

## 지도 앱 사용성 개선 (v17)
- **1차**
  - AI 해설을 상권·시나리오별로 저장해서 다른 상권을 보고 와도 남아 있음
  - 지도 바로 아래에 선택 요약 카드, 그 아래에 패널 3개(상권 상세 / 정거장 500m / 상권 비교)
  - 지도에 상권 이름 표시
  - 색: 증감 지표는 감소 파랑·0 흰색·증가 빨강, 점수는 의미별 색(위험 = 빨강 계열, 성장 = 초록, 트램 = 파랑), 범례는 지도 바로 위
- **2차**
  - 첫 화면에 '한눈에 보기' 추가: 진단 4분류별 상권 칩, 누르면 그 상권으로 이동
  - 숫자 카드에 도움말(?)
  - 예측 그래프: 80% 범위를 띠로, 2028 개통선 표시
  - 점포 그래프: 수집 기준이 바뀐 분기를 빨간 점선으로 표시
  - 땅값 그래프: 그 상권의 사건을 회색 점선으로 표시
  - 20개 비교표: 막대 칸, 선택 표시, 행 클릭으로 이동
- **3차**
  - 공유 링크: 주소에 `?area=A04&station=210` 처럼 선택이 남음
  - 상권 2곳 비교
  - 파일 읽기 캐시
  - 격자 보기는 '실험용'으로 표시, 합성 매출은 맨 뒤로
  - 사이드바 순서: 보기 → 색칠 → 시나리오
  - 지도 높이 620px

## 지도 화면 개선 (v18)
- **첫 화면**: 트램 노선에 맞춤 (zoom 12). 노선이 화면에서 차지하는 비율 8.5% → 22.5%
- **색 위계**: 권역은 옅게(투명도 95), 점포가 모인 핵심 영역은 진하게(225). 정체 모를 회색 원 윤곽은 없앰
- **노선·정거장**: 먹색 선에 흰 테두리, 정거장은 흰 점에 먹색 링 (파랑 지표 색과 안 겹침). 선택한 정거장은 먹색으로 채움
- **선택 상권**: 흰 후광 + 먹색 굵은 선
- **이름**: 흰 테두리 글자. 점포 많은 순으로 놓고, 겹치면 위·아래·옆으로 옮김 (첫 화면 겹침 7곳 → 0곳). 선택 상권 이름은 크게
- **땅값 5년 색**: 0 기준 → 대전 평균 기준 (모든 상권이 올라서 0 기준이면 전부 빨강이었음)
- **안내**: 지도 위 제목줄에 범례와 기호 설명. 마우스를 올리면 흰 카드 모양 안내창

## 트램 효과 기준 재설정 (v19, 편향 점검 반영)
- 새 파일 `tram_effect.py`: 트램 효과 기준을 한 곳에서 정의. 결과 → `outputs/tram_scenarios.csv`, `outputs/tram_effect_profile.csv`
  - 낮음 +0.9% (해외 트램 하한), **기본 +1.8% (대전 1호선 1·2단계 합산)**, 높음 +5.8% (1호선 1단계만)
  - 추세 보정값(+9.3~15.2%)은 추세 기간에 따라 크게 흔들려 시나리오에서 제외, 참고값으로만
  - 시간 경로: 대전 1호선 연차별 모양 (개통 1~4년 = 1, 6년 0.35, 7년 0.17). 예전 영국식 램프(6년 뒤 100%) 폐기
  - 효과 = 정거장 500m 안 × 수준 × 업종 비율(Lan 2025). 고베 중심·주변 가중, 소비 상한, 영국 버스밀도 계수는 제거
- `analyze_landprice.py`: '1호선 1·2단계 합산' 행 추가 (landprice_effects.csv)
- 표기: 트램 효과 = "개통 초기 1~4년, 정거장 500m 안 땅값 기준 추정 효과(%)". 매출 변화가 아님
- `score_areas.py`
  - 트램 지표 = 앱과 같은 % 하나 (scenario_tram_uplift 상권 평균)
  - '트램 반등 기회' 기준 = 상대 위험 50↑ 이면서 상권 점포 절반 이상이 정거장 500m 안
  - 성장 점수에서 '2034 지가 예측(트램 기본)' 제거 (트램 이중 계산)
  - 진단 안정도: 지표 빼기 9 · 위험/성장 기준 45·55 · 반경 400/600m = 15가지 변형 중 같은 진단 비율 (`quadrant_stability`), 0.8 미만 `quadrant_uncertain`
- 앱: 시나리오 이름·설명을 `tram_scenarios.csv` 에서 읽음, 점수 이름 '상대 쇠퇴 위험'·'상대 성장 가능', 진단 '불확실' 배지·안정도

## 업종 점수 (v20) — `score_industry.py`
- 20개 상권 × 6개 업종(음식·소매·수리·개인·교육·보건의료·숙박) 100점 점수, 트램 건설 전·후
- 항목 (건설 전 가중치 → 건설 후)
  - 성장 30→27: 업종의 대전 내 점포 비중 5년 변화 (2021-06→2026-06)
  - 규모 20→18: 업종 점포 수 (로그)
  - 특화도 15→13.5: 입지계수
  - 생존 20→18: 상권 분기 폐업률 (낮을수록 높은 점수, 업종 공통)
  - 땅값 흐름 15→13.5: 상권 5년 상승률
  - 트램 효과 0→10: 정거장 500m 안 비율 × 업종 민감도
- 항목 점수 = 업종 안 20개 상권 백분위 (트램만 절대 척도), 총점 = 가중 평균 (값 있는 항목만)
- 업종 점포 5개 미만 상권은 점수 없음, 도룡동은 성장·생존 제외
- 출력: `outputs/industry_scores.csv`, `outputs/industry_score_weights.csv`
- 앱
  - 사이드바: '업종' 선택(지도가 업종 점수로 칠해짐), '트램 건설 후' 토글
  - 패널 '업종 점수': 점수순 순위표(전·후·변화·순위 변화), 전→후 덤벨 그림, 20×6 점수 표, 선택 상권 근거, 가중치·근거 표와 가중치 직접 조정

## 앱 화면 정리 (v21) — 기능을 줄이고 합침
- 사이드바: 트램 2호선(건설 전/후) · 지도에 칠할 것(진단, 트램 효과, 땅값 5년, 점포 비중 5년, 업종 점수 6개) · 분석 방법 · 고급 설정(시나리오, 권역 채우기, 이름 표시)
- 본문: 진단 요약 한 줄 → 지도 → (정거장을 고르면) 500m 영향권 → 선택 상권 카드 → 탭 3개(상권 상세 · 업종 점수 · 20개 상권 비교)
- 없앤 것: 격자(250m) 실험 보기(합성 매출), 상권 2곳 나란히 비교, 진단별 상권 칩, 정거장 패널(지도 아래 영향권 상자로 대체), 지도 색칠 지표 일부(상대 위험·성장, 땅값 대비, 폐업률, 점포 수, 유형 → 표·상세에 남김)
- 합친 것: 업종 선택은 '지도에 칠할 것'으로, 트램 전·후 토글은 사이드바 하나로, 상세의 그래프 3개는 탭으로, 업종 점수의 그림·근거·가중치도 탭으로

## 커버 화면 (v22) — `cover_page.py`
- 앱을 처음 열면 커버 화면 → '지도 열기' 로 지도 화면, 지도 사이드바의 '처음 화면으로' 로 되돌아감
- 주소에 `?view=map` 또는 `?area=A04` 가 있으면 커버 없이 바로 지도 (공유 링크용)
- 디자인: 리넨 바탕·숲색 글자·세이지 언덕(adaline.ai 분위기 참고), 제목만 세리프(Newsreader·Noto Serif KR), 본문 Pretendard
- 그림: 실제 정거장 좌표로 그린 트램 2호선 노선을 언덕 풍경 위에 겹친 원본 SVG (외부 이미지 없음)
- 수치(반등 기회 수, 시나리오 효과, 업종 점수 수)는 결과 파일에서 읽음

## 화면 3개로 분리 (v28)
- 사이드바 '화면': 지도 · 업종 점수 · 20개 상권 비교 (+ 처음 화면으로). 고른 상권·트램 전후·업종은 화면을 옮겨도 유지
- 지도: 진단 요약 → 지도 → (정거장) → 상권 카드 → 상권 상세(그래프·AI 해설)
- 업종 점수: 업종 선택 → 업종 점수 색칠 지도(누르면 근거) → 순위표 → 근거·전후 비교·6개 업종·가중치 탭
- 20개 상권 비교: 표, 행을 누르면 그 상권으로 지도 화면 이동
- 지도 상권 이름은 글자 모양 도형(GeoJsonLayer)으로 그림 — 이 Streamlit(1.65)에서는 TextLayer 가 안 그려지고 IconLayer 는 지도를 멈추게 함

## 업종 점수 '건설 후' 계산 방식 변경 (v31)
- 예전: 트램 10점 항목을 넣고 나머지를 0.9배 → 트램이 닿지 않는 상권이 일제히 내려가 트램이 악영향처럼 보였음
- 지금: 성장(+업종별 트램 효과)·땅값 흐름(+500m 안 비율 × 효과 수준)에 트램 예상 효과를 더하고, '건설 전' 20개 상권 분포에 대어 다시 점수화
  → 트램이 닿지 않는 상권은 점수 그대로, 닿는 상권만 오름 (기본 시나리오 최대 +8점, 높음 +16점, 내려가는 곳 0)
- 가중치는 건설 전·후 같음 (성장 30 · 규모 20 · 특화도 15 · 생존 20 · 땅값 15). 시나리오별 열: score_after_low/base/high

## 트램 효과 크기 보기 + 해외 메타분석 (2026-10-12)
효과 %(낮음 0.9 / 기본 1.8 / 높음 5.8)는 그대로 두고, **보여 주는 단위**만 금액·거리·경로로 바꿈.

| 스크립트 | 하는 일 | 출력 |
|---|---|---|
| analyze_tram_meta.py | 해외 트램·경전철 개통 전후 비교 10곳 랜덤효과 메타분석 (`data/literature_tram_meta.csv`), 대전 값은 `landprice_effects.csv` 에서 읽음 | tram_meta_estimates.csv, tram_meta_summary.csv, tram_meta_forest.png |
| analyze_tram_impact.py | ① 정거장 500m 안 필지 2026 공시지가 총액 × 효과 % → 증가액(억 원) ② 1호선 역 거리 띠(100m 단위)별 효과 ③ 반등 기회 5곳 트램 없을 때/있을 때 경로와 차이 금액 | parcel_value.csv.gz(필지 면적·가격, 있으면 재사용), tram_impact_money.csv/.png, tram_impact_station.csv, tram_distance_bands.csv/.png, tram_with_without.csv/.png |

- 필지 면적: 최신 개별공시지가 shp 의 폴리곤 면적(EPSG:5186, ㎡). dbf 의 A13 면적은 3%만 있어 쓰지 않음(있는 곳은 폴리곤과 상관 0.998)
- 가격: 같은 dbf 의 2026 공시가(A9), 없으면 1·2년 전 값(A16·A17)
- 도로·하천·구거·철도·제방·유지·공원은 합계에서 제외
- 금액은 공시지가 기준(시세보다 낮음), 개통 초기 1~4년 최대치
- 거리 띠 결과: 1호선 1단계 효과는 역 750m까지 비슷(+4.5~6.9%) → '역 바로 앞 집중'은 대전 자료로 확인되지 않음. 대신 영향권 750m 변형 금액(`ALL_750`)을 함께 계산
- `landprice_long.pkl` 을 못 여는 환경(pyarrow 없음)에서는 원본 D151 에서 필요한 연도만 읽음
- run_all: `analyze_tram_meta` 는 `analyze_tram_benchmark` 다음, `analyze_tram_impact` 는 `score_areas` 다음
- 앱: '분석 방법' 팝업 첫 탭 '트램 효과 크기'(금액·경로·거리·메타 그림), 결론 띠에 '정거장 500m 안 땅값 +○억 원', 상권 상세 트램 지표에 상권별 금액


## 1호선 개통 전후 점포 이중차분 — `analyze_line1_permits.py` (2026-10-13)
- 데이터: 공공데이터포털 **행정안전부_식품_일반음식점·휴게음식점·제과점영업**(대전 부분, cp949) → `data/raw/permits/`
  - 파일이 없으면 오픈API로: `python tram_model/download_permits_api.py 인증키` (대전 5개 구 코드 3640000~3680000)
  - 폐업일 기록이 2001년부터 → 분석 기간 2002~2014 (그 전은 점포 수 과소)
- 방법: 1호선 1단계(2006-03) 역 500m vs 1~3km, 250m 격자 × 연도, 격자·연도 고정효과 이중차분, 격자 군집 표준오차
  - 검사: 반경 300/750m, 비교군 1~2km, 가짜 개통연도 2004, 가짜 처리군 200회(무작위 추론)
  - 업종 그룹 6개(카페·빵·과자·편의점·간편식·주점·식사 음식점), 업태구분명으로 분류
- 실행: `python tram_model/analyze_line1_permits.py` (약 20초), run_all 에서는 analyze_line1_trend 다음
- 출력: `outputs/line1_permits_effects.csv`, `line1_permits_sector.csv`, `line1_permits_es.csv`, `line1_permits_series.csv`, 그림 `line1_permits.png`, `line1_permits_sector.png`
- 결과(2026-10-13): 전체 점포 +4.7%(−3.3~+13.3, 무작위 p 0.17, 확인 안 됨) / **카페 +24.8%(+8.0~+44.2)**, **빵·과자 +18.3%(+3.3~+35.4)** 세 검사 통과 / 편의점(격자 24개로 적음)·간편식·주점·식사 음식점 효과 확인 안 됨. 효과는 개통 3년 뒤부터 커짐(2009~14 +5~9%)

### 업종 점수에 1호선 인허가 결과 반영 (2026-10-13, `score_industry.py`)
- 음식 업종의 '건설 후' 트램 효과 = 상권 음식점 중 업종 그룹 비중 × 대전 1호선 인허가 점포 효과 (`food_tram_effects()`)
  - 기본: 카페 +24.8%, 빵·과자 +18.3%(세 검사 통과), 나머지 그룹 0 / 낮음: 두 그룹의 95% 하한 / 높음: 모든 그룹 추정치
  - 상권 비중은 지금 영업 중인 인허가 점포를 상권 경계(sangkwon_polygons.geojson) 안에서 셈 → `outputs/industry_food_tram_mix.csv`
  - 인허가 파일이 없으면 예전 방식(땅값 효과 × 해외 업종 비율)으로 자동 복귀. 다른 5개 업종은 그대로
- 결과: 음식 트램 효과(기본) 대전역·중앙시장 1.77→4.34%, 대전복합터미널 1.52→4.23%(카페 비중 16~17%), 소제동 1.77→1.54%(카페 4%). 순위 변화는 만년동 7→6위, 대전복합터미널 14→12위


## 3D 지도 (B안) — `map3d.py` + `map3d_component/` (2026-10-18)
- **본 앱**: 지도 화면 머리줄의 `평면 | 3D` 로 바꿈. 3D 에서 기둥·정거장을 누르면 오른쪽 상권 진단·아래 정거장 영향권이 바뀜 (평면 지도와 같은 선택 상태)
  - 앱 위쪽 '건설 전/후'·'시나리오'가 3D 에도 그대로 적용, 건설 전에는 '트램 반등 기회'를 정거장 없이 다시 분류한 진단 색(앱과 같은 규칙)
  - '지도에 칠할 것'이 땅값 전망·트램 효과이면 기둥 높이도 같은 지표로 맞춤. 나머지는 3D 안에서 고름
  - 구현: Streamlit 부품 v1(`components.declare_component`, 폴더 `map3d_component/index.html`). 클릭 → `{"area"|"station", "t"}` 값 → `ss.map3d` 로 받아 선택 상권 변경
  - 3D 를 못 열면(라이브러리 로드 실패 등) 경고 후 평면 지도로 대신 보여 줌
- **'3D 지도' 화면** (사이드바, 2026-10-19): 3D 만 화면 너비 전체·높이 780px 로 크게 봄 (`map3d.show(..., mode="full", key="map3d_full")`)
  - 왼쪽 위 조작판(기둥 높이·연도·보는 곳·회전), 오른쪽 아래 상권 카드. 건설 전/후·시나리오는 앱 위쪽 조작을 따름
  - 카드의 '이 상권 진단 보기' → `{"goto": 코드}` → 그 상권을 고른 채 지도 화면으로 이동
  - 지도 화면 3D 칸의 '크게 보기' 버튼 → 이 화면으로 이동
- **단독 화면**: `streamlit run app_3d.py`, 또는 `python tram_model/map3d.py` → `outputs/map3d.html` 을 브라우저로 바로 열기
- 화면 원본은 `map3d_component/index.html` 하나 (단독 화면은 여기에 데이터를 끼워 넣음). deck.gl 9.1 을 jsdelivr 에서 불러옴 → 인터넷 필요
- 읽는 파일: `area_profile.csv`, `sangkwon_polygons.geojson`, `forecast_land.csv`, `station_summary.csv`, `tram_scenarios.csv`, `dong_polygons.geojson`, `data/tram_stations.csv` → run_all 재실행 불필요(결과가 바뀌면 자동 반영)
- 화면: 상권 20개 핵심 영역을 기둥으로 세움(높이 = 땅값 전망 지수 / 땅값 기준 트램 효과 / 점포 수 / 쇠퇴 위험, 색 = 진단 4분류), 2026→2034 재생, 2030 개통 후 트램 운행(연출), 보는 곳 4곳(전체·원도심·둔산·유성), 천천히 돌리기
- 높이 눈금은 지표마다 고정(연도·시나리오를 바꿔도 같은 자), 땅값 지수는 바닥 80 기준. 배경 지도 타일 없음(행정동 경계를 바닥으로 그림)
- 실제 건물(선택): `outputs/buildings_3d.geojson`(Polygon, 속성 `height_m`)을 두면 회색 건물로 함께 올림. 변환 스크립트는 아직 없음(GIS건물통합정보, 노선 500m 안)
- 한계: 트램 운행 간격·속도는 화면용(실제 시간표 아님), 정거장 일부 좌표 추정값, 트램 효과 높이 차이는 작음(95% 구간 0 포함)

## 행정동 82 · 8989 · 업종 구성 · 임대료 부담 (2026-10-20~25)

방향: **트램이 바꾸는 것 = 상권 가치(땅값) + 업종 구성(카페)**, 점포당 매출은 잘 안 바뀜(검증·근거용), 그 결과 위험 = 임대료 부담.
8989 수집·표 만들기 자세한 설명은 `README_8989.md`.

| 순서 | 스크립트 | 하는 일 | 주요 출력 (`outputs/`) |
|---|---|---|---|
| 1 | `check_sector_evidence.py` | 1호선 인허가 업종 근거 점검: 사전 추세, 비중, 거리 띠, 2단계 재현, 밀도 맞춤, Bonferroni | `sector_evidence_checks/es/share.csv` |
| 1-1 | `check_other_sectors.py` | 비음식 8업종(미용·세탁·숙박·노래연습장·체력단련·약국·의원·안경) 인허가로 같은 점검. 입력 `data/raw/permits_other/*_대전광역시.csv` (file.localdata.go.kr 대전 파일) | `sector_evidence_other(_summary/_es).csv` |
| 2 | `build_8989_tables.py` | 8989 원본(json) → 행정동·상권 표 | `8989/*.csv`, `dong_panel_8989.csv`, `dong_code_map.csv` |
| 3 | `analyze_8989.py` | 행정동 매출 요약, 진단 외부 검증, 상권 배분 | `area_sales_summary.csv` |
| 4 | `analyze_station_sales.py` | 1호선 역세권 땅값 vs 점포당 매출 (+32% vs +7%, 0.24배) | `station_sales_premium.csv`, `station_sales_dong.csv` |
| 5 | `analyze_8989_trdar.py` | 골목상권 144곳 증감(금액은 격자 합이라 증감·비중만) | `trdar_summary.csv`, `area_trdar_match.csv` |
| 6 | `parse_8989_reports.py` | 월간 상권동향 PDF → 표 | `report_*.csv` |
| 7~10 | `build_dong_year_panel.py` → `cluster_dongs.py` → `forecast_dongs.py` → `score_dongs.py` | 행정동 82 패널·유형·예측·진단 (82개 안 백분위) | `dong_year_panel.csv`, `dong_*` |
| 11 | `analyze_tram_impact_dongs.py` | 동별 정거장 500m 땅값 증가액 (합계 4,349억) | `dong_tram_money.csv` |
| 12 | `build_dong_map_profile.py` | 지도용 행정동 표·경계, 정거장–동 표 | `dong_map_profile.csv`, `dong_map.geojson`, `dong_station_summary.csv` |
| 13 | `build_composition.py` | 업종 구성 현재·2034 예상 (카페만 기본 효과, 빵·과자는 높음에만) | `composition_now/forecast/evidence.csv` |
| 14 | `build_rent_pressure.py` | 임대료 부담 위험 = 땅값-매출 격차·폐업률·업종 교체 백분위 평균 | `rent_pressure.csv` |
| 15 | `build_rent_survey.py` | 부동산원 임대동향(임대료·지수·공실률) → 상권 대응·검증 | `rent_survey_long/area/validation.csv` |
| 15-1 | `build_rent_long.py` | R-ONE 임대가격지수(시계열) vs 같은 기간 상권 땅값(대전 +47% vs −4.8%), 전국 상권 자본수익률 → 임대료 전가(ρ 0.72), 공시지가 vs R-ONE 지가지수 | `rent_long_vs_land.csv`, `rent_capital_passthrough.csv`, `landprice_vs_rone.csv` |
| 16 | `analyze_station_sensitivity.py` | 정거장 추정 좌표 28곳을 0~300m 무작위로 300번 옮겨 500m 안 점포 비율·진단 다시 계산 → 상권 20곳 모두 안정, 행정동 6곳 민감(앱 ⚑) | `station_coord_sensitivity.csv` |
| 17 | `validate_closures_8989.py` | 8989 폐업률(2025) ↔ 82개 동 위험 점수(ρ +0.24, p 0.02) | `validation_closures_8989*.csv` |
| 18 | `analyze_construction_8989.py` | 공사 구간 동 vs 정거장 먼 동 월별 카드매출 이중차분(−1.4%, 도소매 −2.3%). 입력 `data/construction_sections.csv` | `construction_8989_did/es.csv` |
| 19 | `analyze_seoul_newline_sales.py` | 서울 신림선(2022) 역 500m 상권 개통 전후 점포당 매출 이중차분. 입력 `data/raw/seoul/`(사용자 다운로드) | `seoul_newline_sales_did/es.csv` |

실행: `python tram_model/run_all.py --from check_sector_evidence` (모두 `run_all.py` STEPS 에 등록)

앱 반영 (B1~B4)
- 지도 '보기 단위' 20개 상권 ↔ 82개 행정동, '칠할 것'에 업종 변화(카페)·임대료 부담, 결론 띠 ⚠
- 상세 탭: 상권 = 땅값 예측·흐름·점포 수·업종 구성·AI 해설 / 행정동 = + 카드매출
- 정거장 패널 행정동 표, '상권·행정동 비교' 화면, 업종 점수 근거 띠
- 3D 지도 기둥 높이: + 업종 변화(카페)·임대료 부담 (`map3d.py` 가 `composition_forecast.csv`·`rent_pressure.csv` 읽음)
- 커버 부제·통계 카드, 분석 방법 팝업 첫 탭 '트램이 바꾸는 것'(`about_page._story`, 수치 자동)
- 주의: `tram_model/` 부품(cover_page·about_page·map3d)을 고치면 앱을 껐다 켜야 반영됨

노선 순서(`tram_route.py`, 2026-10-25): 순환선 201~240 + 연축지선(241~244) + 진잠지선(233 관저네거리 → 245 진잠네거리, KDI 2024 공식 순서)
