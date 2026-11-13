"""상권 사건 효과를 행정동 82개 단위로 다시 추정 (비교군 7~15개 → 약 60개).

입력: outputs/dong_panel_land.csv, dong_panel_store.csv (build_dong_panel.py), data/area_events.csv,
      data/sangkwon_areas.csv, data/line1_stations.csv, data/daejeon_dong_2023.geojson
출력: outputs/dong_event_effects.csv, outputs/dong_event_effects.png

처리 행정동
- 1호선 1·2단계(E01·E02): 해당 단계 역이 있는 행정동
- 나머지 사건: 사건 상권 기준점이 있는 행정동
비교 행정동: 어떤 사건에도 처리되지 않은 행정동 (1호선 역 행정동도 제외)
방법
- 지가(연): 사건 뒤 첫 1월 1일 공시 = t0, 사건 전 4년 평균 대비 사건 후 4년 평균의 log 변화 차이 (2006 제외)
- 점포 비중(분기): 같은 자료 구간(regime) 안에서 사건 전·후 최대 3년, 대전 내 점포 비중 log 변화 차이
- 가짜 처리군 검정: 비교 행정동 하나하나를 처리군으로 놓고 같은 계산 → 실제 효과의 순위 p (양측)
"""
import json

import numpy as np
import pandas as pd

import config as C
from build_dong_layer import DONG, label_points

WIN = 4          # 지가 전후 연수
WIN_Q = 12       # 점포 전후 분기 수


def treated_dongs():
    gj = json.load(open(DONG, encoding="utf-8"))
    ev = pd.read_csv(C.ROOT / "data" / "area_events.csv", encoding="utf-8-sig")
    ev = ev[ev.area_codes != "ALL"]
    areas = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig")
    cen = areas.anchors.str.split(";").str[0].str.split(expand=True).astype(float)
    areas["k"] = label_points(gj, cen[1].values, cen[0].values)
    a2k = dict(zip(areas.code, areas.k))
    l1 = pd.read_csv(C.ROOT / "data" / "line1_stations.csv", encoding="utf-8-sig")
    l1["k"] = label_points(gj, l1.lon.values, l1.lat.values)
    T = {}
    for _, e in ev.iterrows():
        if e.event_id in ("E01", "E02"):
            ph = 1 if e.event_id == "E01" else 2
            T[e.event_id] = sorted(set(l1.k[(l1.phase == ph) & (l1.k >= 0)]))
        else:
            T[e.event_id] = sorted({a2k[c] for c in e.area_codes.split(";") if a2k.get(c, -1) >= 0})
    excl = set().union(*T.values()) | set(l1.k[l1.k >= 0])
    controls = [k for k in range(len(gj["features"])) if k not in excl]
    return ev.set_index("event_id"), T, controls


def did_land(L, treat, controls, t0):
    pre = [y for y in range(t0 - WIN, t0) if y != 2006]
    post = [y for y in range(t0, t0 + WIN) if y <= L.index.max()]
    if min(pre) < L.index.min() or len(post) < 2:
        return None
    d = L.loc[post].mean() - L.loc[pre].mean()
    tr = [k for k in treat if k in d and not np.isnan(d[k])]
    ct = [k for k in controls if k in d and not np.isnan(d[k])]
    if not tr:
        return None
    eff = d[tr].mean() - d[ct].mean()
    plac = np.array([d[c] - d[[x for x in ct if x != c]].mean() for c in ct])
    p = (np.sum(np.abs(plac) >= abs(eff)) + 1) / (len(plac) + 1)
    return eff, p, len(ct), plac.std(), f"{pre[0]}-{pre[-1]} → {post[0]}-{post[-1]}"


def did_store(S, reg, treat, controls, t0):
    periods = list(S.index)
    after = [i for i, p in enumerate(periods) if pd.Timestamp(p[:4] + "-" + p[4:] + "-01") >= t0]
    if not after:
        return None
    i0 = after[0]
    r0 = reg.get(periods[i0 - 1]) if i0 > 0 else None
    pre = [p for p in periods[max(0, i0 - WIN_Q):i0] if reg[p] == r0]
    post = [p for p in periods[i0:i0 + WIN_Q] if reg[p] == r0]
    if len(pre) < 2 or len(post) < 2:
        return None
    d = S.loc[post].mean() - S.loc[pre].mean()
    tr = [k for k in treat if k in d and not np.isnan(d[k])]
    ct = [k for k in controls if k in d and not np.isnan(d[k])]
    if not tr:
        return None
    eff = d[tr].mean() - d[ct].mean()
    plac = np.array([d[c] - d[[x for x in ct if x != c]].mean() for c in ct])
    p = (np.sum(np.abs(plac) >= abs(eff)) + 1) / (len(plac) + 1)
    return eff, p, len(ct), plac.std(), f"{pre[0]}-{pre[-1]} → {post[0]}-{post[-1]} (구간 {r0})"


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

    ev, T, controls = treated_dongs()
    DL = pd.read_csv(C.OUT_DIR / "dong_panel_land.csv", encoding="utf-8-sig")
    names = DL.drop_duplicates("k").set_index("k").apply(lambda r: f"{r.si} {r.dong}", axis=1)
    L = np.log(DL.pivot(index="year", columns="k", values="idx"))
    DS = pd.read_csv(C.OUT_DIR / "dong_panel_store.csv", dtype={"period": str}, encoding="utf-8-sig")
    S = np.log(DS.pivot(index="period", columns="k", values="share"))
    reg = DS.drop_duplicates("period").set_index("period").regime.to_dict()
    print(f"비교 행정동 {len(controls)}개 (사건·1호선 역 행정동 제외)")

    rows = []
    for eid, e in ev.iterrows():
        dt = pd.Timestamp(e.date)
        tr = T[eid]
        base = {"event": eid, "label": e.description[:34], "expected": e.direction,
                "treated_dongs": ", ".join(names.get(k, str(k)) for k in tr)}
        r = did_land(L, tr, controls, dt.year + 1)
        if r:
            rows.append({**base, "outcome": "지가", "effect_pct": round(np.expm1(r[0]) * 100, 1),
                         "placebo_p": round(r[1], 3), "n_controls": r[2],
                         "placebo_sd_pct": round(r[3] * 100, 1), "window": r[4]})
        r = did_store(S, reg, tr, controls, dt)
        if r:
            rows.append({**base, "outcome": "점포 비중", "effect_pct": round(np.expm1(r[0]) * 100, 1),
                         "placebo_p": round(r[1], 3), "n_controls": r[2],
                         "placebo_sd_pct": round(r[3] * 100, 1), "window": r[4]})
    R = pd.DataFrame(rows)
    R["판정"] = np.select([R.placebo_p <= 0.05, R.placebo_p <= 0.10], ["유의(5%)", "약한 근거(10%)"], "구별 안 됨")
    R.to_csv(C.OUT_DIR / "dong_event_effects.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(R[["event", "label", "outcome", "effect_pct", "placebo_p", "n_controls", "판정", "treated_dongs"]]
          .to_string(index=False))

    fig, ax = plt.subplots(figsize=(10, 0.42 * len(R) + 1.5))
    y = np.arange(len(R))[::-1]
    col = ["C3" if p <= 0.05 else ("C1" if p <= 0.1 else "gray") for p in R.placebo_p]
    ax.barh(y, R.effect_pct, color=col)
    ax.errorbar(R.effect_pct, y, xerr=1.96 * R.placebo_sd_pct, fmt="none", ecolor="k", lw=.8)
    ax.set_yticks(y); ax.set_yticklabels([f"{a} {b[:18]} ({c})" for a, b, c in zip(R.event, R.label, R.outcome)], fontsize=8)
    ax.axvline(0, c="k", lw=.6)
    ax.set_xlabel("효과 (%) — 막대: 빨강 p≤0.05, 주황 p≤0.10, 회색 구별 안 됨 / 선: 가짜 처리군 분포 ±1.96sd")
    ax.set_title(f"행정동 단위 사건 효과 (비교 행정동 {len(controls)}개)")
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "dong_event_effects.png", dpi=130)
    print("→ outputs/dong_event_effects.csv, dong_event_effects.png")


if __name__ == "__main__":
    main()
