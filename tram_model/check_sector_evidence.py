"""업종 구성 변화 근거 점검: 대전 1호선 인허가 이중차분(카페·빵·과자)이 '확실'한지 추가 검사

analyze_line1_permits.py 의 자료·함수를 그대로 씀. 입력은 같음(data/raw/permits, data/line1_stations.csv).
출력: outputs/sector_evidence_checks.csv, outputs/sector_evidence_es.csv
검사
 1. 업종별 연도 효과(사건연구): 개통 전 2002~2004 계수가 0 근처인지(사전 추세), 개통 후 모양(서서히 커지는지)
 2. 표본 정의: 기존은 '2005년에 그 업종 점포가 있던 격자'만 → 새로 생긴 격자(빈 곳에 처음 생긴 카페) 빠짐.
    '2005년 음식점이 1곳 이상 있던 모든 격자'로 넓혀 다시 추정
 3. 구성(비중): 격자 음식점 중 카페(빵·과자) 비율의 이중차분 → '점포 수는 그대로, 구성만 바뀜'을 직접 검정
 4. 거리 띠: 0~300, 300~500, 500~750, 750~1000m (vs 1~3km) → 효과가 역 가까이에 몰리는지
 5. 2단계 재현: 1호선 2단계(2007-12 개통, 2008년부터) 역 500m(1단계 역 1km 밖)에서도 같은 효과가 나오는지 — 독립 표본
 6. 밀도 맞춘 비교군: 2005년 음식점 수가 처리군 범위(하위 25% 이상)인 비교군 격자만 → '원래 번화한 곳에 카페가 늘었다' 반박
 7. 여러 업종 검정 보정: 6개 업종 Bonferroni(0.05/6 = 0.0083)
 8. 비중·전체 점포: 1단계·2단계 각각 카페·빵 비중(가짜 개통연도 포함), 전체 음식점 수(기본·밀도 맞춤) → outputs/sector_evidence_share.csv
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_line1_permits as AP

SECS = ["카페", "빵·과자", "식사 음식점", "간편식(분식·패스트푸드·조리판매)"]


def panel_all_cells(q, sec, years=AP.YEARS):
    """2005년 음식점(아무 업종) 1곳 이상 격자 전부에서 그 업종 점포 수 (빈 격자도 0으로 포함)"""
    allp = AP.cell_panel(q, years)
    base = allp[allp.year == AP.BASE_YEAR].set_index("cell").active
    keep = base[base >= 1].index
    sp = AP.cell_panel(q[q.sector == sec], years) if (q.sector == sec).any() else allp.assign(active=0)
    sp = allp[["cell", "year", "active"]].rename(columns={"active": "all"}).merge(
        sp[["cell", "year", "active"]], on=["cell", "year"], how="left").fillna({"active": 0})
    grp = q.groupby("cell").group.first()
    sp["treat"] = (sp.cell.map(grp) == "처리군").astype(int)
    sp = sp[sp.cell.isin(keep)].copy()
    sp["ly"] = np.log(sp.active + 1)
    sp["share"] = sp.active / sp["all"].clip(lower=1)
    sp["base_all"] = sp.cell.map(base)
    return sp


def es(panel, ycol="ly", open_year=AP.OPEN_YEAR, base=AP.BASE_YEAR):
    yrs = [t for t in AP.YEARS if t != base]
    d = panel.copy(); xc = []
    for t in yrs:
        c = f"e{t}"; d[c] = ((d.year == t) & (d.treat == 1)).astype(float); xc.append(c)
    b, se, _ = AP.twfe(d, ycol, xc)
    return pd.DataFrame({"year": yrs, "b": b, "se": se})


def grp(qq):
    qq = qq[qq.group.notna()]; cg = qq.groupby("cell").group.agg(lambda s: s.value_counts().index[0]); return qq[qq.group == qq.cell.map(cg)]


def share_checks(p):
    out = []
    q1 = p.copy(); q1["group"] = np.where(q1.d_p1 <= 500, "처리군", np.where((q1.d_any > 1000) & (q1.d_any <= 3000), "비교군", None))
    q2 = p.copy(); q2["group"] = np.where((q2.d_p2 <= 500) & (q2.d_p1 > 1000), "처리군", np.where((q2.d_any > 1000) & (q2.d_any <= 3000), "비교군", None))
    def row(phase, what, b, se, unit, fake=None):
        k = 100 if unit == "%p" else None
        v = (lambda x: x * 100) if unit == "%p" else AP.pct
        r = dict(단계=phase, 지표=what, 단위=unit, 효과=round(v(b), 2), 하한=round(v(b - 1.96 * se), 2), 상한=round(v(b + 1.96 * se), 2), p값=round(AP._pval(b / se), 4))
        if fake is not None: r.update(가짜연도_효과=round(v(fake[0]), 2), 가짜연도_p=round(AP._pval(fake[0] / fake[1]), 4))
        out.append(r)
    for phase, qq, oy, fy in [("1단계(2006)", grp(q1), 2006, 2004), ("2단계(2008)", grp(q2), 2008, 2006)]:
        for sec in ("카페", "빵·과자"):
            A = panel_all_cells(qq, sec)
            b, se, _ = AP.did(A, "treat", oy, ycol="share"); bf, sef, _ = AP.did(A, "treat", fy, ycol="share", years=range(2002, oy))
            row(phase, f"{sec} 비중(음식점 중)", b, se, "%p", (bf, sef))
        A = panel_all_cells(qq, "카페"); A["lall"] = np.log(A["all"] + 1)
        b, se, _ = AP.did(A, "treat", oy, ycol="lall"); bf, sef, _ = AP.did(A, "treat", fy, ycol="lall", years=range(2002, oy))
        row(phase, "전체 음식점 수", b, se, "%", (bf, sef))
        lo25 = A[(A.treat == 1) & (A.year == 2005)]["all"].quantile(.25); M = A[(A.treat == 1) | (A.base_all >= lo25)]
        b, se, _ = AP.did(M, "treat", oy, ycol="lall"); row(phase, "전체 음식점 수(밀도 맞춤)", b, se, "%")
        b, se, _ = AP.did(M, "treat", oy, ycol="share"); row(phase, "카페 비중(밀도 맞춤)", b, se, "%p")
    S = pd.DataFrame(out); S.to_csv(os.path.join(AP.OUT_DIR, "sector_evidence_share.csv"), index=False, encoding="utf-8-sig")
    print(S.to_string(index=False))


def main():
    if not [f for f in os.listdir(AP.RAW_DIR) if f.endswith(".csv")] if os.path.isdir(AP.RAW_DIR) else True:
        print("인허가 자료 없음 (data/raw/permits) → 건너뜀"); return
    p = AP.load_permits(); st = AP.load_stations(); p = AP.assign_space(p, st)
    p["sector"] = AP.sector_of(p)
    s2 = st[st.phase == 2]; p["d_p2"] = AP._min_dist(p.lat, p.lon, s2.lat, s2.lon)
    q = AP.build_sample(p); q["sector"] = AP.sector_of(q)
    rows, esr = [], []
    def add(check, sec, b, se, G, note=""):
        rows.append(dict(검사=check, 업종=sec, 효과_퍼센트=round(AP.pct(b), 1), 하한=round(AP.pct(b - 1.96 * se), 1), 상한=round(AP.pct(b + 1.96 * se), 1),
                         p값=round(AP._pval(b / se), 4) if se > 0 else np.nan, 격자수=G, 비고=note))
    for sec in SECS:
        g = q[q.sector == sec]
        sp = AP.panel_for(g)                                   # 기존 정의
        b, se, G = AP.did(sp, "treat", AP.OPEN_YEAR); add("0 기존(2005년 그 업종 있던 격자)", sec, b, se, G)
        e = es(sp); e["업종"] = sec; e["정의"] = "기존"; esr.append(e)
        pre = e[e.year < AP.OPEN_YEAR]
        add("1 개통 전 연도 효과 평균(2002~2004)", sec, pre.b.mean(), np.sqrt((pre.se ** 2).mean() / len(pre)), G, "0 근처여야 통과")
        post = e[e.year >= AP.OPEN_YEAR].set_index("year").b
        rows[-1]["비고"] += f" · 개통 후 연도별 % = " + ", ".join(f"{t}:{AP.pct(v):+.0f}" for t, v in post.items())
        A = panel_all_cells(q, sec)                            # 2 빈 격자 포함
        b, se, G = AP.did(A, "treat", AP.OPEN_YEAR); add("2 모든 음식점 격자(빈 곳 포함)", sec, b, se, G)
        ea = es(A); ea["업종"] = sec; ea["정의"] = "모든 격자"; esr.append(ea)
        b, se, G = AP.did(A, "treat", AP.OPEN_YEAR, ycol="share")   # 3 구성 비중 (%p)
        rows.append(dict(검사="3 음식점 중 비중(%p)", 업종=sec, 효과_퍼센트=round(b * 100, 2), 하한=round((b - 1.96 * se) * 100, 2),
                         상한=round((b + 1.96 * se) * 100, 2), p값=round(AP._pval(b / se), 4), 격자수=G,
                         비고=f"2005년 처리군 평균 비중 {A[(A.treat == 1) & (A.year == 2005)].share.mean() * 100:.1f}%"))
        for lo, hi in [(0, 300), (300, 500), (500, 750), (750, 1000)]:   # 4 거리 띠
            qq = p.copy(); qq["group"] = np.where((qq.d_p1 > lo) & (qq.d_p1 <= hi), "처리군", np.where((qq.d_any > 1000) & (qq.d_any <= 3000), "비교군", None))
            qq = qq[qq.group.notna()]; cg = qq.groupby("cell").group.agg(lambda s: s.value_counts().index[0]); qq = qq[qq.group == qq.cell.map(cg)]
            AA = panel_all_cells(qq, sec)
            if AA.treat.sum() == 0: continue
            b, se, G = AP.did(AA, "treat", AP.OPEN_YEAR); add(f"4 거리 {lo}~{hi}m", sec, b, se, G)
        qq = p.copy()                                          # 5 2단계 재현
        qq["group"] = np.where((qq.d_p2 <= 500) & (qq.d_p1 > 1000), "처리군", np.where((qq.d_any > 1000) & (qq.d_any <= 3000), "비교군", None))
        qq = qq[qq.group.notna()]; cg = qq.groupby("cell").group.agg(lambda s: s.value_counts().index[0]); qq = qq[qq.group == qq.cell.map(cg)]
        B2 = panel_all_cells(qq, sec)
        b, se, G = AP.did(B2, "treat", 2008); add("5 2단계 역 재현 (2008~)", sec, b, se, G, f"처리 격자 {B2[B2.treat == 1].cell.nunique()}")
        bf, sef, _ = AP.did(B2, "treat", 2006, years=range(2002, 2008)); add("5b 2단계 가짜 개통연도 2006", sec, bf, sef, G, "0 근처여야 통과")
        lo25 = A[(A.treat == 1) & (A.year == 2005)].base_all.quantile(.25)   # 6 밀도 맞춤
        M = A[(A.treat == 1) | (A.base_all >= lo25)]
        b, se, G = AP.did(M, "treat", AP.OPEN_YEAR); add("6 밀도 맞춘 비교군", sec, b, se, G, f"비교군 2005년 음식점 ≥{lo25:.0f}곳")
    R = pd.DataFrame(rows)
    R["Bonferroni(6업종) 통과"] = np.where(R.검사.str.startswith(("0", "2", "3", "5 ", "6")), R.p값 < 0.05 / 6, np.nan)
    R.to_csv(os.path.join(AP.OUT_DIR, "sector_evidence_checks.csv"), index=False, encoding="utf-8-sig")
    share_checks(p)
    E = pd.concat(esr); E["효과_%"] = [AP.pct(v) for v in E.b]; E.to_csv(os.path.join(AP.OUT_DIR, "sector_evidence_es.csv"), index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 90)
    print(R.to_string(index=False))


if __name__ == "__main__":
    main()
