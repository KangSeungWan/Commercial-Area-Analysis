"""트램 효과 기준 (한 곳에서 정의 → 시나리오·예측·점수·앱이 모두 이 값을 씀).

수준 (개통 초기 1~4년, 정거장 500m 안 땅값 기준 추정 효과)
- 낮음 : 해외 트램 하한 수준 = Lan 2025(영국 LRT) 버스 저밀 계수 0.89% (청두 트램 1.4%, 파리 T3 0% 와 비슷)
- 기본 : 대전 1호선 1·2단계 합산 (analyze_landprice → landprice_effects.csv)
- 높음 : 대전 1호선 1단계만 (같은 파일)
  ※ 개통 전 추세 보정값(+9.3~15.2%)은 추세 기간에 따라 크게 흔들려 시나리오에서 제외, 참고값으로만 보고

시간 경로: 대전 1호선 1단계 연차별 효과(landprice_line1_es.csv)를 개통 후 1~4년 평균 = 1 로 맞춘 모양.
          개통 1~4년 ≈ 1.0, 5년 0.6, 6년 0.35, 7년 0.2 → 효과는 개통 초기에 크고 점점 줄어듦.
업종 차이: Lan 2025 업종별 계수의 비율 (음식 0.99, 소매 0.86, 기타 0.24) — 유일하게 남은 외부 가정.
"""
import numpy as np
import pandas as pd

import config as C

SCEN = ("low", "base", "high")
LABEL = {"low": "낮음", "base": "기본", "high": "높음"}


def _effects():
    f = C.OUT_DIR / "landprice_effects.csv"
    return pd.read_csv(f, encoding="utf-8-sig") if f.exists() else None


def _lit():
    return pd.read_csv(C.LIT_PARAMS).set_index("param_id").value


def levels():
    """{scen: dict(log, pct, ci, source)} — log 단위 효과 수준."""
    E, lit = _effects(), _lit()

    def row(key, fallback_pct):
        if E is not None:
            r = E[E.analysis.str.contains(key, regex=False)]
            if len(r):
                return float(r.effect_pct.iloc[0]), str(r.ci95.iloc[0])
        return fallback_pct, ""

    pooled, pooled_ci = row("1·2단계 합산", 1.8)
    ph1, ph1_ci = row("1호선 1단계", 5.8)
    low = float(lit["P2_mod_bus_low"])
    out = {"low": dict(pct=round(np.expm1(low) * 100, 2), ci="", source="해외 트램 하한 수준 (영국 LRT 버스 저밀 계수, 청두 트램 1.4%·파리 T3 0%와 비슷)"),
           "base": dict(pct=pooled, ci=pooled_ci, source="대전 1호선 1·2단계 합산 (역 500m vs 1~3km, 개통 후 2008~2011)"),
           "high": dict(pct=ph1, ci=ph1_ci, source="대전 1호선 1단계만 (역 500m vs 1~3km, 개통 후 2007~2010)")}
    for v in out.values():
        v["log"] = float(np.log1p(max(v["pct"], 0) / 100))     # 음수 효과는 0 으로 (트램이 땅값을 낮춘다는 가정은 두지 않음)
    return out


def profile(years_after):
    """개통 후 연차별 효과 비율 (개통 후 1~4년 평균 = 1). 대전 1호선 1단계 실측 모양."""
    f = C.OUT_DIR / "landprice_line1_es.csv"
    y = np.asarray(years_after, float)
    if f.exists():
        es = pd.read_csv(f, encoding="utf-8-sig")
        es = es[es.phase == 1].set_index("year").coef
        k = es.index - 2006
        peak = es[(k >= 1) & (k <= 4)].mean()
        shape = pd.Series((es.values / peak).clip(0, None), index=k)
        shape = shape[shape.index >= 0]
    else:
        shape = pd.Series([0.45, 0.96, 1.06, 1.02, 0.97, 0.62, 0.35, 0.17], index=range(8))
    last = float(shape.iloc[-1])
    return np.array([0.0 if t < 0 else float(shape.get(int(t), last * 0.5 ** (t - shape.index.max()))) for t in y])


def cat_ratio(cat):
    """업종 비율 (Lan 2025 업종별 계수 / 부동산 계수)."""
    lit = _lit()
    key = {"I2": "P2_POI_eatdrink", "G2": "P2_POI_retail", "L1": "P2_POI_property"}.get(cat, "P2_POI_homeofficeleisure")
    return float(lit[key] / lit["P2_POI_property"])


def write_table():
    L = levels()
    rows = [{"scenario": s, "label": LABEL[s], "effect_pct": L[s]["pct"], "ci95": L[s]["ci"], "source": L[s]["source"]}
            for s in SCEN]
    T = pd.DataFrame(rows)
    T.to_csv(C.OUT_DIR / "tram_scenarios.csv", index=False, encoding="utf-8-sig")
    P = pd.DataFrame({"years_after_open": range(0, 9), "share_of_peak": profile(range(0, 9)).round(3)})
    P.to_csv(C.OUT_DIR / "tram_effect_profile.csv", index=False, encoding="utf-8-sig")
    return T, P


if __name__ == "__main__":
    T, P = write_table()
    print(T.to_string(index=False)); print(P.to_string(index=False))
