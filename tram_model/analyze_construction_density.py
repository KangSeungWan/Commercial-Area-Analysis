"""B4: 공사 기간 점검의 비교군을 '상업 밀도가 비슷한 동'으로 바꾼 변형 (analyze_construction_8989 의 강건성 점검).

왜: 기본 비교군(정거장 500m 점포 비율 10% 미만 34개 동)은 대부분 외곽·주거 동이고, 공사 구간 동(42개)은 도심 상업 동이 많음
    → 같은 시기 도심 상권 전체의 흐름(경기·소비 이동)이 '공사 효과'에 섞일 수 있음
입력: analyze_construction_8989 와 같음 + outputs/dong_polygons.geojson(면적) · dong_map_profile.csv(점포 수)
상업 밀도 = 동 점포 수 ÷ 동 면적(㎢), 로그
변형
  V0 기본          : 기존과 같은 처리·비교 (다시 계산해서 나란히)
  V1 공통 범위      : 처리·비교 모두 밀도가 서로 겹치는 범위 안의 동만
  V2 밀도 3등분×월  : 모든 동, 밀도 3등분마다 따로 월 고정효과 (밀도 비슷한 동끼리의 시간 흐름 차이를 뺌)
  V3 최근접 짝      : 처리 동마다 밀도가 가장 가까운 비교 동 1곳(중복 허용) → 쓰인 비교 동만, 쓰인 횟수로 가중
결과: 전체 카드매출 · 음식점 · 도소매, 동 고정효과 + 월 고정효과, 주민 수 통제, 동 군집 표준오차
출력: outputs/construction_8989_density.csv (변형 × 결과), outputs/construction_8989_balance.csv (밀도 균형)
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import analyze_line1_permits as AP

OUT = C.OUT_DIR
SEC = C.ROOT / "data" / "construction_sections.csv"
YS = [("useAmount_합계", "전체 카드매출"), ("useAmount_음식점", "음식점 매출"), ("useAmount_도소매", "도소매 매출")]


def dong_area_km2():
    g = json.loads((OUT / "dong_polygons.geojson").read_text(encoding="utf-8"))
    out = {}
    for f in g["features"]:
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        a = 0.0
        for p in polys:
            for k, ring in enumerate(p):
                r = np.asarray(ring, float)
                lat0 = math.radians(r[:, 1].mean())
                x = r[:, 0] * 111.320 * math.cos(lat0)
                y = r[:, 1] * 110.540
                s = abs(0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))
                a += s if k == 0 else -s                       # 구멍은 빼기
        out[str(f["properties"]["id"])] = a
    return pd.Series(out)


def twfe_w(d, ycol, xcols, w=None, extra_fe=None):
    """가중 2원 고정효과(동·월) + 선택: 추가 고정효과 열(범주) × 월. 동 군집 표준오차."""
    d = d.copy()
    if extra_fe is not None:                                   # 밀도 등급 × 월 더미 (등급 하나 기준)
        lv = sorted(d[extra_fe].unique())[1:]
        for g in lv:
            for m in sorted(d.year.unique())[1:]:
                c = f"fe_{g}_{m}"
                d[c] = ((d[extra_fe] == g) & (d.year == m)).astype(float)
                xcols = xcols + [c]
    if w is None:
        b, se, G = AP.twfe(d, ycol, xcols)
        return b, se, G
    # 가중: √w 를 곱한 뒤 고정효과 제거 근사 대신, 동·월 더미를 직접 넣은 가중 최소제곱 (동 80개·월 20개라 작음)
    X = d[xcols].to_numpy(float)
    D1 = pd.get_dummies(d.cell, drop_first=False).to_numpy(float)
    D2 = pd.get_dummies(d.year, drop_first=True).to_numpy(float)
    Z = np.column_stack([X, D1, D2])
    y = d[ycol].to_numpy(float)
    sw = np.sqrt(d[w].to_numpy(float))
    Zw, yw = Z * sw[:, None], y * sw
    ZtZi = np.linalg.pinv(Zw.T @ Zw)
    beta = ZtZi @ Zw.T @ yw
    u = yw - Zw @ beta
    meat = np.zeros((Z.shape[1], Z.shape[1]))
    groups = pd.Series(np.arange(len(y))).groupby(d.cell.values).indices
    for idx in groups.values():
        s = Zw[idx].T @ u[idx]
        meat += np.outer(s, s)
    G, N, K = len(groups), len(y), Z.shape[1]
    V = G / max(G - 1, 1) * (N - 1) / max(N - K, 1) * ZtZi @ meat @ ZtZi
    k = len(xcols)
    return beta[:k], np.sqrt(np.diag(V))[:k], G


def main():
    if not SEC.exists():
        print(f"공사 구간 표 없음({SEC}) → 건너뜀"); return
    S = pd.read_csv(SEC, encoding="utf-8-sig", dtype=str)
    P = pd.read_csv(OUT / "8989" / "dong_panel_8989.csv", dtype={"adm_cd2": str})
    P = P.dropna(subset=["useAmount_합계"])
    P = P[P["useAmount_합계"] > 0]
    DS = pd.read_csv(OUT / "dong_station_summary.csv", encoding="utf-8-sig", dtype={"dong_id": str})
    prof = pd.read_csv(OUT / "dong_map_profile.csv", encoding="utf-8-sig", dtype={"dong_id": str}).set_index("dong_id")
    # 처리 동: analyze_construction_8989 와 같은 규칙
    rows_t = []
    for r in S.itertuples():
        stns = [int(x) for x in str(r.stations).split(";") if x.strip()]
        d = DS[DS.station_no.isin(stns) & ((DS.inside.astype(str) == "True") | (DS.dist_m <= 300))]
        for k in d.dong_id.unique():
            rows_t.append(dict(dong_id=k, start=int(r.start_ym),
                               end=int(r.end_ym) if str(r.end_ym) not in ("", "nan") else 999912))
    T = pd.DataFrame(rows_t).sort_values("start").drop_duplicates("dong_id")
    ctrl_all = set(prof[prof.tram500_share < 0.10].index) - set(T.dong_id)

    area = dong_area_km2()
    dens = np.log((prof.n_stores / area.reindex(prof.index)).clip(lower=1e-3))
    prof = prof.assign(area_km2=area.reindex(prof.index), log_density=dens)

    P = P.merge(T, left_on="adm_cd2", right_on="dong_id", how="left")
    P["treat"] = P.start.notna().astype(int)
    P["during"] = ((P.stdrYm >= P.start) & (P.stdrYm <= P.end)).astype(int) * P.treat
    P = P.rename(columns={"adm_cd2": "cell", "stdrYm": "year"})
    P["lres"] = np.log(P.resident.clip(lower=1))
    P["log_density"] = P.cell.map(prof.log_density)
    P = P[P.treat.eq(1) | P.cell.isin(ctrl_all)]

    tset = sorted(T.dong_id)
    cset = sorted(ctrl_all)
    tl, cl = prof.loc[tset, "log_density"], prof.loc[cset, "log_density"]
    lo, hi = max(tl.min(), cl.min()), min(tl.max(), cl.max())
    # V3 최근접 짝 (중복 허용)
    use = {}
    for t in tset:
        c = (cl - tl[t]).abs().idxmin()
        use[c] = use.get(c, 0) + 1
    # 밀도 3등분 (처리+비교 전체 기준)
    allv = prof.loc[tset + cset, "log_density"]
    q = allv.quantile([1 / 3, 2 / 3]).to_numpy()
    P["dbin"] = np.digitize(P.log_density, q)

    variants = {
        "V0 기본 (정거장 먼 동 전체)": dict(keep=lambda x: x, w=None, fe=None),
        "V1 밀도 겹치는 범위만": dict(keep=lambda x: x[x.log_density.between(lo, hi)], w=None, fe=None),
        "V2 밀도 3등분별 월 흐름 통제": dict(keep=lambda x: x, w=None, fe="dbin"),
        "V3 밀도 최근접 짝(가중)": dict(keep=lambda x: x[x.treat.eq(1) | x.cell.isin(use)], w="wt", fe=None),
    }
    P["wt"] = np.where(P.treat == 1, 1.0, P.cell.map(use).fillna(0))

    rows, bal = [], []
    for vname, v in variants.items():
        base = v["keep"](P)
        dd = base.drop_duplicates("cell")
        bal.append(dict(변형=vname, 처리_동=int(dd.treat.sum()), 비교_동=int((dd.treat == 0).sum()),
                        처리_밀도_평균=round(float(np.exp(dd[dd.treat == 1].log_density.mean())), 0),
                        비교_밀도_평균=round(float(np.exp(np.average(dd[dd.treat == 0].log_density,
                                                                 weights=dd[dd.treat == 0].wt if v["w"] else None))), 0),
                        로그밀도_차이=round(float(dd[dd.treat == 1].log_density.mean()
                                             - np.average(dd[dd.treat == 0].log_density,
                                                          weights=dd[dd.treat == 0].wt if v["w"] else None)), 2)))
        for y, lab in YS:
            d = base[base[y] > 0].assign(ly=lambda x: np.log(x[y]), D=lambda x: x.during.astype(float)).dropna(subset=["ly", "lres"])
            full = d.groupby("cell").year.nunique()
            d = d[d.cell.isin(full[full == full.max()].index)]
            b, se, G = twfe_w(d, "ly", ["D", "lres"], w=v["w"], extra_fe=v["fe"])
            rows.append(dict(변형=vname, 결과=lab, 효과_퍼센트=round(AP.pct(b[0]), 2),
                             하한=round(AP.pct(b[0] - 1.96 * se[0]), 2), 상한=round(AP.pct(b[0] + 1.96 * se[0]), 2),
                             p값=round(AP._pval(b[0] / se[0]), 4),
                             처리_동=int(d[d.treat == 1].cell.nunique()), 비교_동=int(d[d.treat == 0].cell.nunique())))
    R, B = pd.DataFrame(rows), pd.DataFrame(bal)
    R.to_csv(OUT / "construction_8989_density.csv", index=False, encoding="utf-8-sig")
    B.to_csv(OUT / "construction_8989_balance.csv", index=False, encoding="utf-8-sig")
    print("상업 밀도(점포/㎢) 균형"); print(B.to_string(index=False))
    print(f"\n공통 범위: {math.exp(lo):.0f} ~ {math.exp(hi):.0f} 점포/㎢ · V3 쓰인 비교 동 {len(use)}곳")
    print(R.to_string(index=False))


if __name__ == "__main__":
    main()
