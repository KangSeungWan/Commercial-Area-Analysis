"""B2 (2차 점검): 땅값(자산가치)-임대료 '간극'이 나중 임대료 상승을 알려 주는가 — 전국 R-ONE 상권.

사전 분석 계획: docs/사전분석계획_2차점검_1103.md (B2)
입력: data/raw/rent_survey_long/rone_capital_vs_rent_regions.csv (중대형 상가, 창 2013Q1~2026Q2 와 2017Q1~2026Q2)
방법: 두 창이 모두 있는 상권에서 앞 시기(2013Q1→2017Q1)를 나눠 계산
      자산가치 앞 = (1+누적13)/(1+누적17) − 1, 임대료 앞 = (1+변화13)/(1+변화17) − 1
      간극 앞 = 자산가치 앞 − 임대료 앞  →  뒤 시기 임대료 변화(2017Q1→2026Q2)와 스피어만 순위상관, 순열 p(10,000회)
      보조: 간극 앞 → 뒤 시기 (임대료 − 자산가치) 변화(간극이 닫히는가)
출력: outputs/rent_gap_national_check.csv
한계: 자본수익률은 감정평가 기반(임대료를 일부 반영) → 간극이 작게 잡힐 수 있음. 시도 합계·'기타' 행 제외.
"""
import numpy as np
import pandas as pd

import config as C

RNG = np.random.default_rng(42)


def spearman_perm(x, y, n=10000):
    rx, ry = pd.Series(x).rank().values, pd.Series(y).rank().values
    r = np.corrcoef(rx, ry)[0, 1]
    null = np.array([np.corrcoef(rx, RNG.permutation(ry))[0, 1] for _ in range(n)])
    return r, (np.sum(np.abs(null) >= abs(r)) + 1) / (n + 1)


def main():
    d = pd.read_csv(C.RAW_DIR / "rent_survey_long" / "rone_capital_vs_rent_regions.csv", encoding="utf-8-sig")
    d = d[(d.sido != d.region) & (d.region != "기타")]
    a = d[d.window == "2013Q1-2026Q2"].set_index(["sido", "region"])
    b = d[d.window == "2017Q1-2026Q2"].set_index(["sido", "region"])
    m = a.join(b, lsuffix="_13", rsuffix="_17", how="inner")
    cap_early = ((1 + m.capital_cum_pct_13 / 100) / (1 + m.capital_cum_pct_17 / 100) - 1) * 100
    rent_early = ((1 + m.rent_idx_chg_pct_13 / 100) / (1 + m.rent_idx_chg_pct_17 / 100) - 1) * 100
    gap = cap_early - rent_early
    rent_late = m.rent_idx_chg_pct_17
    close_late = m.rent_idx_chg_pct_17 - m.capital_cum_pct_17
    r1, p1 = spearman_perm(gap, rent_late)
    r2, p2 = spearman_perm(gap, close_late)
    if r1 > 0 and p1 < 0.05:
        v = "ρ>0 유의 → 간극이 큰 곳은 뒤에 임대료가 더 오름 → ④를 '나중 임대료 상승 신호'로 되돌림"
    elif r1 < 0 and p1 < 0.05:
        v = "ρ<0 유의 → 대전 6곳과 같은 방향 → ④ 처방에서 상승 대비 수단 빼고 '모니터링'만"
    else:
        v = "유의하지 않음 → ④는 '간극 현황'으로만, 예측·위험이라는 말 쓰지 않음"
    hi, lo = gap >= gap.median(), gap < gap.median()
    R = pd.DataFrame([
        dict(test="간극(2013→17) vs 뒤 임대료 변화(2017→26)", n=len(m), spearman=round(r1, 3), perm_p=round(p1, 4),
             rent_late_gap_high=round(rent_late[hi].median(), 1), rent_late_gap_low=round(rent_late[lo].median(), 1), verdict=v),
        dict(test="간극(2013→17) vs 뒤 (임대료 − 자산가치)(2017→26) = 간극이 닫히는가", n=len(m), spearman=round(r2, 3),
             perm_p=round(p2, 4), verdict="")])
    R.to_csv(C.OUT_DIR / "rent_gap_national_check.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(R.to_string(index=False))
    print("앞 시기 간극 중앙값 %.1f%%p, 범위 %.1f~%.1f" % (gap.median(), gap.min(), gap.max()))


if __name__ == "__main__":
    main()
