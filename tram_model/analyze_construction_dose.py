"""B3 (2차 점검): 공사 피해의 '용량-반응' — 공사 구간 정거장에 가까울수록, 공사가 길어질수록 매출이 더 줄었나.

사전 분석 계획: docs/사전분석계획_2차점검_1103.md (B3)
왜: 비교군(외곽 골목상권)을 바꾸면 평균 효과가 사라짐 → 비교군 선택에 덜 민감한 '처리 강도별 비교'로 다시 본다.
입력: analyze_construction_trdar.py 와 같음 (8989 골목상권 월 매출 2024-01~2026-08, 공사 구간 표, 정거장 좌표)
방법: 처리 강도 = 공사 구간 정거장까지 거리 띠(0~150 / 150~300 / 300~500m) × 공사 중
      그리고 공사 경과 개월 띠(0~5 / 6~11 / 12개월 이상). 비교 = 모든 트램 정거장에서 1km 넘게 떨어진 골목상권.
      log(월 매출) ~ 골목상권 FE + 월 FE + Σ 띠 더미, 골목상권 군집 표준오차
출력: outputs/construction_dose.csv
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_construction_trdar as T
import analyze_line1_permits as AP
import config as C

BANDS = [(0, 150), (150, 300), (300, 500)]
DUR = [(0, 5), (6, 11), (12, 99)]


def build():
    M = pd.read_csv(T.O8 / "sales_month.csv", dtype={"code": str, "sclasCd": str})
    M = M[(M.anal == "trdarAnal") & (M.level == "trdar")]
    P = M.groupby(["code", "stdrYm"]).useAmount.sum().rename("all").reset_index()
    S = pd.read_csv(T.O8 / "trdar_summary.csv", dtype={"trdarNo": str}).set_index("trdarNo")
    cen = T.centroids()
    keep = []
    for k, g in S.groupby(S.dup_group.fillna(-1)):
        keep += list(g.index) if k == -1 else [g.index[0]]
    cen = cen[cen.index.isin(keep) & (cen.type != "축제")]
    TR = pd.read_csv(C.ROOT / "data" / "tram_stations.csv", encoding="utf-8-sig"); st = TR.set_index("station_no")
    dmin = np.full(len(cen), np.inf)
    for r in TR.itertuples():
        dmin = np.minimum(dmin, T.hav(cen.lat.values, cen.lon.values, r.lat, r.lon))
    cen["d_tram"] = dmin
    SEC = pd.read_csv(C.ROOT / "data" / "construction_sections.csv", encoding="utf-8-sig", dtype=str)
    cen["start"] = np.nan; cen["end"] = np.nan; cen["d_con"] = np.inf
    for r in SEC.sort_values("start_ym").itertuples():
        ids = [int(x) for x in str(r.stations).split(";") if x.strip()]
        dd = np.full(len(cen), np.inf)
        for i in ids:
            if i in st.index:
                dd = np.minimum(dd, T.hav(cen.lat.values, cen.lon.values, st.loc[i, "lat"], st.loc[i, "lon"]))
        m = (dd <= BANDS[-1][1]) & cen.start.isna().values
        cen.loc[m, "start"] = int(r.start_ym)
        cen.loc[m, "end"] = int(r.end_ym) if str(r.end_ym) not in ("", "nan") else 999912
        cen.loc[m, "d_con"] = dd[m]
    cen["treat"] = cen.start.notna().astype(int)
    cen = cen[(cen.treat == 1) | (cen.d_tram > T.CTRL_M)]
    P = P[P.code.isin(cen.index)].merge(cen[["name", "treat", "start", "end", "d_con"]], left_on="code", right_index=True)
    P = P.rename(columns={"code": "cell", "stdrYm": "year"})
    P = P[P["all"] > 0].assign(ly=lambda x: np.log(x["all"]))
    full = P.groupby("cell").year.nunique(); P = P[P.cell.isin(full[full == full.max()].index)].copy()
    P["during"] = ((P.year >= P.start) & (P.year <= P.end)).astype(int) * P.treat
    months = sorted(P.year.unique()); idx = {m: i for i, m in enumerate(months)}
    P["elapsed"] = np.where(P.during == 1, P.year.map(idx) - P.start.map(lambda s: idx.get(int(s), np.nan) if pd.notna(s) else np.nan), np.nan)
    return P


def fit(P, cols, labels, kind):
    b, se, G = AP.twfe(P, "ly", cols)
    rows = []
    for c, lab, bb, ss in zip(cols, labels, b, se):
        rows.append(dict(kind=kind, band=lab, effect_pct=round(AP.pct(bb), 2), lo=round(AP.pct(bb - 1.96 * ss), 2),
                         hi=round(AP.pct(bb + 1.96 * ss), 2), p=round(AP._pval(bb / ss), 4),
                         n_cells=int(P[P[c] > 0].cell.nunique()), clusters=G))
    return rows


def main():
    P = build()
    rows = []
    cols, labs = [], []
    for a, b in BANDS:
        c = f"b{a}"; P[c] = ((P.during == 1) & (P.d_con > a) & (P.d_con <= b)).astype(float) if a else ((P.during == 1) & (P.d_con <= b)).astype(float)
        cols.append(c); labs.append(f"{a}~{b}m")
    rows += fit(P, cols, labs, "거리 띠")
    cols, labs = [], []
    for a, b in DUR:
        c = f"e{a}"; P[c] = ((P.during == 1) & (P.elapsed >= a) & (P.elapsed <= b)).astype(float)
        cols.append(c); labs.append(f"공사 {a}~{b if b < 99 else ''}개월".replace("~개월", "개월 이상"))
    rows += fit(P, cols, labs, "공사 경과")
    R = pd.DataFrame(rows)
    d = R[R.kind == "거리 띠"].reset_index(drop=True)
    e = R[R.kind == "공사 경과"].reset_index(drop=True)
    near_ok = (d.effect_pct.idxmin() == 0) and (d.hi.iloc[0] < 0)
    mono_d = d.effect_pct.is_monotonic_increasing
    mono_e = e.effect_pct.is_monotonic_decreasing
    v = ("공사 피해 방향 확인 (가까운 띠가 가장 크고 0을 넘지 않음, 거리·기간 모두 단조)" if near_ok and mono_d and mono_e else
         f"'동 평균 손실 확인 안 됨' 유지 (가장 가까운 띠 최대·유의={near_ok}, 거리 단조={mono_d}, 기간 단조={mono_e})")
    R["verdict"] = ""; R.loc[0, "verdict"] = v
    R.to_csv(C.OUT_DIR / "construction_dose.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(R.drop(columns="verdict").to_string(index=False)); print("판정:", v)


if __name__ == "__main__":
    main()
