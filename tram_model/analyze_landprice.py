"""공시지가로 본 대전 과거 교통·상권 사건 효과.

입력: build_landprice.py 출력 (outputs/landprice_parcels.csv.gz, landprice_long.pkl, landprice_area_panel.csv)
출력 (outputs/)
- landprice_line1_es.csv     : 1호선 1·2단계 역 500m 필지 vs 1~3km 필지 연도별 차이 (이벤트 스터디, 2005=0)
- landprice_tram_es.csv      : 트램 2호선 정거장 500m vs 1~3km (2019=0, 2019-01 예타 면제 직전)
- landprice_rings.csv        : 1호선 역 거리대별 효과 (0-250 / 250-500 / 500-1000m)
- landprice_area_events.csv  : 20개 상권 사건(E01~E14) 이중차분 + 가짜 처리군 순위 p
- landprice_effects.csv      : 위 결과 요약 + 논문값(P2 Lan 2025 부동산 +0.108) 비교
- landprice_line1_es.png (왼쪽 1호선, 오른쪽 트램), landprice_area_trend.png

방법
- 결과: log(공시지가). 같은 필지의 기준연도 대비 변화 → 필지 고정효과와 같음
- 처리군 - 비교군 평균 차이 = 연도 고정효과를 둔 이중차분과 같음
- 신뢰구간: 법정동 단위 군집 부트스트랩 (같은 동 필지는 함께 감정되므로)
- 공시지가는 1월 1일 기준 → 2006-03 개통이면 첫 '개통 후' 값은 2007년
- 지목 '대'(건축물 부지)만 사용. 2006년은 필지 27% 누락이라 기준연도로 쓰지 않음
"""
import numpy as np
import pandas as pd

import config as C

RNG = np.random.default_rng(42)
N_BOOT = 300
P2_PROPERTY = 0.1079       # literature_params: P2 Lan 2025 부동산 POI DiD (log)


def load():
    G = pd.read_csv(C.OUT_DIR / "landprice_parcels.csv.gz", encoding="utf-8-sig")
    G = G[G.is_dae == 1]
    L = pd.read_pickle(C.OUT_DIR / "landprice_long.pkl")
    W = np.log(L[L.pnu.isin(G.pnu)].pivot(index="pnu", columns="year", values="price"))
    return G.set_index("pnu").loc[W.index], W


def event_study(G, W, treat, ctrl, base, years):
    """연도별 (처리군 평균 변화 − 비교군 평균 변화), 법정동 군집 부트스트랩 95% CI."""
    years = [y for y in years if y in W.columns]
    D = W[years].sub(W[base], axis=0)
    D = D[W[base].notna()]
    lo, hi = D.quantile(0.01), D.quantile(0.99)
    D = D.clip(lo, hi, axis=1)                                 # 극단값(지목 변경 등) 완화
    grp = pd.Series(np.where(treat, "T", np.where(ctrl, "C", "")), index=G.index).reindex(D.index)
    D, grp = D[grp != ""], grp[grp != ""]
    dong = G.dong_code.reindex(D.index).values
    ud, di = np.unique(dong, return_inverse=True)
    rows = []
    stats = {}
    for g in ("T", "C"):
        m = (grp == g).values
        X = D.values[m]
        S = np.zeros((len(ud), len(years))); N = np.zeros_like(S)
        np.add.at(S, di[m], np.nan_to_num(X)); np.add.at(N, di[m], ~np.isnan(X))
        stats[g] = (S, N)
    B = RNG.multinomial(len(ud), np.ones(len(ud)) / len(ud), size=N_BOOT).astype(float)
    est = stats["T"][0].sum(0) / stats["T"][1].sum(0) - stats["C"][0].sum(0) / stats["C"][1].sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        boot = (B @ stats["T"][0]) / (B @ stats["T"][1]) - (B @ stats["C"][0]) / (B @ stats["C"][1])
    ci = np.nanpercentile(boot, [2.5, 97.5], axis=0)
    for k, y in enumerate(years):
        rows.append({"year": y, "coef": est[k], "ci_lo": ci[0, k], "ci_hi": ci[1, k],
                     "n_treat": int(stats["T"][1][:, k].sum()), "n_ctrl": int(stats["C"][1][:, k].sum())})
    return pd.DataFrame(rows), boot, years


def window_mean(es, boot, years, sel):
    k = [i for i, y in enumerate(years) if y in sel]
    b = np.nanmean(boot[:, k], axis=1)
    return float(es.coef.values[k].mean()), *np.nanpercentile(b, [2.5, 97.5])


def pct(x):
    return round((np.exp(x) - 1) * 100, 1)


def area_events(A):
    ev = pd.read_csv(C.ROOT / "data" / "area_events.csv", encoding="utf-8-sig")
    ev = ev[ev.area_codes != "ALL"]
    ev["date"] = pd.to_datetime(ev.date)
    P = A[A.code != "ALL"].pivot(index="year", columns="code", values="idx").apply(np.log)
    treated_any = {c for s in ev.area_codes for c in s.split(";")}
    controls = [c for c in P.columns if c not in treated_any]
    rows = []
    for _, e in ev.iterrows():
        t0 = e.date.year + 1                     # 사건 뒤 첫 1월 1일 공시
        pre = [y for y in range(t0 - 4, t0) if y not in (2006,)]
        post = list(range(t0, t0 + 4))
        if min(pre) < P.index.min() or max(post) > P.index.max():
            continue
        delta = P.loc[post].mean() - P.loc[pre].mean()
        tg = [c for c in e.area_codes.split(";") if c in P.columns and not np.isnan(delta[c])]
        ctl = [c for c in controls if not np.isnan(delta[c])]
        if not tg or len(ctl) < 3:
            continue
        eff = delta[tg].mean() - delta[ctl].mean()
        plac = [delta[c] - delta[[x for x in ctl if x != c]].mean() for c in ctl]
        p = (np.sum(np.abs(plac) >= abs(eff)) + 1) / (len(plac) + 1)
        rows.append({"event": e.event_id, "label": e.description[:40], "areas": ";".join(tg),
                     "pre_years": f"{min(pre)}-{max(pre)}", "post_years": f"{t0}-{t0 + 3}",
                     "expected": e.direction, "effect_pct": pct(eff), "placebo_p": round(p, 3),
                     "n_controls": len(ctl)})
    return pd.DataFrame(rows), controls


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

    print("필지 자료 읽는 중 ...", flush=True)
    G, W = load()
    summary = []

    # ---------------- 1) 1호선 1·2단계
    ctrl = (G.d_l1 > 1000) & (G.d_l1 <= 3000)
    l1_es, rings = [], []
    for ph, first_post, label in [(1, 2007, "1호선 1단계(2006-03 개통)"), (2, 2008, "1호선 2단계(2007-04 개통)")]:
        tr = (G.l1_phase == ph) & (G.d_l1 <= 500)
        es, boot, yrs = event_study(G, W, tr, ctrl, 2005, list(range(1996, 2014)))
        es["phase"] = ph
        l1_es.append(es)
        post = range(first_post, first_post + 4)
        m, lo, hi = window_mean(es, boot, yrs, post)
        pm, plo, phi = window_mean(es, boot, yrs, range(2000, 2004))
        summary.append({"analysis": label, "treat": "역 500m 필지", "control": "1호선 역 1~3km 필지",
                        "base": 2005, "post": f"{post[0]}-{post[-1]}", "effect_pct": pct(m),
                        "ci95": f"{pct(lo)} ~ {pct(hi)}", "pre_2000_03_pct": pct(pm),
                        "n_treat": int(es.n_treat.max()), "n_ctrl": int(es.n_ctrl.max())})
        for a, b in [(0, 250), (250, 500), (500, 1000)]:
            t2 = (G.l1_phase == ph) & (G.d_l1 > a) & (G.d_l1 <= b)
            e2, b2, y2 = event_study(G, W, t2, ctrl, 2005, list(post))
            m2, lo2, hi2 = window_mean(e2, b2, y2, post)
            rings.append({"phase": ph, "ring_m": f"{a}-{b}", "effect_pct": pct(m2),
                          "ci95": f"{pct(lo2)} ~ {pct(hi2)}", "n": int(e2.n_treat.max())})
    l1_es = pd.concat(l1_es)
    rings = pd.DataFrame(rings)

    # ---------------- 2) 트램 2호선 (계획 확정 효과)
    far_l1 = G.d_l1 > 500
    tr = (G.d_tram <= 500) & far_l1
    ct = (G.d_tram > 1000) & (G.d_tram <= 3000) & far_l1
    tram_es, tboot, tyrs = event_study(G, W, tr, ct, 2019, list(range(2008, 2027)))
    for sel, lab in [(range(2020, 2023), "2020-2022"), (range(2023, 2027), "2023-2026")]:
        m, lo, hi = window_mean(tram_es, tboot, tyrs, sel)
        pm, *_ = window_mean(tram_es, tboot, tyrs, range(2012, 2016))
        summary.append({"analysis": "트램 2호선 예타 면제(2019-01)", "treat": "정거장 500m(1호선 역 500m 밖)",
                        "control": "정거장 1~3km(1호선 역 500m 밖)", "base": 2019, "post": lab,
                        "effect_pct": pct(m), "ci95": f"{pct(lo)} ~ {pct(hi)}", "pre_2000_03_pct": None,
                        "pre_2012_15_pct": pct(pm),
                        "n_treat": int(tram_es.n_treat.max()), "n_ctrl": int(tram_es.n_ctrl.max())})

    # ---------------- 3) 상권 사건
    A = pd.read_csv(C.OUT_DIR / "landprice_area_panel.csv", encoding="utf-8-sig")
    AE, controls = area_events(A)

    S = pd.DataFrame(summary)
    S["vs_P2_property_pct"] = pct(P2_PROPERTY)
    for name, df in [("landprice_line1_es", l1_es), ("landprice_tram_es", tram_es), ("landprice_rings", rings),
                     ("landprice_area_events", AE), ("landprice_effects", S)]:
        df.round(4).to_csv(C.OUT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 200)
    print("\n[1·2] 역/정거장 권역 효과 (처리 − 비교, %)\n", S.drop(columns=["treat", "control"]).to_string(index=False))
    print("\n[1호선 거리대별]\n", rings.to_string(index=False))
    print(f"\n[3] 상권 사건 (비교 상권: {', '.join(controls)})\n", AE.to_string(index=False))

    # ---------------- 그림
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for ph, c in [(1, "C3"), (2, "C0")]:
        e = l1_es[l1_es.phase == ph]
        axes[0].plot(e.year, (np.exp(e.coef) - 1) * 100, "o-", c=c, ms=3, label=f"{ph}단계 역 500m")
        axes[0].fill_between(e.year, (np.exp(e.ci_lo) - 1) * 100, (np.exp(e.ci_hi) - 1) * 100, color=c, alpha=.15)
    axes[0].axvline(2006.2, c="C3", ls="--", lw=.8); axes[0].axvline(2007.3, c="C0", ls="--", lw=.8)
    axes[0].axhline(0, c="k", lw=.6)
    axes[0].set_title("1호선 역 500m 필지 − 1~3km 필지 (2005년 = 0, %)")
    axes[0].legend(fontsize=8)
    e = tram_es
    axes[1].plot(e.year, (np.exp(e.coef) - 1) * 100, "o-", c="C2", ms=3, label="트램 정거장 500m")
    axes[1].fill_between(e.year, (np.exp(e.ci_lo) - 1) * 100, (np.exp(e.ci_hi) - 1) * 100, color="C2", alpha=.15)
    axes[1].axvline(2014.95, c="gray", ls=":", lw=.8); axes[1].axvline(2019.1, c="C2", ls="--", lw=.8)
    axes[1].axhline(0, c="k", lw=.6)
    axes[1].set_title("트램 정거장 500m − 1~3km (2019년 = 0, %)\n점선: 2014-12 트램 방식 확정 / 파선: 2019-01 예타 면제", fontsize=10)
    axes[1].legend(fontsize=8)
    from matplotlib.ticker import MaxNLocator
    for ax in axes:
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    fig.text(0.5, 0.01, "음영 = 법정동 군집 부트스트랩 95% 구간. 2006년 값은 필지 누락이 많아 참고용.", ha="center", fontsize=8)
    plt.tight_layout(rect=(0, 0.04, 1, 1)); plt.savefig(C.OUT_DIR / "landprice_line1_es.png", dpi=130)
    plt.close()

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), sharey=True)
    for ax, grp in zip(axes, [("원도심", "원도심권"), ("신도심",)]):
        for code, g in A[A.type.isin(grp)].groupby("code"):
            g = g[g.year >= 1995]
            ax.plot(g.year, g.rel_idx, lw=1.3, label=g.name.iloc[0])
        ax.axhline(100, c="k", lw=.6)
        ax.axvspan(2006, 2007.3, color="gray", alpha=.12)
        ax.set_title(("원도심" if "원도심" in grp else "신도심") + " 상권 공시지가: 대전 전체 대비 (2015 = 100)")
        ax.legend(fontsize=7, ncol=2)
    fig.text(0.5, 0.01, "회색 띠 = 1호선 개통(2006-03 ~ 2007-04). 100보다 위 = 2015년 이후 대전 평균보다 더 오름.", ha="center", fontsize=9)
    plt.tight_layout(rect=(0, 0.03, 1, 1)); plt.savefig(C.OUT_DIR / "landprice_area_trend.png", dpi=130)
    plt.close()
    print("\n→ outputs/landprice_effects.csv, landprice_line1_es.csv, landprice_tram_es.csv, landprice_rings.csv,"
          " landprice_area_events.csv, landprice_line1_es.png, landprice_area_trend.png")


if __name__ == "__main__":
    main()
