"""가정 민감도 (B1·B2): ① 1호선 효과 기준(1단계만 / 2단계만 / 합산 / 추세 보정)을 바꾸면 무엇이 바뀌나
                      ② 임대료 부담 신호의 세 요소 가중치를 바꾸면 등급이 얼마나 바뀌나

B1 입력: landprice_effects.csv, line1_trend_adjusted.csv, tram_impact_money.csv(500m 안 공시지가 총액), area_profile.csv, forecast_land.csv
   원리: 정책 진단 4칸(2026-11-12~)은 땅값 효과를 쓰지 않음(위험 점수 + 절대 쇠퇴 신호 × 업종 변화) → 땅값 기준을 바꿔도 진단 불변
         (성장 점수의 트램 항목 = 상권별 500m 비율 × 수준 → 수준은 모든 상권에 같은 배수 → 백분위 순위 불변). 이를 실제로 확인함.
         바뀌는 것: 금액(총액 × 효과 %), 2034 트램 유무 차이, 임대료 신호의 ① 요소(역시 같은 배수라 순위 불변)
B1 출력: outputs/sensitivity_effect_basis.csv (기준별 효과 %, 500m 안 금액, 업종 변화 큰 곳 2034 차이, 진단 변화 수, 임대료 등급 변화 수)
B2 입력: rent_pressure.csv (세 요소 백분위 p_*), 변형 = 각 요소 2배·각 요소 제외·순위 대신 표준화 평균
B2 출력: outputs/sensitivity_rent_weights.csv (단위·대상별 변형 중 같은 등급 비율), rent_pressure_stability 열을 rent_pressure.csv 에 덧붙임
"""
import numpy as np
import pandas as pd
import config as C

OUT = C.OUT_DIR


def b1():
    E = pd.read_csv(OUT / "landprice_effects.csv", encoding="utf-8-sig")
    pick = lambda k: float(E[E.analysis.str.contains(k, regex=False)].effect_pct.iloc[0])
    bases = [("1·2단계 합산 (현재 기본)", pick("1·2단계 합산")), ("1단계만 (현재 '높음')", pick("1호선 1단계")),
             ("2단계만", pick("1호선 2단계")), ("낮음 시나리오(해외 하한)", 0.89)]
    T = OUT / "line1_trend_adjusted.csv"
    if T.exists():
        t = pd.read_csv(T, encoding="utf-8-sig"); tt = t[t.method.str.contains("추세 보정")]
        if len(tt):
            bases.append(("1단계 추세 보정 (최소)", float(tt.effect_pct.min())))
    M = pd.read_csv(OUT / "tram_impact_money.csv", encoding="utf-8-sig")
    value500 = float(M[M.code == "ALL"].value_eok.iloc[0])
    P = pd.read_csv(OUT / "area_profile.csv", encoding="utf-8-sig")
    base_pct = pick("1·2단계 합산")
    import policy_quadrant as PQ
    reb = P[P.quadrant.isin(PQ.CHANGE_BIG)]
    F = pd.read_csv(OUT / "forecast_land.csv", encoding="utf-8-sig")
    f34 = F[F.year == F.year.max()].set_index("code")
    base_gap = sum((f34.loc[c, "tram_base"] - f34.loc[c, "base_path"]) / 100 * float(M[M.code == c].value_eok.iloc[0])
                   for c in reb.code if c in f34.index and (M.code == c).any())
    rp = pd.read_csv(OUT / "rent_pressure.csv", encoding="utf-8-sig", dtype={"key": str})
    rows = []
    for lab, e in bases:
        k = max(e, 0) / base_pct if base_pct else 0          # 음수는 0 처리(트램이 땅값을 낮춘다는 가정은 두지 않음)
        # 진단: 성장 점수의 트램 항목은 상권별 500m 비율 × 수준 → 순위 불변 (확인)
        g = (P.tram_effect * k).rank(pct=True); g0 = P.tram_effect.rank(pct=True)
        rank_same = bool(np.allclose(g.fillna(0), g0.fillna(0))) if k > 0 else False
        quad_change = 0                                     # 정책 진단은 땅값 효과를 쓰지 않음 → 기준과 무관
        rent_change = 0 if k > 0 else int((rp.rent_pressure != "해당 없음").sum())
        rows.append(dict(기준=lab, 효과_퍼센트=round(e, 2), 계산에_쓰는_값=round(max(e, 0), 2),
                         정거장500m_땅값_증가_억=round(value500 * max(e, 0) / 100), 업종변화큰곳_2034_차이_억=round(base_gap * k),
                         진단_바뀌는_상권수=quad_change, 임대료_등급_바뀌는_곳=rent_change,
                         비고=("기준값" if "합산" in lab else "음수 → 0, 트램 땅값 효과 없음으로 취급 → 금액·임대료 신호의 땅값 요소가 사라짐(진단 4칸은 그대로)" if e < 0
                              else "성장 점수 순위 불변 확인" if rank_same else "")))
    S = pd.DataFrame(rows); S.to_csv(OUT / "sensitivity_effect_basis.csv", index=False, encoding="utf-8-sig")
    print(S.to_string(index=False))


def b2():
    D = pd.read_csv(OUT / "rent_pressure.csv", encoding="utf-8-sig", dtype={"key": str})
    cols = ["p_c1_land_gap_indep", "p_close_rate", "p_cafe_bakery_pp"]
    raw = ["c1_land_gap_indep", "close_rate", "cafe_bakery_pp"]
    variants = {"기본 1:1:1": [1, 1, 1], "격차 2배": [2, 1, 1], "폐업 2배": [1, 2, 1], "업종 2배": [1, 1, 2],
                "격차 제외": [0, 1, 1], "폐업 제외": [1, 0, 1], "업종 제외": [1, 1, 0]}
    out = []; stab = {}
    for lvl, g in D.groupby("level"):
        exp = g.rent_pressure != "해당 없음"
        grades = {}
        for nm, w in variants.items():
            w = np.array(w, float)
            sc = (g.loc[exp, cols].values * w).sum(axis=1) / w.sum()
            q1, q2 = np.quantile(sc, [1 / 3, 2 / 3])
            grades[nm] = pd.Series(np.select([sc >= q2, sc >= q1], ["높음", "보통"], "낮음"), index=g.index[exp])
        z = g.loc[exp, raw].apply(lambda s: (s - s.mean()) / (s.std() or 1)).mean(axis=1)   # 순위 대신 표준화 평균
        q1, q2 = z.quantile([1 / 3, 2 / 3]); grades["표준화 평균"] = pd.Series(np.select([z >= q2, z >= q1], ["높음", "보통"], "낮음"), index=z.index)
        G = pd.DataFrame(grades)
        same = G.eq(G["기본 1:1:1"], axis=0).mean(axis=1)
        for i in G.index:
            stab[i] = round(float(same[i]), 2)
        hi_base = G["기본 1:1:1"] == "높음"
        out.append(dict(level=lvl, n=int(exp.sum()), 변형수=len(variants) + 1,
                        등급_유지_평균=round(float(same.mean()), 3),
                        기본_높음_중_모든변형에서_높음=int((G[hi_base] == "높음").all(axis=1).sum()), 기본_높음_수=int(hi_base.sum()),
                        가장_흔들리는_곳=", ".join(g.loc[same.sort_values().index[:3], "name"].astype(str))))
        # 업종 변화 큰 곳(먼저 지원·변화 관찰) 중 임대료 신호 높음의 안정도
        rb = g.loc[exp & g.quadrant.isin(["먼저 지원", "변화 관찰"])]
        if len(rb):
            out[-1]["업종변화큰곳_높음_안정"] = "; ".join(f"{r['name']}:{stab[i]:.0%}" for i, r in rb.iterrows() if r.rent_pressure == "높음")
    S = pd.DataFrame(out); S.to_csv(OUT / "sensitivity_rent_weights.csv", index=False, encoding="utf-8-sig")
    D["rent_pressure_stability"] = D.index.map(stab)
    D.to_csv(OUT / "rent_pressure.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 80)
    print(S.to_string(index=False))


if __name__ == "__main__":
    b1(); print(); b2()
