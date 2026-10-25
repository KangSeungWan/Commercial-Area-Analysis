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
         "n_unc": "-", "rho_area": "0.07", "money_base": "-", "money_range": "-", "value500": "-", "money_750": "-",
         "gap5_base": "-", "gap5_high": "-", "gap_year": "2034", "meta": "-", "meta_ci": "-", "meta_k": "-"}
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
    m = _read("tram_impact_money.csv")
    if m is not None and len(m):
        r = m.set_index("code")
        if "ALL" in r.index:
            a = r.loc["ALL"]
            n["money_base"] = f"{a.gain_base_eok / 1e4:,.2f}조 원"
            n["money_range"] = f"{a.gain_low_eok / 1e4:,.2f}~{a.gain_high_eok / 1e4:,.2f}조"
            n["value500"] = f"{a.value_eok / 1e4:,.1f}조 원"
        if "ALL_750" in r.index:
            n["money_750"] = f"{r.loc['ALL_750'].gain_base_eok / 1e4:,.2f}조 원"
    ww = _read("tram_with_without.csv")
    if ww is not None and len(ww):
        e = ww[ww.year == ww.year.max()]
        n["gap5_base"] = f"{e.gap_base_eok.sum():,.0f}억 원"
        n["gap5_high"] = f"{e.gap_high_eok.sum():,.0f}억"
        n["gap_year"] = str(int(ww.year.max()))
    ms = _read("tram_meta_summary.csv")
    if ms is not None and len(ms):
        g = ms[ms.group == "전체 (트램·경전철)"]
        if len(g):
            g = g.iloc[0]
            n["meta"] = f"{g.mu_pct:+.1f}%"
            n["meta_ci"] = f"{g.ci_low_pct:.1f}~{g.ci_high_pct:.1f}%"
            n["meta_k"] = str(int(g.k))
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
     "500m 영향권, 상권 가치(땅값) 기준 트램 효과"),
    ("도시철도 1호선 역", "역명 버스정류장 좌표 평균", "2006·2007 개통", "22개", "철도 개통 효과(자연 실험)"),
    ("버스정류장", "국토교통부 전국 버스정류장", "2025-10", "대전 BIS", "버스 밀도(상권 가치(땅값) 기준 트램 효과 조절)"),
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
    ("상권 가치(땅값) 기준 트램 효과 (추정)", "정거장 500m × 수준(낮음 {low} / 기본 {base} / 높음 {high}) × 업종 비율 × 개통 후 연차별 모양",
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
    ("메타", "해외 트램·경전철 개통 전후 비교 {meta_k}곳 메타분석 (랜덤효과) — 영국·핀란드·폴란드·이탈리아·중국·미국·호주·대구",
     "평균 {meta} (95% {meta_ci}) → 기본 {base}·높음 {high} 모두 이 범위 안 (analyze_tram_meta.py)"),
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


def other_sectors_line():
    """비음식 업종 인허가 점검 한 줄 (check_other_sectors.py 결과). 결과가 없으면 빈 문자열."""
    s = _read("sector_evidence_other_summary.csv")
    if s is None or "판정" not in s:
        return ""
    s = s[s["판정"].notna()]
    nm = lambda x: x.replace("업", "") if x.endswith("장업") or x in ("미용업", "세탁업", "숙박업", "안경업") else x
    sure = s[s["판정"].str.startswith("확실")]
    ref = s[s["판정"].str.startswith("참고")]
    none = s[s["판정"] == "효과 없음"]
    lack = s[s["판정"] == "자료 부족"]
    tested = len(s) - len(lack)
    head = (f"비음식 {tested}개 업종(대전 인허가)도 같은 방법으로 검사: "
            + ("확실한 효과는 " + "·".join(f"{nm(r['업종'])} {r['판정'][3:-1]}" for _, r in sure.iterrows()) if len(sure) else "확실한 효과 없음"))
    parts = []
    if len(ref):
        parts.append("·".join(f"{nm(r['업종'])} {r['판정'][3:-1]}" for _, r in ref.iterrows()) + "는 참고 수준")
    if len(none):
        parts.append("·".join(nm(x) for x in none["업종"]) + " 효과 없음")
    if len(lack):
        parts.append("·".join(nm(x) for x in lack["업종"]) + "은 폐업 기록이 2008년 이후부터라 검사 불가")
    return head + (" (" + ", ".join(parts) + ")" if parts else "")


def _story(n):
    """트램이 바꾸는 것 / 잘 안 바꾸는 것 — 근거 4줄 (땅값·업종·매출·임대). 결과 파일에서 수치를 읽음."""
    v = dict(cafe="+24.8% [8.0, 44.2]", cafe_pp="+1.4%p", cafe_pp2="+27.5%", dens="+18.7%", stores="+4.7% [−3.3, 13.3]",
             bake_pp="+0.1%p", add="+272곳 (88~484)", pp="+0.3%p", land32="+32%", sales7="+7%", sales_ci="", ratio="0.24",
             rent_hi="6곳", rent_rb="", idx="−1%", vac="14%")
    c = _read("sector_evidence_checks.csv")
    if c is not None:
        g = lambda k: c[c["검사"].str.startswith(k) & (c["업종"] == "카페")]
        for key, k, unit in (("cafe", "0 ", "%"), ("cafe_pp", "3 ", "%p"), ("cafe_pp2", "5 ", "%"), ("dens", "6 ", "%")):
            r = g(k)
            if len(r):
                r = r.iloc[0]
                v[key] = f"{r['효과_퍼센트']:+.1f}{unit}" + (f" [{r['하한']:.1f}, {r['상한']:.1f}]" if key == "cafe" else "")
    e = _read("composition_evidence.csv")
    if e is not None:
        r = e[e["대상"] == "빵·과자 비중(음식점 중)"]
        if len(r):
            v["bake_pp"] = f"{r['효과_퍼센트'].iloc[0]:+.1f}%p"
        r = e[e["대상"] == "전체 점포 수"]
        if len(r):
            r = r.iloc[0]; v["stores"] = f"{r['효과_퍼센트']:+.1f}% [{r['하한']:.1f}, {r['상한']:.1f}]"
    f = _read("composition_forecast.csv")
    if f is not None:
        d = f[(f.level == "대전") & (f.year == f.year.max())].set_index("scenario")
        if {"low", "base", "high"} <= set(d.index):
            v["add"] = f"+{d.loc['base', 'add_카페']:.0f}곳 ({d.loc['low', 'add_카페']:.0f}~{d.loc['high', 'add_카페']:.0f})"
            v["pp"] = f"+{d.loc['base', 'cafe_bakery_pp']:.1f}%p"
    sp = _read("station_sales_premium.csv")
    if sp is not None:
        sp = sp.set_index("model")
        if "땅값: 기본" in sp.index and "전체: 기본" in sp.index:
            v["land32"] = f"{sp.loc['땅값: 기본', 'premium_pct']:+.0f}%"
            t = sp.loc["전체: 기본"]
            v["sales7"] = f"{t.premium_pct:+.0f}%"; v["ratio"] = f"{t.ratio_to_land:.2f}"
            v["sales_ci"] = f" (95% {(pow(2.718281828, t.lo) - 1) * 100:+.0f}~{(pow(2.718281828, t.hi) - 1) * 100:+.0f}%)"
    rp = _read("rent_pressure.csv")
    if rp is not None:
        a = rp[rp.level == "상권"]
        v["rent_hi"] = f"{(a.rent_pressure == '높음').sum()}곳"
        rb = a[a.quadrant == "트램 반등 기회"]
        v["rent_rb"] = f", 반등 기회 {len(rb)}곳 중 {(rb.rent_pressure == '높음').sum()}곳"
    rs = _read("rent_survey_area.csv")
    if rs is not None:
        u = rs.drop_duplicates("region")
        v["idx"] = f"{u.idx_chg_all_24_26.mean():+.1f}%"; v["vac"] = f"{u.vac_mid_4q.median():.0f}%"
    return [
        ("① 상권 가치(땅값)", "바꿈", "대전 1호선 역 500m 공시지가 이중차분 + 가짜 처리군·가짜 개통연도",
         f"1단계 {n['ph1']}, 합산 {n['pool']} → 트램 시나리오 낮음 {n['low']} · 기본 {n['base']} · 높음 {n['high']}",
         "지하철 효과를 트램에 빌려 씀, 95% 구간이 0 포함"),
        ("② 업종 구성(카페)", "바꿈", "대전 1호선 음식점 인허가 이중차분(2002~2014) + 사전 추세·2단계 재현·밀도 맞춤",
         f"역 500m 카페 수 {v['cafe']}, 음식점 중 카페 비중 {v['cafe_pp']}, 2단계 역 재현 카페 수 {v['cafe_pp2']}, 밀도 맞춤 {v['dens']} "
         f"→ 2034 대전 카페 {v['add']}, 대전 카페·빵 비중 {v['pp']}",
         f"전체 점포 수 효과는 불확실({v['stores']}), 빵집은 개수만 늘고 비중 {v['bake_pp']}"
         + (f". {other_sectors_line()}" if other_sectors_line() else "")),
        ("③ 점포당 매출", "잘 안 바꿈", "8989 행정동 카드매출(2026-01~08) 단면 회귀, 동 특성 통제",
         f"1호선 역세권 땅값 {v['land32']} 차이 vs 점포당 매출 {v['sales7']}{v['sales_ci']} → 땅값 효과의 {v['ratio']}배",
         "단면이라 인과 아님, 2025~ 자료만 있음"),
        ("④ 임대료 부담", "위험", "땅값-매출 격차 · 폐업률 · 업종 교체 백분위 평균 + 부동산원 임대동향",
         f"위험 '높음' 상권 {v['rent_hi']}{v['rent_rb']}. 지금 시장은 임대가격지수 {v['idx']}(2024→2026), 중대형 공실률 {v['vac']}",
         "금액 아닌 위험 순위, 부동산원 상권 경계 ≠ 분석 상권"),
    ]


LIMITS = [
    "**매출 금액**: 격자 매출은 '구 매출 ÷ 점포 수' 합성값 → 매출 예측·잔차는 참고용. 2026-10부터 대전 소상공인 상권분석 서비스(8989)의 "
    "행정동 82개 카드매출(2025-01~)을 상권 점포 비율로 배분해 '실측 참고값'으로 함께 표시 — 전통시장 동(중앙동)은 현금 거래가 빠져 과소, 카드사 범위 미확인",
    "**상권 가치(땅값) 기준 트램 효과**: 매출 변화가 아니라 땅값으로 추정한 값(대전 1호선 역세권은 땅값 +32% 차이, 점포당 카드매출 +7% 차이로 유의하지 않음 → 트램은 매출보다 상권 가치·업종 구성을 바꿈). 지하철(1호선) 효과를 지상 트램에 빌려 씀 → 과대 가능, 범위(낮음~높음)로 제시",
    "**금액 환산**: 공시지가 총액 × 효과 % 라서 효과 %의 불확실성(기본 구간 {base_ci})을 그대로 가짐. 도로·하천 등 공공 시설 땅 제외",
    "**1호선 효과의 불확실성**: 1단계 +5.8%(구간 0~12.8%), 2단계 −8.3%(개통 전부터 하락 추세), 트램 발표(2019) 뒤 정거장 주변 땅값 −1% 안팎",
    "**정거장 좌표**: 45곳 중 17곳은 설계 도면, 28곳은 정류장 위치로 추정한 값. 추정 28곳을 0~300m 무작위로 300번 옮겨 다시 계산 → "
    "핵심 상권 20곳의 진단은 모두 그대로(가장 흔들리는 송촌–법동–중리도 94% 유지), 행정동은 6곳(가양1·2동, 용두동, 중리동, 태평1동, 법2동)이 10% 넘게 바뀜 → 지도에 ⚑ 표시",
    "**자료 단절**: 상가정보 수집 기준이 2023-03·2024-12·2026-06 에 바뀜 → 대전 내 비중·구간 분리로 보정",
    "**공시지가**: 2019~22 현실화율 정책 영향 → 대전 평균 대비 지수 위주로 해석",
    "**표본 크기**: 상권 20개·행정동 80개 → 유의성·예측력 한계, '함께 움직이는 요인'으로 해석",
    "**외부 검증**: 행정동 단위로는 2021 실태조사 '어려움' 응답률이 원도심(ρ +0.41)·지가 상대 하락(ρ −0.36)과 같은 방향. "
    "하지만 20개 상권 위험 점수와는 ρ {rho_area}로 검증되지 않음 (코로나 시기 조사). "
    "8989 실측 카드매출(2025→2026 1~8월)로는 위험 점수가 높을수록 매출 증감이 낮음(ρ −0.41, p 0.05, n 20) → 진단 방향과 일치. "
    "다만 매출 증감은 주민 인구 변화(ρ +0.55, 재개발 입주)와 가장 강하게 움직임",
    "**업종 변화(카페)**: 대전 1호선(지하철) 인허가 근거 → 지상 트램은 다를 수 있어 낮음~높음 범위로 표시. 카페 외 음식 업종(빵·편의점·주점·식사)과 "
    "비음식 업종(미용·세탁·숙박·노래연습장·체력단련)은 확실한 근거 없음. 약국·의원·안경은 폐업 기록이 2008년 이후부터라 검사하지 못함",
    "**임대료 부담**: 임대료 금액 예측이 아니라 '개통 후 잠재 위험' 순위. 부동산원 임대동향 지역은 분석 상권과 경계가 달라 설명 자료로만 사용",
    "**진단은 상대 비교**: 20개 상권 안 순위라 언제나 약 절반이 '위험 50 이상' → 절대적 쇠퇴 판정이 아님",
]


def _body(st):
    n = _numbers()
    st.caption("대전 트램 2호선(2030 개통 예정) 상권 분석 — 공공데이터로 과거 30년 변화를 학습하고, 대전 1호선 개통 전후 땅값으로 상권 가치(땅값) 기준 트램 효과 범위를 추정")
    c = st.columns(4)
    c[0].metric("상권 가치(땅값) 기준 트램 효과 (기본)", n["base"], f"1단계 {n['ph1']} · 2단계 {n['ph2']}", delta_color="off", delta_arrow="off")
    c[1].metric("지가 1년 예측 오차", n["land_rmse"], n.get("land_best", ""), delta_color="off", delta_arrow="off")
    c[2].metric("상권 유형", f"{n['k']}개", f"안정성 ARI {n['ari']}", delta_color="off", delta_arrow="off")
    c[3].metric("분석 단위", "20개 상권", "82개 행정동 · 293개 격자", delta_color="off", delta_arrow="off")
    t6, t0, t1, t2, t5, t3, t4 = st.tabs(["트램이 바꾸는 것", "트램 효과 크기", "데이터", "분석·모델", "프레임워크", "참고 논문", "검증·한계"])
    with t6:
        st.markdown("**트램은 가게의 매출보다 상권의 가치와 업종 구성을 바꿉니다.** 그 결과 생기는 위험이 임대료 부담입니다.")
        for what, verdict, how, res, lim in _story(n):
            with st.container(border=True):
                esc = lambda x: str(x).replace("~", "\\~")      # 물결표 두 개가 취소선으로 읽히지 않게
                st.markdown(f"**{what}** — 트램이 **{verdict}**  \n{esc(res)}")
                st.caption(esc(f"근거: {how} · 한계: {lim}"))
        st.caption("처방은 시점별로: 개통 초(공실 많고 임대료 하락 중) → 빈 점포 채우기·업종 전환 지원, 땅값이 오른 뒤 → 상생 협약·임대료 안정 장치")
        rl = _read("rent_long_vs_land.csv")
        if rl is not None and len(rl):
            st.markdown("**임대료와 땅값, 같은 기간에 어떻게 움직였나** (한국부동산원 임대가격지수 vs 공시지가)")
            a = rl[rl.region == "대전 전체"]
            if len(a):
                a = a.iloc[0]
                st.caption(f"대전 전체 {a.start[:4]}→{a.end}: 땅값 {a.land_chg_pct:+.0f}% 오르는 동안 상가 임대가격지수는 {a.rent_chg_pct:+.1f}% "
                           f"(가장 높았던 때 {a.rent_peak}). 땅값이 올라도 임대료가 곧바로 따라 오르지 않았음 → 트램 뒤 임대료 부담은 "
                           "'공실이 채워지고 땅값이 오른 다음'의 위험")
            show = rl.assign(기간=rl.start.str[:4] + "→" + rl.end,
                             임대료=rl.rent_chg_pct.map(lambda v: f"{v:+.1f}%"), 땅값=rl.land_chg_pct.map(lambda v: f"{v:+.1f}%"),
                             차이=rl.gap_pp.map(lambda v: f"{v:+.0f}%p"))
            show = show.rename(columns={"region": "부동산원 지역", "areas": "대응 상권", "ptype": "상가 종류", "quadrant": "진단",
                                        "rent_pressure": "임대료 부담 위험"})
            st.dataframe(show[["부동산원 지역", "임대료", "땅값", "차이", "기간", "대응 상권", "상가 종류", "진단", "임대료 부담 위험"]].fillna(""),
                         hide_index=True, use_container_width=True)
            st.caption("임대료 = 임대가격지수 변화(중대형 상가 우선, 없으면 집합 상가, 3년 넘게 이어진 지역만), 땅값 = 대응 상권 공시지가 지수의 같은 기간 변화(1월 1일 기준). "
                       "부동산원 상권 경계는 분석 상권과 달라 이름으로 대응. 공시지가는 2019~22 현실화율 정책으로 더 올랐을 수 있음. "
                       "출처: R-ONE 임대동향 지역별 임대가격지수(시계열), outputs/rent_long_vs_land.csv")
    with t0:
        c = st.columns(3)
        c[0].metric("정거장 500m 안 땅값 증가 (기본)", n["money_base"], f"낮음~높음 {n['money_range']}",
                    delta_color="off", delta_arrow="off")
        c[1].metric(f"반등 기회 5곳 {n['gap_year']}년 차이", n["gap5_base"], f"높음 {n['gap5_high']}",
                    delta_color="off", delta_arrow="off")
        c[2].metric("해외 트램 평균 (메타분석)", n["meta"], f"95% {n['meta_ci']}", delta_color="off", delta_arrow="off")
        st.caption(f"같은 효과 %(기본 {n['base']})를 정거장 500m 안 2026 공시지가 총액 {n['value500']}에 곱한 값. "
                   "공시지가 기준이라 시세로는 더 큼. 개통 초기 1~4년 최대치이며 6년 뒤에는 약 35%로 줄어듦.")
        for f, cap in [("tram_impact_money.png", "상권별 증가액 (막대 = 기본, 선 = 낮음~높음)"),
                       ("tram_with_without.png", "트램 없을 때 vs 있을 때 (반등 기회 5곳)"),
                       ("tram_distance_bands.png", f"거리별 효과: 1호선 역 750m까지 비슷하게 오름 → 영향권을 750m로 넓히면 기본 {n['money_750']}"),
                       ("tram_meta_forest.png", "해외 트램·경전철 개통 효과와 대전 값 비교")]:
            if os.path.exists(f"{OUT}/{f}"):
                st.image(f"{OUT}/{f}", caption=cap, use_container_width=True)
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
