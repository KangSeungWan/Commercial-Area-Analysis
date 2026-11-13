"""B1 (2차 점검): '점포당 매출 효과 ÷ 땅값 효과 = 0.24배'의 불확실성 — 행정동 부트스트랩.

사전 분석 계획: docs/사전분석계획_2차점검_1103.md (B1)
입력: outputs/station_sales_dong.csv (analyze_station_sales.py 출력)
방법: analyze_station_sales 의 '기본' 모형(OLS, 1호선 500m 비율 + 원도심·log 인구·log 점포 수·음식점 비율)을
      같은 동 표본에서 매출(log 점포당 월 카드매출)과 땅값(log 공시지가 중앙값)에 각각 적합.
      동을 복원 추출 2,000회 → 비율 b_S/b_L 과 차이 b_L − b_S(로그 차이)의 2.5~97.5% 구간.
출력: outputs/station_sales_ratio_ci.csv
"""
import numpy as np
import pandas as pd

import config as C

RNG = np.random.default_rng(42)
N_BOOT = 2000


def coef(y, d, treat="l1_500"):
    X = np.column_stack([np.ones(len(d)), d[treat], d.old_town, np.log(d.resident), np.log(d.n_stores), d.food_ratio])
    return np.linalg.lstsq(X, y, rcond=None)[0][1]


def main():
    D = pd.read_csv(C.OUT_DIR / "station_sales_dong.csv", encoding="utf-8-sig", index_col=0)
    D = D[D.n_stores >= 200]
    rows = []
    for g in ["전체", "음식", "소매(전문)"]:
        y = f"sps_{g}"
        d = D.dropna(subset=[y, "l1_500", "resident", "land", "old_town", "food_ratio"])
        d = d[(d[y] > 0) & (d.land > 0)]
        yS, yL = np.log(d[y].values), np.log(d.land.values)
        bS, bL = coef(yS, d), coef(yL, d)
        bs, bl = [], []
        n = len(d)
        for _ in range(N_BOOT):
            i = RNG.integers(0, n, n)
            di = d.iloc[i]
            if di.l1_500.std() == 0:
                continue
            bs.append(coef(yS[i], di)); bl.append(coef(yL[i], di))
        bs, bl = np.array(bs), np.array(bl)
        ratio = bs / bl
        diff = bl - bs
        q = lambda v: np.nanpercentile(v, [2.5, 97.5])
        rows.append(dict(group=g, n=n, sales_pct=round((np.exp(bS) - 1) * 100, 1), land_pct=round((np.exp(bL) - 1) * 100, 1),
                         ratio=round(bS / bL, 2), ratio_lo=round(q(ratio)[0], 2), ratio_hi=round(q(ratio)[1], 2),
                         share_land_le0=round((bl <= 0).mean(), 3),
                         diff_logpt=round(bL - bS, 3), diff_lo=round(q(diff)[0], 3), diff_hi=round(q(diff)[1], 3),
                         diff_gt0_share=round((diff > 0).mean(), 3)))
    R = pd.DataFrame(rows)
    k = R[R.group == "전체"].iloc[0]
    R["verdict"] = ""
    R.loc[R.group == "전체", "verdict"] = (
        "차이 구간이 0보다 위 → '땅값 차이가 매출 차이보다 크다' 유지, ③ 등급 '방향만'" if k.diff_lo > 0 else
        "차이 구간이 0 포함 → '땅값과 매출의 차이도 확인되지 않았다', ③ 등급 '확인 안 됨'")
    R.to_csv(C.OUT_DIR / "station_sales_ratio_ci.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(R.to_string(index=False))


if __name__ == "__main__":
    main()
