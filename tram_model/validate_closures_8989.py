"""진단 외부 검증 보강 (C13): 8989 폐업 점포 수(2025년 12개월)로 82개 동 위험 점수가 맞는 방향인지

입력: outputs/8989/closures_month.csv (dongAnal, 기준 2026-01 묶음의 2025-01~12 월별 폐업 수·점포 수, 79개 소분류),
      outputs/8989/dong_code_map.csv, outputs/dong_map_profile.csv (위험·성장 점수, 진단, 상가정보 폐업률)
출력: outputs/validation_closures_8989.csv (동별 폐업률), outputs/validation_closures_8989_summary.csv (상관·진단별 평균)
주의: 최근 달(2026-05~)은 폐업 신고가 늦게 잡혀 적음 → 완결된 2025년만 사용. 79개 업종 기준(사이트 전체 업종 아님).
      위험 점수에 상가정보 폐업률이 들어가 있으므로, 8989 폐업률과의 상관은 '다른 출처로도 같은 방향'인지 확인하는 용도.
"""
import numpy as np
import pandas as pd
import config as C

OUT = C.OUT_DIR


def main():
    f = OUT / "8989" / "closures_month.csv"
    if not f.exists():
        print("8989 폐업 자료 없음 → 건너뜀"); return
    c = pd.read_csv(f, dtype={"plcCd": str})
    c = c[(c.anal == "dongAnal") & (c.baseYm == 202601) & c.stdrYm.between(202501, 202512)]
    clos = c.groupby("plcCd").clsbizStorCo.sum()
    stores = c[c.stdrYm == 202512].groupby("plcCd").storCo_plc.sum()
    cm = pd.read_csv(OUT / "8989" / "dong_code_map.csv", dtype=str)
    key = "admdstCd"                                          # 8989 plcCd = 행정동 코드(8자리)
    cm = cm.set_index(key)
    D = pd.DataFrame({"closures_2025": clos, "stores_2025_12": stores}).dropna()
    D["close_rate_2025_pct"] = (D.closures_2025 / D.stores_2025_12.clip(lower=1) * 100).round(2)
    D["dong_id"] = D.index.map(cm.adm_cd2)
    P = pd.read_csv(OUT / "dong_map_profile.csv", encoding="utf-8-sig", dtype={"dong_id": str})
    keep = [c_ for c_ in ["dong_id", "name", "risk_score", "growth_score", "quadrant", "close_rate", "n_stores"] if c_ in P]
    M = D.merge(P[keep], on="dong_id", how="inner")
    M = M[M.stores_2025_12 >= 50]                                  # 점포가 아주 적은 동은 비율이 튐
    M.to_csv(OUT / "validation_closures_8989.csv", index=False, encoding="utf-8-sig")
    sp = lambda a, b: round(M[a].rank().corr(M[b].rank()), 3)
    n = len(M)
    def p_of(r):                                                  # 순위상관 근사 p (t 분포 → 정규 근사)
        t = r * np.sqrt((n - 2) / max(1e-9, 1 - r * r)); from math import erfc, sqrt
        return round(erfc(abs(t) / sqrt(2)), 4)
    rows = [dict(검사="위험 점수 ↔ 8989 폐업률(2025)", n=n, spearman=sp("risk_score", "close_rate_2025_pct")),
            dict(검사="성장 점수 ↔ 8989 폐업률(2025)", n=n, spearman=sp("growth_score", "close_rate_2025_pct"))]
    if "close_rate" in M:
        rows.append(dict(검사="상가정보 폐업률 ↔ 8989 폐업률 (출처 간 일치)", n=n, spearman=sp("close_rate", "close_rate_2025_pct")))
    for r in rows:
        r["p"] = p_of(r["spearman"])
    S = pd.DataFrame(rows)
    G = M.groupby("quadrant").close_rate_2025_pct.agg(["count", "median", "mean"]).round(2).reset_index()
    G.insert(0, "검사", "진단별 8989 폐업률(%)")
    out = pd.concat([S, G], ignore_index=True)
    out.to_csv(OUT / "validation_closures_8989_summary.csv", index=False, encoding="utf-8-sig")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
