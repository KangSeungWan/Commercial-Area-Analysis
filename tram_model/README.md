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
