"""1호선 1단계 효과 재추정 — 개통 전 추세 보정 (가짜 개통연도 검정이 경계였던 문제 대응).

입력: build_landprice.py 출력 (analyze_landprice.load 재사용)
출력: outputs/line1_trend_adjusted.csv, outputs/line1_trend_adjusted.png

방법 (모두 역 500m vs 1~3km, 지목 '대', 기준 2005, 개통 후 2007~2010 평균, 법정동 군집 부트스트랩 95% 구간)
 1 기본 이중차분                      : 지금 값 (+5.8%)
 2 추세 보정 (1996~2005 직선)         : 개통 전 '처리−비교' 차이의 직선 추세를 개통 후로 연장해 뺀 값
 3 추세 보정 (2000~2005 직선)         : 최근 추세만 사용
 4 사전 성장 매칭                     : 비교 필지를 구 × 2000→2005 상승률 5분위 × 2005 가격 3분위 칸으로 가중 →
                                        개통 전 오르던 속도와 가격대가 같은 필지끼리 비교
 5 매칭 + 추세 보정(2000~2005)
 가짜 검정: 2001년 개통 가정(기준 2000, 2002~2004)을 같은 방법으로 → 0 근처여야 정상
"""
import numpy as np
import pandas as pd

import config as C
from analyze_landprice import load, pct

RNG = np.random.default_rng(7)
N_BOOT = 400


def es_weighted(G, W, treat, ctrl, base, years, w=None):
    """연도별 (처리 평균 − 비교 평균), 법정동 군집 부트스트랩. w = 필지 가중치(없으면 1)."""
    years = [y for y in years if y in W.columns]
    D = W[years].sub(W[base], axis=0)[W[base].notna()]
    D = D.clip(D.quantile(0.01), D.quantile(0.99), axis=1)
    grp = pd.Series(np.where(treat, "T", np.where(ctrl, "C", "")), index=G.index).reindex(D.index)
    keep = (grp != "").values
    D, grp = D[keep], grp[keep]
    wt = (pd.Series(1.0, index=D.index) if w is None else w.reindex(D.index).fillna(0.0)).values
    dong = G.dong_code.reindex(D.index).values
    ud, di = np.unique(dong, return_inverse=True)
    stats = {}
    for g in ("T", "C"):
        m = (grp == g).values
        X = D.values[m]; ww = wt[m][:, None]
        S = np.zeros((len(ud), len(years))); N = np.zeros_like(S)
        np.add.at(S, di[m], np.nan_to_num(X) * ww); np.add.at(N, di[m], (~np.isnan(X)) * ww)
        stats[g] = (S, N)
    est = stats["T"][0].sum(0) / stats["T"][1].sum(0) - stats["C"][0].sum(0) / stats["C"][1].sum(0)
    B = RNG.multinomial(len(ud), np.ones(len(ud)) / len(ud), size=N_BOOT).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        boot = (B @ stats["T"][0]) / (B @ stats["T"][1]) - (B @ stats["C"][0]) / (B @ stats["C"][1])
    return np.array(years), est, boot


def effect(years, est, boot, post, trend_from=None, base=2005):
    """개통 후 평균 효과. trend_from 이 있으면 [trend_from, base] 의 직선 추세를 빼고 계산."""
    pm = np.isin(years, list(post))

    def one(v):
        if trend_from is None:
            return np.nanmean(v[pm])
        pre = (years >= trend_from) & (years <= base) & (years != 2006)
        ok = pre & ~np.isnan(v)
        if ok.sum() < 3:
            return np.nan
        b = np.polyfit(years[ok], v[ok], 1)
        return np.nanmean(v[pm] - np.polyval(b, years[pm]))
    e = one(est)
    bs = np.array([one(b) for b in boot])
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    return pct(e), pct(lo), pct(hi)


def matching_weights(G, W, treat, ctrl, base=2005, pre=2000):
    """비교 필지 가중치: 구 × 사전 상승률 5분위 × 가격 3분위 칸에서 처리 필지 비율을 맞춤."""
    g = pd.DataFrame({"gu": (G.dong_code // 100000).astype(int),
                      "growth": W[base] - W[pre], "level": W[base]}, index=G.index).dropna()
    g["gq"] = pd.qcut(g.growth, 5, labels=False, duplicates="drop")
    g["lq"] = pd.qcut(g.level, 3, labels=False, duplicates="drop")
    g["cell"] = g.gu.astype(str) + "_" + g.gq.astype(str) + "_" + g.lq.astype(str)
    t = g[treat.reindex(g.index).fillna(False)]
    c = g[ctrl.reindex(g.index).fillna(False)]
    nt, nc = t.cell.value_counts(), c.cell.value_counts()
    ratio = (nt / nc).dropna()
    w = pd.Series(0.0, index=G.index)
    w[t.index] = 1.0
    w[c.index] = c.cell.map(ratio).fillna(0.0).values
    cover = t.cell.isin(ratio.index).mean()
    w[t.index[~t.cell.isin(ratio.index)]] = 0.0           # 비교 필지가 없는 칸의 처리 필지는 제외
    return w, cover


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
    tr = (G.l1_phase == 1) & (G.d_l1 <= 500)
    ct = (G.d_l1 > 1000) & (G.d_l1 <= 3000)
    yrs = list(range(1996, 2014))
    post = range(2007, 2011)
    rows = []
    y, est, boot = es_weighted(G, W, tr, ct, 2005, yrs)
    wm, cover = matching_weights(G, W, tr, ct)
    ym, estm, bootm = es_weighted(G, W, tr, ct, 2005, yrs, wm)
    # 가짜 개통 2001 (기준 2000, 2002~04, 추세는 1996~2000)
    yp, estp, bootp = es_weighted(G, W, tr, ct, 2000, list(range(1993, 2006)))
    wmp, _ = matching_weights(G, W, tr, ct, base=2000, pre=1996)
    ypm, estpm, bootpm = es_weighted(G, W, tr, ct, 2000, list(range(1993, 2006)), wmp)
    specs = [("1 기본 이중차분", (y, est, boot), None, (yp, estp, bootp), None),
             ("2 추세 보정 (1996~2005)", (y, est, boot), 1996, (yp, estp, bootp), 1993),
             ("3 추세 보정 (2000~2005)", (y, est, boot), 2000, (yp, estp, bootp), 1996),
             ("4 사전 성장 매칭", (ym, estm, bootm), None, (ypm, estpm, bootpm), None),
             ("5 매칭 + 추세 보정 (2000~2005)", (ym, estm, bootm), 2000, (ypm, estpm, bootpm), 1996)]
    for name, (yy, ee, bb), tf, (py, pe, pb), ptf in specs:
        e, lo, hi = effect(yy, ee, bb, post, tf, 2005)
        pe_, plo, phi = effect(py, pe, pb, range(2002, 2005), ptf, 2000)
        rows.append({"method": name, "effect_pct": e, "ci_lo": lo, "ci_hi": hi,
                     "placebo_2001_pct": pe_, "placebo_ci": f"{plo:+.1f} ~ {phi:+.1f}",
                     "placebo_pass": bool(plo < 0 < phi)})
    R = pd.DataFrame(rows)
    R.to_csv(C.OUT_DIR / "line1_trend_adjusted.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print(R.to_string(index=False))
    print(f"(매칭: 처리 필지의 {cover:.0%} 가 같은 칸의 비교 필지를 가짐)")
    ok = R[R.placebo_pass]
    if len(ok):
        print(f"\n가짜 검정을 통과한 방법의 효과 범위: {ok.effect_pct.min():+.1f}% ~ {ok.effect_pct.max():+.1f}%")

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(y, (np.exp(est) - 1) * 100, "o-", c="C3", ms=3, label="기본 (역 500m − 1~3km)")
    ax.plot(ym, (np.exp(estm) - 1) * 100, "s-", c="C0", ms=3, label="사전 성장 매칭")
    pre = (y >= 1996) & (y <= 2005) & (y != 2006)
    b = np.polyfit(y[pre], est[pre], 1)
    ax.plot(y, (np.exp(np.polyval(b, y)) - 1) * 100, c="C3", ls=":", label="개통 전 추세(1996~2005) 연장")
    ax.axvline(2006.2, c="k", lw=.8); ax.axhline(0, c="k", lw=.5)
    ax.set_title("1호선 1단계: 개통 전 추세를 빼면 효과가 어떻게 바뀌나 (2005 = 0, %)")
    ax.legend(fontsize=8)
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "line1_trend_adjusted.png", dpi=130)
    print("→ outputs/line1_trend_adjusted.csv, line1_trend_adjusted.png")
    return R


if __name__ == "__main__":
    main()
