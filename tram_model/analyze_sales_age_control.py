"""B7 (2차 점검): 8989 추정매출(신한카드 결제 보정)의 동 간 편향 점검 — 주민 연령 구성을 통제해도 '점포당 매출' 계수가 유지되나.

사전 분석 계획: docs/사전분석계획_2차점검_1103.md (B7)
입력: outputs/station_sales_dong.csv, outputs/8989/pop_breakdown.csv (주민 성·연령, 2026-01), outputs/8989/dong_code_map.csv
방법: analyze_station_sales '기본' 모형 + 주민 20~39세 비율, 60세 이상 비율 (카드사 점유율이 연령에 따라 다를 수 있음)
판정: 매출 계수가 기본 대비 부호가 바뀌거나 절댓값이 50% 넘게 바뀌면 ③ 문구에 '구성 통제에 민감' 추가
출력: outputs/station_sales_age_control.csv
"""
import numpy as np
import pandas as pd

import config as C


def ols_hc1(y, X):
    X = np.column_stack([np.ones(len(y))] + X); n, k = X.shape
    b = np.linalg.lstsq(X, y, rcond=None)[0]; e = y - X @ b
    XtXi = np.linalg.inv(X.T @ X); V = XtXi @ ((X * e[:, None] ** 2).T @ X) @ XtXi * n / (n - k)
    return b[1], np.sqrt(V[1, 1])


def main():
    D = pd.read_csv(C.OUT_DIR / "station_sales_dong.csv", encoding="utf-8-sig", index_col=0)
    D.index = D.index.astype(str)
    p = pd.read_csv(C.OUT_DIR / "8989" / "pop_breakdown.csv", dtype=str)
    p = p[(p.anal == "dongAnal") & (p["var"] == "resident") & (p.dim == "sex_age") & (p.baseYm == "202601")]
    p = p.drop_duplicates(["plcCd", "key"])
    p["value"] = p.value.astype(float)
    code = p.key.str.split("_").str[1]                       # 09 / 1019 / 2029 … / 100
    p["age"] = [100 if c == "100" else int(c[:len(c) // 2]) for c in code]
    tot = p.groupby("plcCd").value.sum()
    young = p[p.age.isin([20, 30])].groupby("plcCd").value.sum() / tot
    old = p[p.age >= 60].groupby("plcCd").value.sum() / tot
    cm = pd.read_csv(C.OUT_DIR / "8989" / "dong_code_map.csv", dtype=str).set_index("admdstCd").adm_cd2   # 8989 plcCd = admdstCd
    A = pd.DataFrame({"young": young, "old": old}); A.index = A.index.map(cm)
    D = D.join(A)
    D = D[D.n_stores >= 200]
    rows = []
    for g in ["전체", "음식", "소매(전문)"]:
        y = f"sps_{g}"
        d = D.dropna(subset=[y, "l1_500", "resident", "land", "young", "old"]); d = d[d[y] > 0]
        base = [d.l1_500.values, d.old_town.values, np.log(d.resident.values), np.log(d.n_stores.values), d.food_ratio.values]
        b0, s0 = ols_hc1(np.log(d[y].values), base)
        b1, s1 = ols_hc1(np.log(d[y].values), base + [d.young.values, d.old.values])
        bl0, _ = ols_hc1(np.log(d.land.values), base)
        bl1, _ = ols_hc1(np.log(d.land.values), base + [d.young.values, d.old.values])
        chg = (b1 - b0) / abs(b0) if b0 else np.nan
        rows.append(dict(group=g, n=len(d), sales_base_pct=round((np.exp(b0) - 1) * 100, 1),
                         sales_age_pct=round((np.exp(b1) - 1) * 100, 1),
                         sales_age_ci=f"{(np.exp(b1 - 1.96 * s1) - 1) * 100:.1f} ~ {(np.exp(b1 + 1.96 * s1) - 1) * 100:.1f}",
                         land_base_pct=round((np.exp(bl0) - 1) * 100, 1), land_age_pct=round((np.exp(bl1) - 1) * 100, 1),
                         ratio_age=round(b1 / bl1, 2), coef_change=round(chg, 2),
                         verdict=("구성 통제에 민감" if (np.sign(b1) != np.sign(b0) or abs(chg) > 0.5) else "유지")))
    R = pd.DataFrame(rows)
    R.to_csv(C.OUT_DIR / "station_sales_age_control.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(R.to_string(index=False))
    print("연령 자료 붙은 동:", D.young.notna().sum())


if __name__ == "__main__":
    main()
