"""20개 상권 × 6개 업종 '업종 상권 점수' (100점, 트램 건설 전·후).

입력: outputs/store_panel.csv (상권 × 분기 × 업종 점포 수), dong_panel_store.csv (대전 전체 업종 합계용),
      area_profile.csv (폐업률·땅값), robust_radius.csv (정거장 500m 비율), tram_effect.py (트램 효과 수준·업종 비율),
      line1_permits_sector.csv + data/raw/permits (대전 1호선 인허가 업종 그룹별 점포 효과, 있으면 음식 업종에 사용)
출력: outputs/industry_scores.csv          (상권 × 업종: 원래 값 + 항목 점수 + 전·후 점수 + 순위)
      outputs/industry_score_weights.csv   (항목·가중치·데이터·계산·근거·한계)

항목 점수 = 그 업종 안에서 20개 상권을 줄 세운 백분위(0~100). 즉 '대전 20개 상권 중 상대 위치'.
점수 = Σ 가중치 × 항목 점수 / Σ 가중치(값이 있는 항목만).
건설 후 = 트램 예상 효과를 실제 값에 더한 뒤(성장 += 업종별 트램 효과, 땅값 흐름 += 500m 안 비율 × 효과 수준),
          '건설 전' 20개 상권 분포에 대어 다시 점수화 → 트램이 닿지 않는 상권은 그대로, 닿는 상권만 오름.
          (예전 방식: 트램 10점 항목을 넣고 나머지를 0.9배 → 트램 밖 상권이 일제히 내려가 트램이 악영향처럼 보였음)
"""
import numpy as np
import pandas as pd

import config as C
import tram_effect as TE

IND = {"음식": ("n_food", "I2"), "소매": ("n_retail", "G2"), "수리·개인": ("n_personal", "S2"),
       "교육": ("n_edu", "P1"), "보건의료": ("n_health", "Q1"), "숙박": ("n_lodging", "I1")}
NOW, PAST = "202606", "202106"          # 최근 · 5년 전 (같은 2분기끼리)
MIN_N = 5                               # 업종 점포가 이보다 적으면 성장·특화 계산 안 함 (표본 부족)
ARTIFACT = {"A12"}                      # 도룡동: 신세계 입점점포 등록으로 점포 지표 왜곡 → 성장·생존 제외

# 항목: (이름, 건설 전 가중치, 방향, 데이터, 계산, 근거, 한계)
COMP = {
    "growth": ("성장", 30, 1, "상가정보 2021-06·2026-06",
               "그 업종의 대전 내 점포 비중 5년 변화(%)",
               "수요가 어디로 옮겨 가는지 가장 직접 보여줌. 업종 분석에서 원도심→신도심 이동 확인",
               "자료 수집 기준 변경(2026-06)은 대전 전체 대비 비중이라 상당 부분 상쇄"),
    "size": ("규모", 20, 1, "상가정보 2026-06", "그 업종 점포 수 (로그)",
             "점포가 모인 곳 = 손님이 모이는 곳 (집적 효과)", "많을수록 경쟁도 큼 — 포화 여부는 반영 못 함"),
    "lq": ("특화도", 15, 1, "상가정보 2026-06", "입지계수 = (상권 안 업종 비율) ÷ (대전 업종 비율)",
           "1보다 크면 그 업종이 특히 모이는 상권 (업종 특화 상권)", "특화 = 과포화일 수도 있음"),
    "survival": ("생존", 20, -1, "상가정보 2023~2026 분기 개·폐업", "상권 분기 폐업률(%), 낮을수록 높은 점수",
                 "문 닫는 가게가 적은 상권이 버티기 쉬움", "업종별 폐업률 자료가 없어 상권 공통값"),
    "land": ("땅값 흐름", 15, 1, "개별공시지가 2021·2026", "상권 땅값 5년 상승률(%)",
             "입지 가치·수요가 오르는 신호", "임대료 부담이 커질 수도 있음 (상권 공통값)"),
    "tram": ("트램 반영 (건설 후)", 0, 1, "대전 1호선 개통 전후 점포(인허가)·땅값 + 정거장 좌표",
             "따로 점수를 매기지 않고, 성장에 업종별 트램 효과(500m 안 비율 × 업종 효과)를, "
             "땅값 흐름에 500m 안 비율 × 땅값 효과 수준을 더해 건설 전 분포 기준으로 다시 점수화. "
             "음식 업종 효과 = 상권 음식점 중 카페·빵과자점 비중 × 대전 1호선 실측 점포 효과(카페 +24.8%, 빵·과자 +18.3%, "
             "나머지 음식 업종은 효과 확인 안 됨 → 기본 0). 다른 업종은 땅값 효과 × 해외 업종 비율",
             "대전 1호선 역 500m 안 카페 +24.8%·빵·과자 +18.3%(2002~2014 인허가 이중차분, 가짜 검정 통과). "
             "식사 음식점·주점·간편식은 효과 확인 안 됨 → 카페·빵집이 많은 상권일수록 음식 점수가 더 오름",
             "지하철 개통 효과를 트램에 빌려 씀, 효과는 개통 후 9년 평균, 공사 기간 손실은 반영 안 함. "
             "음식 외 업종은 대전 실측 점포 효과가 없어 땅값 기준 그대로"),
}
TRAM_W = 0                              # (예전: 건설 후 트램 10점 항목) 지금은 값에 더하는 방식


def ref_pct(before, new):
    """new 값을 '건설 전' 분포(before)에 대어 0~100 백분위로 (before 값 자체는 원래 점수와 같음)."""
    b = before.dropna()
    if len(b) < 2:
        return new * np.nan
    pr = pct_rank(b)
    tab = pd.DataFrame({"v": b.values, "p": pr.values}).groupby("v").p.mean().sort_index()
    return pd.Series(np.interp(new, tab.index.values, tab.values), index=new.index).where(new.notna())


def pct_rank(s):
    """0~100 백분위 (값 없는 곳은 NaN). 동점은 평균 순위."""
    r = s.rank(method="average")
    n = s.notna().sum()
    return (r - 1) / (n - 1) * 100 if n > 1 else r * 0 + 50


FOOD_SECTORS = ["카페", "빵·과자", "간편식(분식·패스트푸드·조리판매)", "주점", "식사 음식점"]   # 편의점은 상가정보에서 소매


def _inside(lon, lat, ring):
    from matplotlib.path import Path as MPath
    return MPath(np.asarray(ring)).contains_points(np.column_stack([lon, lat]))


def food_tram_effects():
    """상권별 음식 업종 트램 효과(%) = Σ 업종 그룹 비중 × 대전 1호선 인허가 점포 효과.
    낮음 = 확실한 그룹(카페)의 95% 하한, 기본 = 카페 추정치(나머지 0), 높음 = 모든 그룹 추정치(빵·과자 포함).
    빵·과자는 개수 효과는 있으나 비중 변화가 없어(근거 점검) 낮음·기본에서 뺌.
    인허가 파일이나 결과가 없으면 None → 예전 방식(땅값 × 해외 업종 비율)."""
    import contextlib, io, json
    f = C.OUT_DIR / "line1_permits_sector.csv"
    if not f.exists() or not list((C.RAW_DIR / "permits").glob("*.csv")):
        return None
    import analyze_line1_permits as AP
    sec = pd.read_csv(f, encoding="utf-8-sig").set_index("업종")
    with contextlib.redirect_stdout(io.StringIO()):
        p = AP.load_permits()
    p["sector"] = AP.sector_of(p)
    p = p[p.close.isna() & p.sector.isin(FOOD_SECTORS)]          # 지금 영업 중인 음식 업종
    sure = sec["판정"].astype(str).str.startswith("확실")
    # 근거 점검(check_sector_evidence.py): 빵·과자는 개수만 늘고 음식점 중 비중은 1·2단계 모두 변화 없음 → 낮음·기본에서 제외
    sure = sure & (sec.index != "빵·과자")
    eff = {"low": sec["하한_%"].where(sure, 0.0), "base": sec["효과_%"].where(sure, 0.0), "high": sec["효과_%"]}
    gj = json.loads((C.OUT_DIR / "sangkwon_polygons.geojson").read_text(encoding="utf-8"))
    out = {}
    for ft in gj["features"]:
        geom, code = ft["geometry"], ft["properties"]["code"]
        rings = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [poly[0] for poly in geom["coordinates"]]
        m = np.zeros(len(p), bool)
        for ring in rings:
            m |= _inside(p.lon.values, p.lat.values, ring)
        mix = p.loc[m, "sector"].value_counts(normalize=True)
        row = {"food_n_permits": int(m.sum()),
               "cafe_share": round(float(mix.get("카페", 0)), 3), "bakery_share": round(float(mix.get("빵·과자", 0)), 3)}
        for sc, e in eff.items():
            row[f"food_eff_{sc}"] = float(sum(mix.get(g, 0) * e.get(g, 0.0) for g in FOOD_SECTORS)) if m.sum() >= 10 else np.nan
        out[code] = row
    F = pd.DataFrame(out).T
    F.to_csv(C.OUT_DIR / "industry_food_tram_mix.csv", encoding="utf-8-sig", index_label="code")
    return F


def tram_effects_for(ind, code, in500, ratio, L, FM):
    """업종·상권별 트램 효과(%, 성장에 더할 값)와 근거 표시."""
    if ind == "음식" and FM is not None and code in FM.index and pd.notna(FM.loc[code, "food_eff_base"]):
        r = FM.loc[code]
        return {**{f"tram_effect_{s}": round(in500 * float(r[f"food_eff_{s}"]), 2) for s in TE.SCEN},
                "tram_basis": "대전 1호선 인허가 업종 효과", "cafe_share": r.cafe_share, "bakery_share": r.bakery_share}
    return {**{f"tram_effect_{s}": round(in500 * np.expm1(L[s]["log"] * ratio) * 100, 2) for s in TE.SCEN},
            "tram_basis": "땅값 효과 × 해외 업종 비율", "cafe_share": np.nan, "bakery_share": np.nan}


def main():
    sp = pd.read_csv(C.OUT_DIR / "store_panel.csv", dtype={"period": str}, encoding="utf-8-sig")
    dp = pd.read_csv(C.OUT_DIR / "dong_panel_store.csv", dtype={"period": str}, encoding="utf-8-sig")
    prof = pd.read_csv(C.OUT_DIR / "area_profile.csv", encoding="utf-8-sig").set_index("code")
    rr = pd.read_csv(C.OUT_DIR / "robust_radius.csv", encoding="utf-8-sig").set_index("zone")
    city = dp.groupby("period")[["n_stores"] + [f"n_{k}" for k in IND]].sum()
    L = TE.levels()
    max_ratio = max(TE.cat_ratio(c) for _, c in IND.values())
    FM = food_tram_effects()
    if FM is None:
        print("인허가 업종 효과 없음 → 음식 업종도 땅값 × 해외 업종 비율 사용")

    now = sp[sp.period == NOW].set_index("code")
    past = sp[sp.period == PAST].set_index("code")
    rows = []
    for ind, (col, cat) in IND.items():
        cn, cp = city.loc[NOW, f"n_{ind}"], city.loc[PAST, f"n_{ind}"]
        ratio = TE.cat_ratio(cat)
        for code in prof.index:
            n1 = float(now.loc[code, col]) if code in now.index else np.nan
            n0 = float(past.loc[code, col]) if code in past.index else np.nan
            tot = float(now.loc[code, "n_stores"]) if code in now.index else np.nan
            ok = (n1 >= MIN_N) and (n0 >= MIN_N)
            in500 = float(rr.in500.get(code, 0))
            rows.append({
                "code": code, "name": prof.loc[code, "name"], "industry": ind, "n_stores": n1, "n_stores_5y_ago": n0,
                "growth": (n1 / cn / (n0 / cp) - 1) * 100 if ok and code not in ARTIFACT else np.nan,
                "size": np.log1p(n1) if pd.notna(n1) else np.nan,
                "lq": (n1 / tot) / (cn / city.loc[NOW, "n_stores"]) if n1 >= MIN_N and tot > 0 else np.nan,
                "survival": prof.loc[code, "close_rate_q_pct"] if code not in ARTIFACT else np.nan,
                "land": prof.loc[code, "land_chg_5y_pct"],
                "tram": in500 * ratio / max_ratio * 100,
                "in500": in500,
                **tram_effects_for(ind, code, in500, ratio, L, FM),
                "flag": ("점포 지표 왜곡(신세계 입점 등록)" if code in ARTIFACT else
                         (f"업종 점포 {MIN_N}개 미만 → 성장·특화 제외" if not ok else "")),
            })
    D = pd.DataFrame(rows)

    # 항목 점수: 업종 안에서 20개 상권 백분위 (트램은 절대 척도 0~100)
    for k, (_, _, sign, *_r) in COMP.items():
        if k == "tram":
            D["s_tram"] = D.tram.round(1)
        else:
            D[f"s_{k}"] = D.groupby("industry")[k].transform(lambda s: pct_rank(s * sign)).round(1)

    def total(df, w):
        S = df[[f"s_{k}" for k in w]]
        W = pd.DataFrame({f"s_{k}": np.where(S[f"s_{k}"].notna(), v, 0.0) for k, v in w.items()}, index=df.index)
        return ((S.fillna(0) * W).sum(axis=1) / W.sum(axis=1)).round(1)

    w_before = {k: v[1] for k, v in COMP.items() if k != "tram"}
    w_after = dict(w_before) | {"tram": 0}
    D["score_before"] = total(D, w_before)
    # 건설 후: 트램 예상 효과를 값에 더하고 건설 전 분포에 대어 다시 점수화 (시나리오별)
    for sc in TE.SCEN:
        D[f"growth_after_{sc}"] = D.growth + D[f"tram_effect_{sc}"]
        D[f"land_after_{sc}"] = D.land + D.in500 * L[sc]["pct"]
        for k in ("growth", "land"):
            D[f"s_{k}_after_{sc}"] = 0.0
            for ind, g in D.groupby("industry"):
                D.loc[g.index, f"s_{k}_after_{sc}"] = ref_pct(g[k], g[f"{k}_after_{sc}"]).round(1)
        A = D.copy()
        A["s_growth"], A["s_land"] = D[f"s_growth_after_{sc}"], D[f"s_land_after_{sc}"]
        D[f"score_after_{sc}"] = total(A, w_before)
    D["score_after"] = D.score_after_base
    few = D.n_stores.fillna(0) < MIN_N                      # 업종 점포가 거의 없으면 점수 안 매김
    D.loc[few, ["score_before", "score_after"] + [f"score_after_{sc}" for sc in TE.SCEN]] = np.nan
    D.loc[few, "flag"] = f"업종 점포 {MIN_N}개 미만 → 점수 없음"
    D["score_change"] = (D.score_after - D.score_before).round(1)
    for t in ("before", "after"):
        D[f"rank_{t}"] = D.groupby("industry")[f"score_{t}"].rank(ascending=False, method="min").astype("Int64")
    D["rank_change"] = D.rank_before - D.rank_after          # + = 트램 후 순위 상승
    D = D.sort_values(["industry", "score_before"], ascending=[True, False])
    D.round(4).to_csv(C.OUT_DIR / "industry_scores.csv", index=False, encoding="utf-8-sig")

    W = pd.DataFrame([{"key": k, "item": v[0], "weight_before": v[1], "weight_after": round(w_after[k], 1),
                       "data": v[3], "method": v[4], "rationale": v[5], "limit": v[6]} for k, v in COMP.items()])
    W.to_csv(C.OUT_DIR / "industry_score_weights.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 220)
    for ind in IND:
        g = D[D.industry == ind].sort_values("score_after", ascending=False).head(5)
        print(f"\n[{ind}] 상위 5 (건설 후)\n", g[["name", "n_stores", "score_before", "score_after", "rank_change",
                                              "flag"]].to_string(index=False))
    print("\n가중치\n", W[["item", "weight_before", "weight_after"]].to_string(index=False))
    print("→ outputs/industry_scores.csv, industry_score_weights.csv")


if __name__ == "__main__":
    main()
