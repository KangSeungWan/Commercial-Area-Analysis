"""비음식 업종(행정안전부 인허가) 대전 1호선 개통 전후 점검 — 카페와 같은 검사를 다른 업종에

입력: data/raw/permits_other/<분류>_<업종>_대전광역시.csv  (공공데이터포털 '행정안전부_생활_미용업' 등, file.localdata.go.kr 대전 파일)
      data/raw/permits/ (음식점 인허가: 비중의 분모 = 음식점 + 비음식 업종 전체)
      ('식품_' 으로 시작하는 파일은 음식점이라 여기서는 읽지 않음)
출력: outputs/sector_evidence_other.csv          업종 × 검사
      outputs/sector_evidence_other_summary.csv  업종별 자료 품질 · 핵심 수치 · 판정
      outputs/sector_evidence_other_es.csv       업종별 연도 효과(사건연구)

자료 품질: 업종마다 폐업일 기록이 시작된 해가 다름. 개통(2006) 전부터 폐업이 기록되지 않으면 그 전 점포 수가
          '살아남은 곳'만 남아 과소 → 개통 후 늘어난 것처럼 보임 → '자료 부족'으로 제외.
          기준: 폐업 10건 이상 처음 기록된 해 ≤ 2003. 분석 기간 2003~2014 (개통 전 2003~2005).
검사(카페와 같음): 0 기본 이중차분(2005년 그 업종이 있던 격자), 1 개통 전 추세(2003~2004 연도 효과),
     2 빈 격자 포함, 3 전체 점포 중 비중(%p), 5 2단계 역 재현 + 가짜 개통연도, 6 밀도 맞춘 비교군
판정: 확실 = 기본 p < 0.05/업종 수(Bonferroni) + 개통 전 추세 없음(p > 0.1) + (2단계 같은 방향 p < 0.05 또는 밀도 맞춤 p < 0.05)
      참고 = 기본 p < 0.05 이지만 위 조건 일부 미달, 또는 기본은 못 넘었지만 빈 격자 포함·밀도 맞춤이 같은 방향으로 p < 0.05
      (2단계 재현은 가짜 개통연도 2006 검사를 통과해야 인정) / 효과 없음 = 기본 p ≥ 0.05 / 자료 부족 = 폐업 기록이 늦게 시작 또는 처리 격자 < 10
"""
import os, sys, glob, unicodedata
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_line1_permits as AP

RAW_O = os.path.join(AP.HERE, "data", "raw", "permits_other")
YEARS = list(range(2003, 2015))
BASE, OPEN, FAKE = 2005, AP.OPEN_YEAR, 2004
GROUP = {"미용업": "생활서비스", "세탁업": "생활서비스", "노래연습장업": "생활서비스(여가)", "체력단련장업": "생활서비스(여가)",
         "약국": "보건의료", "의원": "보건의료", "안경업": "소매", "숙박업": "기타(숙박)"}


def load_other():
    files = [f for f in sorted(glob.glob(os.path.join(RAW_O, "*.csv")))
             if not unicodedata.normalize("NFC", os.path.basename(f)).startswith("식품")]
    frames, quality = [], []
    for path in files:
        name = unicodedata.normalize("NFC", os.path.basename(path))
        parts = name.replace(".csv", "").split("_")
        sec = parts[1] if len(parts) >= 3 else parts[0]
        df = AP._read_csv(path); cols = list(df.columns)
        c_x, c_y = AP._find(cols, "좌표", "X"), AP._find(cols, "좌표", "Y")
        c_state = AP._find(cols, "영업상태명", exclude=("상세",))
        c_kind = AP._find(cols, "업태구분명")
        d = pd.DataFrame({"id": df[AP._find(cols, "관리번호")], "service": sec, "kind": df[c_kind] if c_kind else "",
                          "open": AP._parse_date(df[AP._find(cols, "인허가일자", exclude=("취소",))]),
                          "close": AP._parse_date(df[AP._find(cols, "폐업일자")]), "state": df[c_state],
                          "x": pd.to_numeric(df[c_x].astype(str).str.strip(), errors="coerce"),
                          "y": pd.to_numeric(df[c_y].astype(str).str.strip(), errors="coerce")})
        if sec == "의원":
            d = d[d.kind.isin(["의원", "한의원", "치과의원"])]
        cy = d.close.dt.year.value_counts()
        first = int(min([y for y, n in cy.items() if n >= 10], default=9999))
        bad = d.open.isna() | d.x.isna() | d.y.isna() | (d.state.fillna("").str.contains("폐업|취소|말소") & d.close.isna())
        quality.append(dict(업종=sec, 앱_업종그룹=GROUP.get(sec, "기타"), 대전_행=len(d), 좌표_있음=round(1 - d.x.isna().mean(), 3),
                            폐업기록_시작=first, 폐업_2003_2005=int(cy.reindex([2003, 2004, 2005]).fillna(0).sum()),
                            폐업_2009_2012_연평균=round(cy.reindex(range(2009, 2013)).fillna(0).mean(), 1),
                            자료_사용=first <= 2003))
        print(f"  {sec}: 대전 {len(d):,}행, 폐업 기록 시작 {first}")
        frames.append(d[~bad])
    p = pd.concat(frames, ignore_index=True)
    p["lat"], p["lon"] = AP.epsg5174_to_wgs84(p.x.values, p.y.values)
    return p, pd.DataFrame(quality)


def sector_panel(q, sec, mode):
    allp = AP.cell_panel(q, YEARS)[["cell", "year", "active"]].rename(columns={"active": "all"})
    s = q[q.sector == sec]
    sp = AP.cell_panel(s, YEARS)[["cell", "year", "active"]] if len(s) else allp.assign(active=0)[["cell", "year", "active"]]
    d = allp.merge(sp, on=["cell", "year"], how="left").fillna({"active": 0})
    grp = q.groupby("cell").group.first()
    d["treat"] = (d.cell.map(grp) == "처리군").astype(int)
    b_all = d[d.year == BASE].set_index("cell")["all"]; b_sec = d[d.year == BASE].set_index("cell").active
    d["base_all"] = d.cell.map(b_all)
    keep = b_sec[b_sec >= 1].index if mode == "had" else b_all[b_all >= 1].index
    d = d[d.cell.isin(keep)].copy()
    d["ly"] = np.log(d.active + 1); d["share"] = d.active / d["all"].clip(lower=1)
    return d


def es(panel):
    d = panel.copy(); xc = []
    for t in [y for y in YEARS if y != BASE]:
        d[f"e{t}"] = ((d.year == t) & (d.treat == 1)).astype(float); xc.append(f"e{t}")
    b, se, _ = AP.twfe(d, "ly", xc)
    return pd.DataFrame({"year": [y for y in YEARS if y != BASE], "b": b, "se": se})


def grouped(p, treat_mask):
    q = p.copy()
    q["group"] = np.where(treat_mask, "처리군", np.where((q.d_any > AP.CTRL_MIN) & (q.d_any <= AP.CTRL_MAX), "비교군", None))
    q = q[q.group.notna()]
    cg = q.groupby("cell").group.agg(lambda s: s.value_counts().index[0])
    return q[q.group == q.cell.map(cg)]


def main():
    if not os.path.isdir(RAW_O) or not [f for f in os.listdir(RAW_O) if f.endswith(".csv")]:
        print("비음식 인허가 자료 없음 (data/raw/permits_other) → 건너뜀"); return
    print("1) 비음식 업종 인허가"); po, Q = load_other()
    print("2) 음식점 인허가 (비중 분모)"); pf = AP.load_permits(); pf["sector"] = "음식점"
    po["sector"] = po.service
    p = pd.concat([pf, po], ignore_index=True)
    st = AP.load_stations(); p = AP.assign_space(p, st)
    s2 = st[st.phase == 2]; p["d_p2"] = AP._min_dist(p.lat, p.lon, s2.lat, s2.lon)
    q1 = grouped(p, p.d_p1 <= AP.TREAT_R)
    q2 = grouped(p, (p.d_p2 <= 500) & (p.d_p1 > 1000))
    use = Q[Q.자료_사용].업종.tolist(); K = max(len(use), 1)
    rows, esr = [], []

    def add(sec, check, b, se, G, unit="%", note=""):
        v = (lambda x: x * 100) if unit == "%p" else AP.pct
        rows.append(dict(업종=sec, 검사=check, 단위=unit, 효과=round(v(b), 2), 하한=round(v(b - 1.96 * se), 2), 상한=round(v(b + 1.96 * se), 2),
                         p값=round(AP._pval(b / se), 4) if se > 0 else np.nan, 격자수=G, 비고=note))

    summ = []
    for sec in Q.업종:
        qr = Q.set_index("업종").loc[sec]
        H = sector_panel(q1, sec, "had"); nt = H[H.treat == 1].cell.nunique()
        if not qr.자료_사용 or nt < 10:
            summ.append(dict(업종=sec, 판정="자료 부족", 이유=(f"폐업 기록이 {qr.폐업기록_시작}년부터 → 개통 전 점포 수 과소" if not qr.자료_사용
                                                         else f"처리 격자 {nt}개"))); continue
        b0, s0, G = AP.did(H, "treat", OPEN); add(sec, "0 기본(2005년 그 업종 있던 격자)", b0, s0, G, note=f"처리 격자 {nt}")
        e = es(H); e["업종"] = sec; esr.append(e)
        pre = e[e.year < OPEN]; bp, sp_ = pre.b.mean(), np.sqrt((pre.se ** 2).mean() / len(pre))
        post = e[e.year >= OPEN].set_index("year").b
        add(sec, "1 개통 전 연도 효과 평균(2003~2004)", bp, sp_, G, note="0 근처여야 통과 · 개통 후 % = " + ", ".join(f"{t}:{AP.pct(v):+.0f}" for t, v in post.items()))
        A = sector_panel(q1, sec, "all")
        b2, s2_, G2 = AP.did(A, "treat", OPEN); add(sec, "2 빈 격자 포함", b2, s2_, G2)
        b3, s3, _ = AP.did(A, "treat", OPEN, ycol="share")
        add(sec, "3 전체 점포 중 비중(%p)", b3, s3, G2, "%p", f"2005년 처리군 평균 비중 {A[(A.treat == 1) & (A.year == BASE)].share.mean() * 100:.1f}%")
        B = sector_panel(q2, sec, "all")
        b5, s5, G5 = AP.did(B, "treat", 2008); add(sec, "5 2단계 역 재현(2008~)", b5, s5, G5, note=f"처리 격자 {B[B.treat == 1].cell.nunique()}")
        bf, sf, _ = AP.did(B, "treat", 2006, years=range(2003, 2008)); add(sec, "5b 2단계 가짜 개통연도 2006", bf, sf, G5, note="0 근처여야 통과")
        lo25 = A[(A.treat == 1) & (A.year == BASE)].base_all.quantile(.25); M = A[(A.treat == 1) | (A.base_all >= lo25)]
        b6, s6, G6 = AP.did(M, "treat", OPEN); add(sec, "6 밀도 맞춘 비교군", b6, s6, G6, note=f"비교군 2005년 점포 ≥{lo25:.0f}곳")
        p0, ppre, p2, p5, pf5, p6 = (AP._pval(x / y) for x, y in [(b0, s0), (bp, sp_), (b2, s2_), (b5, s5), (bf, sf), (b6, s6)])
        rep5 = p5 < 0.05 and np.sign(b5) == np.sign(b0) and pf5 > 0.05          # 2단계 재현 (가짜 개통연도 통과해야 인정)
        rep6 = p6 < 0.05 and np.sign(b6) == np.sign(b0)
        sure = p0 < 0.05 / K and ppre > 0.1 and (rep5 or rep6)
        alt = p2 < 0.05 and p6 < 0.05 and np.sign(b2) == np.sign(b6)             # 기본은 못 넘었지만 빈 격자·밀도 맞춤이 같은 방향
        dirn = "증가" if (b0 if p0 < 0.05 else b6) > 0 else "감소"
        verdict = f"확실({dirn})" if sure else (f"참고({dirn})" if (p0 < 0.05 or alt) else "효과 없음")
        why = []
        if not sure:
            if p0 >= 0.05: why.append(f"기본 검사 유의하지 않음(p {p0:.2f})")
            elif p0 >= 0.05 / K: why.append(f"여러 업종 보정 미통과(p {p0:.3f})")
            if alt and p0 >= 0.05: why.append(f"빈 격자 포함 {AP.pct(b2):+.1f}%·밀도 맞춤 {AP.pct(b6):+.1f}%는 유의")
            if ppre <= 0.1: why.append(f"개통 전부터 차이(p {ppre:.2f})")
            if p5 < 0.05 and pf5 <= 0.05: why.append(f"2단계 {AP.pct(b5):+.1f}%는 개통 전부터 오름(가짜 개통연도 p {pf5:.3f}) → 인정 안 함")
            elif rep5 and not sure: why.append(f"2단계 역 {AP.pct(b5):+.1f}% 재현")
            late = e[e.year >= 2010].b.mean()
            if AP.pct(late) >= 8 and p0 >= 0.05: why.append(f"2010년 이후 평균 {AP.pct(late):+.0f}%로 늦게 커짐")
        summ.append(dict(업종=sec, 판정=verdict, 이유=" · ".join(why),
                         기본_효과=round(AP.pct(b0), 1), 기본_하한=round(AP.pct(b0 - 1.96 * s0), 1), 기본_상한=round(AP.pct(b0 + 1.96 * s0), 1), 기본_p=round(p0, 4),
                         개통전_p=round(ppre, 3), 비중_pp=round(b3 * 100, 2), 비중_p=round(AP._pval(b3 / s3), 3),
                         단계2_효과=round(AP.pct(b5), 1), 단계2_p=round(p5, 3), 밀도맞춤_효과=round(AP.pct(b6), 1), 밀도맞춤_p=round(p6, 3)))
    R = pd.DataFrame(rows); S = Q.merge(pd.DataFrame(summ), on="업종", how="left")
    R.to_csv(os.path.join(AP.OUT_DIR, "sector_evidence_other.csv"), index=False, encoding="utf-8-sig")
    S.to_csv(os.path.join(AP.OUT_DIR, "sector_evidence_other_summary.csv"), index=False, encoding="utf-8-sig")
    if esr:
        E = pd.concat(esr); E["효과_%"] = [AP.pct(v) for v in E.b]
        E.to_csv(os.path.join(AP.OUT_DIR, "sector_evidence_other_es.csv"), index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 80)
    print(R.to_string(index=False)); print(); print(S.to_string(index=False))


if __name__ == "__main__":
    main()
