"""AI 상권 해설: 앱(app.py)과 미리 만들기 스크립트(make_ai_comments.py)가 함께 쓰는 부분.

- 상권 정보 묶음(area_context)과 질문 글(build_prompt)을 한곳에서 만들어, 실시간 해설과 저장본이 같은 내용을 근거로 함
- 저장본: outputs/ai_comments.json (생성 날짜·모델·시나리오 포함)
- API 키는 화면·로그에 절대 출력하지 않음
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT_DIR, DATA_DIR = HERE / "outputs", HERE / "data"
SAVED_PATH = OUT_DIR / "ai_comments.json"
DEFAULT_MODEL = "gemini-3.8-flash"
TIMEOUT_MS = 30_000                     # 발표장에서 한없이 기다리지 않도록 (30초 넘으면 실패로 보고 저장본으로)
TRAM_DEF = "상권 가치(땅값) 기준 효과: 개통 초기 1~4년, 정거장 500m 안 땅값으로 추정한 %. 점포당 매출 변화가 아님(대전 실측상 매출 차이는 작음)"
IND_ORDER = ["음식", "소매", "수리·개인", "교육", "보건의료", "숙박"]
SCEN_COL = {"base": "tram_effect", "low": "tram_effect_low", "high": "tram_effect_high"}


# ── 결과 파일 읽기 (스크립트용. 앱은 자기 캐시로 읽은 값을 넘김) ──
def _csv(path, **kw):
    return pd.read_csv(path, encoding="utf-8-sig", **kw) if Path(path).exists() else None


def load_inputs(out=OUT_DIR, data=DATA_DIR):
    return {"prof": _csv(out / "area_profile.csv"), "fc": _csv(out / "forecast_land.csv"),
            "IS": _csv(out / "industry_scores.csv"), "ISW": _csv(out / "industry_score_weights.csv"),
            "ind_area": _csv(out / "industry_by_area.csv"), "events": _csv(data / "area_events.csv"),
            "st_areas": _csv(out / "station_areas.csv"), "ts": _csv(out / "tram_scenarios.csv")}


# ── 시나리오 이름·설명 (tram_scenarios.csv → 화면 표기와 실제 값이 항상 일치) ──
def scenarios(ts, prof_cols):
    """{화면 이름: prof 열}, [시나리오 근거 문장], {키: 행}"""
    TS = {r.scenario: r for r in ts.itertuples()} if ts is not None else {}
    scen, help_ = {}, []
    for k in ("base", "low", "high"):
        r = TS.get(k)
        lab = f"{r.label} {r.effect_pct:+.1f}%" if r is not None else {"base": "기본", "low": "낮음", "high": "높음"}[k]
        if SCEN_COL[k] in prof_cols:
            scen[lab] = SCEN_COL[k]
            if r is not None:
                help_.append(f"{r.label} {r.effect_pct:+.1f}%: {r.source}"
                             + (f" (95% 구간 {r.ci95}%)" if isinstance(r.ci95, str) and r.ci95 else ""))
    return scen, help_, TS


def ind_list(IS):
    if IS is None:
        return []
    have = set(IS.industry)
    return [i for i in IND_ORDER if i in have] + sorted(have - set(IND_ORDER))


def default_weights(ISW):
    return {r.key: float(r.weight_before) for r in ISW.itertuples() if r.key != "tram"} if ISW is not None else {}


def score_industries(IS, w, after, scen_key="base"):
    """업종 점수 = 항목 점수(0~100) 가중 평균.
    건설 후 = 성장·땅값 흐름에 트램 예상 효과를 더한 값을 '건설 전' 분포에 대어 다시 매긴 항목 점수를 씀
    → 트램이 닿지 않는 상권은 점수 그대로, 닿는 상권만 오름."""
    w = {k: v for k, v in dict(w).items() if k != "tram"}
    tot = sum(w.values()) or 1.0
    w = {k: v / tot * 100 for k, v in w.items()}
    cols = {k: (f"s_{k}_after_{scen_key}" if after and f"s_{k}_after_{scen_key}" in IS.columns else f"s_{k}") for k in w}
    S = IS[[cols[k] for k in w]].values
    Wm = np.where(~np.isnan(S), np.array(list(w.values())), 0.0)
    den = Wm.sum(1)
    sc = np.where(den > 0, (np.nan_to_num(S) * Wm).sum(1) / np.where(den > 0, den, 1), np.nan)
    out = IS.assign(score=np.round(sc, 1), **{f"sa_{k}": IS[cols[k]] for k in w})
    out.loc[IS.score_before.isna(), "score"] = np.nan          # 업종 점포가 거의 없는 상권
    return out, w


# ── AI에게 보낼 상권 정보 묶음 ──
def area_context(code, info, fc=None, IS=None, weights=None, ind_area=None, events=None, st_areas=None,
                 scen_key="base"):
    r = info.loc[code]
    g = lambda k, nd=1: (None if k not in r or pd.isna(r[k]) else (round(float(r[k]), nd) if not isinstance(r[k], str) else r[k]))
    ctx = {"상권": f"{code} {r['name']} ({r.gu}, {r.type})",
           "유형(K-means)": g("type_name"), "진단": g("quadrant"),
           "진단 안정도(15가지 변형 중 같은 진단 비율)": g("quadrant_stability", 2),
           "상대 쇠퇴 위험 점수(0~100, 20개 상권 중 순위 기반)": g("risk_score", 0), "위험 주요 원인": g("risk_drivers"),
           "상대 성장 가능 점수(0~100)": g("growth_score", 0), "성장 주요 근거": g("growth_drivers"),
           "점포 수(2026-06)": g("n_stores", 0), "주요 업종": g("top3_mid"),
           "대전 내 점포 비중 5년 변화(%)": g("store_share_chg_5y_pct"), "분기 폐업률(%, 최근 3년)": g("close_rate_q_pct", 2),
           "공시지가 5년·10년 상승률(%)": (g("land_chg_5y_pct"), g("land_chg_10y_pct")),
           "가까운 트램 정거장": f"{g('nearest_tram', 0)}번, {g('nearest_tram_m', 0)}m",
           "트램 효과(개통 초기 1~4년, 땅값 기준 추정 %) 낮음/기본/높음": (g("tram_effect_low", 2), g("tram_effect", 2), g("tram_effect_high", 2))}
    if fc is not None and code in set(fc.code):
        f = fc[(fc.code == code)].set_index("year")
        y = f.index.max()
        ctx[f"{y}년 공시지가 예측(2026=100): 트램 없음 / 트램 기본 / 80% 범위"] = (
            round(f.loc[y, "base_path"], 1), round(f.loc[y, "tram_base"], 1), f"{f.loc[y, 'lo80']:.0f}~{f.loc[y, 'hi80']:.0f}")
    if "bad_pct" in r and pd.notna(r.get("bad_pct")):
        ctx["2021 실태조사(소속 행정동)"] = f"{r.survey_dong}: 매출·이익 감소 {r.decline_pct:.0f}%, 폐업·전환 고려 " \
                                      f"{r.closing_pct:.0f}% (대전 평균 74%·7%, 코로나 시기)"
    if ind_area is not None and code in set(ind_area.iloc[:, 0]):
        ia = ind_area.set_index(ind_area.columns[0]).loc[code]
        ctx["업종 비율 변화 2016→2026(%p)"] = {c.replace("_변화p", ""): ia[c] for c in ia.index if c.endswith("_변화p")}
    if IS is not None and weights:
        _b, _ = score_industries(IS, weights, False, scen_key)
        _a, _ = score_industries(IS, weights, True, scen_key)
        _b, _a = _b[_b.code == code].set_index("industry").score, _a[_a.code == code].set_index("industry").score
        ctx["업종 점수(100점, 20개 상권 중 상대, 트램 건설 전→후)"] = {
            i: (f"{_b[i]:.0f}→{_a[i]:.0f}" if pd.notna(_b.get(i)) else "점포 부족") for i in ind_list(IS)}
    if events is not None:
        ev = events[events.area_codes.fillna("").str.contains(code)]
        if len(ev):
            ctx["과거 사건"] = [f"{e.date} {e.description}" for e in ev.itertuples()]
    if st_areas is not None:
        sa = st_areas[st_areas.code == code]
        if len(sa):
            ctx["트램 정거장 500m 영향권에 드는 점포"] = [f"{int(x.station_no)}번 정거장 {int(x.stores_in_500m)}개"
                                               f"({x.share_of_area_pct:.0f}%)" for x in sa.itertuples()]
    return ctx


def context_text(ctx):
    return json.dumps(ctx, ensure_ascii=False, default=str, indent=1)


def build_prompt(ctx_text, scen_text, scen_help):
    return f"""너는 대전 상권 분석가야. 아래는 우리 팀이 공공데이터로 분석한 상권 정보야.
{ctx_text}

[지표 설명]
- 점수: 20개 상권 안 상대 순위(0~100). 절대적 쇠퇴 판정이 아님
- 진단: 상대 쇠퇴 위험 50점 이상이면서 상권 점포 절반 이상이 트램 정거장 500m 안이면 '트램 반등 기회', 아니면 '쇠퇴 우려', 위험 50 미만이면 '성장 지속'/'정체·안정'. 진단 안정도가 0.8 미만이면 '불확실'이라고 꼭 말할 것
- 트램 효과: {TRAM_DEF}. 시나리오 근거: {' / '.join(scen_help)}. 지하철 효과를 지상 트램에 빌려 쓴 것이라 과대일 수 있음. 선택된 시나리오: {scen_text}
- 업종 점수: 성장·규모·특화도·생존·땅값(+건설 후 트램 효과)을 업종 안 20개 상권 순위로 합친 100점 점수
- 공시지가 예측: 상권별 ARIMA + 트램 효과, 80% 범위가 넓어 비교용
- 매출 금액은 위치별 실측이 없어 사용하지 않음
- 관광: 보조 관점. 트램이 관광객을 늘렸다는 인과 근거는 없음. 관광을 언급할 때는 '접근성이 좋아지면 방문이 늘 수 있다'는 시나리오로만, 범위로 쓰고 '관광객 ○명 증가'·'관광 매출 ○원' 같은 확정 표현은 쓰지 말 것

[작성 형식] 한국어, 각 항목 1~2줄, 숫자 근거를 괄호로 인용
1. 한 줄 요약 (현재 상태: 성장/정체/쇠퇴)
2. 근거 수치 3개
3. 트램 개통 기회
4. 위험 요인
5. 유리한 업종 2개와 조심할 업종 1개 (업종 점수·업종 비율 변화 근거)
6. 상권 활성화 정책 제안 1개
추정치는 '추정'이라고 표시하고, 위 정보에 없는 사실은 지어내지 마."""


# ── Gemini 호출 ──
class NoApiKey(RuntimeError):
    pass


def generate(prompt, api_key, model=DEFAULT_MODEL, timeout_ms=TIMEOUT_MS):
    if not api_key:
        raise NoApiKey("GEMINI_API_KEY 가 설정되어 있지 않습니다.")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))
    text = client.models.generate_content(model=model, contents=prompt).text
    if not text or not text.strip():
        raise RuntimeError("AI가 빈 답을 돌려주었습니다.")
    return text


# ── 저장본 ──
def load_saved(path=SAVED_PATH):
    """저장본을 읽음. 파일이 없거나 깨져 있으면 None (앱이 멈추지 않도록)."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d.get("areas"), dict) else None
    except (OSError, ValueError, AttributeError):
        return None


def saved_entry(saved, code):
    """{'text', 'generated_at', 'scenario', 'model'} 또는 None."""
    if not saved:
        return None
    e = saved["areas"].get(code)
    if not isinstance(e, dict) or not str(e.get("text", "")).strip():
        return None
    return {"text": e["text"], "generated_at": e.get("generated_at") or saved.get("generated_at", ""),
            "scenario": e.get("scenario") or saved.get("scenario", ""), "model": e.get("model") or saved.get("model", "")}
