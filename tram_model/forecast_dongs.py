"""행정동 82개 예측: 공시지가 지수·점포 비중 지수 2026→2034 + 2030 트램 개통 시나리오 (forecast_areas.py 의 행정동판)

입력: outputs/dong_year_panel.csv, outputs/dong_panel_store.csv, outputs/dong_profile.csv, tram_effect.py (수준·시간 경로)
출력: outputs/dong_forecast_backtest.csv, dong_forecast_land.csv, dong_forecast_store.csv (forecast_land.csv 와 같은 열, code = dong_id)
모델: naive / drift(최근 5년) / ARIMA(p,1,0) 직접 구현 (ML 은 제외 — 상권 검증에서 더 나빴고 sklearn 의존 제거)
트램 효과: 지가 = 정거장 500m 안 점포 비율(tram500_share) × 시나리오 수준(log) × 대전 1호선 연차 모양
          점포 = 지가 효과 × 업종 비율 가중(음식·소매·기타, Lan 2025 비율) — 상권 scenario_tram_uplift 와 같은 논리
"""
import numpy as np
import pandas as pd

import config as C
import tram_effect as TE

OPEN_YEAR, END_YEAR = 2030, 2034
STORE_EXCLUDE = {"3020055000"}     # 신성동 (도룡동 신세계 입점 등록 왜곡)


def f_naive(y, h, w=None): return y[-1]
def f_drift(y, h, w=5):
    d = np.diff(y[-(w + 1):]); return y[-1] + h * d.mean() if len(d) else y[-1]
def _ar_fit(d, p):
    X = np.column_stack([np.ones(len(d) - p)] + [d[p - k - 1:len(d) - k - 1] for k in range(p)]); yv = d[p:]
    b, *_ = np.linalg.lstsq(X, yv, rcond=None); rss = ((yv - X @ b) ** 2).sum()
    return b, len(yv) * np.log(rss / len(yv) + 1e-12) + 2 * (p + 1)
def f_arima(y, h, w=None, pmax=2):
    d = np.diff(y); best = None
    for p in range(1, pmax + 1):
        if len(d) < 3 * p + 4: continue
        b, aic = _ar_fit(d, p)
        if best is None or aic < best[1]: best = (b, aic, p)
    if best is None: return f_drift(y, h)
    b, _, p = best; hist = list(d); lvl = y[-1]
    for _ in range(h):
        nxt = float(np.clip(b[0] + sum(b[k + 1] * hist[-k - 1] for k in range(p)), -0.3, 0.3)); hist.append(nxt); lvl += nxt
    return lvl
TS = {"naive(작년값)": f_naive, "drift(최근 추세)": f_drift, "ARIMA(p,1,0)": f_arima}


def land_series(P):
    return np.log(P.pivot(index="year", columns="dong_id", values="land_idx"))

def store_series():
    T = pd.read_csv(C.OUT_DIR / "dong_panel_store.csv", dtype={"period": str, "dong_id": str}, encoding="utf-8-sig").sort_values(["dong_id", "period"])
    r = (T.share / T.groupby("dong_id").share.shift()).where(T.data_break == 0, 1.0).fillna(1.0)
    T["chain"] = r.groupby(T.dong_id).cumprod()
    return np.log(T.pivot(index="period", columns="dong_id", values="chain"))


def backtest(W, target, horizons, origins, per_year):
    res = []
    for t in origins:
        for h in horizons:
            if t + h >= len(W): continue
            for c in W.columns:
                y = W[c].values[: t + 1]; yt = W[c].values[t + h]
                if np.isnan(yt) or np.isnan(y[-6:]).any(): continue
                y = y[~np.isnan(y)]
                for name, f in TS.items():
                    p = f(y, h, 5 * per_year)
                    res.append(dict(target=target, model=name, origin=W.index[t], h=h, code=c, pred=p - y[-1], true=yt - y[-1]))
    return pd.DataFrame(res)

def score(R):
    R = R.assign(err=R.pred - R.true)
    return R.groupby(["target", "model", "h"]).apply(lambda d: pd.Series({
        "rmse_log_pct": np.sqrt((d.err ** 2).mean()) * 100, "bias_pct": d.err.mean() * 100,
        "dir_acc": ((np.sign(d.pred) == np.sign(d.true)) | (d.true.abs() < 0.005)).mean(), "n": len(d)}), include_groups=False).reset_index().round(3)


def project(W, R_best, best, per_year, eff, label):
    sd_h = R_best.assign(e=R_best.pred - R_best.true).groupby("h").e.std()
    sd1 = float(sd_h.iloc[0] / np.sqrt(sd_h.index[0])) if len(sd_h) else 0.05
    start_year = int(str(W.index[-1])[:4]); f = TS[best]; out = []
    for c in eff.index:
        if c not in W.columns: continue
        y = W[c].dropna().values
        for yr in range(start_year, END_YEAR + 1):
            h = (yr - start_year) * per_year
            lvl = y[-1] if h == 0 else f(y, h, 5 * per_year)
            sd = sd1 * np.sqrt(max(h, 0))
            row = dict(code=c, year=yr, base_path=np.exp(lvl), lo80=np.exp(lvl - 1.2816 * sd), hi80=np.exp(lvl + 1.2816 * sd))
            w = float(TE.profile([yr - OPEN_YEAR])[0])
            for s in TE.SCEN: row[f"tram_{s}"] = np.exp(lvl + eff.loc[c, s] * w)
            out.append(row)
    P = pd.DataFrame(out); last = P[P.year == start_year].set_index("code").base_path
    for col in ("base_path", "lo80", "hi80", "tram_low", "tram_base", "tram_high"): P[col] = (P[col] / P.code.map(last) * 100).round(2)
    P["tram_gain_base_pct"] = ((P.tram_base / P.base_path - 1) * 100).round(2); P.insert(2, "target", label)
    return P


def main():
    P = pd.read_csv(C.OUT_DIR / "dong_year_panel.csv", dtype={"dong_id": str}, encoding="utf-8-sig")
    prof = pd.read_csv(C.OUT_DIR / "dong_profile.csv", dtype={"id": str}, encoding="utf-8-sig").set_index("id")
    WL, WS = land_series(P), store_series()
    print("1/3 지가 검증 (기준 2010~2023, 1·2·3년) ...", flush=True)
    RL = backtest(WL, "지가", [1, 2, 3], [i for i, y in enumerate(WL.index) if 2010 <= y <= 2023], 1)
    print("2/3 점포 검증 (분기 기준점, 4·8분기) ...", flush=True)
    WSx = WS.drop(columns=[c for c in STORE_EXCLUDE if c in WS.columns])
    RS = backtest(WSx, "점포 비중", [4, 8], list(range(16, len(WSx) - 4)), 4)
    B = score(pd.concat([RL, RS])); B.to_csv(C.OUT_DIR / "dong_forecast_backtest.csv", index=False, encoding="utf-8-sig")
    print(B.pivot_table(index=["target", "model"], columns="h", values="rmse_log_pct").round(2).to_string())
    best_l = B[B.target == "지가"].groupby("model").rmse_log_pct.mean().idxmin()
    best_s = B[B.target == "점포 비중"].groupby("model").rmse_log_pct.mean().idxmin()
    print(f"장기 경로 모델: 지가 = {best_l}, 점포 비중 = {best_s}")
    # 트램 효과 (log)
    L = TE.levels(); share = prof.tram500_share.fillna(0)
    last_store = P.sort_values("year").groupby("dong_id").tail(1).set_index("dong_id")
    cat_w = (last_store.food_ratio.fillna(0) * TE.cat_ratio("I2") + last_store.retail_ratio.fillna(0) * TE.cat_ratio("G2")
             + (1 - last_store.food_ratio.fillna(0) - last_store.retail_ratio.fillna(0)) * TE.cat_ratio("X")).reindex(share.index).fillna(0.5)
    eland = pd.DataFrame({s: share * L[s]["log"] for s in TE.SCEN})
    estore = pd.DataFrame({s: share * L[s]["log"] * cat_w for s in TE.SCEN})
    print("3/3 2034 경로 ...", flush=True)
    PL = project(WL, RL[RL.model == best_l], best_l, 1, eland, "지가 지수")
    PS = project(WSx, RS[RS.model == best_s], best_s, 4, estore.drop(index=[c for c in STORE_EXCLUDE if c in estore.index]), "점포 비중 지수")
    names = prof.name
    for X in (PL, PS): X.insert(1, "name", X.code.map(names))
    PL.to_csv(C.OUT_DIR / "dong_forecast_land.csv", index=False, encoding="utf-8-sig")
    PS.to_csv(C.OUT_DIR / "dong_forecast_store.csv", index=False, encoding="utf-8-sig")
    s34 = PL[PL.year == END_YEAR].set_index("name")[["base_path", "lo80", "hi80", "tram_base", "tram_gain_base_pct"]]
    print(f"[{END_YEAR} 지가 지수, 2026=100] 트램 기본 효과 큰 순\n", s34.sort_values("tram_gain_base_pct", ascending=False).head(8).to_string())
    print("기준 경로 2034 분포:", s34.base_path.describe().round(1)[["min", "25%", "50%", "75%", "max"]].to_dict())


if __name__ == "__main__":
    main()
