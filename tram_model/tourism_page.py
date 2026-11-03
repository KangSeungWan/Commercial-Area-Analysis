"""'트램과 관광' 화면 — 부수 효과로 '이런 효과도 기대할 수 있다' 수준만 보여 줌 (10-28 결정).

app.py 에서: import tourism_page → elif PAGE == "tourism": tourism_page.render(st)
내용: ① 국내 트램 개통 예정 ② 해외에서 관광 효과를 보는 사례(+주의 사례) ③ 대전 기대 효과(build_tourism_layer 결과)
     ④ 근거와 방법(접힘: tourism_about.tourism_tab)
진단·점수·결론 띠에는 관광을 넣지 않음. 국내 현황은 2026-10 기사 기준 → 발표 전 한 번 더 확인.
"""
import os

import pandas as pd

OUT = "tram_model/outputs"
CHECKED = "2026-10-28"

# (노선, 지역·구간, 규모, 개통 목표, 지금 상태, 관광과의 관계, 출처 링크)
DOMESTIC = [
    ("위례선", "서울 송파·성남·하남 (마천~복정·남위례)", "5.4km · 12곳", "2026-12 (잠정 26일)",
     "시험 운행·최종 점검", "신도시 생활 노선. **국내 첫 개통 트램** → 대전보다 4년 먼저 실제 자료가 나옴",
     "https://www.redaily.co.kr/news/articleView.html?idxno=16441"),
    ("울산 1호선 (수소트램)", "태화강역 ~ 신복교차로", "10.85km · 15곳 · 3,814억 원", "2029 말",
     "우선 시공 착수", "철도역(태화강역)에서 출발 → 관문역 연결형", "https://www.kmib.co.kr/article/view.asp?arcid=0029710732"),
    ("대전 2호선", "대전 순환선 + 지선", "38.8km · 45곳 · 1조 4,782억 원", "2030 하반기 (2년 연기)",
     "공사 중", "관문 3곳(대전역·서대전역·복합터미널)을 지나고 과학관·수목원·볼파크 정거장",
     "https://www.mt.co.kr/policy/2026/06/23/2026062314254843510"),
    ("동탄 트램", "화성 동탄 (2개 노선)", "34.4km · 36곳 · 9,981억 원", "2031-12 준공",
     "계약·실시설계", "신도시 생활 노선", "https://www.kyeongin.com/article/1768474"),
    ("부산항선 트램 (계획)", "경성대·부경대역 ~ 영도 태종대", "24.21km", "미정",
     "계획 (오륙도선 실증노선은 2026-06 무산, 일부 구간 반영)", "종점이 관광지(태종대) → 국내에서 드문 관광지 직결 계획",
     "https://v.daum.net/v/20260612143306325"),
    ("수원·성남·부천·시흥·안산", "경기도", "—", "미정", "재원 문제로 정체", "—",
     "https://www.segye.com/newsView/20260908518120"),
]

# (도시·노선, 무엇을 봤나, 숫자, 읽는 법, 등급, 링크)
GOOD = [
    ("히로시마 노면전차", "관광객의 시내 이동 수단", "노면전차 40% (일본인 40.1%, 외국인 39.8%)",
     "평화공원·원폭돔을 바로 잇는 오래된 노선. 관광객이 '알기 쉬운 수단'으로 씀", "상",
     "https://www.city.hiroshima.lg.jp/_res/projects/default_project/_page_/001/017/595/16761.pdf"),
    ("나가사키 노면전차", "관광 목적 도착자의 역 하차 후 수단", "37% (하루 약 800명)",
     "역 → 관광지 직결. 크루즈 승객도 27%가 이용", "상",
     "https://www.pref.nagasaki.jp/shared/uploads/2020/02/1582101947.pdf"),
    ("구마모토 시전", "1일 승차권 월 판매", "5,486 → 8,720장 (2023.4 → 2024.4, +59%)",
     "외국인 관광 회복기와 겹침 → 트램 자체 효과는 아님", "상",
     "https://www.city.kumamoto.jp/kiji00349663/5_49663_413075_up_VGAE4I6T.pdf"),
    ("멜버른 무료 트램 구역", "구역 안 트램 통행 (2015 무료화 뒤)", "연 1,850만 → 3,550만",
     "관광객·주민 구분 없음, 일부는 열차에서 옮겨 온 이동", "상",
     "https://parliament.vic.gov.au/4af7f4/contentassets/56015a73cd3f4842926026a7ac22e7e4/inquiry-into-expanding-melbournes-free-tram-zone.pdf"),
    ("에든버러 트램 (2014)", "이용 목적·축제 주간", "여가 57% · 축제 주간 13.7만 명",
     "관광객 비율은 따로 없음. 축제 때 수송 역할", "상",
     "https://www.edinburgh.gov.uk/tramstonewhaven/downloads/file/68/steer-report"),
    ("가오슝 순환 경전철 (2024 완전 개통)", "이용객", "2024년 1~10월 1,031만 명",
     "보얼예술특구 등 관광지를 잇지만 관광 증가 인과는 확인 안 됨", "중",
     "https://www.cna.com.tw/news/aloc/202412070038.aspx"),
    ("도야마 센트램 (2009)", "도심 휴일 보행자", "8,421 → 11,144명 (+32%)",
     "관광객이 아니라 도심 보행. 거리 활력 쪽 근거", "상", "https://www.mlit.go.jp/common/001000821.pdf"),
    ("홍콩 트램 · 샌프란시스코 케이블카", "관광객 비율", "15~20% · '대다수'",
     "운영사 추정·비공식 → 참고만", "하", "https://www.td.gov.hk/mini_site/atd/2023/en/section5-2.html"),
]
CAUTION = [
    ("골드코스트 G:Link", "현대 트램을 비교군과 견준 유일한 연구: 대중교통 이용 +3.6%, 상권 매출 효과는 확인 안 됨", "중",
     "https://www.worldtransitresearch.info/research/10421"),
    ("리스본 28번", "관광객이 몰려 대기 1시간 넘음 → 주민용 미니버스를 따로 운행", "하",
     "https://fortune.com/europe/2024/10/26/lisbon-trams-tourists-locals-stranded"),
    ("하코다테 시전", "주민 46%가 관광객 때문에 혼잡하다고 응답", "상",
     "https://www.city.hakodate.hokkaido.jp/docs/2024101700025/file_contents/shiryoR602_1-1.pdf"),
    ("포틀랜드 스트리트카", "통근형 신설 노선: 승객 중 관광객 5% 미만", "하",
     "https://nextcity.org/urbanist-news/new-survey-portland-streetcar-ridership-locals-tourists"),
]


def _read(name):
    p = f"{OUT}/{name}"
    return pd.read_csv(p, encoding="utf-8-sig", dtype={"id": str}) if os.path.exists(p) else None


def _domestic(st):
    st.markdown("#### 국내 트램 개통 예정")
    df = pd.DataFrame(DOMESTIC, columns=["노선", "구간", "규모", "개통 목표", "지금", "관광과의 관계", "링크"])
    df["관광과의 관계"] = df["관광과의 관계"].str.replace("**", "", regex=False)
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"링크": st.column_config.LinkColumn("링크", display_text="기사")})
    st.caption(f"기사 기준 ({CHECKED} 확인). 국내에는 아직 개통한 현대 트램이 없어 관광 효과를 잰 사례가 없음 → "
               "위례선(2026-12)이 첫 비교 대상. 일정은 자주 바뀌므로 발표 전에 다시 확인")


def _overseas(st):
    st.markdown("#### 해외에서 관광 효과를 보는 사례")
    st.caption("공통점: 관광지를 **바로 잇는 노선**일수록 관광객이 많이 탐(히로시마·나가사키 37~40%). "
               "통근형 신설 노선은 5% 안팎. 숫자는 '이용 비율'이며 '트램 때문에 관광객이 늘었다'는 인과가 아님")
    df = pd.DataFrame(GOOD, columns=["도시·노선", "무엇을 봤나", "숫자", "읽는 법", "등급", "링크"])
    st.dataframe(df.style.apply(lambda r: ["color: #9aa0a6"] * len(r) if r["등급"] == "하" else [""] * len(r), axis=1),
                 hide_index=True, use_container_width=True,
                 column_config={"링크": st.column_config.LinkColumn("링크", display_text="원문")})
    st.markdown("**같이 봐야 할 사례** (효과 없음·부작용)")
    for city, txt, g, url in CAUTION:
        st.markdown(f"- **{city}**: {txt} · 등급 {g} · [원문]({url})")


def _daejeon(st):
    st.markdown("#### 대전에서 기대할 수 있는 효과")
    L, S = _read("tourism_layer.csv"), _read("tourism_station.csv")
    if L is None or S is None:
        st.info("관광 계산 결과가 없습니다. python tram_model/build_tourism_layer.py 를 실행하세요.")
        return
    A = L[L.kind == "area"]
    on = A[A.tourism_type == "관광자원형"]
    c = st.columns(2)                                   # 2차 점검(11-03): 인과 근거가 없는 방문 증가 %는 첫 화면에서 뺌 → '근거와 방법' 안 표로만
    c[0].metric("관광지가 가까운 상권", f"{len(on)} / {len(A)}", f"그중 관광지 많은 곳 {int((on.tour_level == '강').sum())}",
                delta_color="off", delta_arrow="off")
    c[1].metric("관광지가 있는 정거장", f"{int((S.n_poi > 0).sum())} / {len(S)}", "500m 안 (큰 공원 1km)",
                delta_color="off", delta_arrow="off")
    st.markdown(
        "- **만년동·과학관·엑스포 일대(정거장 220·221)**: 수목원·과학관·신세계·한빛탑이 모여 있어 트램이 가장 의미 있는 곳. "
        "다만 대전역에서는 지금 버스가 더 빨라 기본 시나리오 효과는 작음\n"
        "- **대전역·원도심(성심당·중앙시장·으능정이)**: 관광 수요는 가장 크지만 대전역에서 걸어서 가는 거리라 트램으로 달라지는 것이 거의 없음\n"
        "- **알기 쉬운 이동 수단**: 땅 위로 다니고 노선이 눈에 보여 처음 온 관광객이 쓰기 쉬움 "
        "(히로시마·나가사키 관광객 37~40% 이용). 이 장점은 숫자로 넣지 못함\n"
        "- **축제 수송**: 0시 축제(중앙로) 기간 대전역·중앙로 정거장 이용 증가 예상 (에든버러 축제 주간 13.7만 명 참고)\n"
        "- **조심할 점**: 관광객이 몰리면 주민 혼잡(리스본·하코다테). 순환선이라 먼 관광지는 오히려 버스보다 느림")
    t = on.sort_values("visit_high_pct", ascending=False)[["name", "tour_level", "top_poi"]].copy()
    t.columns = ["상권", "관광지", "가까운 관광지"]
    t["관광지"] = t["관광지"].map({"강": "많음", "약": "조금"})
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**관광지가 가까운 상권**")
        st.dataframe(t, hide_index=True, use_container_width=True)
    with c2:
        st.markdown("**관광지가 있는 정거장**")
        s = S[S.n_poi > 0].sort_values("tour_score", ascending=False)[["station_no", "station_name", "pois"]]
        s.columns = ["번호", "정거장", "관광지 (거리)"]
        st.dataframe(s, hide_index=True, use_container_width=True)
    st.caption("시나리오: 관문 4곳(대전역·대전복합터미널·서대전역·유성복합터미널, 하루 이용객 비율로 가중)에서 상권까지 이동 시간이 "
               "트램으로 줄어드는 만큼 방문이 는다고 가정(해외 고속철 탄력성 0~1.0 차용). 이동 시간은 근사(환승 제외). "
               "효과는 개통 후 2년쯤에 절반. 앱의 진단·점수에는 넣지 않음. 트램이 관광객을 늘렸다는 인과 연구가 없어 상권별 방문 증가 %는 "
               "화면에 숫자로 내지 않음(계산 결과는 outputs/tourism_layer.csv, 근거와 방법 참고)")


def render(st):
    st.markdown('<h1 class="page-t">트램과 관광</h1>', unsafe_allow_html=True)
    st.caption("관광은 트램의 **부수 효과**입니다. 트램이 관광객을 늘렸다는 인과 측정은 세계적으로 없어서, "
               "이 화면은 '이런 효과도 기대할 수 있다' 수준으로만 보여 주고 상권 진단·점수에는 넣지 않습니다.")
    t1, t2, t3 = st.tabs(["대전 기대 효과", "해외 사례", "국내 개통 예정"])
    with t1:
        _daejeon(st)
    with t2:
        _overseas(st)
    with t3:
        _domestic(st)
    with st.expander("근거와 방법 (문헌 90건 · 관광지 목록 · 쓸 수 있는 숫자)"):
        try:
            from tourism_about import tourism_tab
            tourism_tab(st)
        except Exception as e:
            st.caption(f"근거 표를 열지 못했습니다: {e}")
    st.caption("출처: tram_model/outputs/tourism_layer.csv · tourism_station.csv (build_tourism_layer.py), "
               "data/literature_tram_tourism.csv, 각 표의 링크")
