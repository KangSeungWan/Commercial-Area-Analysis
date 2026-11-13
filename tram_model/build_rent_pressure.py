"""임대료 부담 위험 (상권 20 · 행정동 82): 트램으로 땅값은 오르는데 점포당 매출은 거의 안 오를 때, 기존 상인이 밀려날 위험의 상대 순위

입력: outputs/area_profile.csv, area_types.csv (상권), outputs/dong_map_profile.csv, dong_types.csv (동),
      outputs/station_sales_premium.csv (땅값 대비 매출 비율, 없으면 0.24), outputs/composition_forecast.csv
출력: outputs/rent_pressure.csv  (level, key, name, 세 요소, 점수 0~100, 등급)
세 요소 (같은 단위 안 백분위의 평균, 트램 효과가 있는 곳만 순위)
 ① 땅값-매출 격차 × 개인 점포 비율: 트램 상권 가치 효과(기본, %) × (1 − 매출 비율 0.24) × (1 − 체인 비율)
    → 오른 땅값 중 매출로 뒷받침되지 않는 몫을 개인 상인이 떠안는 정도
 ② 취약성: 폐업률(2017~2025 평균)
 ③ 업종 교체 압력: 2034 카페·빵집 비중 증가(%p, 기본)
등급: 트램 효과 0.1% 미만 = '해당 없음', 나머지에서 점수 상위 1/3 '높음', 중간 '보통', 하위 '낮음'
한계: 임대료 시계열이 없어 실제 임대료 상승이 아니라 '위험 순위'. 금액으로 쓰지 않음.
"""
import numpy as np
import pandas as pd

import config as C

OUT = C.OUT_DIR


def ratio():
    f = OUT / "station_sales_premium.csv"
    if f.exists():
        R = pd.read_csv(f, encoding="utf-8-sig"); r = R[R.model == "전체: 기본"]
        if len(r): return float(r.ratio_to_land.iloc[0])
    return 0.24


def score(D, rr):
    D = D.copy()
    D["gap_pct"] = (D.tram_effect * (1 - rr)).round(3)
    D["indep_share"] = (1 - D.branch_share).round(3)
    D["c1_land_gap_indep"] = (D.gap_pct * D.indep_share).round(3)
    exp = D.tram_effect >= 0.1
    for c in ("c1_land_gap_indep", "close_rate", "cafe_bakery_pp"):
        D[f"p_{c}"] = np.nan
        D.loc[exp, f"p_{c}"] = (D.loc[exp, c].rank(pct=True) * 100).round(1)
    D["rent_pressure_score"] = D[["p_c1_land_gap_indep", "p_close_rate", "p_cafe_bakery_pp"]].mean(axis=1).round(1)
    q1, q2 = D.loc[exp, "rent_pressure_score"].quantile([1 / 3, 2 / 3])
    D["rent_pressure"] = np.select([~exp, D.rent_pressure_score >= q2, D.rent_pressure_score >= q1], ["해당 없음", "높음", "보통"], "낮음")
    D["rent_drivers"] = D.apply(lambda r: ", ".join(lab for c, lab in (("p_c1_land_gap_indep", "땅값-매출 격차"), ("p_close_rate", "폐업률"), ("p_cafe_bakery_pp", "업종 교체"))
                                                    if pd.notna(r[c]) and r[c] >= 66) if pd.notna(r.rent_pressure_score) else "", axis=1)
    return D


def main():
    rr = ratio()
    F = pd.read_csv(OUT / "composition_forecast.csv", dtype={"key": str}, encoding="utf-8-sig")
    f34 = F[(F.scenario == "base") & (F.year == F.year.max())].set_index(["level", "key"]).cafe_bakery_pp
    A = pd.read_csv(OUT / "area_profile.csv", encoding="utf-8-sig")
    AT = pd.read_csv(OUT / "area_types.csv", encoding="utf-8-sig").set_index("code")
    A = A[["code", "name", "quadrant", "tram_effect", "branch_share"]].rename(columns={"code": "key"})
    A["close_rate"] = A.key.map(AT.close_rate); A["cafe_bakery_pp"] = [f34.get(("상권", k), np.nan) for k in A.key]
    A = score(A, rr); A.insert(0, "level", "상권")
    D = pd.read_csv(OUT / "dong_map_profile.csv", dtype={"dong_id": str}, encoding="utf-8-sig")
    D = D[["dong_id", "name", "quadrant", "tram_effect", "branch_share", "close_rate"]].rename(columns={"dong_id": "key"})
    D["cafe_bakery_pp"] = [f34.get(("행정동", k), np.nan) for k in D.key]
    D = score(D, rr); D.insert(0, "level", "행정동")
    R = pd.concat([A, D], ignore_index=True)
    R.to_csv(OUT / "rent_pressure.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print(f"매출 비율 {rr} (땅값 효과 중 매출로 이어지는 몫)")
    for lvl in ("상권", "행정동"):
        x = R[R.level == lvl]
        print(f"\n[{lvl}] 등급:", x.rent_pressure.value_counts().to_dict())
        print(x.sort_values("rent_pressure_score", ascending=False).head(8)[["name", "quadrant", "tram_effect", "gap_pct", "indep_share", "close_rate", "cafe_bakery_pp", "rent_pressure_score", "rent_pressure", "rent_drivers"]].round(3).to_string(index=False))
        reb = x[x.quadrant == "트램 반등 기회"]
        print("반등 기회:", ", ".join(f"{n}({p})" for n, p in zip(reb.name, reb.rent_pressure)))


if __name__ == "__main__":
    main()
