"""해외 트램·경전철 개통 전후 효과 메타분석.

입력  : data/literature_tram_meta.csv  (연구별 효과 1행)
출력  : outputs/tram_meta_estimates.csv   연구별 log-point 효과·SE (변환 결과)
        outputs/tram_meta_summary.csv     묶음별 랜덤효과 평균·95% CI·예측구간·I²
        outputs/tram_meta_forest.png      숲 그림 (대전 1호선 값 함께 표시)

효과 단위 통일
- effect_scale = log  : 회귀계수(log point) 그대로
- effect_scale = pct  : 퍼센트 → ln(1 + p/100)
정밀도 (먼저 있는 것 사용)
- se                         : 같은 scale 의 표준오차 (pct 면 log 로 근사 변환)
- ci_low, ci_high            : 95% 구간 → (ln(1+hi) - ln(1+lo)) / (2 × 1.96)
- t_stat                     : SE = |b| / |t|
- p_value                    : SE = |b| / z(1 - p/2)
정밀도가 없거나 별표만 있는 행은 pooled 에서 빼고 표에만 남김.

랜덤효과: DerSimonian–Laird, 예측구간은 t(k-2) (Higgins 2009).
role = reference 인 행(대전 1호선)은 풀링에 넣지 않고 그림에 비교선으로만 그림.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
SRC = HERE / "data" / "literature_tram_meta.csv"
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)
Z = stats.norm.ppf(0.975)


def to_log(v, scale):
    if pd.isna(v):
        return np.nan
    return np.log1p(v / 100.0) if scale == "pct" else float(v)


def row_se(r):
    b = r["b_log"]
    sc = r["effect_scale"]
    if pd.notna(r.get("se")):
        if sc == "pct":  # delta method: d ln(1+p)/dp = 1/(1+p)
            return (r["se"] / 100.0) / (1 + r["effect"] / 100.0)
        return float(r["se"])
    if pd.notna(r.get("ci_low")) and pd.notna(r.get("ci_high")):
        return (to_log(r["ci_high"], sc) - to_log(r["ci_low"], sc)) / (2 * Z)
    if pd.notna(r.get("t_stat")) and r["t_stat"] != 0:
        return abs(b) / abs(r["t_stat"])
    if pd.notna(r.get("p_value")) and 0 < r["p_value"] < 1 and b != 0:
        return abs(b) / stats.norm.ppf(1 - r["p_value"] / 2)
    return np.nan


def dl_pool(b, se):
    """DerSimonian–Laird 랜덤효과."""
    b, se = np.asarray(b, float), np.asarray(se, float)
    k = len(b)
    w = 1 / se**2
    fe = np.sum(w * b) / np.sum(w)
    q = np.sum(w * (b - fe) ** 2)
    c = np.sum(w) - np.sum(w**2) / np.sum(w)
    tau2 = max(0.0, (q - (k - 1)) / c) if k > 1 else 0.0
    wr = 1 / (se**2 + tau2)
    mu = np.sum(wr * b) / np.sum(wr)
    se_mu = np.sqrt(1 / np.sum(wr))
    i2 = max(0.0, (q - (k - 1)) / q) if q > 0 else 0.0
    if k >= 3:
        tcrit = stats.t.ppf(0.975, k - 2)
        half = tcrit * np.sqrt(tau2 + se_mu**2)
        pi = (mu - half, mu + half)
    else:
        pi = (np.nan, np.nan)
    return dict(k=k, mu=mu, se=se_mu, ci_low=mu - Z * se_mu, ci_high=mu + Z * se_mu,
                pi_low=pi[0], pi_high=pi[1], tau2=tau2, I2=i2, Q=q)


def pct(x):
    return (np.exp(x) - 1) * 100


def main():
    df = pd.read_csv(SRC, encoding="utf-8-sig")
    # 대전 기준값(role=reference)은 결과 파일에서 읽어 최신값으로 (analyze_landprice → landprice_effects.csv)
    eff = OUT / "landprice_effects.csv"
    if eff.exists():
        E = pd.read_csv(eff, encoding="utf-8-sig")
        for rid, pat in (("DJ1", "1호선 1단계"), ("DJ12", "1·2단계 합산")):
            r = E[E.analysis.str.contains(pat, regex=False)]
            if len(r) and (df.id == rid).any():
                lo, hi = [float(x) for x in str(r.ci95.iloc[0]).replace(" ", "").split("~")]
                df.loc[df.id == rid, ["effect", "ci_low", "ci_high"]] = [float(r.effect_pct.iloc[0]), lo, hi]
    for c in ["effect", "se", "ci_low", "ci_high", "t_stat", "p_value"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = np.nan
    df["role"] = df.get("role", "study").fillna("study")
    df["include"] = df.get("include", "yes").fillna("yes").str.lower()
    df["b_log"] = [to_log(v, s) for v, s in zip(df.effect, df.effect_scale)]
    df["se_log"] = df.apply(row_se, axis=1)
    df["pooled"] = (df.role == "study") & (df.include == "yes") & df.se_log.notna() & df.b_log.notna()
    df["effect_pct"] = pct(df.b_log)
    df["ci_low_pct"] = pct(df.b_log - Z * df.se_log)
    df["ci_high_pct"] = pct(df.b_log + Z * df.se_log)
    given = (df.effect_scale == "pct") & df.ci_low.notna() & df.ci_high.notna()
    df.loc[given, "ci_low_pct"] = df.loc[given, "ci_low"]     # 원래 보고된 구간 그대로 표시
    df.loc[given, "ci_high_pct"] = df.loc[given, "ci_high"]
    df.to_csv(OUT / "tram_meta_estimates.csv", index=False, encoding="utf-8-sig")

    pool = df[df.pooled]
    st = pool[(pool.outcome_class == "value") & (pool.phase == "operation")]   # 기본 묶음
    df["main_pool"] = df.index.isin(st.index)
    df.to_csv(OUT / "tram_meta_estimates.csv", index=False, encoding="utf-8-sig")
    yes = lambda s: s.astype(str).str.lower() == "yes"
    groups = {
        "전체 (트램·경전철)": st,
        "트램만": st[st["mode"].str.contains("tram|streetcar", case=False, na=False)],
        "동료심사 논문만": st[yes(st.peer_reviewed)],
        "중소도시만": st[yes(st.city_small)],
        "주택 가격만": st[st.outcome == "residential"],
        "공사 기간 (별도)": pool[(pool.outcome_class == "value") & (pool.phase == "construction")],
        "점포·창업 (별도, 단위 다름)": pool[pool.outcome_class == "business"],
    }
    rows = []
    for name, g in groups.items():
        if len(g) < 2:
            continue
        r = dl_pool(g.b_log, g.se_log)
        r["group"] = name
        rows.append(r)
    # 한 연구씩 빼기 (전체 묶음 안정성)
    if len(st) >= 4:
        loo = [dl_pool(st.b_log.drop(i), st.se_log.drop(i))["mu"] for i in st.index]
        rows.append(dict(group="한 연구씩 빼기: 평균 범위", k=len(st) - 1,
                         mu=np.nan, ci_low=min(loo), ci_high=max(loo)))
    # 대전 값 보정: 해외 예측분포(새 도시 효과 ~ N(mu, tau² + se²))를 사전분포로 두고
    # 대전 추정치와 정밀도 가중으로 합침 (정규-정규 결합)
    main = dl_pool(st.b_log, st.se_log)
    prior_var = main["tau2"] + main["se"] ** 2
    for _, r in df[df.role == "reference"].iterrows():
        v = r.se_log ** 2
        post_var = 1 / (1 / prior_var + 1 / v)
        post = post_var * (main["mu"] / prior_var + r.b_log / v)
        rows.append(dict(group=f"보정값: {r['id']} + 해외 사전분포", k=main["k"], mu=post,
                         se=np.sqrt(post_var), ci_low=post - Z * np.sqrt(post_var),
                         ci_high=post + Z * np.sqrt(post_var),
                         weight_daejeon=round(prior_var / (prior_var + v), 3)))
    summ = pd.DataFrame(rows)
    for c in ["mu", "ci_low", "ci_high", "pi_low", "pi_high"]:
        if c in summ:
            summ[c + "_pct"] = pct(summ[c])
    summ.to_csv(OUT / "tram_meta_summary.csv", index=False, encoding="utf-8-sig")
    print(summ[["group", "k", "mu_pct", "ci_low_pct", "ci_high_pct", "pi_low_pct", "pi_high_pct", "I2"]]
          .round(2).to_string(index=False))

    forest(df, summ)


def forest(df, summ):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    st = df[df.main_pool].sort_values("b_log")
    ref = df[(df.role == "reference") & df.b_log.notna()]
    allp = summ[summ.group == "전체 (트램·경전철)"]

    labels, mids, lows, highs, kinds = [], [], [], [], []
    for _, r in st.iterrows():
        labels.append(f"{r['label_en']}")
        mids.append(r.effect_pct); lows.append(r.ci_low_pct); highs.append(r.ci_high_pct)
        kinds.append("study")
    if len(allp):
        a = allp.iloc[0]
        labels.append(f"Pooled, random effects (k={int(a.k)})")
        mids.append(a.mu_pct); lows.append(a.ci_low_pct); highs.append(a.ci_high_pct)
        kinds.append("pooled")
    for _, r in ref.iterrows():
        labels.append(r["label_en"])
        mids.append(r.effect_pct); lows.append(r.ci_low_pct); highs.append(r.ci_high_pct)
        kinds.append("ref")

    n = len(labels)
    fig, ax = plt.subplots(figsize=(8.5, 0.38 * n + 1.6))
    y = np.arange(n)[::-1]
    ink, muted, accent = "#1f2a1c", "#8a9682", "#2f5d8a"
    if len(allp) and pd.notna(allp.iloc[0].pi_low_pct):
        a = allp.iloc[0]
        ax.axvspan(a.pi_low_pct, a.pi_high_pct, color=accent, alpha=0.07, lw=0)
        ax.text(a.pi_high_pct, y[0] + 0.6, "95% prediction interval", ha="right", va="bottom",
                fontsize=8, color=accent)
    ax.axvline(0, color=muted, lw=0.8)
    for yi, m, lo, hi, k in zip(y, mids, lows, highs, kinds):
        col = {"study": ink, "pooled": accent, "ref": "#b0563a"}[k]
        if pd.notna(lo) and pd.notna(hi):
            ax.plot([lo, hi], [yi, yi], color=col, lw=1.4)
        mk = {"study": "s", "pooled": "D", "ref": "o"}[k]
        ax.plot(m, yi, mk, color=col, ms=6 if k == "study" else 8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    for t, k in zip(ax.get_yticklabels(), kinds):
        if k != "study":
            t.set_fontweight("bold")
    ax.set_xlabel("Effect of opening on nearby values (%), point and 95% CI")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    lo_all = np.nanmin(lows + [0]); hi_all = np.nanmax(highs + [0])
    pad = (hi_all - lo_all) * 0.05
    ax.set_xlim(max(lo_all - pad, -60), min(hi_all + pad, 80))
    fig.tight_layout()
    fig.savefig(OUT / "tram_meta_forest.png", dpi=170)
    print("saved", OUT / "tram_meta_forest.png")


if __name__ == "__main__":
    main()
