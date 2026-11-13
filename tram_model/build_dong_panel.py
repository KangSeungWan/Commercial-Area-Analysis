"""행정동 82개 단위 패널 (사건 분석 비교군 확대 · 요인 분석용).

입력: data/daejeon_dong_2023.geojson, data/raw/상가_과거/*.csv, outputs/landprice_parcels.csv.gz·landprice_long.pkl
출력 (outputs/)
- dong_panel_land.csv  : 행정동 × 연(1990~2026) 공시지가 연쇄 지수 (지목 '대', 30필지 미만이면 전체 지목)
- dong_panel_store.csv : 행정동 × 분기 점포 수·업종 대분류별 수·개폐업·대전 내 비중·자료 구간(regime)
"""
import json

import numpy as np
import pandas as pd

import config as C
from build_dong_layer import DONG, label_points
from build_landprice import chain_index
from build_store_panel import load_snapshots

CATS = ["음식", "소매", "수리·개인", "과학·기술", "교육", "예술·스포츠", "시설관리·임대", "부동산", "보건의료", "숙박"]


def dong_meta():
    gj = json.load(open(DONG, encoding="utf-8"))
    meta = pd.DataFrame([{"k": k, "dong_id": f["properties"]["adm_cd2"], "si": f["properties"]["si"],
                          "dong": f["properties"]["dong"]} for k, f in enumerate(gj["features"])])
    return gj, meta


def land_panel(gj, meta):
    G = pd.read_csv(C.OUT_DIR / "landprice_parcels.csv.gz", encoding="utf-8-sig",
                    usecols=["pnu", "lat", "lon", "is_dae"])
    G["k"] = label_points(gj, G.lon.values, G.lat.values)
    G = G[G.k >= 0]
    L = pd.read_pickle(C.OUT_DIR / "landprice_long.pkl")
    L = L[L.pnu.isin(G.pnu)]
    groups, sample = {}, {}
    for k in meta.k:
        dae = G.pnu[(G.k == k) & (G.is_dae == 1)].values
        if len(dae) >= 30:
            groups[k], sample[k] = dae, "대"
        else:
            groups[k], sample[k] = G.pnu[G.k == k].values, "전체지목"
    groups["ALL"] = G.pnu[G.is_dae == 1].values
    A = chain_index(L, groups)
    city = A[A.code == "ALL"].set_index("year").idx
    A = A[A.code != "ALL"].rename(columns={"code": "k"})
    A["k"] = A.k.astype(int)
    A["rel_idx"] = (A.idx / A.year.map(city) * 100).round(2)
    A["sample"] = A.k.map(sample)
    return A.merge(meta, on="k")


def store_panel(gj, meta):
    snaps = load_snapshots()
    rows, prev_ids, prev_k = [], None, None
    city = []
    for per, d in snaps.items():
        d = d.copy()
        d["k"] = label_points(gj, d.lon.values, d.lat.values)
        ids = set(d["상가업소번호"])
        keep = len(ids & prev_ids) / len(prev_ids) if prev_ids else np.nan
        city.append({"period": per, "n_city": len(d), "keep_rate": keep})
        cur = dict(zip(d["상가업소번호"], d.k))
        cat = pd.crosstab(d.k, d["상권업종대분류명"]).reindex(columns=CATS, fill_value=0)
        for k, g in d[d.k >= 0].groupby("k"):
            r = {"period": per, "k": k, "n_stores": len(g),
                 "branch_share": float(g["지점명"].fillna("").str.strip().ne("").mean()),
                 **{f"n_{c}": int(cat.loc[k, c]) for c in CATS}}
            if prev_ids is not None:
                prev_here = {i for i, kk in prev_k.items() if kk == k}
                r["n_open"] = len(set(g["상가업소번호"]) - prev_ids)
                r["n_close"] = len(prev_here - ids)
                r["n_prev"] = len(prev_here)
            rows.append(r)
        prev_ids, prev_k = ids, cur
        print(f"  {per}: 행정동 배정 {(d.k >= 0).mean():.1%}", flush=True)
    P = pd.DataFrame(rows)
    Cy = pd.DataFrame(city)
    Cy["chg_city"] = Cy.n_city.pct_change()
    Cy["data_break"] = ((Cy.chg_city.abs() > 0.08) | (Cy.keep_rate < 0.9)).astype(int)
    Cy["no_closure_info"] = (Cy.keep_rate >= 0.999).astype(int)
    Cy["regime"] = Cy.data_break.cumsum().map(lambda i: "ABCDEFG"[i])
    P = P.merge(Cy, on="period")
    P["share"] = P.n_stores / P.n_city
    P = P.sort_values(["k", "period"])
    r = (P.share / P.groupby("k").share.shift()).where(P.data_break == 0, 1.0).fillna(1.0)
    P["share_chain"] = r.groupby(P.k).cumprod()
    P["open_rate"] = np.where((P.n_prev > 0) & (P.data_break == 0), P.n_open / P.n_prev, np.nan)
    P["close_rate"] = np.where((P.n_prev > 0) & (P.data_break == 0) & (P.no_closure_info == 0),
                               P.n_close / P.n_prev, np.nan)
    return P.merge(meta, on="k")


def main():
    gj, meta = dong_meta()
    print("1/2 행정동 공시지가 지수 ...", flush=True)
    A = land_panel(gj, meta)
    A.to_csv(C.OUT_DIR / "dong_panel_land.csv", index=False, encoding="utf-8-sig")
    print(f"   {A.k.nunique()}개 행정동 × {A.year.nunique()}년")
    print("2/2 행정동 점포 패널 (42개 분기, 몇 분 걸림) ...", flush=True)
    P = store_panel(gj, meta)
    P.to_csv(C.OUT_DIR / "dong_panel_store.csv", index=False, encoding="utf-8-sig")
    print(f"   {P.k.nunique()}개 행정동 × {P.period.nunique()}분기 → outputs/dong_panel_land.csv, dong_panel_store.csv")


if __name__ == "__main__":
    main()
