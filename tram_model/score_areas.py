"""E. 상권별 쇠퇴 위험 · 성장 가능 점수 (0~100, 20개 상권 안 순위 기반).

입력: area_types.csv (cluster_areas.py), area_panel.csv, forecast_land.csv (forecast_areas.py)
출력: outputs/area_scores.csv, outputs/area_scores.png

쇠퇴 위험 (높을수록 위험) — 아래 지표의 '나쁜 쪽' 백분위 평균
  점포 비중 10년 변화(↓), 최근 3년 변화(↓), 폐업률(↑), 지가 대전 대비 10년(↓), 지가 최근 4년(↓),
  2034 지가 예측(트램 없음, ↓)
성장 가능 (높을수록 유리) — '좋은 쪽' 백분위 평균
  트램 기본 효과(%, ↑), 개업률(↑), 점포 비중 최근 3년(↑)
  (예전의 '2034 지가 예측(트램 기본)'은 트램 효과를 두 번 세서 뺌)
※ 두 점수 모두 20개 상권 안 '상대' 순위 → 절대 수준이 아님 (앱에서 '상대 쇠퇴 위험'으로 표기)
네 칸 분류 (위험 50점 기준)
  위험 ≥ 50 : 상권 점포의 절반 이상이 정거장 500m 안(IN500_MIN)이면 '트램 반등 기회', 아니면 '쇠퇴 우려'
  위험 < 50 : 성장 ≥ 50 이면 '성장 지속', 아니면 '정체·안정'
진단 안정도: 지표 하나 빼기(9) · 위험/성장 기준 45·55(4) · 정거장 반경 400·600m(2) = 15가지로 다시 분류해
  같은 진단이 나온 비율. 80% 미만이면 '불확실'
도룡동은 점포 지표가 신세계 입점 등록으로 왜곡 → 점포 지표 빼고 나머지로 계산
가중치는 모두 같음. 지표 하나씩 빼도 순위가 유지되는지(스피어만 상관) 함께 출력
"""
import numpy as np
import pandas as pd

import config as C

RISK = {"store_g": -1, "store_recent": -1, "close_rate": 1, "land_rel_g10": -1, "land_recent": -1, "fc_base": -1}
GROW = {"tram_gain": 1, "open_rate": 1, "store_recent": 1}
LABEL = {"store_g": "점포 비중 10년", "store_recent": "점포 비중 최근 3년", "close_rate": "폐업률",
         "land_rel_g10": "지가 대전 대비 10년", "land_recent": "지가 최근 4년", "fc_base": "2034 지가 예측(트램 없음)",
         "fc_tram": "2034 지가 예측(트램 기본)", "tram_gain": "트램 기본 효과", "open_rate": "개업률"}
IN500_MIN = 0.5           # 상권 점포(격자)의 절반 이상이 정거장 500m 안 → 트램 효과가 의미 있게 닿는 상권
STABLE_MIN = 0.8          # 진단 안정도 80% 미만 = 불확실
ARTIFACT = {"A12": ["store_g", "store_recent", "open_rate", "close_rate"]}


def pct_score(X, spec):
    P = pd.DataFrame(index=X.index)
    for k, sign in spec.items():
        P[k] = (X[k] * sign).rank(pct=True) * 100
    return P


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

    T = pd.read_csv(C.OUT_DIR / "area_types.csv", encoding="utf-8-sig").set_index("code")
    F = pd.read_csv(C.OUT_DIR / "forecast_land.csv", encoding="utf-8-sig")
    end = F.year.max()
    f = F[F.year == end].set_index("code")
    X = T[["name", "type", "cluster", "type_name", "store_g", "store_recent", "close_rate", "open_rate",
           "land_rel_g10", "land_recent"]].copy()
    X["fc_base"] = f.base_path
    X["fc_tram"] = f.tram_base
    # 트램 지표 = 앱과 같은 % 하나 (scenario_tram_uplift 상권 평균, 개통 초기 1~4년, 땅값 기준 추정)
    U = pd.read_csv(C.OUT_DIR / "scenario_tram_uplift.csv", encoding="utf-8-sig").groupby("zone")
    eff = np.expm1(U[["eff_low", "eff_base", "eff_high"]].mean()) * 100
    X["tram_gain"] = eff.eff_base.reindex(X.index).fillna(0).round(2)
    rr = pd.read_csv(C.OUT_DIR / "robust_radius.csv", encoding="utf-8-sig").set_index("zone")
    X["in500"] = rr.in500.reindex(X.index).fillna(0)
    in_alt = {"반경 400m": rr.in400.reindex(X.index).fillna(0), "반경 600m": rr.in600.reindex(X.index).fillna(0)}
    for c, cols in ARTIFACT.items():
        X.loc[c, cols] = np.nan

    R = pct_score(X, RISK)
    G = pct_score(X, GROW)
    X["risk_score"] = R.mean(axis=1).round(1)
    X["growth_score"] = G.mean(axis=1).round(1)
    def classify(risk, grow, in500, rcut=50, gcut=50):
        hi_r, hi_g, tram = risk >= rcut, grow >= gcut, in500 >= IN500_MIN
        return pd.Series(np.select([hi_r & tram, hi_r & ~tram, ~hi_r & hi_g],
                                   ["트램 반등 기회", "쇠퇴 우려", "성장 지속"], "정체·안정"), index=risk.index)

    X["quadrant"] = classify(X.risk_score, X.growth_score, X.in500)
    # 진단 안정도: 15가지 변형에서 같은 진단이 나온 비율
    alts = []
    for k in R.columns:
        alts.append(classify(R.drop(columns=k).mean(axis=1), X.growth_score, X.in500))
    for k in G.columns:
        alts.append(classify(X.risk_score, G.drop(columns=k).mean(axis=1), X.in500))
    for c in (45, 55):
        alts.append(classify(X.risk_score, X.growth_score, X.in500, rcut=c))
        alts.append(classify(X.risk_score, X.growth_score, X.in500, gcut=c))
    for v in in_alt.values():
        alts.append(classify(X.risk_score, X.growth_score, v))
    A = pd.concat(alts, axis=1)
    X["quadrant_stability"] = A.eq(X.quadrant, axis=0).mean(axis=1).round(2)
    X["quadrant_alt"] = [", ".join(sorted(set(row) - {q})) for q, row in zip(X.quadrant, A.values)]
    X["quadrant_uncertain"] = X.quadrant_stability < STABLE_MIN
    # 주요 원인 (위험 점수에 가장 크게 기여한 지표 2개)
    X["risk_drivers"] = R.apply(lambda r: ", ".join(LABEL[k] for k in r.dropna().sort_values(ascending=False).index[:2]),
                                axis=1)
    X["growth_drivers"] = G.apply(lambda r: ", ".join(LABEL[k] for k in r.dropna().sort_values(ascending=False).index[:2]),
                                  axis=1)
    X["note"] = ["점포 지표 제외(신세계 입점 왜곡)" if c in ARTIFACT else "" for c in X.index]

    # 가중치 민감도: 지표 하나씩 뺐을 때 순위 상관
    sens = []
    for name, P, col in (("쇠퇴 위험", R, "risk_score"), ("성장 가능", G, "growth_score")):
        for k in P.columns:
            alt = P.drop(columns=k).mean(axis=1)
            sens.append({"score": name, "drop": LABEL[k], "spearman": round(alt.corr(X[col], method="spearman"), 3)})
    S = pd.DataFrame(sens)
    X.round(4).reset_index().to_csv(C.OUT_DIR / "area_scores.csv", index=False, encoding="utf-8-sig")
    S.to_csv(C.OUT_DIR / "area_scores_sensitivity.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 200)
    show = X.sort_values("risk_score", ascending=False)[["name", "type_name", "risk_score", "growth_score", "quadrant",
                                                         "risk_drivers"]]
    print(show.to_string())
    print("\n[가중치 민감도] 지표 하나 뺐을 때 순위 상관 최소:",
          S.groupby("score").spearman.min().to_dict())
    print("\n네 칸 분류:", X.groupby("quadrant").name.apply(lambda v: ", ".join(v)).to_dict())
    print("\n진단 안정도 (70% 미만 = 불확실):\n", X[["name", "quadrant", "quadrant_stability", "quadrant_alt"]]
          .sort_values("quadrant_stability").to_string())

    fig, ax = plt.subplots(figsize=(9, 7.5))
    for k, g in X.groupby("cluster"):
        ax.scatter(g.risk_score, g.growth_score, s=110, label=f"{k}. {g.type_name.iloc[0]}")
        for code, r in g.iterrows():
            ax.annotate(r["name"].split("(")[0], (r.risk_score, r.growth_score), fontsize=8, xytext=(4, 3),
                        textcoords="offset points")
    ax.axvline(50, c="gray", ls=":"); ax.axhline(50, c="gray", ls=":")
    for (x, y, t) in [(20, 95, "성장 지속"), (75, 95, "위험 높음: 절반 이상 500m 안이면 '반등 기회'"), (20, 5, "정체·안정")]:
        ax.text(x, y, t, fontsize=10, color="gray", ha="center")
    for code, r in X[X.quadrant == "트램 반등 기회"].iterrows():
        ax.scatter(r.risk_score, r.growth_score, s=260, facecolors="none", edgecolors="C3", lw=1.5)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xlabel("상대 쇠퇴 위험 점수 (20개 상권 안 순위) →"); ax.set_ylabel("상대 성장 가능 점수 →")
    ax.set_title("20개 상권 상대 쇠퇴 위험 × 상대 성장 가능 (빨간 원 = 트램 반등 기회)")
    ax.legend(fontsize=8, loc="center left")
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "area_scores.png", dpi=130)
    print("→ outputs/area_scores.csv, area_scores_sensitivity.csv, area_scores.png")


if __name__ == "__main__":
    main()
