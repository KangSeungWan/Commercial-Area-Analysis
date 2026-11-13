"""'분석 방법' 팝업의 '관광' 탭 — 트램 관광 효과 근거(보조 관점)와 검증한 관광지 목록 요약.

about_page.py 에서: from tourism_about import tourism_tab → with t7: tourism_tab(st)
읽는 파일 (tram_model/data, 없으면 해당 부분만 건너뜀)
  literature_tram_tourism.csv  문헌 90건 (근거_트램관광효과.md 와 같은 내용)
  tourism_params.csv           시나리오 파라미터 14개
  tourism_poi.csv              관광지 115곳(검증 반영, 관문 3곳 포함)
관광은 '확정 효과'가 아니라 '접근성 변화 → 방문 소비 시나리오'로만 씀 (10-25 결정).
"""
import os

import pandas as pd

DATA = "tram_model/data"
GRADES = ["상", "중", "하"]


def _csv(name):
    p = f"{DATA}/{name}"
    if not os.path.exists(p):
        return None
    return pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False, dtype=str)


def _grade(x):
    x = str(x)
    return x[0] if x[:1] in GRADES else "중"


def _param(P, pid, default=""):
    if P is None:
        return default
    r = P[P.param_id == pid]
    return r.iloc[0]["value"] if len(r) else default


def _gray_low(row):
    return ["color: #9aa0a6"] * len(row) if row["등급"] == "하" else [""] * len(row)


def tourism_tab(st):
    P = _csv("tourism_params.csv")
    st.markdown("**관광은 보조 관점입니다.** 트램 개통이 관광객을 늘렸다는 인과 측정은 세계적으로 **없습니다**. "
                "그래서 앱은 관광 효과를 확정 숫자가 아니라 **'관광 접근성 변화 → 방문 소비' 시나리오(범위)** 로만 보여 줍니다.")

    st.markdown("**① 쓸 수 있는 숫자** (시나리오의 재료, 모두 다른 교통수단·다른 도시에서 빌림)")
    use = [
        ("접근성 1% ↑ → 외지인 도착", f"{_param(P, 'TOUR_eps_low', '0')} / {_param(P, 'TOUR_eps_base_arrivals', '0.726')} / "
         f"{_param(P, 'TOUR_eps_high', '1.0')} (낮음·기본·높음)", "이탈리아·스페인 고속철(HSR) — 트램 아님, 상한 성격"),
        ("접근성 1% ↑ → 숙박", _param(P, "TOUR_eps_base_nights", "0.532"), "이탈리아 고속철"),
        ("관광객의 트램 이용률", f"{_param(P, 'TOUR_tram_share_low', '0.05')} ~ {_param(P, 'TOUR_tram_share_high', '0.37~0.40')}",
         "포틀랜드(신설 통근형) ~ 나가사키·히로시마(관광지 직결 노면전차)"),
        ("효과가 절반 나타나는 시점", f"개통 후 {_param(P, 'TOUR_ramp_midpoint', '24')}개월", "뉴욕 복합개발 PPML DiD (S-커브)"),
        ("비통근 승객 비중", _param(P, "TOUR_noncommute_share", "0.721"), "일본 노면전차 전국 (관광만은 아님)"),
    ]
    st.dataframe(pd.DataFrame(use, columns=["무엇", "값", "출처·주의"]), hide_index=True, use_container_width=True)

    st.markdown("**② 효과가 없거나 반대였던 결과** (같이 보여 줘야 공정함)")
    st.markdown(
        f"- 골드코스트 G:Link(현대 트램, 유일한 트램 DiD): 대중교통 이용 +{_param(P, 'TOUR_tram_did_null', '3.6')}%, "
        "상권 매출 부진은 트램 탓으로 볼 수 없음(무효)\n"
        f"- 멜버른 무료 트램구역: 늘어난 트램 통행 중 상당수가 열차에서 옮겨 온 것({_param(P, 'TOUR_mode_substitution', '-7000/13700')} 통행/일) → 새 방문 아님\n"
        f"- 고속철도 체류 기간 변화 ≈ 0 ({_param(P, 'TOUR_stay_adj', '-0.002')}): 오는 사람은 늘어도 더 오래 머물지는 않음\n"
        "- 미국 스트리트카 여러 곳: 관광객 의존 노선은 계절에 따라 이용이 크게 흔들림")

    st.markdown("**③ 이 앱이 말하지 않는 것**")
    st.markdown(
        "- '트램이 관광객을 몇 명 늘린다', '관광 매출 몇 억 원' 같은 확정 숫자\n"
        "- 해외 관광도시(나가사키·홍콩 등) 수치를 대전에 그대로 적용\n"
        "- 8989 카드 매출의 외지인 비율 (자료에 거주지 구분이 없음 → 방문 강도·주말 비중·숙박음식 비중으로 대신 봄)\n"
        "- 개통 후 실제 효과는 2030년 이후 자료로 검증해야 함 (계획: PPML DiD)")

    L = _csv("literature_tram_tourism.csv")
    if L is not None and len(L):
        L["등급"] = L.reliability.map(_grade)
        st.markdown(f"**④ 모은 문헌 {len(L)}건** (등급 '하'는 회색: 운영기관 홍보·언론 수치 등)")
        c1, c2 = st.columns(2)
        gs = c1.multiselect("신뢰도", GRADES, default=["상", "중"], key="tour_lit_grade")
        groups = ["전체"] + sorted(L.group.unique())
        gp = c2.selectbox("분야", groups, key="tour_lit_group")
        f = L[L["등급"].isin(gs or GRADES)]
        if gp != "전체":
            f = f[f.group == gp]
        f = f[["등급", "group", "source", "city_system", "year", "finding", "use_in_project", "url"]]
        f.columns = ["등급", "분야", "출처", "도시·노선", "연도", "결과", "앱에서 쓰는 곳", "링크"]
        st.dataframe(f.style.apply(_gray_low, axis=1), hide_index=True, use_container_width=True,
                     column_config={"링크": st.column_config.LinkColumn("링크", display_text="원문")})
        st.caption(" · ".join(f"{g} {int((L['등급'] == g).sum())}건" for g in GRADES))

    T = _csv("tourism_poi.csv")
    if T is not None and len(T):
        u = T[T.use_in_tourism == "1"]
        gw = T[T.get("gateway", pd.Series("0", index=T.index)) == "1"]
        st.markdown(f"**⑤ 검증한 대전 관광지 {len(u)}곳** (전체 {len(T)}곳 중, 인터넷 대조로 폐장·숙박·중복·호텔 제외)")
        k = u.tour_type.value_counts()
        cols = st.columns(4)
        for c_, (name, note) in zip(cols, [("관광지", "가중치 1"), ("문화재(소규모)", "지도만, 가중치 0"),
                                          ("체험시설", "낮은 가중치"), ("축제장", "연 1회 피크, 따로")]):
            c_.metric(name, f"{int(k.get(name, 0))}곳", note, delta_color="off", delta_arrow="off")
        g = u.groupby("gu").size().reindex(["동구", "중구", "서구", "유성구", "대덕구"]).fillna(0).astype(int)
        st.caption("구별: " + " · ".join(f"{a} {b}" for a, b in g.items()))
        if len(gw):
            st.markdown("**관문(교통) " + str(len(gw)) + "곳**: " + ", ".join(gw.name) +
                        " — 관광지가 아니라 관광객이 대전에 들어오는 곳. 관광 지표에는 넣지 않고, "
                        "정거장까지의 접근성(관문 → 관광지 이동 시간)을 계산하는 출발점으로만 씀")
        st.caption("좌표: 카카오 로컬 API(이름 → 주소 순) · 행정동: 2023 경계 · 입장객: 문체부 주요관광지점 입장객 통계(59곳)")
    st.caption("자세한 근거: tram_model/docs/근거_트램관광효과.md · 검증 기록: tram_model/docs/검증_관광지목록.md")
