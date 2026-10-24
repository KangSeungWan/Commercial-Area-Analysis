"""행정동 82개 쇠퇴 위험 · 성장 가능 점수 + 진단 4분류 (score_areas.py 의 행정동판)

입력: dong_types.csv, dong_year_panel.csv, dong_forecast_land.csv, dong_profile.csv, outputs/8989/dong_8989_summary.csv(있으면)
출력: outputs/dong_scores.csv, dong_scores_sensitivity.csv, dong_scores_validation.csv, dong_scores.png
지표·규칙은 상권과 같음(82개 안 백분위). 다른 점
- 트램 지표 = 정거장 500m 안 점포 비율 × 기본 시나리오 수준(%) (상권은 scenario_tram_uplift 평균)
- '트램 반등 기회' 조건 = 동 점포의 절반 이상이 500m 안 (IN500_MIN 0.5, 상권과 같음) → 해당 동 적음. 0.3 변형을 안정도에 포함
- 점포 200개 미만 동은 진단 뒤에 '(점포 적음)' 표시
- 외부 검증: 8989 카드매출 증감(2025→2026)·실태조사 어려움 응답률과 점수의 스피어만 상관
"""
import numpy as np
import pandas as pd

import config as C
import tram_effect as TE

RISK = {"store_g": -1, "store_recent": -1, "close_rate": 1, "land_rel_g10": -1, "land_recent": -1, "fc_base": -1}
GROW = {"tram_gain": 1, "open_rate": 1, "store_recent": 1}
LABEL = {"store_g": "점포 비중 10년", "store_recent": "점포 비중 최근 3년", "close_rate": "폐업률", "land_rel_g10": "지가 대전 대비 10년",
         "land_recent": "지가 최근 4년", "fc_base": "2034 지가 예측(트램 없음)", "tram_gain": "트램 기본 효과", "open_rate": "개업률"}
IN500_MIN, STABLE_MIN, SMALL = 0.5, 0.8, 200
ARTIFACT = {"3020055000": ["store_g", "store_recent", "open_rate", "close_rate"]}   # 신성동


def pct_score(X, spec):
    return pd.DataFrame({k: (X[k] * s).rank(pct=True) * 100 for k, s in spec.items()}, index=X.index)

def spearman(x, y):
    d = pd.DataFrame({"x": x, "y": y}).dropna(); n = len(d)
    if n < 5: return np.nan, np.nan, n
    r = d.x.rank().corr(d.y.rank()); from math import erf, sqrt
    t = r * np.sqrt((n - 2) / max(1e-9, 1 - r * r)); return round(r, 3), round(2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2)))), 4), n


def main():
    T = pd.read_csv(C.OUT_DIR / "dong_types.csv", dtype={"dong_id": str}, encoding="utf-8-sig").set_index("dong_id")
    F = pd.read_csv(C.OUT_DIR / "dong_forecast_land.csv", dtype={"code": str}, encoding="utf-8-sig")
    f = F[F.year == F.year.max()].set_index("code")
    X = T[["name", "si", "dong", "old_town", "n_stores", "small", "cluster", "type_name", "store_g", "store_recent", "close_rate", "open_rate", "land_rel_g10", "land_recent", "tram500_share", "sales_per_store", "sales_yoy"]].copy()
    X["fc_base"], X["fc_tram"] = f.base_path, f.tram_base
    base_pct = TE.levels()["base"]["pct"]
    X["tram_gain"] = (X.tram500_share.fillna(0) * base_pct).round(2)
    X["in500"] = X.tram500_share.fillna(0)
    for c, cols in ARTIFACT.items():
        if c in X.index: X.loc[c, cols] = np.nan
    R, G = pct_score(X, RISK), pct_score(X, GROW)
    X["risk_score"], X["growth_score"] = R.mean(axis=1).round(1), G.mean(axis=1).round(1)
    def classify(risk, grow, in500, rcut=50, gcut=50, imin=IN500_MIN):
        hi_r, hi_g, tram = risk >= rcut, grow >= gcut, in500 >= imin
        return pd.Series(np.select([hi_r & tram, hi_r & ~tram, ~hi_r & hi_g], ["트램 반등 기회", "쇠퇴 우려", "성장 지속"], "정체·안정"), index=risk.index)
    X["quadrant"] = classify(X.risk_score, X.growth_score, X.in500)
    alts = [classify(R.drop(columns=k).mean(axis=1), X.growth_score, X.in500) for k in R.columns]
    alts += [classify(X.risk_score, G.drop(columns=k).mean(axis=1), X.in500) for k in G.columns]
    for c in (45, 55):
        alts += [classify(X.risk_score, X.growth_score, X.in500, rcut=c), classify(X.risk_score, X.growth_score, X.in500, gcut=c)]
    alts += [classify(X.risk_score, X.growth_score, X.in500, imin=m) for m in (0.3, 0.7)]
    A = pd.concat(alts, axis=1)
    X["quadrant_stability"] = A.eq(X.quadrant, axis=0).mean(axis=1).round(2)
    X["quadrant_alt"] = [", ".join(sorted(set(row) - {q})) for q, row in zip(X.quadrant, A.values)]
    X["quadrant_uncertain"] = X.quadrant_stability < STABLE_MIN
    X["risk_drivers"] = R.apply(lambda r: ", ".join(LABEL[k] for k in r.dropna().sort_values(ascending=False).index[:2]), axis=1)
    X["growth_drivers"] = G.apply(lambda r: ", ".join(LABEL[k] for k in r.dropna().sort_values(ascending=False).index[:2]), axis=1)
    X["note"] = ["점포 지표 제외(신세계 입점 왜곡)" if c in ARTIFACT else ("점포 적음(200개 미만), 참고" if s else "") for c, s in zip(X.index, X.small)]
    sens = [{"score": nm, "drop": LABEL[k], "spearman": round(P.drop(columns=k).mean(axis=1).rank().corr(X[col].rank()), 3)}
            for nm, P, col in (("쇠퇴 위험", R, "risk_score"), ("성장 가능", G, "growth_score")) for k in P.columns]
    S = pd.DataFrame(sens)
    # 외부 검증
    V = []
    sv = pd.read_csv(C.OUT_DIR / "survey_dong.csv", dtype={"동코드": str}, encoding="utf-8-sig").set_index("동코드")
    X["survey_bad_pct"] = sv.bad_pct.reindex(X.index)
    for y, lab in [("sales_yoy", "8989 카드매출 증감 2025→2026(%)"), ("sales_per_store", "8989 점포당 카드매출 2026"), ("survey_bad_pct", "2021 실태조사 어려움 응답률(%)")]:
        for sc in ("risk_score", "growth_score"):
            r, p, n = spearman(X[sc], X[y]); V.append(dict(score=sc, against=lab, spearman=r, p_approx=p, n=n))
    V = pd.DataFrame(V)
    X.round(4).reset_index().to_csv(C.OUT_DIR / "dong_scores.csv", index=False, encoding="utf-8-sig")
    S.to_csv(C.OUT_DIR / "dong_scores_sensitivity.csv", index=False, encoding="utf-8-sig")
    V.to_csv(C.OUT_DIR / "dong_scores_validation.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print(X.sort_values("risk_score", ascending=False)[["name", "type_name", "n_stores", "risk_score", "growth_score", "quadrant", "in500", "sales_yoy"]].head(15).round(2).to_string())
    print("\n네 칸 분류 수:", X.quadrant.value_counts().to_dict())
    print("트램 반등 기회:", ", ".join(X[X.quadrant == "트램 반등 기회"].dong))
    print("불확실(안정도<0.8):", int(X.quadrant_uncertain.sum()), "개")
    print("[가중치 민감도] 최소 순위 상관:", S.groupby("score").spearman.min().to_dict())
    print("[외부 검증]\n", V.to_string(index=False))
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        from matplotlib import font_manager as fm
        for ff in fm.findSystemFonts():
            if any(k in ff for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
                fm.fontManager.addfont(ff); plt.rcParams["font.family"] = fm.FontProperties(fname=ff).get_name(); break
        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(figsize=(10, 8))
        for k, g in X.groupby("cluster"):
            ax.scatter(g.risk_score, g.growth_score, s=60, label=f"{k}. {g.type_name.iloc[0]}")
        for c, r in X[X.quadrant == "트램 반등 기회"].iterrows():
            ax.scatter(r.risk_score, r.growth_score, s=180, facecolors="none", edgecolors="C3", lw=1.5); ax.annotate(r.dong, (r.risk_score, r.growth_score), fontsize=8, xytext=(4, 3), textcoords="offset points")
        ax.axvline(50, c="gray", ls=":"); ax.axhline(50, c="gray", ls=":"); ax.set_xlim(0, 100); ax.set_ylim(0, 100)
        ax.set_xlabel("상대 쇠퇴 위험 (82개 동 안 순위)"); ax.set_ylabel("상대 성장 가능"); ax.legend(fontsize=8)
        plt.tight_layout(); plt.savefig(C.OUT_DIR / "dong_scores.png", dpi=130)
    except Exception as e:
        print("그림 생략:", e)
    return X


if __name__ == "__main__":
    main()
