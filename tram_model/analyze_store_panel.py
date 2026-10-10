"""상권 × 분기 점포 패널 분석: 추세 그림 + 과거 사건 효과(이중차분, 가짜 처리군 검정).

입력: outputs/store_panel.csv, outputs/store_panel_city.csv (build_store_panel.py)
출력:
- outputs/panel_trend.png         : 상권별 대전 내 점포 비중 추이 (2019-12 = 100)
- outputs/panel_events.png        : 사건별 처리 상권 vs 비교 상권
- outputs/panel_event_effects.csv : 사건 효과 추정 + 가짜 처리군(placebo) 순위 p값

방법
- 결과 변수: log(상권 점포 비중) — 대전 전체 대비 비중이라 수집 기준 변화가 대부분 상쇄됨
- 이중차분: 상권 고정효과 + 분기 고정효과 + (처리 상권 × 사건 후). 사건 전후 3년, 같은 자료 구간(regime) 안에서만
- 비교군: 어떤 사건에도 처리되지 않은 상권
- 가짜 처리군 검정: 비교군 상권 하나하나를 '처리됐다'고 놓고 같은 추정 → 실제 효과가 몇 등인지 (20개 상권이라 표준오차 대신 사용)
"""
import numpy as np
import pandas as pd

import config as C

EVENTS = {  # 패널 기간(2015-12~2026-06) 안에서 전후 비교가 가능한 사건
    "E10": ("A03", "2019-01-01", "소제동 카페거리 형성"),
    "E11": ("A15", "2020-06-26", "현대프리미엄아울렛 개점(관평)"),
    "E12": ("A12", "2021-08-27", "대전신세계 개점(도룡)"),
    "E13": ("A07", "2021-08-27", "신세계 개점 → 타임월드 상권 영향"),
    "E14": ("A06", "2024-01-01", "백화점 세이 폐업(서대전네거리)"),
}
WIN_YEARS = 3


def did(P, code, t0, controls):
    d = P[P.code.isin(controls + [code])].copy()
    d = d[(d.date >= t0 - pd.DateOffset(years=WIN_YEARS)) & (d.date <= t0 + pd.DateOffset(years=WIN_YEARS))]
    reg0 = d[(d.code == code) & (d.date < t0)].regime
    if reg0.empty:
        return np.nan, 0, 0
    r = reg0.iloc[-1]
    d = d[d.regime == r]                                    # 같은 자료 구간 안에서만
    n_pre = d[(d.code == code) & (d.date < t0)].shape[0]
    n_post = d[(d.code == code) & (d.date >= t0)].shape[0]
    if n_pre < 2 or n_post < 2:
        return np.nan, n_pre, n_post
    d["post"] = ((d.code == code) & (d.date >= t0)).astype(float)
    X = pd.get_dummies(d[["code", "period"]].astype(str), drop_first=True).astype(float)
    X = np.c_[np.ones(len(d)), X.values, d.post.values]
    b = np.linalg.lstsq(X, np.log(d.share.values), rcond=None)[0]
    return float(b[-1]), n_pre, n_post


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

    P = pd.read_csv(C.OUT_DIR / "store_panel.csv", dtype={"period": str}, encoding="utf-8-sig")
    P["date"] = pd.to_datetime(P.date)
    Cy = pd.read_csv(C.OUT_DIR / "store_panel_city.csv", dtype={"period": str}, encoding="utf-8-sig")
    treated = {v[0] for v in EVENTS.values()}
    controls = sorted(set(P.code) - treated)

    rows = []
    for eid, (code, dt, label) in EVENTS.items():
        t0 = pd.Timestamp(dt)
        b, n_pre, n_post = did(P, code, t0, controls)
        if np.isnan(b):
            rows.append({"event": eid, "label": label, "area": code, "effect_pct": np.nan,
                         "note": f"추정 불가 (같은 자료 구간 안의 사건 전 {n_pre}·후 {n_post} 분기)"})
            continue
        # 가짜 처리군: 비교군 상권을 하나씩 처리군으로
        plac = []
        for c in controls:
            pb, *_ = did(P, c, t0, [x for x in controls if x != c])
            if not np.isnan(pb):
                plac.append(pb)
        plac = np.array(plac)
        p_rank = (np.sum(np.abs(plac) >= abs(b)) + 1) / (len(plac) + 1)
        rows.append({"event": eid, "label": label, "area": code,
                     "effect_pct": round((np.exp(b) - 1) * 100, 1),
                     "placebo_p": round(p_rank, 3), "n_placebo": len(plac),
                     "pre_q": n_pre, "post_q": n_post,
                     "sensitive_area": int(P[P.code == code].break_sensitive.iloc[0]),
                     "note": "가짜 처리군보다 효과가 큼" if p_rank <= 0.1 else "가짜 처리군과 구별 안 됨"})
    E = pd.DataFrame(rows)
    E.to_csv(C.OUT_DIR / "panel_event_effects.csv", index=False, encoding="utf-8-sig")
    print(E.to_string(index=False))

    # 그림 1: 추세
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), sharey=True)
    for ax, grp in zip(axes, [("원도심", "원도심권"), ("신도심",)]):
        for code, g in P[P.type.isin(grp)].groupby("code"):
            ax.plot(g.date, g.share_idx, lw=1.3, label=g.name.iloc[0])
        for _, r in Cy[Cy.data_break == 1].iterrows():
            ax.axvline(pd.to_datetime(r.period, format="%Y%m"), color="gray", ls=":", lw=1)
        ax.axhline(100, color="k", lw=.6)
        ax.set_title(("원도심" if "원도심" in grp else "신도심") + " 상권: 대전 전체 대비 점포 비중 (2019-12 = 100)")
        ax.legend(fontsize=7, ncol=2)
    axes[0].set_ylim(60, 140)
    fig.text(0.5, 0.01, "점선 = 자료 단절 분기(수집 기준 변경). 단절 전후 값은 직접 비교하지 말 것. "
             "도룡동은 2021년 신세계 입점점포 등록으로 범위(최대 약 220) 밖.", ha="center", fontsize=9)
    plt.tight_layout(rect=(0, 0.03, 1, 1)); plt.savefig(C.OUT_DIR / "panel_trend.png", dpi=130)

    # 그림 2: 사건별
    fig, axes = plt.subplots(1, len(EVENTS), figsize=(4 * len(EVENTS), 3.6))
    ctl = P[P.code.isin(controls)].groupby("date").share.mean()
    for ax, (eid, (code, dt, label)) in zip(axes, EVENTS.items()):
        t0 = pd.Timestamp(dt)
        g = P[P.code == code].set_index("date").share
        w = (g.index >= t0 - pd.DateOffset(years=WIN_YEARS)) & (g.index <= t0 + pd.DateOffset(years=WIN_YEARS))
        g, cc = g[w], ctl.reindex(g.index[w])
        base = g[g.index < t0].iloc[-1] if (g.index < t0).any() else g.iloc[0]
        cbase = cc[cc.index < t0].iloc[-1] if (cc.index < t0).any() else cc.iloc[0]
        ax.plot(g.index, g / base * 100, c="C3", label="처리 상권")
        ax.plot(cc.index, cc / cbase * 100, c="gray", label="비교 상권 평균")
        ax.axvline(t0, c="k", lw=.8)
        for _, r in Cy[Cy.data_break == 1].iterrows():
            ax.axvline(pd.to_datetime(r.period, format="%Y%m"), color="gray", ls=":", lw=1)
        e = E[E.event == eid].iloc[0]
        ax.set_title(f"{eid} {label}\n효과 {e.effect_pct}%" if not pd.isna(e.effect_pct) else f"{eid} {label}\n추정 불가",
                     fontsize=9)
        ax.tick_params(labelsize=7); ax.legend(fontsize=7)
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "panel_events.png", dpi=130)
    print("→ outputs/panel_trend.png, panel_events.png, panel_event_effects.csv")


if __name__ == "__main__":
    main()
