"""D. 상권 예측 모델 비교 + 2030 트램 개통 시나리오 예측.

예측 대상 (매출은 합성값이라 제외)
- 지가: 상권 공시지가 지수 (연, 1990~2026)                     → 1·2·3년 뒤
- 점포: 대전 안 점포 비중 지수 (분기, 2015-12~2026-06, 단절 보정) → 4·8분기(1·2년) 뒤

모델
- 기준선 naive  : 마지막 값 그대로
- drift        : 최근 5년(20분기) 평균 변화율로 연장
- ARIMA(p,1,0) : 상권별 log 차분 자기회귀 (p=1·2 중 AIC), 직접 구현 → 추가 설치 없음
- ML           : 전 상권 한 모델 (LightGBM 있으면 LightGBM, 없으면 sklearn HistGradientBoosting)
                 특징 = 최근 1·2·3·5기 변화, 대전 전체 변화, 대전 대비 수준, 원도심 여부, 트램 거리, 1호선 역세권 여부, 예측 기간
검증
- 시간 순서 분할: 기준 시점 t 까지 자료로만 학습 → t+h 예측 (지가 t=2010~2023, 점포 분기 기준점 16개~)
- 상권 단위 분할(ML): 같은 기준 시점에서 상권을 5묶음으로 나눠, 학습에 없던 상권 예측
- 지표: RMSE(log, ≈ % 오차), WAPE(수준, |오차| 합 / 실제 합)

출력 (outputs/)
- forecast_backtest.csv, forecast_backtest.png
- forecast_land.csv  : 상권 × 2026~2034 지가 지수 기준 경로·80% 구간·트램 시나리오(낮음/기본/높음)
- forecast_store.csv : 상권 × 2026~2034 점포 비중 지수 (같은 형식)
- forecast_paths.png : 대표 상권 예측 그림
"""
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

import config as C

OPEN_YEAR = 2030
END_YEAR = 2034
STORE_EXCLUDE = {"A12"}      # 도룡동: 2021 신세계 입점점포 등록으로 점포 비중 +600% → 점포 예측 검증·예측에서 제외
LAG_START = 6               # (예전 영국식 램프, 지금은 tram_effect.profile 사용)


def ramp(years_after):
    y = np.asarray(years_after, float)
    return np.where(y <= 0, 0.0, np.where(y < LAG_START, 0.5 * y / (LAG_START - 1), 1.0))


def make_ml():
    try:
        from lightgbm import LGBMRegressor
        return LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=10,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=42), "LightGBM"
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_depth=3, min_samples_leaf=10,
                                             random_state=42), "GBM(sklearn)"


# ------------------------------------------------------------------ 시계열 모델 (log 수준 기준)
def f_naive(y, h):
    return y[-1]


def f_drift(y, h, w=5):
    d = np.diff(y[-(w + 1):])
    return y[-1] + h * d.mean() if len(d) else y[-1]


def ar_fit(d, p):
    X = np.column_stack([np.ones(len(d) - p)] + [d[p - k - 1:len(d) - k - 1] for k in range(p)])
    yv = d[p:]
    b, *_ = np.linalg.lstsq(X, yv, rcond=None)
    rss = ((yv - X @ b) ** 2).sum()
    aic = len(yv) * np.log(rss / len(yv) + 1e-12) + 2 * (p + 1)
    return b, aic


def f_arima(y, h, pmax=2):
    d = np.diff(y)
    best = None
    for p in range(1, pmax + 1):
        if len(d) < 3 * p + 4:
            continue
        b, aic = ar_fit(d, p)
        if best is None or aic < best[1]:
            best = (b, aic, p)
    if best is None:
        return f_drift(y, h)
    b, _, p = best
    hist = list(d)
    lvl = y[-1]
    for _ in range(h):
        nxt = b[0] + sum(b[k + 1] * hist[-k - 1] for k in range(p))
        nxt = float(np.clip(nxt, -0.3, 0.3))
        hist.append(nxt); lvl += nxt
    return lvl


TS_MODELS = {"naive(작년값)": f_naive, "drift(최근 추세)": f_drift, "ARIMA(p,1,0)": f_arima}


# ------------------------------------------------------------------ 자료
def land_series():
    L = pd.read_csv(C.OUT_DIR / "landprice_area_panel.csv", encoding="utf-8-sig")
    W = np.log(L.pivot(index="year", columns="code", values="idx"))
    return W   # index=연도, 열=상권+ALL


def store_series():
    T = pd.read_csv(C.OUT_DIR / "store_panel.csv", dtype={"period": str}, encoding="utf-8-sig")
    T = T.sort_values(["code", "period"])
    r = (T.share / T.groupby("code").share.shift()).where(T.data_break == 0, 1.0).fillna(1.0)
    T["chain"] = r.groupby(T.code).cumprod()
    W = np.log(T.pivot(index="period", columns="code", values="chain"))
    return W


def static_feats():
    a = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig").set_index("code")
    e = pd.read_csv(C.OUT_DIR / "features_ext.csv", encoding="utf-8-sig")
    ds = pd.read_csv(C.OUT_DIR / "daejeon_tram_area_dataset.csv", encoding="utf-8-sig").drop_duplicates("area_id")
    e = e.merge(ds[["area_id", "dist_tram_m"]], on="area_id")
    S = pd.DataFrame({"old_town": a.type.str.contains("원도심").astype(int),
                      "line1": a.line1_station.notna().astype(int) if "line1_station" in a else 0})
    S["tram_in500"] = e.groupby("zone").in_tram_500.mean()
    S["tram_dist"] = e.groupby("zone").dist_tram_m.median()
    return S.fillna(0)


def ml_rows(W, S, t_idx, h, per_year):
    """기준 시점 위치 t_idx 에서의 특징 (상권별 한 줄)."""
    rows = []
    city = W["ALL"] if "ALL" in W else W.mean(axis=1)
    for c in S.index:
        y = W[c].values[: t_idx + 1]
        if np.isnan(y[-1]) or np.isnan(y[-(max(5, per_year) + 1):]).any():
            continue
        cy = city.values[: t_idx + 1]
        rows.append({"code": c, "h": h, "lvl_rel": y[-1] - cy[-1],
                     **{f"chg{k}": y[-1] - y[-1 - k] for k in (1, 2, 3, 5)},
                     "chg_y": y[-1] - y[-1 - per_year], "city_chg1": cy[-1] - cy[-2],
                     "city_chg_y": cy[-1] - cy[-1 - per_year], **S.loc[c].to_dict()})
    return pd.DataFrame(rows)


def backtest(W, S, target, horizons, origins, per_year):
    codes = [c for c in S.index if c in W.columns]
    res = []
    ml, ml_name = make_ml()
    for t in origins:
        for h in horizons:
            if t + h >= len(W):
                continue
            # 시계열 모델
            for c in codes:
                y = W[c].values[: t + 1]
                yt = W[c].values[t + h]
                if np.isnan(yt) or np.isnan(y[-6:]).any():
                    continue
                y = y[~np.isnan(y)]
                for name, f in TS_MODELS.items():
                    w = 5 * per_year if name.startswith("drift") else None
                    p = f(y, h, w) if w else f(y, h)
                    res.append({"target": target, "model": name, "origin": W.index[t], "h": h, "code": c,
                                "pred": p - y[-1], "true": yt - y[-1]})
            # ML: t 시점까지 끝난 학습 표본 (기준 s, s+h ≤ t)
            tr = []
            for s in range(max(6, per_year * 5), t - h + 1):
                X = ml_rows(W, S, s, h, per_year)
                if len(X):
                    X["y"] = [W[c].values[s + h] - W[c].values[s] for c in X.code]
                    tr.append(X)
            if not tr:
                continue
            TR = pd.concat(tr).dropna(subset=["y"])
            TE = ml_rows(W, S, t, h, per_year)
            TE["y"] = [W[c].values[t + h] - W[c].values[t] for c in TE.code]
            TE = TE.dropna(subset=["y"])
            if len(TR) < 30 or not len(TE):
                continue
            fx = [c for c in TR.columns if c not in ("code", "y")]
            ml.fit(TR[fx], TR.y)
            for c, p, yv in zip(TE.code, ml.predict(TE[fx]), TE.y):
                res.append({"target": target, "model": ml_name, "origin": W.index[t], "h": h, "code": c,
                            "pred": p, "true": yv})
            # 상권 단위 분할: 학습에서 빠진 상권 예측
            g = GroupKFold(n_splits=5)
            for tr_i, te_i in g.split(TE, groups=TE.code):
                te_codes = set(TE.code.iloc[te_i])
                TRs = TR[~TR.code.isin(te_codes)]
                ml.fit(TRs[fx], TRs.y)
                sub = TE.iloc[te_i]
                for c, p, yv in zip(sub.code, ml.predict(sub[fx]), sub.y):
                    res.append({"target": target, "model": ml_name + " · 상권 분할", "origin": W.index[t], "h": h,
                                "code": c, "pred": p, "true": yv})
    return pd.DataFrame(res), ml_name


def score(R):
    R = R.assign(err=R.pred - R.true, lvl_true=np.exp(R.true), lvl_pred=np.exp(R.pred))
    g = R.groupby(["target", "model", "h"])
    out = g.apply(lambda d: pd.Series({
        "rmse_log_pct": np.sqrt((d.err ** 2).mean()) * 100,
        "wape_pct": (d.lvl_pred - d.lvl_true).abs().sum() / d.lvl_true.sum() * 100,
        "bias_pct": d.err.mean() * 100,
        "dir_acc": ((np.sign(d.pred) == np.sign(d.true)) | (d.true.abs() < 0.005)).mean(),
        "n": len(d)}), include_groups=False).reset_index()
    return out.round(3)


def tram_effects():
    """상권별 트램 효과(log) — tram_effect.py 의 시나리오 수준 하나로 통일.
    지가 = 정거장 500m 셀 비율 × 수준, 점포 = scenario_tram_uplift 상권 평균(업종 비율 반영)."""
    import tram_effect as TE
    L = TE.levels()
    S = static_feats()
    land = pd.DataFrame({s: S.tram_in500 * L[s]["log"] for s in TE.SCEN})
    sc = pd.read_csv(C.OUT_DIR / "scenario_tram_uplift.csv", encoding="utf-8-sig")
    store = sc.groupby("zone")[["eff_low", "eff_base", "eff_high"]].mean()
    store.columns = ["low", "base", "high"]
    return land, store.reindex(S.index).fillna(0)


def project(W, R_best, best, per_year, last_label, eff, label):
    """2034년까지 기준 경로 + 80% 구간 + 트램 시나리오."""
    import tram_effect as TE
    codes = [c for c in eff.index if c in W.columns]
    sd_h = R_best.assign(e=R_best.pred - R_best.true).groupby("h").e.std()
    sd1 = float(sd_h.iloc[0] / np.sqrt(sd_h.index[0])) if len(sd_h) else 0.05
    start_year = int(str(last_label)[:4])
    out = []
    f = TS_MODELS.get(best, f_drift)
    for c in codes:
        y = W[c].dropna().values
        for yr in range(start_year, END_YEAR + 1):
            h = (yr - start_year) * per_year
            if h == 0:
                lvl = y[-1]
            else:
                lvl = f(y, h, 5 * per_year) if best.startswith("drift") else f(y, h)
            sd = sd1 * np.sqrt(max(h, 0))
            row = {"code": c, "year": yr, "base_path": np.exp(lvl) * 100 / np.exp(y[-1]) if False else np.exp(lvl),
                   "lo80": np.exp(lvl - 1.2816 * sd), "hi80": np.exp(lvl + 1.2816 * sd)}
            w = float(TE.profile([yr - OPEN_YEAR])[0])   # 대전 1호선 연차별 모양
            for s in ("low", "base", "high"):
                row[f"tram_{s}"] = np.exp(lvl + eff.loc[c, s] * w)
            out.append(row)
    P = pd.DataFrame(out)
    # 지수를 '마지막 관측 = 100' 으로 다시 맞춰 읽기 쉽게
    last = P[P.year == start_year].set_index("code").base_path
    for col in ("base_path", "lo80", "hi80", "tram_low", "tram_base", "tram_high"):
        P[col] = (P[col] / P.code.map(last) * 100).round(2)
    P["tram_gain_base_pct"] = ((P.tram_base / P.base_path - 1) * 100).round(2)   # % (지수 포인트 아님)
    P.insert(2, "target", label)
    return P


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

    S = static_feats()
    WL = land_series()
    WS = store_series()
    print("1/3 지가 예측 검증 (기준 2010~2023년, 1·2·3년 뒤) ...", flush=True)
    l_orig = [WL.index.get_loc(y) for y in range(2010, 2024)]
    RL, ml_name = backtest(WL, S, "지가", [1, 2, 3], l_orig, per_year=1)
    print("2/3 점포 비중 예측 검증 (분기, 4·8분기 뒤) ...", flush=True)
    s_orig = list(range(16, len(WS) - 4))
    S_st = S.drop(index=[c for c in STORE_EXCLUDE if c in S.index])
    RS, _ = backtest(WS, S_st, "점포 비중", [4, 8], s_orig, per_year=4)
    R = pd.concat([RL, RS])
    R.to_csv(C.OUT_DIR / "forecast_backtest_rows.csv", index=False, encoding="utf-8-sig")
    B = score(R)
    B.to_csv(C.OUT_DIR / "forecast_backtest.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print("\n[검증] RMSE(log, %) 낮을수록 좋음\n",
          B.pivot_table(index=["target", "model"], columns="h", values="rmse_log_pct").round(2).to_string())
    print("\n[검증] WAPE(%)\n", B.pivot_table(index=["target", "model"], columns="h", values="wape_pct").round(2).to_string())

    # 장기 경로용 모델: 시계열 모델 중 평균 RMSE 최소 (ML 은 1~3년 직접 예측용이라 2034 경로엔 사용 안 함)
    def pick(target):
        b = B[(B.target == target) & B.model.isin(TS_MODELS)].groupby("model").rmse_log_pct.mean()
        return b.idxmin()

    best_l, best_s = pick("지가"), pick("점포 비중")
    print(f"\n장기 경로 모델: 지가 = {best_l}, 점포 비중 = {best_s}")
    print(f"3/3 {OPEN_YEAR} 트램 개통 시나리오 예측 (~2034) ...", flush=True)
    eland, estore = tram_effects()
    PL = project(WL, RL[RL.model == best_l], best_l, 1, WL.index[-1], eland, "지가 지수")
    PS = project(WS, RS[RS.model == best_s], best_s, 4, WS.index[-1], estore.drop(index=list(STORE_EXCLUDE)),
                 "점포 비중 지수")
    names = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig").set_index("code").name
    for P in (PL, PS):
        P.insert(1, "name", P.code.map(names))
    PL.to_csv(C.OUT_DIR / "forecast_land.csv", index=False, encoding="utf-8-sig")
    PS.to_csv(C.OUT_DIR / "forecast_store.csv", index=False, encoding="utf-8-sig")
    s34 = PL[PL.year == END_YEAR].set_index("name")[["base_path", "lo80", "hi80", "tram_base", "tram_gain_base_pct"]]
    print(f"\n[{END_YEAR} 지가 지수, 2026=100] 트램 기본 효과 큰 순\n",
          s34.sort_values("tram_gain_base_pct", ascending=False).head(8).to_string())

    # 그림 1: 검증
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for ax, tg in zip(axes, ["지가", "점포 비중"]):
        b = B[B.target == tg]
        for m, g in b.groupby("model"):
            ax.plot(g.h, g.rmse_log_pct, "o-", label=m)
        ax.set_title(f"{tg}: 예측 오차 RMSE(%) — 낮을수록 좋음")
        ax.set_xlabel("예측 기간 (" + ("년" if tg == "지가" else "분기") + ")"); ax.legend(fontsize=8)
        ax.set_xticks(sorted(b.h.unique()))
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "forecast_backtest.png", dpi=130); plt.close()

    # 그림 2: 대표 상권 경로
    pick_codes = ["A03", "A04", "A13", "A18", "A07", "A17"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharey=False)
    for ax, c in zip(axes.flat, pick_codes):
        hist = np.exp(WL[c].loc[2010:] - WL[c].iloc[-1]) * 100
        ax.plot(hist.index, hist.values, c="k", lw=1.5, label="실제")
        p = PL[PL.code == c]
        ax.fill_between(p.year, p.lo80, p.hi80, color="gray", alpha=.2, label="80% 구간")
        ax.plot(p.year, p.base_path, c="gray", ls="--", label=f"기준 ({best_l})")
        ax.plot(p.year, p.tram_base, c="C3", label="트램 기본")
        ax.plot(p.year, p.tram_high, c="C1", ls=":", label="트램 높음")
        ax.axvline(OPEN_YEAR, c="C0", lw=.8)
        ax.set_title(f"{c} {names[c]}", fontsize=10); ax.legend(fontsize=7)
    fig.suptitle(f"상권 공시지가 지수 예측 (2026 = 100, 파란 선 = {OPEN_YEAR} 트램 개통)")
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "forecast_paths.png", dpi=130); plt.close()
    print("→ outputs/forecast_backtest.csv/.png, forecast_land.csv, forecast_store.csv, forecast_paths.png")


if __name__ == "__main__":
    main()
