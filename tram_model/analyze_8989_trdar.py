"""8989 골목상권(전통시장·상점가·골목형상점가 144곳) 카드매출 정리 + 핵심 상권 20개 대응

입력: outputs/8989/sales_month.csv (anal=trdarAnal, 핵심 27업종), data/raw/8989/meta/trdar_polygons.geojson, trdar_geo_attr.csv,
      outputs/sangkwon_polygons.geojson, outputs/dong_polygons.geojson, outputs/8989/area_sales_summary.csv, report_alley_cumulative.csv
출력: outputs/8989/trdar_summary.csv   골목상권별: 월평균 매출 지수, 2025→2026 증감(전체·음식·소매), 주점·음료 비중, 같은 값 묶음, 소속 동·상권
      outputs/8989/area_trdar_match.csv 핵심 상권 20 × 골목상권 겹침 비율
      outputs/8989/area_sales_compare.csv 핵심 상권별 증감: 행정동 배분 vs 골목상권 실측(겹침 가중, 같은 값 묶음 1번만)
주의: 골목상권 금액은 경계 정밀 집계가 아니라 주변 격자 합으로 보임(10개 묶음이 완전히 같은 값, 144곳 합이 대전 전체보다 큼)
      → 금액·점포당 금액은 쓰지 않고 증감률·업종 비중만 사용
"""
import json
import numpy as np
import pandas as pd

import config as C
import sys
if not (C.OUT_DIR / "8989" / "sales_month.csv").exists():
    print("8989 표 없음 → 건너뜀"); sys.exit(0)

OUT, O8, META = C.OUT_DIR, C.OUT_DIR / "8989", C.ROOT / "data" / "raw" / "8989" / "meta"
P24 = [f"2024{m:02d}" for m in range(1, 9)]; P25 = [f"2025{m:02d}" for m in range(1, 9)]; P26 = [f"2026{m:02d}" for m in range(1, 9)]
FOOD = ["I2561", "I2562"]; RETAIL = ["G0472", "G0473", "G0474", "G0475", "G0476", "G0478"]


def polys_of(geom):
    return [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]

def pip(x, y, poly):
    px, py = np.array(poly)[:, 0], np.array(poly)[:, 1]; inside = np.zeros(len(x), bool); j = len(px) - 1
    for i in range(len(px)):
        inside ^= ((py[i] > y) != (py[j] > y)) & (x < (px[j] - px[i]) * (y - py[i]) / (py[j] - py[i] + 1e-12) + px[i]); j = i
    return inside

def inside_any(x, y, polys):
    m = np.zeros(len(x), bool)
    for p in polys: m |= pip(x, y, p)
    return m

def sample_points(polys, n=400, seed=0):
    pts = np.array([q for p in polys for q in p]); rng = np.random.default_rng(seed)
    x = rng.uniform(pts[:, 0].min(), pts[:, 0].max(), n * 6); y = rng.uniform(pts[:, 1].min(), pts[:, 1].max(), n * 6)
    m = inside_any(x, y, polys); return x[m][:n], y[m][:n]


def main():
    s = pd.read_csv(O8 / "sales_month.csv", dtype={"code": str, "stdrYm": str, "sclasCd": str})
    t = s[(s.anal == "trdarAnal") & (s.level == "trdar")]
    g = pd.read_csv(META / "trdar_geo_attr.csv", dtype=str).set_index("trdarNo")
    def mavg(df, months): return df[df.stdrYm.isin(months)].groupby("code").useAmount.sum() / len(months)
    S = pd.DataFrame(index=sorted(t.code.unique()))
    S["name"], S["type"] = g.trdarNm.reindex(S.index), g.trdarSeNm.reindex(S.index)
    for lab, sub in [("all", t), ("food", t[t.sclasCd.isin(FOOD)]), ("retail", t[t.sclasCd.isin(RETAIL)])]:
        a26, a25 = mavg(sub, P26), mavg(sub, P25)
        S[f"yoy_{lab}"] = ((a26 / a25 - 1) * 100).round(2)
        # 2024→2026 (1~8월): 2024년에 값이 있는 업종끼리만 비교 (2024는 23개 업종)
        have24 = set(sub[sub.stdrYm.isin(P24)].sclasCd)
        sub2 = sub[sub.sclasCd.isin(have24)]
        S[f"chg2y_{lab}"] = ((mavg(sub2, P26) / mavg(sub2, P24) - 1) * 100).round(2)
    f26 = mavg(t[t.sclasCd.isin(FOOD)], P26)
    S["bar_cafe_share_food"] = (mavg(t[t.sclasCd == "I2562"], P26) / f26).round(3)        # 주점·비알코올 음료(카페) / 음식 전체
    S["bar_cafe_share_food_24"] = (mavg(t[t.sclasCd == "I2562"], P24) / mavg(t[t.sclasCd.isin(FOOD)], P24)).round(3)
    S["food_share"] = (f26 / mavg(t, P26)).round(3)
    tot = t.groupby(["code", "stdrYm"]).useAmount.sum().unstack()
    key = tot.round(-3).astype(str).agg("|".join, axis=1)
    S["dup_group"] = key.map({k: i for i, k in enumerate(key[key.duplicated(keep=False)].unique())}).reindex(S.index)
    S["months"] = tot.notna().sum(axis=1).reindex(S.index)

    # 공간: 골목상권 → 소속 행정동(가장 많이 겹치는), 핵심 상권 겹침 비율
    tg = json.load(open(META / "trdar_polygons.geojson", encoding="utf-8"))
    ag = json.load(open(OUT / "sangkwon_polygons.geojson", encoding="utf-8"))
    dg = json.load(open(OUT / "dong_polygons.geojson", encoding="utf-8"))
    A = [(f["properties"]["code"], f["properties"].get("name"), polys_of(f["geometry"])) for f in ag["features"]]
    Dg = [(str(f["properties"]["id"]), f["properties"].get("name"), polys_of(f["geometry"])) for f in dg["features"]]
    rows = []
    for f in tg["features"]:
        k = str(f["properties"]["trdarNo"])
        if k not in S.index: continue
        x, y = sample_points(polys_of(f["geometry"]))
        best = max(((dn, inside_any(x, y, dp).mean()) for _, dn, dp in Dg), key=lambda z: z[1])
        S.loc[k, "dong"] = best[0]
        for code, an, ap in A:
            fr = inside_any(x, y, ap).mean()
            if fr > 0: rows.append(dict(area=code, area_name=an, trdar=k, trdar_name=S.loc[k, "name"], type=S.loc[k, "type"], overlap=round(fr, 3)))
    M = pd.DataFrame(rows).sort_values(["area", "overlap"], ascending=[True, False])
    M.to_csv(O8 / "area_trdar_match.csv", index=False, encoding="utf-8-sig")
    S.reset_index(names="trdarNo").to_csv(O8 / "trdar_summary.csv", index=False, encoding="utf-8-sig")

    # 핵심 상권별: 겹침 ≥ 0.3 골목상권, 같은 값 묶음은 1번만, 겹침 가중 평균
    sel = M[M.overlap >= 0.3].merge(S[["yoy_all", "yoy_food", "yoy_retail", "chg2y_all", "bar_cafe_share_food", "dup_group"]], left_on="trdar", right_index=True)
    sel["dkey"] = sel.dup_group.fillna(-1).astype(int).astype(str).where(sel.dup_group.notna(), sel.trdar)
    sel = sel.sort_values("overlap", ascending=False).drop_duplicates(["area", "dkey"])
    def wavg(d, c): v = d[[c, "overlap"]].dropna(); return np.average(v[c], weights=v.overlap) if len(v) else np.nan
    G = sel.groupby("area").apply(lambda d: pd.Series({"n_trdar": len(d), "trdar_names": ", ".join(d.trdar_name),
        "trdar_yoy_all": wavg(d, "yoy_all"), "trdar_chg2y_all": wavg(d, "chg2y_all"), "trdar_yoy_food": wavg(d, "yoy_food"), "trdar_bar_cafe_share": wavg(d, "bar_cafe_share_food")}), include_groups=False)
    AS = pd.read_csv(O8 / "area_sales_summary.csv")[["code", "name", "quadrant", "risk_score", "sales_yoy_pct", "main_dong_weight"]].set_index("code")
    AS = AS.rename(columns={"sales_yoy_pct": "dong_alloc_yoy"}).join(G)
    cum = pd.read_csv(O8 / "report_alley_area_match.csv").groupby("area").card_cum.mean() if (O8 / "report_alley_area_match.csv").exists() else None
    if cum is not None: AS["pdf_cum_dec_jul"] = cum
    AS = AS.round(2); AS.to_csv(O8 / "area_sales_compare.csv", encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print("골목상권 144곳: 매출 증감(핵심 27업종 합) 중앙값", S.yoy_all.median(), "% · 같은 값 묶음", int(S.dup_group.nunique()), "개")
    print(AS[["name", "quadrant", "dong_alloc_yoy", "main_dong_weight", "n_trdar", "trdar_yoy_all", "trdar_chg2y_all", "trdar_yoy_food", "trdar_bar_cafe_share", "trdar_names"]].to_string())
    v = AS.dropna(subset=["trdar_yoy_all"])
    print(f"\n대응 골목상권 있는 핵심 상권 {len(v)}개: 행정동 배분 vs 골목상권 증감 순위상관 {v.dong_alloc_yoy.rank().corr(v.trdar_yoy_all.rank()):.2f}, "
          f"위험 점수 vs 골목상권 증감 {v.risk_score.rank().corr(v.trdar_yoy_all.rank()):.2f}, 위험 점수 vs 2년 변화 {v.risk_score.rank().corr(v.trdar_chg2y_all.rank()):.2f}")
    print("골목상권 2년 변화(2024→2026 1~8월) 중앙값", S.chg2y_all.median(), "% · 주점·음료 비중(음식 중) 2024", S.bar_cafe_share_food_24.median(), "→ 2026", S.bar_cafe_share_food.median())


if __name__ == "__main__":
    main()
