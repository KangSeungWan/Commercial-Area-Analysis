"""tram_model 결과 → 지도 앱(app.py)용 map_data.csv 생성.

- 컬럼은 기존 Colab map_data.csv 와 동일:
  cell_id, category, lat, lon, zone, dong, sales, dist_tram, tram_effect, resid_pct
- tram_effect 를 '가정 5%·거리감쇠' 대신 tram_effect.py 시나리오(개통 초기 1~4년, 땅값 기준 %)로 교체
- tram_effect_low / tram_effect_high 컬럼 추가 (app.py 시나리오 선택용)
- resid_pct 는 Colab(LightGBM) 결과이므로, 기존 map_data.csv 가 있으면 거기서 가져옴

사용:  python tram_model/make_map_data.py            (Project 폴더에서)
       python tram_model/make_map_data.py --old 기존_map_data.csv --out map_data.csv
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"


def main(old_path, out_path):
    lk = pd.read_csv(OUT / "area_lookup.csv", encoding="utf-8-sig")
    ds = pd.read_csv(OUT / "daejeon_tram_area_dataset.csv", encoding="utf-8-sig")
    sc = pd.read_csv(OUT / "scenario_tram_uplift.csv", encoding="utf-8-sig")

    sales = ds.groupby("area_id").agg(sales=("sales", "mean"), dist_tram=("dist_tram_m", "first")).reset_index()
    m = (lk.merge(sales, on="area_id")
           .merge(sc[["area_id", "eff_low", "eff_base", "eff_high"]], on="area_id", how="left"))
    for s, col in [("low", "tram_effect_low"), ("base", "tram_effect"), ("high", "tram_effect_high")]:
        m[col] = (np.expm1(m[f"eff_{s}"]) * 100).round(2)           # log-point → %, 개통 초기 1~4년 (땅값 기준 추정)

    map_df = m.rename(columns={"cat_name": "category", "zone": "area", "zone_name": "zone"})[
        ["cell_id", "category", "lat", "lon", "area", "zone", "dong", "sales", "dist_tram",
         "tram_effect", "tram_effect_low", "tram_effect_high"]]
    lp = OUT / "landprice_cells.csv"
    if lp.exists():                                     # 공시지가 (원/㎡) · 5년 상승률(%)
        feat = pd.read_csv(OUT / "features_ext.csv", encoding="utf-8-sig")
        if "land_price" in feat.columns:
            f = feat.assign(cell_id=feat.area_id.str.rsplit("_", n=1).str[0]).drop_duplicates("cell_id")
            f = f[["cell_id", "land_price", "land_growth_5y"]]
            f["land_growth_5y"] = (f.land_growth_5y * 100).round(1)
            map_df = map_df.merge(f, on="cell_id", how="left")

    # resid_pct: ① --old 파일(Colab)에 값이 있으면 그것, ② 없으면 train_analyze.py 가 만든 cell_resid.csv
    src = None
    if old_path and Path(old_path).exists():
        old = pd.read_csv(old_path, encoding="utf-8-sig")
        if "resid_pct" in old.columns and old.resid_pct.notna().any() \
                and old.cell_id.isin(map_df.cell_id).mean() > 0.5:          # 셀 이름이 같을 때만 (4권역→20상권 전환 후엔 안 맞음)
            r, src = old.groupby("cell_id")["resid_pct"].first().reset_index(), old_path
    if src is None and (OUT / "cell_resid.csv").exists():
        r, src = pd.read_csv(OUT / "cell_resid.csv", encoding="utf-8-sig"), "tram_model/outputs/cell_resid.csv"
    if src:
        map_df = map_df.drop(columns=["resid_pct"], errors="ignore").merge(r, on="cell_id", how="left")
        print(f"resid_pct ← {src}")
    else:
        map_df["resid_pct"] = np.nan
        print("resid_pct 없음 → python tram_model/train_analyze.py 를 먼저 실행하세요")

    map_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    area_profile(map_df)
    print(f"{out_path}: {len(map_df)}행, tram_effect(기본) 범위 "
          f"{map_df.tram_effect.min():.2f}~{map_df.tram_effect.max():.2f}%")


def area_profile(map_df):
    """20개 상권 요약 → outputs/area_profile.csv (지도 앱 상권 클릭 정보)."""
    A = pd.read_csv(HERE / "data" / "sangkwon_areas.csv", encoding="utf-8-sig")[["code", "name", "gu", "type", "p6_zone"]]
    S = pd.read_csv(OUT / "sangkwon_summary.csv", encoding="utf-8-sig")
    keep = [c for c in ["code", "n_stores", "top3_mid", "branch_share", "nearest_tram", "nearest_tram_m", "tram_group"]
            if c in S.columns]
    P = A.merge(S[keep], on="code", how="left")
    lp = OUT / "landprice_area_panel.csv"
    if lp.exists():
        L = pd.read_csv(lp, encoding="utf-8-sig")
        L = L[L.code != "ALL"].pivot(index="code", columns="year", values="idx")
        ly = L.columns.max()
        P = P.merge(pd.DataFrame({
            "land_chg_5y_pct": ((L[ly] / L[ly - 5] - 1) * 100).round(1),
            "land_chg_10y_pct": ((L[ly] / L[ly - 10] - 1) * 100).round(1),
            "land_chg_since2005_pct": ((L[ly] / L[2005] - 1) * 100).round(1) if 2005 in L else np.nan,
        }).reset_index(), on="code", how="left")
        rel = pd.read_csv(lp, encoding="utf-8-sig")
        rel = rel[rel.year == ly].set_index("code").rel_idx
        P["land_rel_idx"] = P.code.map(rel)          # 2015 대비, 대전 전체 대비 (100 위 = 더 오름)
    sp = OUT / "store_panel.csv"
    if sp.exists():
        T = pd.read_csv(sp, dtype={"period": str}, encoding="utf-8-sig")
        T = T.sort_values(["code", "period"])
        # 자료 단절 분기의 비중 변화는 빼고 분기별 변화를 이어 붙인 비중 지수 (단절 영향 제거)
        r = (T.share / T.groupby("code").share.shift()).where(T.data_break == 0, 1.0).fillna(1.0)
        T["share_chain"] = r.groupby(T.code).cumprod()
        last = T.period.max()
        y5 = str(int(last[:4]) - 5) + last[4:]
        a = T[T.period == last].set_index("code").share_chain
        b = T[T.period == y5].set_index("code").share_chain
        P["store_share_chg_5y_pct"] = P.code.map(((a / b - 1) * 100).round(1))
        rec = T[T.period > str(int(last[:4]) - 3) + last[4:]]
        P["close_rate_q_pct"] = P.code.map((rec.groupby("code").close_rate.mean() * 100).round(2))
    tf = OUT / "area_types.csv"
    if tf.exists():                                        # cluster_areas.py 결과 (상권 유형)
        P = P.merge(pd.read_csv(tf, encoding="utf-8-sig")[["code", "cluster", "type_name"]], on="code", how="left")
    sf = OUT / "area_scores.csv"
    if sf.exists():                                        # score_areas.py 결과 (쇠퇴 위험·성장 가능)
        _sc = pd.read_csv(sf, encoding="utf-8-sig")
        _cols = ["code", "risk_score", "growth_score", "quadrant", "risk_drivers", "growth_drivers"] + \
            [c for c in ("quadrant_stability", "quadrant_alt", "quadrant_uncertain", "in500") if c in _sc.columns]
        P = P.merge(_sc[_cols], on="code", how="left")
    vf = OUT / "survey_area.csv"
    if vf.exists():                                        # analyze_survey_sales.py (소속 행정동 2021 실태조사)
        P = P.merge(pd.read_csv(vf, encoding="utf-8-sig")[["code", "dong", "decline_pct", "closing_pct", "bad_pct"]]
                    .rename(columns={"dong": "survey_dong"}), on="code", how="left")
    eff = map_df.groupby("area")[["tram_effect", "tram_effect_low", "tram_effect_high"]].mean().round(2)
    P = P.merge(eff, left_on="code", right_index=True, how="left")
    P.to_csv(OUT / "area_profile.csv", index=False, encoding="utf-8-sig")
    print(f"outputs/area_profile.csv: 상권 {len(P)}개 요약 (지도 클릭용)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default="map_data.csv", help="Colab에서 만든 기존 map_data.csv (resid_pct 가져오기)")
    ap.add_argument("--out", default="map_data.csv")
    a = ap.parse_args()
    main(a.old, a.out)
