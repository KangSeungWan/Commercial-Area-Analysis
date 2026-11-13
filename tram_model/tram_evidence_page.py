"""지도 앱 '트램 효과 근거' 팝업 — 트램 효과 숫자가 어디서 왔는지 한곳에서 보여 줌.

app.py 에서: from tram_evidence_page import open_tram_evidence
  - open_tram_evidence(st): 팝업 열기 (지도 화면 결론 띠의 '트램 효과 근거' 버튼)
수치는 outputs 결과 파일에서 읽음 (파일이 없으면 그 부분만 빠짐).

탭: 한눈에 · 대전 1호선 땅값 · 대전 1호선 점포 · 해외 사례 · 앱에 쓰는 방식
"""
import os

import pandas as pd

OUT = "tram_model/outputs"
TITLE = "트램 효과 근거"


def _read(name):
    p = f"{OUT}/{name}"
    try:
        return pd.read_csv(p, encoding="utf-8-sig") if os.path.exists(p) else None
    except Exception:
        return None


def _img(st, name, cap):
    p = f"{OUT}/{name}"
    if os.path.exists(p):
        st.image(p, caption=cap, use_container_width=True)


# 해외 근거 (원문 확인, 2026-10-13). 비교군 = 노선이 없는 비교 지역과 견준 연구인지
OVERSEAS = [
    ("상권", "피렌체 트램 1호선 (2010)", "트램 거리 일상용품(식료품·카페) 점포", "개통 후에도 늘어난 상태 유지, 옆 거리 파급은 미미",
     "있음", "Grossi 외, JRSS-A 2025",
     "https://moodle2.units.it/pluginfile.php/769838/mod_resource/content/1/Grossi%20et%20al.%202025_paper%20JRSSA.pdf"),
    ("상권", "마르세유 트램 T1·T2·T3", "신규 사업체 중 숙박·음식점 비중", "5% → 14% (T1 2% → 16%)",
     "도심 추세와 비교", "Agam 트램 관측 보고서, 2023",
     "https://www.agam.org/wp-content/uploads/2023/10/Observatoire-les-effets-du-Tramway-Economie-BD-1.pdf"),
    ("상권", "샬럿 경전철 LYNX (2007)", "역 주변 가게 폐업 위험 (개통 5~10년 뒤)", "전문소매 −58%, 음식·숙박 −66%",
     "있음", "Liu & Bardaka, Transport Policy 2025", "https://www.worldtransitresearch.info/research/11567"),
    ("상권", "피닉스 경전철 (2008)", "새 가게 창업 (개통 때)", "소매 +28%, 서비스 +40% (해마다 6~8% 줄어듦)",
     "있음", "Credit, Urban Studies 2018", "https://mural.maynoothuniversity.ie/14606/"),
    ("상권", "LA 도시철도 23개 역", "역세권 일자리", "+34% (대부분 개통 5~10년 뒤)",
     "있음", "Schuetz 외, Cityscape 2018", "https://www.huduser.gov/Portal/periodicals/cityscpe/vol20num1/ch8.pdf"),
    ("상권", "서울 지하철 9호선 (참고)", "소상공인 생존 (인허가 데이터)", "전체 효과 없음, 250~500m 음식점 +12.7%",
     "있음", "Jin & Kim, RTBM 2026",
     "https://pure.ewha.ac.kr/en/publications/survival-of-small-firms-after-new-transit-lines-evidence-from-seo/"),
    ("땅값", "피렌체 트램 1호선 (2010)", "집값", "+3~8% (공사 시작부터 상승)",
     "있음", "Budiakivska & Casolaro, 이탈리아 중앙은행 2018",
     "https://www.bancaditalia.it/pubblicazioni/temi-discussione/2018/2018-1161/index.html"),
    ("땅값", "헬싱키 Raide-Jokeri (2023)", "정류장 800m 집값", "약 +5%", "있음", "핀란드경제학회지",
     "https://journal.fi/jfea/article/view/112406"),
    ("땅값", "가오슝 순환 경전철", "800m 집값", "+3.5~4.3% (2년 뒤 사라짐)", "있음", "Lee 외, 대만토지연구 2020",
     "https://landeconomics.nccu.edu.tw/upload/29/download_file/5157/195-222.pdf"),
    ("땅값", "샬럿 경전철 LYNX (2007)", "1마일 집값", "아파트 +11.3%, 단독 +4.0%, 상업용 0", "있음", "Billings, RSUE 2011",
     "https://ideas.repec.org/a/eee/regeco/v41y2011i6p525-536.html"),
    ("땅값", "철도역 메타분석", "역 400m 부동산", "상업용 +16.4%, 주거용 +4.2%", "여러 연구 종합", "Debrezion 외, JREFE 2007",
     "https://research.vu.nl/en/publications/the-impact-of-railway-stations-on-residential-and-commercial-prop/"),
    ("교통", "보르도 트램 (2003~08)", "자동차 분담률", "63% → 57% (1998→2009)", "없음", "프랑스 사후평가 2013",
     "https://www.bordeaux-metropole.fr/sites/MET-BXMETRO-DRUPAL/files/bm_actes/organismes/bordeaux-metropole/conseils/2013-10-25/P0G0L.pdf"),
    ("교통", "도야마 포트램 (2006)", "평일 이용객", "2,266 → 4,820명/일, 60세 이상 약 +250%", "없음", "도야마시·세계은행 2020",
     "https://documents1.worldbank.org/curated/en/113011604996380368/pdf/Toyama-City-Compact-City-Development.pdf"),
    ("공사 피해", "마르세유 로마 거리 공사 (2013~17)", "상인 보상", "439건 약 600만 유로 (손실의 60%)", "–", "Agam 2023",
     "https://www.agam.org/wp-content/uploads/2023/10/Observatoire-les-effets-du-Tramway-Economie-BD-1.pdf"),
    ("효과 없음", "노퍽 타이드 경전철 (2011)", "1,500m 집값", "−7.8%", "있음", "클리블랜드 연준 WP 2017",
     "https://www.clevelandfed.org/-/media/project/clevelandfedtenant/clevelandfedsite/publications/working-papers/2017/wp-1626r-is-the-light-rail-tide-lifting-property-values-pdf.pdf"),
    ("효과 없음", "그르노블 트램 C·D (2006~07)", "1층 점포 수", "'전반적으로 안정' (변화 없음)", "없음", "프랑스 사후평가",
     "https://www.igedd.developpement-durable.gouv.fr/IMG/pdf/014094-01_rapport_publie_cle57c44e-1.pdf"),
]


def _land(st):
    e = _read("landprice_effects.csv")
    sc = _read("tram_scenarios.csv")
    st.markdown("**대전 1호선 개통 전후 역 500m 안 땅값을 역에서 1~3km 땅값과 비교** (개별공시지가, 필지 단위 이중차분)")
    if e is not None:
        t = e[e.analysis.str.contains("1호선|예타", regex=True)][["analysis", "post", "effect_pct", "ci95", "n_treat", "n_ctrl"]]
        t.columns = ["분석", "개통 후 기간", "효과 %", "95% 구간", "역 500m 필지", "비교 필지"]
        st.dataframe(t, hide_index=True, use_container_width=True)
    if sc is not None:
        st.markdown("**앱의 상권 가치(땅값) 기준 트램 효과 시나리오**")
        s = sc[["label", "effect_pct", "ci95", "source"]].copy()
        s.columns = ["시나리오", "효과 %", "95% 구간", "근거"]
        st.dataframe(s, hide_index=True, use_container_width=True)
    _img(st, "landprice_line1_es.png", "연도별 효과: 1호선 역 500m 땅값, 비교 지역 대비")
    st.caption("한계: 1단계 신뢰구간이 0을 포함하고, 2단계는 개통 전부터 하락 추세라 해석이 어려움. 지하철 효과를 지상 트램에 빌려 씀.")


def _store(st):
    sec = _read("line1_permits_sector.csv")
    eff = _read("line1_permits_effects.csv")
    if sec is None:
        st.info("인허가 분석 결과가 없습니다. tram_model/data/raw/permits 에 데이터를 넣고 analyze_line1_permits.py 를 실행하세요.")
        return
    st.markdown("**대전 1호선 1단계(2006-03) 역 500m 안 영업 중 점포를 역에서 1~3km 점포와 비교** "
                "(음식점·카페·제과점 인허가 8만 건, 2002~2014)")
    _img(st, "line1_permits_sector.png", "업종 그룹별 효과 (파란색 = 세 가지 검사 통과)")
    t = sec[["업종", "점포수", "효과_%", "하한_%", "상한_%", "가짜연도_%", "무작위_p", "판정"]].copy()
    t.columns = ["업종", "점포", "효과 %", "하한 %", "상한 %", "가짜 개통연도 %", "무작위 p", "판정"]
    st.dataframe(t, hide_index=True, use_container_width=True)
    if eff is not None:
        b = eff[eff["분석"].str.startswith("기본")]
        if len(b):
            r = b.iloc[0]
            st.caption(f"전체 점포는 {r['효과_%']:+.1f}% ({r['하한_%']:+.1f}~{r['상한_%']:+.1f}%)로 우연과 구별되지 않음 → "
                       "트램이 바꾸는 것은 가게 '수'보다 업종 구성")
    st.markdown("**세 가지 검사**  \n"
                "① 기본 비교: 역 500m vs 1~3km, 250m 격자·연도 고정효과  \n"
                "② 가짜 개통연도: 2004년에 개통했다고 치고 계산 → 0 근처면 개통 전 차이 없음  \n"
                "③ 가짜 처리군 200회: 역과 무관한 격자를 무작위로 골라 같은 계산 → 진짜 효과보다 큰 경우의 비율(무작위 p)")
    _img(st, "line1_permits.png", "전체 점포 수 추이와 연도별 효과 (개통 3년 뒤부터 커짐)")
    st.caption("한계: 폐업 기록이 2001년부터라 그 전 연도 제외, 1호선은 지하철, 편의점은 표본이 적어(격자 24개) 판단 보류.")


def _overseas(st):
    st.markdown("**해외 트램·경전철 사례** (원문 확인, 비교군 = 노선이 없는 비교 지역과 견준 연구인지)")
    kinds = ["전체"] + list(dict.fromkeys(k for k, *_ in OVERSEAS))
    pick = st.segmented_control("분야", kinds, default="전체", key="tram_ev_kind")
    rows = [r for r in OVERSEAS if pick in (None, "전체") or r[0] == pick]
    df = pd.DataFrame(rows, columns=["분야", "사례", "무엇을 쟀나", "결과", "비교군", "출처", "링크"])
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"링크": st.column_config.LinkColumn("링크", display_text="원문")})
    ms = _read("tram_meta_summary.csv")
    if ms is not None and len(ms):
        g = ms[ms.group == "전체 (트램·경전철)"]
        if len(g):
            g = g.iloc[0]
            st.caption(f"해외 트램·경전철 땅값 효과 메타분석 {int(g.k)}곳: 평균 {g.mu_pct:+.1f}% "
                       f"(95% {g.ci_low_pct:.1f}~{g.ci_high_pct:.1f}%)")
    _img(st, "tram_meta_forest.png", "해외 트램·경전철 개통 효과와 대전 값 비교")
    st.caption("공통점: 비교군이 있는 연구는 부동산 +3~12%, 점포 수보다 업종 구성·가게 수명이 바뀜, 효과는 몇 년 뒤 커짐, "
               "공사 기간 손실은 거의 모든 도시에서 확인. 개발 투자액('수조 원') 같은 운영기관 집계는 인과가 아님.")
    st.caption("관광: 트램이 관광객을 늘렸다는 인과 측정은 없음(유일한 트램 DiD인 골드코스트도 매출 효과 무효). "
               "관광지 직결 노선의 관광객 이용률(나가사키·히로시마 37~40%)은 이용 비율이지 새 방문이 아님 → 앱은 관광을 "
               "부수 효과로 따로 보여 줌 ('트램과 관광' 화면)")


def _how(st):
    st.markdown("**앱의 '건설 후' 숫자는 이렇게 만듭니다**")
    st.markdown(
        "| 쓰는 곳 | 계산 | 근거 |\n|---|---|---|\n"
        "| 땅값 예측·진단·땅값 흐름 점수 | 정거장 500m 안 비율 × 땅값 효과 수준(낮음·기본·높음) × 개통 후 연차별 모양 | 대전 1호선 땅값 |\n"
        "| 업종 점수 – 음식 | 정거장 500m 안 비율 × 상권 음식점 중 카페 비중 × 카페 효과 (빵·과자는 높음 시나리오에만) | 대전 1호선 인허가 점포 |\n"
        "| 업종 변화 (지도·패널) | 카페 점포 중 500m 안 비율 × 카페 효과 × 카페 연차 모양(개통 후 계속 커짐) → 2034 카페 비중 증가 %p | 대전 1호선 인허가 + 근거 점검 |\n"
        "| 업종 점수 – 소매·숙박 등 5개 | 정거장 500m 안 비율 × 땅값 효과 × 해외 업종 비율(영국 경전철 논문) | 대전 1호선 땅값 + 해외 |\n")
    fm = _read("industry_food_tram_mix.csv")
    sc = _read("industry_scores.csv")
    if fm is not None and sc is not None and "tram_effect_base" in sc:
        f = sc[sc.industry == "음식"][["code", "name", "in500", "tram_effect_low", "tram_effect_base", "tram_effect_high"]]
        f = f.merge(fm[["code", "cafe_share", "bakery_share"]], on="code", how="left")
        f["cafe_share"] = (f.cafe_share * 100).round(0)
        f["bakery_share"] = (f.bakery_share * 100).round(0)
        f["in500"] = (f.in500 * 100).round(0)
        f = f.sort_values("tram_effect_base", ascending=False)[
            ["name", "in500", "cafe_share", "bakery_share", "tram_effect_low", "tram_effect_base", "tram_effect_high"]]
        f.columns = ["상권", "500m 안 점포 %", "카페 비중 %", "빵·과자 비중 %", "음식 효과 낮음 %", "기본 %", "높음 %"]
        st.markdown("**상권별 음식 업종 트램 효과** (카페가 많고 정거장에 가까울수록 큼)")
        st.dataframe(f, hide_index=True, use_container_width=True)
    st.caption("음식 효과 시나리오: 낮음 = 카페 효과의 95% 하한 / 기본 = 카페 추정치, 나머지 음식 업종 0 / "
               "높음 = 모든 음식 업종 추정치(빵·과자 포함). 빵·과자는 개수만 늘고 음식점 중 비중은 1·2단계 모두 그대로라 기본에서 뺌. "
               "효과는 개통 후 9년 평균(2006~2014).")
    st.markdown("**주의**  \n- 대전 1호선은 지하철이라 지상 트램(차로 축소·속도)과 다를 수 있음  \n"
                "- 공사 기간 손실은 앱 숫자에 들어 있지 않음 (해외는 상인 매출 −30% 안팎, 보상 사례 다수)  \n"
                "- 매출이 아니라 땅값·점포 수 기준 효과")


def _body(st):
    sc = _read("tram_scenarios.csv")
    sec = _read("line1_permits_sector.csv")
    ms = _read("tram_meta_summary.csv")
    st.caption("앱의 트램 효과 숫자는 모두 대전 1호선(2006 개통) 실측에서 나오고, 해외 트램 사례로 크기를 확인했습니다.")
    c = st.columns(4)
    if sc is not None and (sc.scenario == "base").any():
        b = sc[sc.scenario == "base"].iloc[0]
        c[0].metric("땅값 효과 (기본)", f"{b.effect_pct:+.1f}%", "대전 1호선 역 500m", delta_color="off", delta_arrow="off")
    if sec is not None:
        for i, name in ((1, "카페"), (2, "빵·과자")):
            r = sec[sec["업종"] == name]
            if len(r):
                r = r.iloc[0]
                c[i].metric(f"{name} 점포", f"{r['효과_%']:+.1f}%", f"{r['하한_%']:+.0f}~{r['상한_%']:+.0f}% · 검사 통과",
                            delta_color="off", delta_arrow="off")
    if ms is not None:
        g = ms[ms.group == "전체 (트램·경전철)"]
        if len(g):
            g = g.iloc[0]
            c[3].metric("해외 트램 땅값 (메타분석)", f"{g.mu_pct:+.1f}%", f"{int(g.k)}곳 평균", delta_color="off", delta_arrow="off")
    t0, t1, t2, t3, t4 = st.tabs(["한눈에", "대전 1호선 땅값", "대전 1호선 점포", "해외 사례", "앱에 쓰는 방식"])
    with t0:
        st.markdown(
            "1. **땅값**: 대전 1호선 역 500m 안 땅값이 비교 지역보다 1단계 +5.8%, 1·2단계 합산 +1.8% 더 올랐음 → "
            "앱 시나리오 낮음·기본·높음의 출발점. 해외 트램과 비슷한 크기 (메타분석 평균 +2.6%, 비교군 있는 개별 연구 대부분 +3~12%).\n"
            "2. **상권**: 같은 역 500m 안에서 전체 가게 수 효과는 불확실했지만(기본 +4.7% 유의 X, 번화도 맞추면 +12%) **카페는 확실히 늘었음** "
            "(개수 +25%, 음식점 중 비중 +1.4%p, 2단계 역에서도 +4.0%p로 따로 재현). 빵집은 개수만 늘고 비중은 그대로 → "
            "트램은 가게 수보다 업종 구성을 바꿈 (피렌체·마르세유와 같은 결과).\n"
            "3. **시간**: 효과는 개통 직후보다 3년 뒤부터 커짐 (대전 점포, LA 일자리, 피닉스 창업).\n"
            "4. **범위**: 효과는 역 500m 안에 몰림 (750m로 넓히면 점포 효과 0).\n"
            "5. **반대 근거**: 효과가 없거나 마이너스인 사례(노퍽 −7.8%, 그르노블 점포 수 변화 없음)와 공사 기간 손실도 있음.")
        _img(st, "line1_permits_sector.png", "대전 1호선 업종 그룹별 점포 효과")
    with t1:
        _land(st)
    with t2:
        _store(st)
    with t3:
        _overseas(st)
    with t4:
        _how(st)
    st.caption("코드: tram_model/analyze_landprice.py · analyze_line1_permits.py · analyze_tram_meta.py · score_industry.py")


def open_tram_evidence(st):
    """팝업 바로 열기. Streamlit 1.37 미만이면 접히는 상자로 대체."""
    if hasattr(st, "dialog"):
        @st.dialog(TITLE, width="large")
        def _dlg():
            _body(st)
        _dlg()
    else:
        with st.expander(TITLE, expanded=True):
            _body(st)
