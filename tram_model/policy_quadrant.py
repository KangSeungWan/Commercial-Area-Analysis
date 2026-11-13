"""정책 진단 4칸 (B2G 담당자용) — 판정 규칙: docs/사전분석계획_분류변경_1112.md (2026-11-12, 결과 보기 전 확정)

두 축
  가로 '지금 위험' : 위험 점수 ≥ 50 그리고 절대 쇠퇴 신호 '있음'·'강함' → 높음 (그 밖, '판단 안 함' 포함 → 낮음)
  세로 '업종 변화' : 2034 기본 시나리오 전체 점포 중 카페·빵 비중 증가(%p, build_composition.py cafe_bakery_pp)
                     ≥ 대상 안 가운데값 → 큼
대상: 상권 = tram_group '트램 근접'(build_areas.py), 행정동 = 점포 10% 이상이 정거장 500m 안(tram500_share ≥ 0.1)
      그 밖 = '비교 지역'(분류 안 함)
네 칸: 먼저 지원(위험↑·변화↑) · 기존 지원 연계(위험↑·변화↓) · 변화 관찰(위험↓·변화↑) · 정기 점검(위험↓·변화↓)
안정도: 위험 지표 하나씩 빼기(6) · 위험 선 45/55(2) · 업종 값 낮음/높음 시나리오(2) = 10가지, 같은 칸 비율 < 0.8 → 불확실
'트램 없을 때'(앱·웹의 건설 전 보기): 업종 변화가 없으므로 위험 높음 → 기존 지원 연계, 낮음 → 정기 점검
"""
import numpy as np
import pandas as pd

import config as C

FIRST, LINK, WATCH, ROUTINE, OUTSIDE = "먼저 지원", "기존 지원 연계", "변화 관찰", "정기 점검", "비교 지역"
NAMES = [FIRST, LINK, WATCH, ROUTINE]
ALL = NAMES + [OUTSIDE]
CHANGE_BIG = (FIRST, WATCH)          # 업종 변화 큰 칸 (예전 '반등 기회 5곳' 자리에 쓰는 묶음)
DESC = {FIRST: "지금도 어렵고 트램으로 업종이 크게 바뀔 곳 → 공사 중·개통 초 지원 우선",
        LINK: "어려움은 트램보다 원래 있던 쇠퇴 때문 → 기존 소상공인 정책과 연결",
        WATCH: "지금은 괜찮지만 업종이 크게 바뀔 곳 → 업종 변화 지켜보기",
        ROUTINE: "변화가 적은 곳 → 분기 갱신 때 다시 보기",
        OUTSIDE: "트램 노선 밖 — 분류하지 않음(비교용)"}
NOTE = "대전 안 비교와 1호선 실측을 바탕으로 한 정책 우선순위입니다. 매출·투자 전망이 아닙니다."
RGB = {FIRST: [200, 50, 50], LINK: [235, 130, 20], WATCH: [42, 111, 151], ROUTINE: [110, 160, 120], OUTSIDE: [190, 190, 190]}
HEX = {k: "#%02x%02x%02x" % tuple(v) for k, v in RGB.items()}
TXT = {FIRST: "#ffffff", LINK: "#0a1d08", WATCH: "#ffffff", ROUTINE: "#0a1d08", OUTSIDE: "#0a1d08"}
RCUT, DONG_TARGET_MIN, STABLE_MIN = 50, 0.1, 0.8
HI_SIGNAL = ("있음", "강함")


def load_change(level):
    """level '상권' | '행정동' → DataFrame(index=key, columns low/base/high) 2034(마지막 해) 카페·빵 비중 증가 %p"""
    f = C.OUT_DIR / "composition_forecast.csv"
    F = pd.read_csv(f, dtype={"key": str}, encoding="utf-8-sig")
    F = F[(F.level == level) & (F.year == F.year.max())]
    return F.pivot_table(index="key", columns="scenario", values="cafe_bakery_pp", aggfunc="first")


def risk_high(risk, abs_decline, rcut=RCUT):
    return (risk >= rcut) & abs_decline.isin(HI_SIGNAL)


def classify(risk, abs_decline, change, target, rcut=RCUT):
    """risk·abs_decline·change·target: 같은 index 의 Series. 가운데값은 대상 안에서 계산."""
    ch = change.fillna(0.0)
    med = float(ch[target].median()) if target.any() else 0.0
    hi_r, big = risk_high(risk, abs_decline, rcut), ch >= med
    q = pd.Series(np.select([hi_r & big, hi_r & ~big, ~hi_r & big], [FIRST, LINK, WATCH], ROUTINE), index=risk.index)
    return q.where(target, OUTSIDE)


def without_tram(risk, abs_decline, target, rcut=RCUT):
    hi_r = risk_high(risk, abs_decline, rcut)
    return pd.Series(np.where(hi_r, LINK, ROUTINE), index=risk.index).where(target, OUTSIDE)


def stability(R, abs_decline, CH, target):
    """R: 위험 지표 백분위 DataFrame(행 = 단위), CH: low/base/high 업종 변화. 반환: (quadrant, stability, alt, uncertain, median)"""
    risk = R.mean(axis=1).round(1)
    base = classify(risk, abs_decline, CH["base"], target)
    alts = [classify(R.drop(columns=k).mean(axis=1).round(1), abs_decline, CH["base"], target) for k in R.columns]
    alts += [classify(risk, abs_decline, CH["base"], target, rcut=c) for c in (45, 55)]
    alts += [classify(risk, abs_decline, CH[s], target) for s in ("low", "high") if s in CH]
    A = pd.concat(alts, axis=1)
    stab = A.eq(base, axis=0).mean(axis=1).round(2)
    alt = [", ".join(sorted(set(row) - {q})) for q, row in zip(base, A.values)]
    med = float(CH["base"].fillna(0)[target].median()) if target.any() else 0.0
    return base, stab, alt, stab < STABLE_MIN, round(med, 3)


def rule_text(q, risk, abs_decline, change, median, after=True):
    """앱·웹 카드의 '왜 이 칸인가' 한 줄"""
    if q == OUTSIDE:
        return "트램 노선 밖이라 분류하지 않음(비교 지역)"
    nz = lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else v
    risk, change, median = nz(risk), nz(change), nz(median) or 0.0
    abs_decline = abs_decline if isinstance(abs_decline, str) else "판단 안 함"
    if risk is None:
        return "위험 점수 없음"
    hi = (risk is not None and risk >= RCUT) and abs_decline in HI_SIGNAL
    r = (f"위험 {risk:.0f}점 + 절대 쇠퇴 신호 '{abs_decline}' → 지금 위험 높음" if hi else
         f"위험 {risk:.0f}점, 절대 쇠퇴 신호 '{abs_decline}' → 지금 위험 낮음(높음 = 50점 이상 + 신호 있음)")
    if not after:
        return r + " · 트램이 없으면 업종 변화 없음"
    c = (f"카페·빵 비중 +{change:.2f}%p ≥ 가운데값 {median:.2f} → 업종 변화 큼" if change is not None and change >= median else
         f"카페·빵 비중 +{(change or 0):.2f}%p < 가운데값 {median:.2f} → 업종 변화 작음")
    return f"{r} · {c}"
