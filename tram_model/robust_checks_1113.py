"""검정 보강 A·B·C (2026-11-13). 판정 규칙: docs/사전분석계획_검정보강_1113.md (결과 계산 전 작성)

A. 카페 효과 — 가장 가까운 1호선 역 단위로 묶은 wild cluster bootstrap-t (귀무 부과, Webb 6점, 9,999회)
B. 카페 효과 — 포아송(PPML) 격자·연도 고정효과, 역 단위 묶음 표준오차
C. 공사 — 코호트(공사 시작 달)별 이중차분, 공사 안 하는 동만 비교군, 동 부트스트랩 1,999회
출력: outputs/robust_cafe_cluster.csv, outputs/robust_construction_cohort.csv
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import analyze_line1_permits as AP

OUT = C.OUT_DIR
RNG = np.random.default_rng(20261113)
WEBB = np.array([-np.sqrt(1.5), -1, -np.sqrt(.5), np.sqrt(.5), 1, np.sqrt(1.5)])


# ---------------------------------------------------------------- A·B 카페
def nearest_station(p, st):
    x, y = AP._xy_m(p.lat, p.lon)
    sx, sy = AP._xy_m(st.lat, st.lon)
    D = np.hypot(np.asarray(x)[:, None] - np.asarray(sx)[None, :], np.asarray(y)[:, None] - np.asarray(sy)[None, :])
    return np.asarray(st.name)[D.argmin(1)]


def demean_balanced(v, cell, year):
    df = pd.DataFrame({"v": v, "c": cell, "t": year})
    return (df.v - df.groupby("c").v.transform("mean") - df.groupby("t").v.transform("mean") + df.v.mean()).values


def cafe_checks():
    p = AP.load_permits(); st = AP.load_stations(); p = AP.assign_space(p, st)
    p["st"] = nearest_station(p, st)
    q = AP.build_sample(p); q["sector"] = AP.sector_of(q)
    g = q[q.sector == "카페"]
    cp = AP.panel_for(g)
    cell_st = g.groupby("cell")["st"].agg(lambda s: s.value_counts().index[0])
    cp["st"] = cp.cell.map(cell_st)
    cp["D"] = (cp.treat * (cp.year >= AP.OPEN_YEAR)).astype(float)
    # 기존 값 재현 (격자 묶음)
    b0, se0, G0 = AP.did(cp, "treat", AP.OPEN_YEAR)
    # 역 묶음 CR1
    b1, se1, G1 = AP.twfe(cp, "ly", ["D"], cluster="st")
    # A. wild cluster bootstrap-t, 귀무 부과
    bal = cp.groupby("cell").year.nunique(); assert (bal == bal.max()).all(), "균형 패널 아님"
    x = demean_balanced(cp.D.values, cp.cell.values, cp.year.values)
    y = demean_balanced(cp.ly.values, cp.cell.values, cp.year.values)
    sxx = (x * x).sum(); b = (x * y).sum() / sxx
    gid, gidx = np.unique(cp.st.values, return_inverse=True); G = len(gid); N = len(y)
    K = 1 + cp.cell.nunique() + cp.year.nunique() - 1
    adj = G / (G - 1) * (N - 1) / (N - K)
    def tstat(yv, bv):
        u = yv - x * bv
        S = np.bincount(gidx, weights=x * u, minlength=G)
        return bv / np.sqrt(adj * (S ** 2).sum() / sxx ** 2)
    t_obs = tstat(y, b)
    ur = y.copy()                                   # 귀무(b=0) 아래 잔차 = y
    B = 9999; tb = np.empty(B)
    for i in range(B):
        w = RNG.choice(WEBB, size=G)[gidx]
        ys = ur * w
        tb[i] = tstat(ys, (x * ys).sum() / sxx)
    p_wcb = float((np.abs(tb) >= abs(t_obs)).mean())
    # B. PPML
    import statsmodels.api as sm
    X = pd.get_dummies(cp[["cell", "year"]].astype(str), drop_first=True).astype(float)
    X.insert(0, "D", cp.D.values); X = sm.add_constant(X)
    m = sm.GLM(cp.active.values, X, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": gidx})
    bp, sep = float(m.params["D"]), float(m.bse["D"])
    pct = AP.pct
    rows = [
        dict(검사="기존(격자 묶음, 재현)", 효과_퍼센트=round(pct(b0), 1), 하한=round(pct(b0 - 1.96 * se0), 1), 상한=round(pct(b0 + 1.96 * se0), 1), p값=np.nan, 묶음수=G0, 비고=f"p={AP._pval(b0 / se0):.4f} — 기존 검정과 같은 값, 검정 목록 중복을 막으려고 p칸 비움"),
        dict(검사="A 역 묶음 CR1(참고)", 효과_퍼센트=round(pct(b1[0]), 1), 하한=round(pct(b1[0] - 1.96 * se1[0]), 1), 상한=round(pct(b1[0] + 1.96 * se1[0]), 1), p값=round(AP._pval(b1[0] / se1[0]), 4), 묶음수=G1, 비고=""),
        dict(검사="A 역 묶음 wild cluster bootstrap-t (등급 결정)", 효과_퍼센트=round(pct(b), 1), 하한=np.nan, 상한=np.nan, p값=round(p_wcb, 4), 묶음수=G,
             비고=f"Webb 6점, 귀무 부과, {B}회, t={t_obs:.2f}, 처리 역 {cp[cp.treat == 1].st.nunique()}개"),
        dict(검사="B 포아송 PPML (역 묶음)", 효과_퍼센트=round(pct(bp), 1), 하한=round(pct(bp - 1.96 * sep), 1), 상한=round(pct(bp + 1.96 * sep), 1), p값=round(AP._pval(bp / sep), 4), 묶음수=G,
             비고=f"격자 {cp.cell.nunique()}, 관측 {len(cp)}"),
    ]
    R = pd.DataFrame(rows)
    va = "확실 유지" if p_wcb < 0.05 else "방향만으로 내림"
    vb = "크기 +24.8% 유지" if 8.0 <= pct(bp) <= 44.2 else "크기를 PPML 값으로 교체"
    R["판정"] = ["", "", va, vb]
    R.to_csv(OUT / "robust_cafe_cluster.csv", index=False, encoding="utf-8-sig")
    print(R.to_string())


# ---------------------------------------------------------------- C 공사
def construction_checks(B=1999):
    S = pd.read_csv(C.ROOT / "data" / "construction_sections.csv", encoding="utf-8-sig", dtype=str)
    P = pd.read_csv(OUT / "8989" / "dong_panel_8989.csv", dtype={"adm_cd2": str})
    P = P.dropna(subset=["useAmount_합계"]); P = P[P["useAmount_합계"] > 0]
    DS = pd.read_csv(OUT / "dong_station_summary.csv", encoding="utf-8-sig", dtype={"dong_id": str})
    prof = pd.read_csv(OUT / "dong_map_profile.csv", encoding="utf-8-sig", dtype={"dong_id": str}).set_index("dong_id")
    rows_t = []
    for r in S.itertuples():
        stns = [int(x) for x in str(r.stations).split(";") if x.strip()]
        d = DS[DS.station_no.isin(stns) & ((DS.inside.astype(str) == "True") | (DS.dist_m <= 300))]
        for k in d.dong_id.unique():
            rows_t.append(dict(dong_id=k, start=int(r.start_ym), end=int(r.end_ym) if str(r.end_ym) not in ("", "nan") else 999912))
    T = pd.DataFrame(rows_t).sort_values("start").drop_duplicates("dong_id")
    ctrl = set(prof.tram500_share[prof.tram500_share < 0.10].index)
    P = P[P.adm_cd2.isin(set(T.dong_id) | ctrl)].merge(T, left_on="adm_cd2", right_on="dong_id", how="left")
    P["during"] = ((P.stdrYm >= P.start) & (P.stdrYm <= P.end)).astype(float)
    P["lres"] = np.log(P.resident.clip(lower=1))
    out = []
    for y, lab in [("useAmount_합계", "전체 카드매출"), ("useAmount_음식점", "음식점 매출"), ("useAmount_도소매", "도소매 매출")]:
        d = P[P[y] > 0].assign(ly=lambda z: np.log(z[y])).dropna(subset=["ly", "lres"])
        full = d.groupby("adm_cd2").stdrYm.nunique(); d = d[d.adm_cd2.isin(full[full == full.max()].index)]
        months = np.sort(d.stdrYm.unique()); Tm = len(months)
        def mats(ids):
            sub = d.set_index(["adm_cd2", "stdrYm"]).loc[[(i, m) for i in ids for m in months]]
            return (sub.ly.values.reshape(len(ids), Tm), sub.lres.values.reshape(len(ids), Tm), sub.during.values.reshape(len(ids), Tm))
        cids = sorted(set(d.adm_cd2) & ctrl)
        Yc, Rc, Dc = mats(cids)
        cohorts = {}
        for s, grp in d[d.start.notna()].groupby("start"):
            ids = sorted(grp.adm_cd2.unique()); cohorts[int(s)] = mats(ids)
        def est(Yc_, Rc_, Dc_, coh):
            vals, ws = [], []
            for s, (Yt, Rt, Dt) in coh.items():
                Y = np.vstack([Yt, Yc_]); Rr = np.vstack([Rt, Rc_]); D = np.vstack([Dt, np.zeros_like(Dc_)])
                dm = lambda A: A - A.mean(1, keepdims=True) - A.mean(0, keepdims=True) + A.mean()
                Xm = np.column_stack([dm(D).ravel(), dm(Rr).ravel()]); yv = dm(Y).ravel()
                bb = np.linalg.lstsq(Xm, yv, rcond=None)[0][0]
                vals.append(bb); ws.append(Yt.shape[0])
            vals, ws = np.array(vals), np.array(ws, float)
            return float((vals * ws).sum() / ws.sum()), vals
        b, per = est(Yc, Rc, Dc, cohorts)
        bs = np.empty(B)
        for i in range(B):
            ci = RNG.integers(0, len(cids), len(cids))
            coh_b = {s: tuple(A[RNG_idx] for A in M) for s, M in cohorts.items() for RNG_idx in [RNG.integers(0, M[0].shape[0], M[0].shape[0])]}
            bs[i] = est(Yc[ci], Rc[ci], Dc[ci], coh_b)[0]
        pval = float((np.abs(bs - b) >= abs(b)).mean())
        lo, hi = np.percentile(bs, [2.5, 97.5])
        out.append(dict(결과=lab, 효과_퍼센트=round(AP.pct(b), 2), 하한=round(AP.pct(lo), 2), 상한=round(AP.pct(hi), 2), p값=round(pval, 4),
                        코호트별=" · ".join(f"{s}: {AP.pct(v):+.1f}% (동 {cohorts[s][0].shape[0]})" for s, v in zip(cohorts, per)),
                        비교_동=len(cids), 부트스트랩=B))
    R = pd.DataFrame(out)
    r0 = R.iloc[0]
    R["판정"] = ["'방향만'으로 올림" if (r0.p값 < 0.05 and r0.효과_퍼센트 < 0) else "'확인 안 됨' 유지", "", ""]
    R.to_csv(OUT / "robust_construction_cohort.csv", index=False, encoding="utf-8-sig")
    print(R.to_string())


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("cafe", "all"): cafe_checks()
    if which in ("constr", "all"): construction_checks()
