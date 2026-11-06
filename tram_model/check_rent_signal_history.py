"""B3: 임대료 부담 신호(상권) ↔ 같은 지역의 지난 13년 실제 임대료 흐름(부동산원 R-ONE) 대조 (참고 수준, 지역 6~7곳).

입력: outputs/rent_long_vs_land.csv (build_rent_long.py), outputs/rent_pressure.csv (build_rent_pressure.py)
출력: outputs/rent_signal_history.csv  지역별 신호 점수·등급 vs 임대료 변화·땅값-임대료 격차, 마지막 줄에 순위상관

읽는 법
- 신호가 '앞으로 임대료가 오를 곳'을 뜻한다면 과거에도 신호 높은 곳의 임대료가 더 올랐어야 함(같은 방향).
- 반대로 나오면: 신호가 높은 곳은 땅값만 오르고 영업이 약해 임대료를 못 올린 곳 → 신호는 '임대료 상승 예측'이 아니라
  '땅값과 매출이 벌어진 곳'(건물주 기대와 상인 지불 능력의 간극)이며, 트램처럼 수요를 끌어오는 사건이 있을 때만 임대료로 옮겨 감.
"""
import numpy as np
import pandas as pd

import config as C


def spearman(a, b):
    a, b = pd.Series(a).rank(), pd.Series(b).rank()
    return float(np.corrcoef(a, b)[0, 1])


def perm_p(a, b, n=20000, seed=0):
    rng = np.random.default_rng(seed); r0 = abs(spearman(a, b)); b = np.asarray(b)
    hits = sum(abs(spearman(a, rng.permutation(b))) >= r0 - 1e-12 for _ in range(n))
    return (hits + 1) / (n + 1)


def main():
    L = pd.read_csv(C.OUT_DIR / "rent_long_vs_land.csv", encoding="utf-8-sig")
    R = pd.read_csv(C.OUT_DIR / "rent_pressure.csv", dtype={"key": str}, encoding="utf-8-sig")
    R = R[R.level == "상권"].set_index("key")
    rows = []
    for _, r in L[L.codes != "ALL"].iterrows():
        codes = [c for c in str(r.codes).split(",") if c in R.index and pd.notna(R.loc[c, "rent_pressure_score"])]
        if not codes:
            continue
        rows.append({"region": r.region, "areas": ", ".join(R.loc[codes, "name"]), "ptype": r.ptype,
                     "period": f"{r.start}~{r.end}", "signal_score": round(R.loc[codes, "rent_pressure_score"].mean(), 1),
                     "signal": " / ".join(R.loc[codes, "rent_pressure"].unique()),
                     "rent_chg_pct": r.rent_chg_pct, "land_chg_pct": r.land_chg_pct, "gap_pp": r.gap_pp})
    T = pd.DataFrame(rows)
    full = T[T.period.str.startswith(("2013", "2014"))]                 # 12~13년 이어진 지역만
    for lab, d in [("모든 지역", T), ("2013~14년부터 이어진 지역", full)]:
        if len(d) >= 4:
            T.loc[len(T)] = {"region": f"순위상관 ({lab}, n={len(d)})", "signal_score": np.nan,
                             "rent_chg_pct": round(spearman(d.signal_score, d.rent_chg_pct), 2),
                             "gap_pp": round(spearman(d.signal_score, d.gap_pp), 2),
                             "areas": f"p(임대료) {perm_p(d.signal_score, d.rent_chg_pct):.2f} · p(격차) {perm_p(d.signal_score, d.gap_pp):.2f}"}
    T.to_csv(C.OUT_DIR / "rent_signal_history.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(T.to_string(index=False))
    print("→ outputs/rent_signal_history.csv")


if __name__ == "__main__":
    main()
