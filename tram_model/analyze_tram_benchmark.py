"""트램 효과 근거 비교: 대전 추정치(기본·추세 보정·매칭·행정동) vs 국내외 경전철·트램 문헌.

입력: outputs/line1_trend_adjusted.csv, outputs/dong_event_effects.csv(있으면), literature_tram_benchmarks.csv
출력: outputs/tram_benchmark.csv, outputs/tram_benchmark.png
판단 기준
- 주거·혼합 토지 트램 문헌: 0~6% (청두 +1.4%, 파리 T3 0, 맨체스터 +6.3%, Norfolk −8%)
- 상업용지: 10~25% (산호세 LRT +23%, 메타분석 상업 15.2%, 서울 BRT 상업 25%+)
"""
import numpy as np
import pandas as pd

import config as C


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

    rows = []
    T = pd.read_csv(C.OUT_DIR / "line1_trend_adjusted.csv", encoding="utf-8-sig")
    for _, r in T.iterrows():
        rows.append({"group": "대전 1호선 (본 분석)", "label": r.method[2:], "value": r.effect_pct,
                     "lo": r.ci_lo, "hi": r.ci_hi, "kind": "지하철·지가(대)"})
    f = C.OUT_DIR / "dong_event_effects.csv"
    if f.exists():
        D = pd.read_csv(f, encoding="utf-8-sig")
        d = D[(D.event == "E01") & (D.outcome == "지가")]
        if len(d):
            r = d.iloc[0]
            rows.append({"group": "대전 1호선 (본 분석)", "label": "행정동 단위 (역 있는 동 전체)", "value": r.effect_pct,
                         "lo": r.effect_pct - 1.96 * r.placebo_sd_pct, "hi": r.effect_pct + 1.96 * r.placebo_sd_pct,
                         "kind": "지하철·지가(동 평균)"})
    L = pd.read_csv(C.ROOT / "literature_tram_benchmarks.csv", encoding="utf-8-sig")
    for _, r in L.iterrows():
        if pd.isna(r.value) or r.unit not in ("%", "log"):
            continue
        v = float(r.value) if r.unit == "%" else float(np.expm1(r.value) * 100)
        if "business" in r.outcome:
            continue          # 창업 수는 단위가 달라 그림에서 제외 (표에는 있음)
        rows.append({"group": "문헌", "label": r.source, "value": v, "lo": np.nan, "hi": np.nan,
                     "kind": r.outcome})
    R = pd.DataFrame(rows)
    R.to_csv(C.OUT_DIR / "tram_benchmark.csv", index=False, encoding="utf-8-sig")

    fig, ax = plt.subplots(figsize=(10, 0.36 * len(R) + 1.8))
    y = np.arange(len(R))[::-1]
    col = ["C3" if g.startswith("대전") else ("C2" if "commercial" in k or "land value" == k else "C0")
           for g, k in zip(R.group, R.kind)]
    ax.scatter(R.value, y, c=col, zorder=3)
    m = R.lo.notna()
    ax.errorbar(R.value[m], y[m.values], xerr=[R.value[m] - R.lo[m], R.hi[m] - R.value[m]], fmt="none", ecolor="C3", lw=1.2)
    ax.axvspan(0, 6, color="C0", alpha=.08, label="트램·LRT 주거 문헌 범위 0~6%")
    ax.axvspan(10, 25, color="C2", alpha=.08, label="LRT 상업용지 문헌 범위 10~25%")
    import tram_effect as TE
    _L = TE.levels()
    for v, ls, t in [(_L["low"]["pct"], ":", "낮음"), (_L["base"]["pct"], "--", "기본"), (_L["high"]["pct"], "-.", "높음")]:
        ax.axvline(v, c="k", ls=ls, lw=.8)
        ax.text(v, len(R) - 0.3, f"시나리오 {t} {v}%", fontsize=7, rotation=90, va="top", ha="right")
    ax.set_yticks(y); ax.set_yticklabels([f"{l[:34]}" for l in R.label], fontsize=8)
    ax.axvline(0, c="k", lw=.5)
    ax.set_xlabel("효과 (%)  빨강 = 대전 추정(95% 구간) · 파랑 = 주거 문헌 · 초록 = 상업·토지 문헌")
    ax.set_title("트램 효과 근거: 대전 1호선 추정 vs 국내외 경전철·트램 연구")
    ax.legend(fontsize=8, loc="lower right")
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "tram_benchmark.png", dpi=130)
    print(R.round(1).to_string(index=False))
    print("→ outputs/tram_benchmark.csv, tram_benchmark.png")


if __name__ == "__main__":
    main()
