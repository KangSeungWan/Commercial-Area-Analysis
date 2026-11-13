"""공사 피해를 '대전시가 정한 공사 영향 상권 52곳'(정보공개 답변 2026-11)으로 다시 재기

판정 규칙(결과 보기 전): tram_model/docs/사전분석계획_공사_시목록_1112.md
입력: data/construction_city_markets.csv(시 목록·공구), data/construction_sections.csv(공구 시작 달),
      outputs/8989/sales_month.csv, outputs/8989/trdar_summary.csv, 8989 골목상권 경계, data/tram_stations.csv
방법: analyze_construction_trdar.py 와 같음(골목상권·월 고정효과 이중차분, 군집 표준오차). 처리군만 시 목록으로 바꿈.
출력: outputs/construction_city_did.csv, outputs/construction_city_es.csv
"""
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_construction_trdar as T
import analyze_line1_permits as AP
import config as C

OUT = C.OUT_DIR
SEC_START = {"1공구": (202503, 999912), "2공구": (202503, 999912), "7공구": (202504, 202708)}   # 나머지 202603~ (construction_sections.csv)
OTHER = (202603, 999912)


def main():
    sm = T.O8 / "sales_month.csv"
    if not sm.exists():
        print("8989 골목상권 매출 없음 → 건너뜀"); return
    M = pd.read_csv(sm, dtype={"code": str, "sclasCd": str})
    M = M[(M.anal == "trdarAnal") & (M.level == "trdar")]
    M["grp"] = np.where(M.sclasCd.str.startswith(T.FOOD), "음식", np.where(M.sclasCd.str.startswith(T.RETAIL), "소매", "기타"))
    P = M.groupby(["code", "stdrYm"]).useAmount.sum().rename("all").to_frame()
    for g in ("음식", "소매"):
        P[g] = M[M.grp == g].groupby(["code", "stdrYm"]).useAmount.sum()
    P = P.reset_index()

    S = pd.read_csv(T.O8 / "trdar_summary.csv", dtype={"trdarNo": str}).set_index("trdarNo")
    cen = T.centroids()
    keep = []
    for k, g in S.groupby(S.dup_group.fillna(-1)):
        keep += list(g.index) if k == -1 else [g.index[0]]
    cen = cen[cen.index.isin(keep) & (cen.type != "축제")]

    TR = pd.read_csv(C.ROOT / "data" / "tram_stations.csv", encoding="utf-8-sig")
    dmin = np.full(len(cen), np.inf)
    for r in TR.itertuples():
        dmin = np.minimum(dmin, T.hav(cen.lat.values, cen.lon.values, r.lat, r.lon))
    cen["d_tram"] = dmin

    CM = pd.read_csv(C.ROOT / "data" / "construction_city_markets.csv", encoding="utf-8-sig")
    norm = lambda v: re.sub(r"\s", "", str(v))
    sec = {norm(r.market): str(r.section) for r in CM.itertuples()}
    cen["key"] = cen.name.map(norm)
    cen["in_city"] = cen.key.isin(sec)
    # 같은 값 묶음 때문에 대표 1곳만 남은 경우: 묶음 안 다른 이름이 시 목록이면 처리로 봄
    allc = T.centroids(); allc["key"] = allc.name.map(norm)
    for k, g in S.groupby(S.dup_group.dropna()):
        names_in = [x for x in allc.loc[allc.index.isin(g.index), "key"] if x in sec]
        rep = [i for i in g.index if i in cen.index]
        if names_in and rep:
            cen.loc[rep, "in_city"] = True; cen.loc[rep, "key"] = names_in[0]

    def start_end(key):
        secs = [s.strip() for s in sec[key].split(";")]
        se = [SEC_START.get(s, OTHER) for s in secs]
        return min(x[0] for x in se), max(x[1] for x in se)
    cen["start"] = np.nan; cen["end"] = np.nan
    for i in cen.index[cen.in_city]:
        cen.loc[i, ["start", "end"]] = start_end(cen.loc[i, "key"])
    cen["treat"] = cen.in_city.astype(int)
    cen["section"] = cen.key.map(sec).fillna("")
    cen = cen[(cen.treat == 1) | (cen.d_tram > T.CTRL_M)]

    P = P[P.code.isin(cen.index)].merge(cen[["name", "type", "treat", "start", "end", "section", "d_tram"]], left_on="code", right_index=True)
    P = P.rename(columns={"code": "cell", "stdrYm": "year"})
    P["during"] = ((P.year >= P.start) & (P.year <= P.end)).astype(int) * P.treat

    def est(d, lab, note=""):
        full = d.groupby("cell").year.nunique(); d = d[d.cell.isin(full[full == full.max()].index)]
        if not d.treat.sum() or not (d.treat == 0).sum():
            return None
        b, se, _ = T.did(d)
        return T.row(lab, b, se, d, note)

    rows = []
    for y, lab in [("all", "시 목록 골목상권 카드매출(23업종)"), ("음식", "음식점 매출"), ("소매", "소매 매출")]:
        d = P[P[y] > 0].assign(ly=lambda x: np.log(x[y]))
        r = est(d, lab, "처리 = 대전시 정보공개 답변 공사 영향 상권")
        if r: rows.append(r)
    # 가짜 공사 시작
    d = P[P["all"] > 0].assign(ly=lambda x: np.log(x["all"]))
    d = d[(d.treat == 0) | (d.year < d.start)].copy()
    fake = (pd.to_datetime(d.start.astype("Int64").astype(str), format="%Y%m", errors="coerce") - pd.DateOffset(months=12))
    d["fstart"] = fake.dt.year * 100 + fake.dt.month
    d["during"] = ((d.year >= d.fstart) & (d.treat == 1)).astype(int)
    full = d[d.treat == 0].groupby("cell").year.nunique().max()
    d = d[(d.treat == 1) | d.cell.isin(d[d.treat == 0].groupby("cell").year.nunique().pipe(lambda s: s[s == full].index))]
    b, se, _ = T.did(d)
    rows.append(T.row("가짜 공사 시작(12개월 앞당김, 공사 전 자료만)", b, se, d, "0 근처여야 정상"))
    # 참고 묶음
    d = P[P["all"] > 0].assign(ly=lambda x: np.log(x["all"]))
    r = est(d[(d.treat == 0) | d.section.str.contains("13공구")], "참고: 13공구 원도심만")
    if r: rows.append(r)
    r = est(d[d.type.isin(["전통시장", "상점가"])], "참고: 전통시장·상점가만")
    if r: rows.append(r)
    R = pd.DataFrame(rows)

    main_r, fk = R.iloc[0], R[R.결과.str.startswith("가짜")].iloc[0]
    if main_r.효과_퍼센트 < 0 and main_r.p값 < 0.05 and fk.p값 >= 0.10:
        v = "방향만으로 올림 (시 목록에서 공사 중 감소가 보이고 가짜 시작 통과)"
    elif main_r.효과_퍼센트 < 0 and main_r.p값 < 0.05:
        v = "확인 안 됨 유지 (가짜 시작도 유의 → 공사 전 흐름 차이 의심)"
    elif main_r.p값 < 0.05:
        v = "확인 안 됨 유지 (양수 유의 → 반대 결과 칸에 기록)"
    else:
        v = "확인 안 됨 유지 (시 목록으로 다시 재도 유의하지 않음)"
    R["판정"] = [v] + [""] * (len(R) - 1)
    R["처리_목록"] = ", ".join(sorted(cen[cen.treat == 1].name))[:600]
    R.to_csv(OUT / "construction_city_did.csv", index=False, encoding="utf-8-sig")

    months = sorted(P.year.unique()); idx = {m: i for i, m in enumerate(months)}
    d = P[P["all"] > 0].assign(ly=lambda x: np.log(x["all"]))
    full = d.groupby("cell").year.nunique(); d = d[d.cell.isin(full[full == full.max()].index)].copy()
    d["rel"] = np.where(d.treat == 1, d.year.map(idx) - d.start.map(lambda s: idx.get(int(s), np.nan) if pd.notna(s) else np.nan), np.nan)
    xs = []
    for k in range(-12, 18):
        if k == -1: continue
        c = f"r{k}"; d[c] = (d.rel == k).astype(float)
        if d[c].sum() > 0: xs.append(c)
    b, se, _ = AP.twfe(d, "ly", xs)
    E = pd.DataFrame({"rel_month": [int(c[1:]) for c in xs], "effect_pct": [AP.pct(x) for x in b],
                      "lo": [AP.pct(x - 1.96 * s) for x, s in zip(b, se)], "hi": [AP.pct(x + 1.96 * s) for x, s in zip(b, se)]})
    E.to_csv(OUT / "construction_city_es.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(R.drop(columns=["처리_목록"]).to_string(index=False))
    print("처리:", R["처리_목록"].iloc[0])
    pre, post = E[E.rel_month < 0], E[E.rel_month >= 0]
    print(f"사건연구: 공사 전 평균 {pre.effect_pct.mean():+.1f}%, 공사 후 평균 {post.effect_pct.mean():+.1f}%")
    print("판정:", v)


if __name__ == "__main__":
    main()
