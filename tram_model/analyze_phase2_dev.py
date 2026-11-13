"""B5 (2차 점검): 1호선 2단계 음수(−8.3%)의 원인 — 개발지(1996~2011 필지 1.5배 이상 법정동)를 빼면 평행 추세가 회복되는가.

사전 분석 계획: docs/사전분석계획_2차점검_1103.md (B5). 판정 규칙은 결과를 보기 전에 정함.
입력: outputs/landprice_parcels.csv.gz, landprice_long.pkl
출력: outputs/phase2_dev_check.csv (변형별 효과·사전 추세·판정), outputs/phase2_dev_es.csv (연도별)
"""
import numpy as np
import pandas as pd

import config as C
from analyze_landprice import event_study, pct, window_mean


def load():
    """analyze_landprice.load 와 같음. pyarrow 가 없어 pkl 을 못 읽으면 1990~2020 CSV 판(landprice_long_portable.py)을 씀."""
    G = pd.read_csv(C.OUT_DIR / "landprice_parcels.csv.gz", encoding="utf-8-sig")
    G = G[G.is_dae == 1]
    try:
        L = pd.read_pickle(C.OUT_DIR / "landprice_long.pkl")
    except Exception:
        L = pd.read_csv(C.OUT_DIR / "landprice_long_1990_2020.csv.gz")
    W = np.log(L[L.pnu.isin(G.pnu)].pivot(index="pnu", columns="year", values="price"))
    return G.set_index("pnu").loc[W.index], W

PG_MIN = 1.5
PRE_TOL = 3.0     # 사전 추세 허용 ±3%


def main():
    G, W = load()
    cnt = W.notna().groupby(G.dong_code.reindex(W.index).values).sum()
    def ratio(a, b):
        return (cnt[b] / cnt[a].replace(0, np.nan)).fillna(np.inf)
    dev_old = set(cnt.index[(ratio(1996, 2005) >= PG_MIN) | (ratio(2005, 2011) >= PG_MIN)])
    not_dev = ~G.dong_code.isin(dev_old)
    old_parcel = W[1996].notna().reindex(G.index)
    ctrl = (G.d_l1 > 1000) & (G.d_l1 <= 3000)
    p1 = (G.l1_phase == 1) & (G.d_l1 <= 500)
    p2 = (G.l1_phase == 2) & (G.d_l1 <= 500)
    yrs_all = list(range(1996, 2014))
    rows, es_rows = [], []
    variants = [("기본(전체)", None), ("개발지 법정동 제외", not_dev), ("1996년에 있던 필지만", old_parcel),
                ("개발지 제외 + 1996년 필지", not_dev & old_parcel)]
    for lab, keep in variants:
        for name, tr, post in [("2단계", p2, range(2008, 2012)), ("1단계", p1, range(2007, 2011)),
                               ("1·2단계 합산", p1 | p2, range(2008, 2012))]:
            t, c = (tr, ctrl) if keep is None else (tr & keep, ctrl & keep)
            es, boot, yrs = event_study(G, W, t, c, 2005, yrs_all)
            m, lo, hi = window_mean(es, boot, yrs, post)
            pm, plo, phi = window_mean(es, boot, yrs, range(2000, 2004))
            rows.append({"variant": lab, "phase": name, "post": f"{post[0]}-{post[-1]}", "effect_pct": pct(m),
                         "ci_lo": pct(lo), "ci_hi": pct(hi), "pre_2000_03_pct": pct(pm),
                         "pre_ci_lo": pct(plo), "pre_ci_hi": pct(phi),
                         "n_treat": int(es.n_treat.max()), "n_ctrl": int(es.n_ctrl.max())})
            e = es.copy(); e["variant"] = lab; e["phase"] = name; es_rows.append(e)
    R = pd.DataFrame(rows)
    # 판정 (사전 계획 B5)
    k = R[(R.variant == "개발지 법정동 제외") & (R.phase == "2단계")].iloc[0]
    if abs(k.pre_2000_03_pct) <= PRE_TOL:
        comb = R[(R.variant == "개발지 법정동 제외") & (R.phase == "1·2단계 합산")].iloc[0]
        verdict = (f"R1/R2: 개발지 제외 2단계 사전 추세 {k.pre_2000_03_pct:+.1f}% (±{PRE_TOL:.0f}% 안) → 해석 가능. "
                   f"새 기본값 = 개발지 제외 1·2단계 합산 {comb.effect_pct:+.1f}% [{comb.ci_lo}, {comb.ci_hi}]")
    else:
        verdict = (f"R3: 개발지 제외 2단계 사전 추세 {k.pre_2000_03_pct:+.1f}% (±{PRE_TOL:.0f}% 밖) → 평행 추세 실패, "
                   f"2단계 해석 불가. 기본값 +1.8% 유지")
    R["verdict"] = ""
    R.loc[0, "verdict"] = verdict
    R.to_csv(C.OUT_DIR / "phase2_dev_check.csv", index=False, encoding="utf-8-sig")
    pd.concat(es_rows).round(4).to_csv(C.OUT_DIR / "phase2_dev_es.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(R.drop(columns="verdict").to_string(index=False))
    print("\n개발지 법정동:", len(dev_old), "\n판정:", verdict)


if __name__ == "__main__":
    main()
