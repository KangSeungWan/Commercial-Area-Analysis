"""트램 효과 근거(1호선 1단계 역세권 지가 효과)의 강건성 검정 + 정거장 반경 민감도.

입력: build_landprice.py 출력, outputs/features_ext.csv·scenario_tram_uplift.csv (train_analyze.py)
출력 (outputs/)
- robust_line1.csv       : 검정별 효과(%), 95% 구간, 개통 전 차이
- robust_radius.csv      : 상권별 정거장 400/500/600m 안 셀 비율과 트램 효과(기본)
- robust_line1.png

검정 (모두 1호선 1단계, 기준 2005년, 개통 후 2007~2010 평균)
 A 기본            : 역 500m vs 1~3km
 B 비교군 거리     : 1~2km / 2~3km / 1.5~4km
 C 처리 반경       : 300 / 400 / 600m
 D 같은 구 안 비교 : 비교군을 처리 필지와 같은 구(동·중·서구)로 제한 → 원도심 전체 반등 영향 줄이기
 E 가짜 개통연도   : 2001년 개통이라 치고 기준 2000, '개통 후' 2002~2004 (실제 개통 전) → 0 근처여야 정상
 F 가짜 역         : 아직 없던 트램 2호선 정거장 500m(1호선 역 1km 밖) vs 1~3km, 같은 기간 → 0 근처여야 정상
"""
import numpy as np
import pandas as pd

import config as C
from analyze_landprice import event_study, load, pct, window_mean

POST = range(2007, 2011)


def run(G, W, tr, ct, base=2005, post=POST, years=None):
    years = years or sorted(set(range(2000, 2011)) | {base})
    es, boot, yrs = event_study(G, W, tr, ct, base, years)
    m, lo, hi = window_mean(es, boot, yrs, post)
    pre = [y for y in yrs if y < base and y >= base - 5]
    pm = window_mean(es, boot, yrs, pre)[0] if pre else np.nan
    return {"effect_pct": pct(m), "ci_lo": pct(lo), "ci_hi": pct(hi), "pre_diff_pct": pct(pm),
            "n_treat": int(es.n_treat.max()), "n_ctrl": int(es.n_ctrl.max())}


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
    ph1 = G.l1_phase == 1
    gu = (G.dong_code // 100000).astype(int)            # 시군구 코드 5자리
    rows = []

    def add(group, label, **kw):
        r = run(G, W, **kw)
        rows.append({"group": group, "test": label, **r})
        print(f"  {group:<10} {label:<28} {r['effect_pct']:+6.1f}%  [{r['ci_lo']:+.1f}, {r['ci_hi']:+.1f}]  "
              f"개통 전 차이 {r['pre_diff_pct']:+.1f}%", flush=True)

    tr500 = ph1 & (G.d_l1 <= 500)
    ctl = (G.d_l1 > 1000) & (G.d_l1 <= 3000)
    add("A 기본", "역 500m vs 1~3km", tr=tr500, ct=ctl)
    for a, b in [(1000, 2000), (2000, 3000), (1500, 4000)]:
        add("B 비교군", f"비교군 {a / 1000:g}~{b / 1000:g}km", tr=tr500, ct=(G.d_l1 > a) & (G.d_l1 <= b))
    for r_ in (300, 400, 600):
        add("C 처리 반경", f"역 {r_}m", tr=ph1 & (G.d_l1 <= r_), ct=ctl)
    tg = set(gu[tr500])
    add("D 같은 구", "비교군을 처리 필지와 같은 구로", tr=tr500, ct=ctl & gu.isin(tg))
    add("E 가짜 개통", "2001년 개통 가정 (2002~04)", tr=tr500, ct=ctl, base=2000, post=range(2002, 2005),
        years=list(range(1995, 2006)))
    far = G.d_l1 > 1000
    add("F 가짜 역", "트램 정거장 500m (2005→2007~10)", tr=(G.d_tram <= 500) & far,
        ct=(G.d_tram > 1000) & (G.d_tram <= 3000) & far)
    R = pd.DataFrame(rows)
    R.to_csv(C.OUT_DIR / "robust_line1.csv", index=False, encoding="utf-8-sig")

    # 판정
    base = R.iloc[0]
    main_tests = R[R.group.str[0].isin(list("BCD"))]
    same_sign = (main_tests.effect_pct > 0).mean()
    plac = R[R.group.str[0].isin(list("EF"))]
    plac_ok = ((plac.ci_lo < -0.05) & (plac.ci_hi > 0.05)).all()     # 구간이 0을 확실히 포함해야 통과
    print(f"\n[판정] 기본 {base.effect_pct:+.1f}% | 비교군·반경·같은 구 검정 {len(main_tests)}개 중 "
          f"{same_sign:.0%} 가 같은 방향(+), 범위 {main_tests.effect_pct.min():+.1f}~{main_tests.effect_pct.max():+.1f}% | "
          f"가짜 검정 {'통과(0 포함)' if plac_ok else '일부 경계/실패 → ' + ', '.join(plac[~((plac.ci_lo < -0.05) & (plac.ci_hi > 0.05))].test) + ' 확인 필요'}")

    # 정거장 반경 민감도 (트램 시나리오)
    e = pd.read_csv(C.OUT_DIR / "features_ext.csv", encoding="utf-8-sig")
    ds = pd.read_csv(C.OUT_DIR / "daejeon_tram_area_dataset.csv", encoding="utf-8-sig")
    dist = ds.drop_duplicates("area_id").set_index("area_id").dist_tram_m
    e["dist"] = e.area_id.map(dist)
    sc = pd.read_csv(C.OUT_DIR / "scenario_tram_uplift.csv", encoding="utf-8-sig").set_index("area_id")
    names = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig").set_index("code").name
    cell = e.drop_duplicates("area_id").assign(cell=lambda d: d.area_id.str.rsplit("_", n=1).str[0])
    cell = cell.drop_duplicates("cell")
    rad = cell.groupby("zone").agg(**{f"in{r}": ("dist", lambda v, r=r: (v <= r).mean()) for r in (400, 500, 600)})
    # 기본 효과(500m) 를 400·600m 로 바꾸면: 500m 안 셀의 평균 효과 × 해당 반경 안 셀 비율
    eff_in = sc[sc.in_tram_500 == 1].groupby("zone").eff_base.mean()
    for r in (400, 500, 600):
        rad[f"eff{r}_pct"] = (np.expm1(eff_in.reindex(rad.index).fillna(eff_in.mean())) * 100
                              * rad[f"in{r}"]).round(2)
    rad.insert(0, "name", rad.index.map(names))
    rad["changes_group"] = ((rad.in400 == 0) != (rad.in600 == 0)).map({True: "반경에 따라 트램 근접 여부 바뀜", False: ""})
    rad.round(3).to_csv(C.OUT_DIR / "robust_radius.csv", encoding="utf-8-sig")
    ch = rad[rad.changes_group != ""]
    print("\n[반경 민감도] 400m↔600m 에서 트램 근접 여부가 바뀌는 상권:",
          ", ".join(ch.name) if len(ch) else "없음")

    fig, ax = plt.subplots(figsize=(9, 5))
    y = np.arange(len(R))[::-1]
    col = ["C3" if g.startswith("A") else ("gray" if g[0] in "EF" else "C0") for g in R.group]
    ax.errorbar(R.effect_pct, y, xerr=[R.effect_pct - R.ci_lo, R.ci_hi - R.effect_pct], fmt="none", ecolor=col, lw=2)
    ax.scatter(R.effect_pct, y, c=col, zorder=3)
    ax.set_yticks(y); ax.set_yticklabels([f"{g} | {t}" for g, t in zip(R.group, R.test)], fontsize=8)
    ax.axvline(0, c="k", lw=.7)
    ax.set_xlabel("효과 (%) — 95% 구간"); ax.set_title("1호선 1단계 역세권 지가 효과 강건성 (회색 = 가짜 검정, 0 근처여야 정상)")
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "robust_line1.png", dpi=130)
    print("→ outputs/robust_line1.csv, robust_radius.csv, robust_line1.png")


if __name__ == "__main__":
    main()
