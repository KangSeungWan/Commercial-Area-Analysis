"""학습·분석 파이프라인 (build_dataset.py 실행 후).

1) 타깃 진단   : sales 가 n_same_type 비례배분값(합성)인지 자동 판별 → 누수 경고
2) ML 모델     : HistGradientBoosting, 셀 단위 GroupKFold(공간 누수 방지), 누수 피처 제외 비교
3) 벤치마크    : 로그-로그 OLS(셀 군집 표준오차) → P4(정은애·성현곤 2018)·P3(김용래 외 2016) 계수와 비교
4) 개통 시나리오: P2(Lan 2025) 업종별·버스밀도별 효과 + 시차, P6(Kakutani 2025) 중심/주변 가중
   → 정거장 500m 셀별 개통 후 매출 low/base/high

실매출(위치별 실측)이 들어오면 같은 코드 그대로 다시 돌리면 됩니다.
"""
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold

import config as C

OPEN_YEAR = 2030            # 2호선 개통 가정
SEED = 42


# ------------------------------------------------------------------ data
def load():
    d = pd.read_csv(C.OUT_DIR / "daejeon_tram_area_dataset.csv")
    e = pd.read_csv(C.OUT_DIR / "features_ext.csv")
    lit = pd.read_csv(C.LIT_PARAMS).set_index("param_id")
    df = d.merge(e, on="area_id", how="left")
    df["cell_id"] = df.area_id.str.rsplit("_", n=1).str[0]
    df["year"] = df.month.str[:4].astype(int)
    df["mon"] = df.month.str[5:7].astype(int)
    return df, lit


def P(lit, key):
    return float(lit.loc[key, "value"])


# ------------------------------------------------------------------ 1. target diagnostic
def diagnose_target(df):
    """sales == n_same_type × (구·업종·월 상수) 이면 합성 타깃."""
    t = df[(df.sales.notna()) & (df.n_same_type > 0)].copy()
    t["ratio"] = t.sales / t.n_same_type
    k = t.groupby(["sigungu", "cat", "month"]).ratio.transform("median")
    pred = k * t.n_same_type
    r2 = r2_score(np.log1p(t.sales), np.log1p(pred))
    synthetic = r2 > 0.95
    msg = (f"log(sales) 의 {r2:.1%} 를 'n_same_type × 구·업종·월 상수' 하나로 설명 → "
           + ("합성 타깃(점포수 비례배분). 성능 지표는 의미 없음, 파이프라인 검증용으로만 사용."
              if synthetic else "위치별 실측 매출로 판단."))
    print("[target]", msg)
    return synthetic, r2, msg


# ------------------------------------------------------------------ 2. ML
NUM = ["foot_traffic", "dist_transit_m", "dist_tram_m", "n_stores", "n_same_type", "rent",
       "bus_stops_300m", "stores_500m", "stores_1km", "same_type_500m", "large_retail_1km",
       "brand_share_500m", "dist_hub_m", "is_transfer_station", "in_tram_500", "bus_dense",
       "year", "mon", "land_price", "land_growth_5y", "land_growth_10y"]   # 공시지가는 있을 때만 사용
CAT = ["cat", "zone_type"]
LEAKY = ["n_same_type", "same_type_500m"]   # 합성 타깃에서 정답을 그대로 담는 피처


def make_X(df, feats):
    X = df[[f for f in feats if f in NUM]].copy()
    for c in [f for f in feats if f in CAT]:
        X[c] = df[c].astype("category").cat.codes
    return X


def run_ml(df, drop=()):
    t = df[(df.sales.notna()) & (df.n_same_type > 0)].reset_index(drop=True)  # 해당 업종 점포가 있는 셀만
    feats = [f for f in NUM + CAT if f not in drop and f in t.columns]
    X, y, g = make_X(t, feats), np.log1p(t.sales.values), t.cell_id.values
    catmask = [c in CAT for c in X.columns]
    oof = np.zeros(len(y))
    label = "누수 피처 제외" if drop else "전체 피처"
    for k, (tr, te) in enumerate(GroupKFold(n_splits=5).split(X, y, g), 1):
        print(f"  [ml:{label}] 교차검증 {k}/5 ...", flush=True)
        m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, categorical_features=catmask,
                                          random_state=SEED)
        m.fit(X.iloc[tr], y[tr])
        oof[te] = m.predict(X.iloc[te])
    res = {"features": len(feats), "n": len(y), "r2_log": r2_score(y, oof),
           "mae_log": mean_absolute_error(y, oof),
           "mape_level": float(np.median(np.abs(np.expm1(oof) - t.sales) / t.sales.clip(lower=1)))}
    print(f"  [ml:{label}] 변수 중요도 계산 ...", flush=True)
    m.fit(X, y)
    sub = np.random.RandomState(SEED).choice(len(y), size=min(3000, len(y)), replace=False)
    pi = permutation_importance(m, X.iloc[sub], y[sub], n_repeats=3, random_state=SEED, n_jobs=1)
    imp = pd.Series(pi.importances_mean, index=X.columns).sort_values(ascending=False)
    return res, imp


# ------------------------------------------------------------------ 2b. 격자 잔차 (Colab 노트북 3·5단계와 같은 정의)
def cell_residuals(df):
    """resid_pct = (격자 실제 매출 합 - 공간 OOF 예측 합) / 예측 합 × 100.
    노트북과 같은 피처·GroupKFold(cell). lightgbm 이 있으면 노트북 PARAMS, 없으면 sklearn HGB."""
    t = df[df.sales.notna()].reset_index(drop=True).copy()
    t["same_ratio"] = t.n_same_type / t.n_stores.clip(lower=1)
    feats = ["dist_transit_m", "dist_tram_m", "n_stores", "n_same_type", "same_ratio", "rent",
             "foot_traffic", "lat", "lon", "year", "mon", "cat", "zone", "sigungu"]
    X = t[feats].copy()
    for c in ["cat", "zone", "sigungu"]:
        X[c] = X[c].astype("category")
    y = np.log1p(t.sales.values)
    try:
        import lightgbm as lgb
        make = lambda: lgb.LGBMRegressor(n_estimators=600, learning_rate=0.03, num_leaves=31, min_child_samples=20,
                                         subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                                         random_state=42, verbose=-1)
        engine = "lightgbm"
    except ImportError:
        for c in ["cat", "zone", "sigungu"]:
            X[c] = X[c].cat.codes
        make = lambda: HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=SEED,
                                                     categorical_features=[c in ("cat", "zone", "sigungu") for c in feats])
        engine = "sklearn-HGB"
    oof = np.zeros(len(y))
    for k, (tr, te) in enumerate(GroupKFold(n_splits=5).split(X, y, t.cell_id), 1):
        print(f"  [resid:{engine}] 교차검증 {k}/5 ...", flush=True)
        oof[te] = make().fit(X.iloc[tr], y[tr]).predict(X.iloc[te])
    t["pred"] = np.expm1(oof)
    cell = t.groupby("cell_id").agg(sales=("sales", "sum"), pred=("pred", "sum")).reset_index()
    cell["resid_pct"] = ((cell.sales - cell.pred) / cell.pred.clip(lower=1) * 100).round(1)
    return cell[["cell_id", "resid_pct"]], engine


# ------------------------------------------------------------------ 3. OLS benchmark
def ols_cluster(y, X, groups):
    X = np.column_stack([np.ones(len(y)), X])
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    u = y - X @ b
    meat = np.zeros((X.shape[1], X.shape[1]))
    for gid in np.unique(groups):
        idx = groups == gid
        s = X[idx].T @ u[idx]
        meat += np.outer(s, s)
    G, n, k = len(np.unique(groups)), len(y), X.shape[1]
    V = XtX_inv @ meat @ XtX_inv * (G / (G - 1)) * ((n - 1) / (n - k))
    r2 = 1 - (u @ u) / ((y - y.mean()) @ (y - y.mean()))
    return b, np.sqrt(np.diag(V)), r2


def benchmark(df, lit):
    t = df[(df.sales > 0) & (df.n_same_type > 0)].copy()
    t["ln_sales"] = np.log(t.sales)
    t["ln_transit"] = np.log1p(t.bus_stops_300m)      # P4 대중교통 이용(집수권 300m) 대용
    t["ln_stores"] = np.log(t.n_stores)               # P4 고용·사업체 요인 대용
    t["ln_dist_tram"] = np.log(t.dist_tram_m.clip(lower=10))
    names = ["ln_transit", "ln_stores", "ln_dist_tram"]
    fe = pd.get_dummies(t[["cat", "month"]].astype(str), drop_first=True).astype(float)
    X = np.column_stack([t[names].values, fe.values])
    b, se, r2 = ols_cluster(t.ln_sales.values, X, t.cell_id.values)
    est = pd.DataFrame({"term": names, "coef": b[1:4], "se_cluster": se[1:4]})
    est["t"] = est.coef / est.se_cluster
    ref = {"ln_transit": [("P4_sales_transit_all", "서울 전체"), ("P4_sales_transit_res", "서울 주거"),
                          ("P4_sales_transit_com", "서울 상업")],
           "ln_stores": [("P4_sales_emp_all", "서울 전체(고용·사업체 요인)")],
           "ln_dist_tram": []}
    rows = []
    for _, r in est.iterrows():
        refs = ref[r.term] or [(None, "")]
        for key, lab in refs:
            rows.append({"term": r.term, "our_coef": round(r.coef, 4), "our_se": round(r.se_cluster, 4),
                         "our_t": round(r.t, 2), "paper": key or "",
                         "paper_value": P(lit, key) if key else np.nan, "paper_segment": lab})
    out = pd.DataFrame(rows)
    out["r2_ours"] = round(r2, 3)
    # P3: 승하차 인원 탄력성(유도값) 비교는 정거장 수요예측이 들어오면 사용
    return out


# ------------------------------------------------------------------ 4. tram scenario
CAT_EFFECT_KEY = {"I2": "P2_POI_eatdrink", "G2": "P2_POI_retail", "L1": "P2_POI_property"}


C_LAG = 6   # literature_params.csv 의 P2_lag_start_yr 로 덮어씀


def ramp(years_after):
    """(사용 안 함) 예전 영국식 램프. 지금은 tram_effect.profile (대전 1호선 연차별 모양) 사용."""
    y = np.asarray(years_after, float)
    return np.where(y <= 0, 0.0, np.where(y < C_LAG, 0.5 * y / (C_LAG - 1), 1.0))


def daejeon_effect(lit):
    """대전 1호선 1단계 역 500m 지가 효과(log). analyze_landprice.py 결과가 있으면 그 값, 없으면 literature_params 값."""
    f = C.OUT_DIR / "landprice_effects.csv"
    if f.exists():
        E = pd.read_csv(f, encoding="utf-8-sig")
        r = E[E.analysis.str.contains("1호선 1단계")]
        if len(r) and pd.notna(r.effect_pct.iloc[0]):
            return float(np.log1p(r.effect_pct.iloc[0] / 100)), "outputs/landprice_effects.csv"
    return P(lit, "DJ_line1_land_500m"), "literature_params.csv"


def scenario(df, lit, tram_riders=None):
    global C_LAG
    C_LAG = int(P(lit, "P2_lag_start_yr"))
    base_months = df[df.year == 2019]                        # 코로나 이전 기준
    b = base_months.groupby("area_id").agg(baseline_sales=("sales", "mean")).reset_index()
    e = df.drop_duplicates("area_id").merge(b, on="area_id")

    # 트램 효과 = 정거장 500m 안 × 시나리오 수준(tram_effect.levels) × 업종 비율
    #   예전의 고베(P6) 중심/주변 가중·소비 상한, 영국 버스밀도 조절계수는 대전 근거가 없어 제외
    import tram_effect as TE
    L = TE.levels()
    in500 = e.in_tram_500.values == 1
    ratio = e.cat.map(TE.cat_ratio).values
    for sc in TE.SCEN:
        e[f"eff_{sc}"] = np.where(in500, L[sc]["log"] * ratio, 0.0)
    TE.write_table()
    print("  시나리오 수준(개통 초기 1~4년, 땅값 기준): " +
          ", ".join(f"{TE.LABEL[s]} {L[s]['pct']:+.1f}%" for s in TE.SCEN), flush=True)

    # (선택) P3 승하차 탄력성: 정거장 일 승하차 예측치가 있으면 base 에 가산
    if tram_riders is not None:
        el = 0.109 * 80422 / 27690   # P3 Table 9 계수 × 평균승하차 / 평균매출(유도) ≈ 0.32
        r = e.nearest_tram.map(tram_riders).fillna(0)
        e["eff_p3_riders"] = np.where(in500, np.log1p(el * r / 80422), 0.0)

    for yrs in (3, 6, 10):
        w = float(TE.profile([yrs])[0])           # 대전 1호선 연차별 효과 모양 (초기에 크고 점점 줄어듦)
        for sc in ("low", "base", "high"):
            e[f"sales_{sc}_y{yrs}"] = (e.baseline_sales * np.exp(e[f"eff_{sc}"] * w)).round(0)
    keep = ["area_id", "zone", "zone_type", "cat", "cat_name", "nearest_tram", "is_transfer_station",
            "dist_tram_m", "in_tram_500", "bus_dense", "baseline_sales", "eff_low", "eff_base", "eff_high"] + \
           [c for c in e.columns if c.startswith("sales_") and "_y" in c]
    sc_df = e[keep].copy()
    for c in ("eff_low", "eff_base", "eff_high"):
        sc_df[c] = sc_df[c].round(4)

    v = sc_df[sc_df.baseline_sales.notna()]
    summ = v.groupby(["zone", "zone_type"]).apply(lambda g: pd.Series({
        "areas_in_500m_share": g.in_tram_500.mean(),
        "baseline_sales_manwon": g.baseline_sales.sum(),
        **{f"chg_{s}_y{y}": g[f"sales_{s}_y{y}"].sum() / g.baseline_sales.sum() - 1
           for s in ("low", "base", "high") for y in (3, 6, 10)}}), include_groups=False).reset_index()
    return sc_df, summ


# ------------------------------------------------------------------ main
def main():
    print("1/4 데이터 읽기 ...", flush=True)
    df, lit = load()
    synthetic, r2diag, diag_msg = diagnose_target(df)

    print("2/4 ML 학습 (1분 안팎 걸림) ...", flush=True)
    res_all, imp_all = run_ml(df)
    res_noleak, imp_noleak = run_ml(df, drop=LEAKY)
    print("[ml] all features      ", {k: round(v, 3) if isinstance(v, float) else v for k, v in res_all.items()})
    print("[ml] without n_same_type", {k: round(v, 3) if isinstance(v, float) else v for k, v in res_noleak.items()})
    pd.DataFrame({"all_features": imp_all, "without_leaky": imp_noleak}).round(4) \
      .to_csv(C.OUT_DIR / "feature_importance.csv", encoding="utf-8-sig")

    print("2b 격자 잔차(resid_pct) 계산 ...", flush=True)
    resid, engine = cell_residuals(df)
    resid.to_csv(C.OUT_DIR / "cell_resid.csv", index=False, encoding="utf-8-sig")

    print("3/4 논문 계수 벤치마크 ...", flush=True)
    bench = benchmark(df, lit)
    bench.to_csv(C.OUT_DIR / "benchmark_vs_papers.csv", index=False, encoding="utf-8-sig")
    print("[benchmark]\n", bench.to_string(index=False))

    print("4/4 트램 개통 시나리오 ...", flush=True)
    sc_df, summ = scenario(df, lit)
    sc_df.to_csv(C.OUT_DIR / "scenario_tram_uplift.csv", index=False, encoding="utf-8-sig")
    summ.round(4).to_csv(C.OUT_DIR / "scenario_summary_by_zone.csv", index=False, encoding="utf-8-sig")
    print("[scenario]\n", summ.round(4).to_string(index=False))

    json.dump({"target_synthetic": bool(synthetic), "target_diag_r2": round(r2diag, 4), "target_diag": diag_msg,
               "ml_all_features": res_all, "ml_without_leaky": res_noleak, "open_year": OPEN_YEAR},
              open(C.OUT_DIR / "metrics.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=float)
    print(f"완료 → {C.OUT_DIR}")


if __name__ == "__main__":
    main()
