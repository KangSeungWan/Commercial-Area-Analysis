"""임대료 장기 흐름(한국부동산원 R-ONE, 2013~2026) vs 같은 기간 땅값(공시지가) — 근거 팝업 표

입력: data/raw/rent_survey_long/rone_rent_index_long.csv  (지역별 임대가격지수(시계열), 2024Q2=100, 중대형 2013~·집합 2014~·소규모 2015~)
      outputs/landprice_area_panel.csv (상권별 공시지가 지수, 1월 1일 기준)
      build_rent_survey.MATCH (부동산원 지역 → 핵심 상권), outputs/area_profile.csv (진단), outputs/rent_pressure.csv (임대료 부담 등급)
출력: outputs/rent_long_vs_land.csv, outputs/rent_capital_passthrough.csv(전국 상권 자산가치 → 임대료 전가), outputs/landprice_vs_rone.csv(공시지가 vs 시장 지가지수)
      region, codes, areas, ptype(중대형 우선), start, end, rent_chg_pct(임대가격지수 시작 1분기 → 2026 최신 분기),
      rent_peak(최고 시점), land_chg_pct(같은 연도 1월 1일 → 2026 1월 1일, 대응 상권 평균), gap_pp(땅값 − 임대료),
      rent_chg_중대형/소규모/집합, quadrant, rent_pressure
읽는 법: 땅값이 크게 올라도 임대료는 내려간 곳이 대부분 → 땅값 상승이 곧바로 임대료로 옮겨 가지 않았음(공실·수요 약세).
         트램 뒤 임대료 부담은 '지금 당장'이 아니라 '공실이 해소되고 땅값이 오른 다음'의 위험이라는 근거.
한계: 부동산원 상권 경계 ≠ 분석 상권(이름으로 대응), 임대가격지수는 표본 건물 임대료의 변동률 지수(금액 아님)
"""
import numpy as np
import pandas as pd

import config as C
from build_rent_survey import MATCH

SRC = C.RAW_DIR / "rent_survey_long" / "rone_rent_index_long.csv"
OUT = C.OUT_DIR
ORDER = ["중대형", "소규모", "집합"]


def main():
    if not SRC.exists():
        print(f"장기 임대가격지수 없음({SRC}) → 건너뜀"); return
    R = pd.read_csv(SRC, encoding="utf-8-sig")
    R = R[R.ptype.isin(ORDER)]
    L = pd.read_csv(OUT / "landprice_area_panel.csv", encoding="utf-8-sig").pivot_table(index="year", columns="code", values="idx")
    prof = pd.read_csv(OUT / "area_profile.csv", encoding="utf-8-sig").set_index("code")
    rp = pd.read_csv(OUT / "rent_pressure.csv", encoding="utf-8-sig", dtype={"key": str})
    rp = rp[rp.level == "상권"].set_index("key").rent_pressure
    regions = ["대전"] + [r for r in MATCH if r in set(R.region) and r != "원도심"]
    rows = []
    for reg in regions:
        codes = ["ALL"] if reg == "대전" else MATCH[reg]
        row = dict(region=reg if reg != "대전" else "대전 전체", codes=",".join(codes),
                   areas=" · ".join(prof.name.get(c, c).split("(")[0] for c in codes) if reg != "대전" else "대전 전체")
        main_done = False
        for pt in ORDER:
            g = R[(R.region == reg) & (R.ptype == pt)].sort_values(["year", "q"])
            g = g[g.year >= g[g.q == 1].year.min()] if (g.q == 1).any() else g
            if len(g) < 12:                                  # 3년 미만은 장기 흐름으로 보지 않음
                continue
            chg = (g.idx.iloc[-1] / g.idx.iloc[0] - 1) * 100
            row[f"rent_chg_{pt}"] = round(chg, 1)
            if not main_done:
                y0 = int(g.year.iloc[0]); y1 = 2026
                lc = [L.loc[y1, c] / L.loc[y0, c] - 1 for c in codes if c in L and y0 in L.index and y1 in L.index]
                land = float(np.mean(lc) * 100) if lc else np.nan
                pk = g.loc[g.idx.idxmax()]
                row.update(ptype=pt, start=f"{y0}Q1", end=g.period.iloc[-1], rent_chg_pct=round(chg, 1),
                           rent_peak=f"{pk.period}", land_chg_pct=round(land, 1), gap_pp=round(land - chg, 1))
                main_done = True
        if not main_done:
            continue
        if reg != "대전":
            row["quadrant"] = " / ".join(dict.fromkeys(str(prof.quadrant.get(c, "")) for c in codes))
            row["rent_pressure"] = " / ".join(dict.fromkeys(str(rp.get(c, "")) for c in codes))
        rows.append(row)
    D = pd.DataFrame(rows)
    D.to_csv(OUT / "rent_long_vs_land.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(D.to_string(index=False))


def passthrough():
    """전국 상권: 자산가치(자본수익률 누적) 변화가 클수록 임대료도 더 올랐나 (R-ONE 중대형 상가)."""
    f = C.RAW_DIR / "rent_survey_long" / "rone_capital_vs_rent_regions.csv"
    if not f.exists():
        return
    d = pd.read_csv(f, encoding="utf-8-sig")
    d = d[(d.sido != d.region) & (d.region != "기타")]                   # 시도 합계 행 제외
    rows = []
    for w, g in d.groupby("window"):
        x, y = g.capital_cum_pct, g.rent_idx_chg_pct
        b = np.polyfit(x, y, 1)[0]
        rows.append(dict(window=w, n=len(g), capital_median=round(x.median(), 1), rent_median=round(y.median(), 1),
                         spearman=round(x.rank().corr(y.rank()), 3), slope=round(b, 3),
                         share_capital_up_rent_down=round(((x > 0) & (y < 0)).mean(), 3),
                         share_rent_up=round((y > 0).mean(), 3)))
    S = pd.DataFrame(rows)
    S.to_csv(OUT / "rent_capital_passthrough.csv", index=False, encoding="utf-8-sig")
    print(S.to_string(index=False))


def landcheck():
    """공시지가(1월 1일) vs R-ONE 지가지수(시장 기반, 연말) — 공시지가가 시장보다 과하게 올랐나 (B9)."""
    f = C.RAW_DIR / "rent_survey_long" / "rone_land_index_daejeon.csv"
    if not f.exists():
        return
    r = pd.read_csv(f, encoding="utf-8-sig").pivot_table(index="year", columns=["use", "region"], values="idx")
    L = pd.read_csv(OUT / "landprice_area_panel.csv", encoding="utf-8-sig").pivot_table(index="year", columns="code", values="idx")
    rows = []
    for a, b, lab in [(2013, 2025, "13년 전체"), (2018, 2022, "현실화율 정책기(2019~22)"), (2013, 2018, "정책 전")]:
        if a not in r.index or b not in r.index or b + 1 not in L.index:
            continue
        rows.append(dict(period=lab, rone_years=f"{a}말→{b}말", gongsi_years=f"{a + 1}.1.1→{b + 1}.1.1",
                         rone_all_pct=round((r.loc[b, ("전체", "대전")] / r.loc[a, ("전체", "대전")] - 1) * 100, 1),
                         rone_commercial_pct=round((r.loc[b, ("상업지역", "대전")] / r.loc[a, ("상업지역", "대전")] - 1) * 100, 1),
                         gongsi_pct=round((L.loc[b + 1, "ALL"] / L.loc[a + 1, "ALL"] - 1) * 100, 1)))
    S = pd.DataFrame(rows)
    S.to_csv(OUT / "landprice_vs_rone.csv", index=False, encoding="utf-8-sig")
    print(S.to_string(index=False))


if __name__ == "__main__":
    passthrough()
    landcheck()
    main()
