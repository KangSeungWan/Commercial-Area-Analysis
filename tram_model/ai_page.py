"""'AI 상권 해설' 화면 — 상권을 고르고, 원하면 추가 질문을 적어 맞춤 해설을 받는 기능.
(11-03 2차 점검: 요금표·'프리미엄' 표기 삭제, 실시간 해설 숫자 자동 대조 추가)

app.py 에서: import ai_page → elif PAGE == "ai": ai_page.render(st, deps)
deps = dict(info, fc, IS, weights, ind_area, events, st_areas, scen_key, scen_text, scen_help, rentp, comp, tour,
            api_key, model, names)   ← 지도 화면과 같은 시나리오·업종 가중치
동작
  - 추가 질문 없음 → 기존 프롬프트로 실시간 호출. 실패하면 outputs/ai_comments.json 의 기본 해설(Claude 사전 작성)
  - 추가 질문 있음 → 기존 프롬프트 + 질문. 실패하면 기본 해설을 보여 주되 "질문 답은 실시간 연결 때만" 안내
  - 실시간 해설의 숫자는 보낸 정보와 기계로 대조(ac.unverified_numbers) → 없는 숫자가 있으면 경고 + 기본 해설 함께 표시
API 키·오류 원문에 섞인 키는 화면에 내보내지 않음.
"""
import ai_comment as ac

EXAMPLES = ["이 상권에서 카페를 열려는데 2030년 개통 전후 어느 시점이 나을까?",
            "임대료 부담 신호가 높다는데, 임차인은 계약할 때 무엇을 확인해야 해?",
            "공사 기간(2025~2028)에 매출 감소 보상을 받으려면 지금 무엇을 준비해야 해?",
            "이 상권과 옆 상권 중 소매업에 더 유리한 곳은 어디야?"]


def _mask(text, key):
    return text.replace(key, "****") if key else text


def render(st, D):
    st.markdown('<h1 class="page-t">AI 상권 해설</h1>', unsafe_allow_html=True)
    st.caption("상권을 고르면 진단·땅값 전망·업종 점수·임대료 신호를 AI에게 보내 해설을 받습니다. "
               "묻고 싶은 것을 직접 적으면 그 상권에 맞춘 답을 함께 받습니다. "
               "숫자는 모두 이 앱의 분석 결과에서 나오고, AI는 그것을 설명·해석하는 역할만 합니다.")

    info, names = D["info"], D["names"]
    codes = list(info.index)
    ss = st.session_state
    ss.setdefault("ai_pick", ss.get("sel_area") or codes[0])
    if ss.ai_pick not in codes:
        ss.ai_pick = codes[0]
    code = st.selectbox("상권", codes, key="ai_pick", format_func=lambda c: f"{c} {names.get(c, c)}")
    r = info.loc[code]
    q = r.get("quadrant")
    st.markdown(f"**{names.get(code, code)}** · 진단 {q} · 상대 쇠퇴 위험 {r.risk_score:.0f}점 · 성장 가능 {r.growth_score:.0f}점"
                + (f" · 절대 쇠퇴 신호 {r.abs_decline}" if isinstance(r.get("abs_decline"), str) else "")
                + f" · 시나리오 {D['scen_text']}")

    st.markdown("**추가로 묻고 싶은 것**", unsafe_allow_html=True)
    ex = st.pills("예시 질문 (누르면 아래에 채워짐)", EXAMPLES, key="ai_ex", selection_mode="single")
    if ex and ss.get("_ai_ex_last") != ex:
        ss["ai_extra"] = ex
        ss["_ai_ex_last"] = ex
    extra = st.text_area("질문 (비워 두면 기본 해설만 받습니다)", key="ai_extra", height=90,
                         placeholder="예: 이 상권에서 10년 넘게 식당을 하고 있는데 트램 개통 뒤 무엇을 준비해야 할까?")
    extra = (extra or "").strip()

    ctx = ac.area_context(code, info, D["fc"], D["IS"], D["weights"], D["ind_area"], D["events"], D["st_areas"],
                          D["scen_key"], D.get("rentp"), D.get("comp"), D.get("tour"))
    prompt = ac.build_prompt(ac.context_text(ctx), D["scen_text"], D["scen_help"], extra or None)
    saved = ac.saved_entry(ac.load_saved(), code)

    ss.setdefault("ai_page_res", {})
    key = (code, D["scen_key"], extra)
    res = ss.ai_page_res.get(key)
    b1, b2 = st.columns([1, 3])
    go = b1.button(("맞춤 해설 받기" if extra else "해설 받기") + (" (다시)" if res else ""), type="primary", key="ai_go")
    b2.caption("실시간 연결이 안 되면 미리 만들어 둔 기본 해설을 보여 드립니다. AI 글 속 숫자는 보낸 정보와 자동으로 대조합니다.")
    if go:
        with st.spinner("AI가 해설을 쓰는 중입니다. 10초쯤 걸립니다."):
            try:
                text = ac.generate(prompt, D["api_key"], D["model"])
                res = {"src": "live", "text": text, "bad": ac.unverified_numbers(text, ac.context_text(ctx), prompt)}
            except Exception as e:
                err = _mask(f"{type(e).__name__}: {e}", D["api_key"])
                why = "API 키가 설정되어 있지 않습니다." if isinstance(e, ac.NoApiKey) else "인터넷 연결이나 AI 서비스에 문제가 있습니다."
                res = {"src": "saved" if saved else "none", "err": err, "why": why}
        ss.ai_page_res[key] = res

    if res is None:
        st.info("위에서 상권을 고르고(원하면 질문을 적고) '해설 받기'를 누르세요.")
    elif res["src"] == "live":
        st.markdown('<span class="ai-saved">실시간 해설</span>' + (' <span class="ai-saved">맞춤 질문 반영</span>' if extra else ""),
                    unsafe_allow_html=True)
        if res.get("bad"):
            st.warning("AI 글에 분석 정보에 없는 숫자가 있습니다: " + ", ".join(f"{v:g}" for v in res["bad"][:8])
                       + ". 이 숫자는 믿지 마세요. 아래 '기본 해설'과 'AI에게 보낸 정보'로 대조할 수 있습니다.")
        st.markdown(res["text"])
        if res.get("bad") and saved:
            with st.expander(f"기본 해설 ({saved['generated_at'][:10]} 작성, 수치 대조 완료)"):
                st.markdown(saved["text"])
    elif res["src"] == "saved":
        st.markdown(f'<span class="ai-saved">기본 해설 ({saved["generated_at"][:10]} 작성)</span>', unsafe_allow_html=True)
        st.caption(f"지금은 실시간 해설을 받을 수 없어 미리 만들어 둔 기본 해설을 보여 드립니다. {res['why']} "
                   f"이 해설은 '{saved['scenario']}' 시나리오와 기본 업종 가중치 기준입니다.")
        if extra:
            st.warning("적어 주신 질문에 대한 답은 실시간 연결이 될 때만 받을 수 있습니다. 질문은 그대로 두었으니 잠시 뒤 다시 눌러 주세요.")
        st.markdown(saved["text"])
        with st.expander("오류 내용 보기 (발표자용)"):
            st.code(res["err"], language=None)
    else:
        st.warning(f"지금은 AI 해설을 받을 수 없습니다. {res['why']} 미리 만들어 둔 해설도 없습니다.")
        with st.expander("오류 내용 보기 (발표자용)"):
            st.code(res["err"], language=None)

    with st.expander("AI에게 보낸 정보와 질문 보기"):
        st.json(ctx)
        st.text_area("실제로 보내는 글 (프롬프트)", prompt, height=260, disabled=True, key="ai_prompt_view")
    st.caption("AI 해설은 분석 결과를 설명하는 참고 자료이며 투자·계약 판단의 근거가 아닙니다. 추정치는 '추정'으로 표시됩니다. "
               "모델: Google Gemini · 기본 해설: 2026-10-28 같은 프롬프트로 사전 작성, 2026-11-03 숫자 기계 대조(check_ai_numbers.py) · "
               "출처: outputs/area_profile.csv, forecast_land.csv, industry_scores.csv, rent_pressure.csv, composition_forecast.csv, tourism_layer.csv")
