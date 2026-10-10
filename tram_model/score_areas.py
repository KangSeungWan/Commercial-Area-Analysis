"""E. 상권별 쇠퇴 위험 · 성장 가능 점수 (0~100, 20개 상권 안 순위 기반).

입력: area_types.csv (cluster_areas.py), area_panel.csv, forecast_land.csv (forecast_areas.py)
출력: outputs/area_scores.csv, outputs/area_scores.png

쇠퇴 위험 (높을수록 위험) — 아래 지표의 '나쁜 쪽' 백분위 평균
  점포 비중 10년 변화(↓), 최근 3년 변화(↓), 폐업률(↑), 지가 대전 대비 10년(↓), 지가 최근 4년(↓),
  2034 지가 예측(트램 없음, ↓)
성장 가능 (높을수록 유리) — '좋은 쪽' 백분위 평균
  2034 지가 예측(트램 기본, ↑), 트램 기본 효과(↑), 개업률(↑), 점포 비중 최근 3년(↑)
네 칸 분류 (위험 50점 기준)
  위험 ≥ 50 : 트램 기본 효과가 TRAM_GAIN_MIN 이상이면 '트램 반등 기회', 아니면 '쇠퇴 우려'
  위험 < 50 : 성장 ≥ 50 이면 '성장 지속', 아니면 '정체·안정'
도룡동은 점포 지표가 신세계 입점 등록으로 왜곡 → 점포 지표 빼고 나머지로 계산
가중치는 모두 같음. 지표 하나씩 빼도 순위가 유지되는지(스피어만 상관) 함께 출력
"""
import numpy as np
import pandas as pd

import config as C

RISK = {"store_g": -1, "store_recent": -1, "close_rate": 1, "land_rel_g10": -1, "land_recent": -1, "fc_base": -1}
GROW = {"fc_tram": 1, "tram_gain": 1, "open_rate": 1, "store_recent": 1}
LABEL = {"store_g": "점포 비중 10년", "store_recent": "점포 비중 최근 3년", "close_rate": "폐업률",
         "land_rel_g10": "지가 대전 대비 10년", "land_recent": "지가 최근 4년", "fc_base": "2034 지가 예측(트램 없음)",
         "fc_tram": "2034 지가 예측(트램 기본)", "tram_gain": "트램 기본 효과", "open_rate": "개업률"}
TRAM_GAIN_MIN = 3.0       # 2034 지가 지수 기준 트램 기본 효과(포인트)
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
    X["tram_gain"] = f.tram_gain_base_pct
    for c, cols in ARTIFACT.items():
        X.loc[c, cols] = np.nan

    R = pct_score(X, RISK)
    G = pct_score(X, GROW)
    X["risk_score"] = R.mean(axis=1).round(1)
    X["growth_score"] = G.mean(axis=1).round(1)
    hi_r, hi_g = X.risk_score >= 50, X.growth_score >= 50
    tram = X.tram_gain >= TRAM_GAIN_MIN
    X["quadrant"] = np.select([hi_r & tram, hi_r & ~tram, ~hi_r & hi_g], ["트램 반등 기회", "쇠퇴 우려", "성장 지속"],
                              "정체·안정")
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

    fig, ax = plt.subplots(figsize=(9, 7.5))
    for k, g in X.groupby("cluster"):
        ax.scatter(g.risk_score, g.growth_score, s=110, label=f"{k}. {g.type_name.iloc[0]}")
        for code, r in g.iterrows():
            ax.annotate(r["name"].split("(")[0], (r.risk_score, r.growth_score), fontsize=8, xytext=(4, 3),
                        textcoords="offset points")
    ax.axvline(50, c="gray", ls=":"); ax.axhline(50, c="gray", ls=":")
    for (x, y, t) in [(20, 95, "성장 지속"), (75, 95, "위험 높음: 트램 효과 크면 '반등 기회'"), (20, 5, "정체·안정")]:
        ax.text(x, y, t, fontsize=10, color="gray", ha="center")
    for code, r in X[X.quadrant == "트램 반등 기회"].iterrows():
        ax.scatter(r.risk_score, r.growth_score, s=260, facecolors="none", edgecolors="C3", lw=1.5)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xlabel("쇠퇴 위험 점수 →"); ax.set_ylabel("성장 가능 점수 →")
    ax.set_title(f"20개 상권 쇠퇴 위험 × 성장 가능 (빨간 원 = 트램 반등 기회, {end}년 기준)")
    ax.legend(fontsize=8, loc="center left")
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "area_scores.png", dpi=130)
    print("→ outputs/area_scores.csv, area_scores_sensitivity.csv, area_scores.png")


if __name__ == "__main__":
    main()
