"""B5: 공사 기간 피해를 골목상권 144곳 × 월(2024-01~2026-08)로 다시 점검 — 공사 전 기간 14개월 확보

왜: 행정동 카드매출은 2025-01부터라 공사 전이 2~6개월뿐(analyze_construction_8989.py, p 0.07).
    재단 확인(2026-10-27): 행정동은 2024 자료 없음, 골목상권은 2024-01부터 있음. 매출은 가맹점 주소를 격자(셀)로 묶어 집계,
    법인카드 포함, 배달앱은 따로 집계(제외).
입력: outputs/8989/sales_month.csv (anal=trdarAnal, 핵심 23업종), outputs/8989/trdar_summary.csv (같은 값 묶음 dup_group),
      data/raw/8989/meta/trdar_polygons.geojson (+ 재단 공식 경계 있으면 중심점), data/tram_stations.csv, data/construction_sections.csv
방법: 처리 = 공사 구간 정거장 300m 안 골목상권(중심점 기준), 비교 = 모든 트램 정거장에서 1km 넘게 떨어진 골목상권
      log(월 매출) ~ 골목상권 고정효과 + 월 고정효과 + 처리×공사 중, 골목상권 군집 표준오차
      같은 값 묶음(셀 집계가 겹쳐 값이 완전히 같은 곳)은 묶음당 1곳만. 사건연구(공사 시작 −12~+17개월), 가짜 공사 시작(12개월 앞당김, 공사 전 자료만)
출력: outputs/construction_trdar_did.csv, outputs/construction_trdar_es.csv
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_line1_permits as AP
import config as C

OUT = C.OUT_DIR
O8 = OUT / "8989"
TREAT_M, CTRL_M = 300, 1000
FOOD = ("I2",)            # 음식·주점
RETAIL = ("G04",)         # 소매


def hav(lat1, lon1, lat2, lon2):
    R = 6371000; p1, p2 = np.radians(lat1), np.radians(lat2); dp, dl = p2 - p1, np.radians(lon2 - lon1)
    return 2 * R * np.arcsin(np.sqrt(np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2))


def centroids():
    tg = json.load(open(C.RAW_DIR / "8989" / "meta" / "trdar_polygons.geojson", encoding="utf-8"))["features"]
    c = {str(f["properties"]["trdarNo"]): (f["properties"]["trdarNm"], f["properties"]["trdarSeNm"], *f["properties"]["centroid"]) for f in tg}
    off = C.RAW_DIR / "8989" / "boundary" / "골목상권" / "alley_polygons_official_20260826.geojson"
    if off.exists():
        norm = lambda v: re.sub(r"\s", "", str(v))
        oc = {norm(f["properties"]["이름"]): f["properties"]["centroid"] for f in json.load(open(off, encoding="utf-8"))["features"]}
        c = {k: (n, t, *oc.get(norm(n), (x, y))) for k, (n, t, x, y) in c.items()}
    return pd.DataFrame([(k, n, t, x, y) for k, (n, t, x, y) in c.items()], columns=["code", "name", "type", "lon", "lat"]).set_index("code")


def did(d, ycol="ly"):
    d = d.assign(D=d.during.astype(float))
    b, se, G = AP.twfe(d, ycol, ["D"])
    return b[0], se[0], G


def row(lab, b, se, d, note=""):
    return dict(결과=lab, 효과_퍼센트=round(AP.pct(b), 2), 하한=round(AP.pct(b - 1.96 * se), 2), 상한=round(AP.pct(b + 1.96 * se), 2),
                p값=round(AP._pval(b / se), 4), 처리_골목상권=int(d[d.treat == 1].cell.nunique()), 비교_골목상권=int(d[d.treat == 0].cell.nunique()),
                월수=int(d.year.nunique()), 비고=note)


def main():
    sm = O8 / "sales_month.csv"
    if not sm.exists():
        print("8989 골목상권 매출 없음 → 건너뜀"); return
    M = pd.read_csv(sm, dtype={"code": str, "sclasCd": str})
    M = M[(M.anal == "trdarAnal") & (M.level == "trdar")]
    M["grp"] = np.where(M.sclasCd.str.startswith(FOOD), "음식", np.where(M.sclasCd.str.startswith(RETAIL), "소매", "기타"))
    P = M.groupby(["code", "stdrYm"]).useAmount.sum().rename("all").to_frame()
    for g in ("음식", "소매"):
        P[g] = M[M.grp == g].groupby(["code", "stdrYm"]).useAmount.sum()
    P = P.reset_index()

    S = pd.read_csv(O8 / "trdar_summary.csv", dtype={"trdarNo": str}).set_index("trdarNo")
    cen = centroids()
    keep = []
    for k, g in S.groupby(S.dup_group.fillna(-1)):
        keep += list(g.index) if k == -1 else [g.index[0]]                 # 같은 값 묶음은 1곳만
    cen = cen[cen.index.isin(keep) & (cen.type != "축제")]

    TR = pd.read_csv(C.ROOT / "data" / "tram_stations.csv", encoding="utf-8-sig")
    st = TR.set_index("station_no")
    dmin = np.full(len(cen), np.inf)
    for r in TR.itertuples():
        dmin = np.minimum(dmin, hav(cen.lat.values, cen.lon.values, r.lat, r.lon))
    cen["d_tram"] = dmin
    SEC = pd.read_csv(C.ROOT / "data" / "construction_sections.csv", encoding="utf-8-sig", dtype=str)
    cen["start"] = np.nan; cen["end"] = np.nan; cen["section"] = ""
    for r in SEC.sort_values("start_ym").itertuples():
        ids = [int(x) for x in str(r.stations).split(";") if x.strip()]
        dd = np.full(len(cen), np.inf)
        for i in ids:
            if i in st.index:
                dd = np.minimum(dd, hav(cen.lat.values, cen.lon.values, st.loc[i, "lat"], st.loc[i, "lon"]))
        m = (dd <= TREAT_M) & cen.start.isna().values
        cen.loc[m, "start"] = int(r.start_ym)
        cen.loc[m, "end"] = int(r.end_ym) if str(r.end_ym) not in ("", "nan") else 999912
        cen.loc[m, "section"] = r.section
    cen["treat"] = cen.start.notna().astype(int)
    cen = cen[(cen.treat == 1) | (cen.d_tram > CTRL_M)]

    P = P[P.code.isin(cen.index)].merge(cen[["name", "type", "treat", "start", "end", "section", "d_tram"]], left_on="code", right_index=True)
    P = P.rename(columns={"code": "cell", "stdrYm": "year"})
    P["during"] = ((P.year >= P.start) & (P.year <= P.end)).astype(int) * P.treat
    rows = []
    for y, lab in [("all", "골목상권 카드매출(23업종)"), ("음식", "음식점 매출"), ("소매", "소매 매출")]:
        d = P[P[y] > 0].assign(ly=lambda x: np.log(x[y]))
        full = d.groupby("cell").year.nunique(); d = d[d.cell.isin(full[full == full.max()].index)]
        b, se, _ = did(d)
        rows.append(row(lab, b, se, d, f"{int(d.year.min())}~{int(d.year.max())}, 공사 전 {int((d[d.treat == 1].year < d[d.treat == 1].start).groupby(d.cell).sum().median())}개월(중앙값)"))
    # 가짜 공사 시작: 공사 전 자료만, 시작을 12개월 앞당김
    d = P[P["all"] > 0].assign(ly=lambda x: np.log(x["all"]))
    d = d[(d.treat == 0) | (d.year < d.start)].copy()
    fake = (pd.to_datetime(d.start.astype("Int64").astype(str), format="%Y%m", errors="coerce") - pd.DateOffset(months=12))
    d["fstart"] = fake.dt.year * 100 + fake.dt.month
    d["during"] = ((d.year >= d.fstart) & (d.treat == 1)).astype(int)
    full = d[d.treat == 0].groupby("cell").year.nunique().max()
    d = d[(d.treat == 1) | d.cell.isin(d[d.treat == 0].groupby("cell").year.nunique().pipe(lambda s: s[s == full].index))]
    b, se, _ = did(d)
    rows.append(row("가짜 공사 시작(12개월 앞당김, 공사 전 자료만)", b, se, d, "0 근처여야 정상"))
    # 원도심·시장형만 (전통시장·상점가)
    d = P[P["all"] > 0].assign(ly=lambda x: np.log(x["all"]))
    d = d[d.type.isin(["전통시장", "상점가"])]
    full = d.groupby("cell").year.nunique(); d = d[d.cell.isin(full[full == full.max()].index)]
    if d.treat.sum() and (d.treat == 0).sum():
        b, se, _ = did(d); rows.append(row("전통시장·상점가만", b, se, d))
    R = pd.DataFrame(rows)
    R["처리_목록"] = ", ".join(sorted(cen[cen.treat == 1].name))[:400]
    R.to_csv(OUT / "construction_trdar_did.csv", index=False, encoding="utf-8-sig")

    # 사건연구 (공사 시작 달 기준)
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
    E = pd.DataFrame({"rel_month": [int(c[1:]) for c in xs], "effect_pct": [AP.pct(v) for v in b],
                      "lo": [AP.pct(v - 1.96 * s) for v, s in zip(b, se)], "hi": [AP.pct(v + 1.96 * s) for v, s in zip(b, se)]})
    E.to_csv(OUT / "construction_trdar_es.csv", index=False, encoding="utf-8-sig")
    pre = E[E.rel_month < 0]; post = E[E.rel_month >= 0]
    pd.set_option("display.width", 220)
    print(R.drop(columns=["처리_목록"]).to_string(index=False))
    print("처리:", R["처리_목록"].iloc[0])
    print(f"사건연구: 공사 전 평균 {pre.effect_pct.mean():+.1f}%, 공사 후 평균 {post.effect_pct.mean():+.1f}%")
    print(E.round(1).to_string(index=False))
    print("→ outputs/construction_trdar_did.csv, construction_trdar_es.csv")


if __name__ == "__main__":
    main()
