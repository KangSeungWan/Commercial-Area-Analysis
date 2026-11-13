"""B6 (2차 점검): 카페 '+272곳'을 기준선(트램 없을 때의 추세) 위에 놓기.

입력: outputs/cafe_saturation_city.csv (인허가 기준 대전 카페 수·연 순증가율), outputs/composition_forecast.csv (상가정보 기준, 트램 몫)
방법: 2026 대전 카페 수(상가정보, composition_forecast 의 2026 값)에 두 가지 추세를 2034년까지 적용
      ① 최근 3년(2023~2025) 연평균 순증가율  ② 최근 7년(2019~2025) 연평균
      트램 몫(add_카페, 낮음·기본·높음)은 그 위에 더함 (트램 몫은 '트램 없을 때보다' 많은 수)
출력: outputs/cafe_baseline.csv (기준선 × 시나리오 × 연도: 트램 없음, 트램 있음, 2026 대비)
"""
import pandas as pd
import config as C


def main():
    city = pd.read_csv(C.OUT_DIR / "cafe_saturation_city.csv")
    g3 = city[city.year.between(2023, 2025)].net_growth_pct.mean() / 100
    g7 = city[city.year.between(2019, 2025)].net_growth_pct.mean() / 100
    F = pd.read_csv(C.OUT_DIR / "composition_forecast.csv")
    F = F[F.level == "대전"]
    n0 = float(F[(F.scenario == "base") & (F.year == 2026)]["n_카페"].iloc[0])
    rows = []
    for bl, g in [("최근 3년 추세(2023~25)", g3), ("최근 7년 평균(2019~25)", g7)]:
        for sc in ["low", "base", "high"]:
            for y in [2026, 2030, 2034]:
                base = n0 * (1 + g) ** (y - 2026)
                add = float(F[(F.scenario == sc) & (F.year == y)]["add_카페"].iloc[0])
                rows.append(dict(baseline=bl, growth_pct=round(g * 100, 2), scenario=sc, year=y, no_tram=round(base),
                                 tram_add=round(add), with_tram=round(base + add), vs_2026_with_tram=round(base + add - n0)))
    R = pd.DataFrame(rows)
    R.to_csv(C.OUT_DIR / "cafe_baseline.csv", index=False, encoding="utf-8-sig")
    print("2026 카페(상가정보):", n0)
    print(R[R.year == 2034].to_string(index=False))


if __name__ == "__main__":
    main()
