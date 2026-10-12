"""지도 앱 '분석 방법 한눈에 보기' 팝업 내용 (데이터 · 모델 · 논문 · 검증/한계).

app.py 에서: from about_page import show_about → 사이드바 버튼으로 팝업(st.dialog) 열기.
수치는 outputs 의 결과 파일에서 읽어 자동으로 최신값을 보여 줌 (파일이 없으면 기본 문구).
"""
import os

import pandas as pd

OUT = "tram_model/outputs"


def _read(name):
    p = f"{OUT}/{name}"
    return pd.read_csv(p, encoding="utf-8-sig") if os.path.exists(p) else None


def _numbers():
    n = {"ph1": "+5.8%", "ph2": "-8.3%", "pool": "+1.8%", "dj_adj": "+9.3~15.2%", "low": "+0.9%", "base": "+1.8%",
         "high": "+5.8%", "base_ci": "", "land_rmse": "4.4%", "store_rmse": "2.7%", "ari": "0.49", "sil": "0.21", "k": "4",
         "n_unc": "-", "rho_area": "0.07"}
    e = _read("landprice_effects.csv")
    if e is not None and len(e):
        for key, pat in (("ph1", "1호선 1단계"), ("ph2", "1호선 2단계"), ("pool", "1·2단계 합산")):
            r = e[e.analysis.str.contains(pat, regex=False)]
            if len(r):
                n[key] = f"{r.effect_pct.iloc[0]:+.1f}%"
    sc = _read("tram_scenarios.csv")
    if sc is not None and len(sc):
        for r in sc.itertuples():
            n[r.scenario] = f"{r.effect_pct:+.1f}%"
        b_ = sc[sc.scenario == "base"]
        if len(b_) and isinstance(b_.ci95.iloc[0], str):
            n["base_ci"] = b_.ci95.iloc[0]
    t = _read("line1_trend_adjusted.csv")
    if t is not None and len(t):
        tt = t[t.method.str.contains("추세 보정")]
        if len(tt):
            n["dj_adj"] = f"{tt.effect_pct.min():+.1f}~{tt.effect_pct.max():+.1f}%"
    b = _read("forecast_backtest.csv")
    if b is not None:
        bl = b[(b.target == "지가") & (b.h == 1)].set_index("model").rmse_log_pct
        bs = b[(b.target == "점포 비중") & (b.h == 4)].set_index("model").rmse_log_pct
        if len(bl):
            n["land_rmse"] = f"{bl.min():.1f}%"
            n["land_best"] = bl.idxmin()
        if len(bs):
            n["store_rmse"] = f"{bs.min():.1f}%"
            n["store_best"] = bs.idxmin()
    s = _read("area_type_stability.csv")
    if s is not None and len(s):
        n["ari"] = f"{s.ari.iloc[0]:.2f}"
    k = _read("area_type_k.csv")
    if k is not None and len(k):
        ty = _read("area_types.csv")
        kk = int(ty.cluster.max()) if ty is not None else 4
        n["k"] = str(kk)
        n["sil"] = f"{k.set_index('k').silhouette.get(kk, float('nan')):.2f}"
    a = _read("area_scores.csv")
    if a is not None and "quadrant_uncertain" in a:
        n["n_unc"] = str(int(a.quadrant_uncertain.sum()))
    v = _read("survey_validation.csv")
    if v is not None:
        r = v[v.level.str.contains("20개") & v.our_metric.str.contains("위험") & v.survey.str.contains("어려움")]
        if len(r):
            n["rho_area"] = f"{r.spearman.iloc[0]:.2f}"
    return n


DATA = [
    ("상가(상권)정보", "소상공인시장진흥공단", "2015-12 ~ 2026-06, 42분기", "점포 약 8만(2026)",
     "점포 수·개폐업·업종 구성, 격자 피처"),
    ("개별공시지가", "국토교통부·국가공간정보포털", "1990 ~ 2026, 연", "필지 31만 (지목 '대' 14만)",
     "지가 지수, 1호선 효과, 예측"),
    ("트램 2호선 정거장", "설계도면(2공구 노선 교점) + 정거장 위치 자료", "2030 개통 예정", "45개 (도면 보정 17)",
     "500m 영향권, 땅값 기준 트램 효과"),
    ("도시철도 1호선 역", "역명 버스정류장 좌표 평균", "2006·2007 개통", "22개", "철도 개통 효과(자연 실험)"),
    ("버스정류장", "국토교통부 전국 버스정류장", "2025-10", "대전 BIS", "버스 밀도(땅값 기준 트램 효과 조절)"),
    ("행정동 경계", "통계청", "2023-01", "82개", "행정동 분석·요인 분석"),
    ("소상공인 실태조사", "대전시", "2021", "3.1만 사업체", "쇠퇴 지표 외부 검증"),
    ("업종별 월 매출", "대전 (지역화폐 결제액으로 추정)", "2020-05 ~ 2021-09", "186업종", "업종 구성·점포당 매출"),
    ("KB국민카드 구×업종 매출", "KB국민카드", "2019·2020년 3~7월", "구 5 × 업종", "격자 매출(합성, 참고용)"),
    ("중대형상가 임대료", "한국부동산원", "2024 1분기", "하위상권 8곳", "임대료 피처"),
    ("유동인구", "대전 중구", "2021 ~ 2024", "중구 행정동", "유동인구 피처(중구만)"),
]

MODELS = [
    ("상권 경계", "20개 상권 기준점 + 반경(250~450m) 가중 거리 분할", "–", "겹치지 않는 폴리곤, 대전 전체 권역"),
    ("철도 개통 효과", "이중차분(DiD)·사건연구, 필지 고정효과, 법정동 군집 부트스트랩",
     "1단계 {ph1} · 2단계 {ph2} · 합산 {pool} (추세 보정 {dj_adj}는 기간에 따라 흔들려 참고만)",
     "비교군·반경 바꿔도 1단계 +5.3~6.6%. 단 1단계 가짜 개통 검사 실패(−4.0%), 신뢰구간이 0을 포함"),
    ("과거 사건 효과", "상권·행정동 이중차분 + 가짜 처리군 순위 검정", "신세계 개점 점포 +17% (p<0.05)",
     "비교 행정동 62개"),
    ("상권 유형", "K-means (6개 특징, 표준화)", "{k}개 유형", "실루엣 {sil}, 부트스트랩 ARI {ari}"),
    ("요인 분석", "표준화 다중회귀(강건 표준오차, VIF) + 랜덤포레스트 순열 중요도", "원도심·역 거리·업종 구성",
     "행정동 80개, 5겹 교차검증"),
    ("지가·점포 예측", "naive · drift · ARIMA(p,1,0) · GBM(LightGBM) 비교", "지가 1년 오차 {land_rmse}, 점포 비중 {store_rmse}",
     "시간 순서 검증 + 상권 분할 검증"),
    ("땅값 기준 트램 효과 (추정)", "정거장 500m × 수준(낮음 {low} / 기본 {base} / 높음 {high}) × 업종 비율 × 개통 후 연차별 모양",
     "개통 초기 1~4년에 가장 크고 6년 뒤 약 35%로 줄어듦 (대전 1호선 실측 모양)",
     "기본 = 1호선 1·2단계 합산, 높음 = 1단계만, 낮음 = 해외 트램 하한. 매출이 아니라 땅값 기준"),
    ("쇠퇴·성장 진단", "20개 상권 안 상대 순위 점수 + 4분류 (반등 기회 = 위험 50↑ & 점포 절반 이상 500m 안)",
     "상대 비교 (절대 수준 아님)", "15가지 변형으로 진단 안정도 계산, 80% 미만 불확실 {n_unc}곳"),
    ("격자 머신러닝", "HistGradientBoosting, 공간 GroupKFold", "–", "매출이 합성값이라 파이프라인 검증용"),
    ("AI 해설", "Google Gemini (분석 결과 묶음만 근거로 답변)", "–", "보낸 정보 공개, 추정 표시"),
]

PAPERS = [
    ("P2", "Lan, Ford & Palacin (2025), Sustainability 17:10505 — 영국 경전철 DiD",
     "업종별 효과의 비율(음식 0.99·소매 0.86·기타 0.24)만 사용 (버스 밀도 조절·6년차 시차는 대전 근거가 없어 뺌)"),
    ("P6", "Kakutani & Hiramatsu (2025), Urban Rail Transit 11 — 고베 LRT 시뮬레이션",
     "참고만 (중심·주변 가중은 대전 근거가 없어 시나리오에서 뺌)"),
    ("P3", "김용래·백성준·임병준 (2016), 감정평가학논집 15(3) — 수도권 30개 역",
     "1차 500m·2차 1km 상권, 승하차→매출 탄력성"),
    ("P4", "정은애·성현곤 (2018), 국토계획 53(5) — 서울 대중교통·소매 매출 SEM", "버스 300m 집수권, 계수 벤치마크"),
    ("P5", "Reyes-Schade 외 (2025), Sustainability 17:5880 — 바르셀로나 트램", "정거장 500m(도보 6분) 권역"),
    ("P7", "양충헌·김진국 (2020), 디지털콘텐츠학회논문지 21(6) — 수원 트램 LUTI", "소매는 환승·종점 정거장으로 재배치"),
    ("P1", "이경미·김명수 (2017), 대한교통학회 — 대전 2호선 VISSIM", "트램 전용차로 차량 속도 저하(참고)"),
    ("비교", "Debrezion 외 2007(메타분석), Cervero·Duncan 2002, Cervero·Kang 2011(서울 BRT), "
             "Yang 외 2025(청두 트램), Ahn·Kim 2021(대구 3호선), Papon 외 2015(파리 T3), Byun·Jang 2024(대전 1호선)",
     "트램 주거 문헌 0~6% → 기본 {base}·높음 {high} 모두 그 범위 안. 지하철 효과를 지상 트램에 쓰므로 과대 가능"),
]

FRAMEWORKS = [
    ("머신러닝", "scikit-learn", "HistGradientBoosting(격자 모델·예측 비교), RandomForest(요인 분석), K-means·PCA(상권 유형), "
                              "GroupKFold(공간 검증), 순열 중요도, 실루엣"),
    ("머신러닝(선택)", "LightGBM", "예측 비교·격자 잔차. 설치돼 있으면 사용, 없으면 scikit-learn HistGradientBoosting 으로 자동 대체"),
    ("통계 모델", "NumPy (직접 구현)", "이중차분·사건연구, 군집 부트스트랩, 강건 표준오차 회귀, ARIMA(p,1,0)"),
    ("과학 계산", "SciPy", "가까운 정거장·점포 검색(KD-tree), 순위 상관"),
    ("데이터 처리", "pandas", "패널 구성·집계 전반"),
    ("공간 처리·그림", "scikit-image, matplotlib", "상권 경계선 추출, 지점의 행정동 판정, 결과 그림"),
    ("지도 앱", "Streamlit + pydeck", "화면·지도·클릭 선택·팝업"),
    ("AI 해설", "Google Gemini (google-genai)", "분석 결과 묶음을 근거로 해설 생성"),
]
WHY = ("딥러닝(PyTorch·TensorFlow)은 쓰지 않음: 상권 20개·행정동 82개·격자 293개 규모라 통계·트리 모델이 적합하고, "
       "예측 비교에서도 단순 모델(ARIMA)이 머신러닝보다 정확했음. 통계 모델은 추가 설치 없이 돌도록 NumPy 로 직접 구현 "
       "→ pandas·numpy·scipy·scikit-learn·scikit-image·matplotlib 만으로 전체 재현 가능")


def _lgbm_status():
    try:
        import lightgbm  # noqa: F401
        return "이 컴퓨터: LightGBM 설치됨 → 예측 비교에 LightGBM 사용"
    except ImportError:
        return "이 컴퓨터: LightGBM 없음 → scikit-learn 모델로 대체 중 (python -m pip install lightgbm 으로 설치 가능)"


LIMITS = [
    "**매출 금액**: 위치별 실측 매출이 없어 격자 매출은 '구 매출 ÷ 점포 수' 합성값 → 매출 예측·잔차는 참고용",
    "**땅값 기준 트램 효과**: 매출 변화가 아니라 땅값으로 추정한 값. 지하철(1호선) 효과를 지상 트램에 빌려 씀 → 과대 가능, 범위(낮음~높음)로 제시",
    "**1호선 효과의 불확실성**: 1단계 +5.8%(구간 0~12.8%), 2단계 −8.3%(개통 전부터 하락 추세), 트램 발표(2019) 뒤 정거장 주변 땅값 −1% 안팎",
    "**정거장 좌표**: 정거장 좌표는 공개 도면과 정류장 위치로 정한 값",
    "**자료 단절**: 상가정보 수집 기준이 2023-03·2024-12·2026-06 에 바뀜 → 대전 내 비중·구간 분리로 보정",
    "**공시지가**: 2019~22 현실화율 정책 영향 → 대전 평균 대비 지수 위주로 해석",
    "**표본 크기**: 상권 20개·행정동 80개 → 유의성·예측력 한계, '함께 움직이는 요인'으로 해석",
    "**외부 검증**: 행정동 단위로는 2021 실태조사 '어려움' 응답률이 원도심(ρ +0.41)·지가 상대 하락(ρ −0.36)과 같은 방향. "
    "하지만 20개 상권 위험 점수와는 ρ {rho_area}로 검증되지 않음 (코로나 시기 조사)",
    "**진단은 상대 비교**: 20개 상권 안 순위라 언제나 약 절반이 '위험 50 이상' → 절대적 쇠퇴 판정이 아님",
]


def _body(st):
    n = _numbers()
    st.caption("대전 트램 2호선(2030 개통 예정) 상권 분석 — 공공데이터로 과거 30년 변화를 학습하고, 대전 1호선 개통 전후 땅값으로 땅값 기준 트램 효과 범위를 추정")
    c = st.columns(4)
    c[0].metric("땅값 기준 트램 효과 (기본)", n["base"], f"1단계 {n['ph1']} · 2단계 {n['ph2']}", delta_color="off", delta_arrow="off")
    c[1].metric("지가 1년 예측 오차", n["land_rmse"], n.get("land_best", ""), delta_color="off", delta_arrow="off")
    c[2].metric("상권 유형", f"{n['k']}개", f"안정성 ARI {n['ari']}", delta_color="off", delta_arrow="off")
    c[3].metric("분석 단위", "20개 상권", "82개 행정동 · 293개 격자", delta_color="off", delta_arrow="off")
    t1, t2, t5, t3, t4 = st.tabs(["데이터", "분석·모델", "프레임워크", "참고 논문", "검증·한계"])
    with t5:
        st.dataframe(pd.DataFrame(FRAMEWORKS, columns=["용도", "프레임워크", "쓴 곳"]), hide_index=True,
                     use_container_width=True)
        st.caption(WHY)
        st.caption(_lgbm_status())
    with t1:
        st.dataframe(pd.DataFrame(DATA, columns=["데이터", "출처", "기간", "규모", "쓰인 곳"]), hide_index=True,
                     use_container_width=True)
    with t2:
        rows = [(a, b, c_.format(**n), d) for a, b, c_, d in MODELS]
        st.dataframe(pd.DataFrame(rows, columns=["목적", "방법·모델", "핵심 결과", "검증"]), hide_index=True,
                     use_container_width=True)
        st.caption("흐름: 원본 → 상권·행정동·격자 패널 → 효과 추정(DiD) → 유형(K-means) → 예측(ARIMA 등) → 트램 시나리오 → 진단 점수 → 지도")
    with t3:
        st.dataframe(pd.DataFrame([(x, y, z.format(**n)) for x, y, z in PAPERS], columns=["", "논문", "이 앱에서 쓴 내용"]),
                     hide_index=True,
                     use_container_width=True)
    with t4:
        for x in LIMITS:
            st.markdown(f"- {x.format(**n)}")
    st.caption("코드: tram_model/ (run_all.py 로 전체 재현) · 자세한 수치: PROGRESS.md")


def show_about(st):
    """사이드바 버튼 → 팝업."""
    if st.sidebar.button("분석 방법 한눈에 보기", icon=":material/menu_book:", use_container_width=True):
        open_about(st)


def open_about(st):
    """분석 방법 팝업 바로 열기. Streamlit 1.37 미만이면 접히는 상자로 대체."""
    if hasattr(st, "dialog"):
        @st.dialog("분석 방법 한눈에 보기", width="large")
        def _dlg():
            _body(st)
        _dlg()
    else:
        with st.expander("분석 방법 한눈에 보기", expanded=True):
            _body(st)
