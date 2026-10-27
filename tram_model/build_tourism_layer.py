"""관광 2단계: 상권 20·행정동 82 관광 지표 + '관광 접근성 변화 → 방문 소비' 시나리오 (보조 관점).

입력 (tram_model/)
  data/tourism_poi.csv              관광지(use_in_tourism=1)·관문(gateway=1) 좌표 — 검증 반영(10-26)
  data/tourism_visitors_monthly.csv 문체부 주요관광지점 입장객 (지점별 월)
  data/tourism_gateway_traffic.csv  관문 4곳 하루 이용(승하차 합) — 접근성 가중치
  data/tourism_params.csv           ε(탄력성)·S-커브 중간점
  data/tram_stations.csv, data/line1_stations.csv, tram_route.py(노선 순서)
  outputs/sangkwon_polygons.geojson, outputs/dong_polygons.geojson
  outputs/8989/dong_8989_summary.csv, sales_breakdown.csv, area_dong_share.csv  (대리지표)
출력 (outputs/)
  tourism_layer.csv    상권 20 + 행정동 82: 관광자원·대리지표 3·접근성 변화·시나리오
  tourism_poi_near.csv 관광지 ↔ 상권·행정동·정거장 대응 (지도 점·패널 목록용)
  tourism_station.csv  정거장 45곳: 500m(대형 공원 1km) 안 관광지
  tourism_ramp.csv     개통 후 개월별 효과 비율(S-커브)

원칙: 트램 관광 인과효과는 측정 사례가 없음 → 숫자는 항상 범위(ε 0 ~ 상한) + '시나리오'.
     관광자원이 없는 생활형 곳은 시나리오 0. 이동 시간은 경로 탐색 API 없이 근사(아래 상수).
실행: python tram_model/build_tourism_layer.py   (몇 초)
"""
import json
import math
import sys

import numpy as np
import pandas as pd
from matplotlib.path import Path as MPath

from config import ROOT, OUT_DIR
from tram_route import LOOP, BRANCH, SPURS

DATA = ROOT / "data"
OUT = OUT_DIR
S8989 = OUT / "8989"

# ── 관광지 가중치·범위 ──
TYPE_W = {"관광지": 1.0, "체험시설": 0.5, "축제장": 1.0, "문화재(소규모)": 0.0}   # 문화재 소규모는 지도에만
BAND_M = 500                          # 정거장·상권 영향권
BIG_BAND_M = 1000                     # 대형 공원·산: 점 하나로는 넓이를 못 나타냄 → 1km
BIG_WORDS = ["수목원", "호수공원", "유림공원", "엑스포", "보문산", "계족산", "식장산", "장태산", "뿌리공원",
             "대청호", "오월드", "유원지", "세천", "황톳길", "현충원", "한빛탑"]
STRONG_SCORE = 3.0                    # 가중 관광지 3곳 이상 또는 입장객 30만+ → '관광자원형(강)'
STRONG_VIS = 300_000

# ── 이동 시간 근사 (분) ──
WALK_KMH, WALK_DETOUR = 4.5, 1.3
BUS_KMH, BUS_DETOUR, BUS_FIXED = 16.0, 1.35, 8.0      # 시내버스(기본): 기다림·걸음 8분 + 도로 거리
BUS_SLOW = (13.0, 12.0)                               # 버스 느린 경우(환승·막힘): 상한 시나리오에 씀
L1_KMH, L1_WAIT = 33.0, 4.0                           # 1호선 표정속도 근사, 배차 절반
TRAM_KMH, TRAM_WAIT = 21.6, 4.0                       # 2호선 계획 표정속도 21.6km/h, 배차 8분 → 4분
RAIL_DETOUR = 1.15                                    # 정거장 사이 직선 → 선로 길이
MAX_ACCESS_M = 1200                                   # 정거장까지 이 거리 넘게 걷지 않음
RAMP_MID = 24                                         # 개월 (tourism_params 에서 다시 읽음)


def hav(lat1, lon1, lat2, lon2):
    """미터. 배열 가능."""
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def walk_min(m):
    return m * WALK_DETOUR / 1000 / WALK_KMH * 60


def csv(p, **k):
    return pd.read_csv(p, encoding="utf-8-sig", **k)


# ── 도형 ──
def load_polys(path, key):
    g = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for f in g["features"]:
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        rings = [np.asarray(p[0], float) for p in polys]
        out[str(f["properties"][key])] = (rings, f["properties"])
    return out


def inside(rings, lon, lat):
    return any(MPath(r).contains_point((lon, lat)) for r in rings)


def dist_to_poly(rings, lat, lon):
    """점이 안이면 0, 밖이면 가장 가까운 꼭짓점·변까지 (미터, 국지 평면 근사)."""
    if inside(rings, lon, lat):
        return 0.0
    kx, ky = 111320 * math.cos(math.radians(lat)), 110540
    best = 1e12
    for r in rings:
        x, y = (r[:, 0] - lon) * kx, (r[:, 1] - lat) * ky
        x0, y0, x1, y1 = x[:-1], y[:-1], x[1:], y[1:]
        dx, dy = x1 - x0, y1 - y0
        t = np.clip(-(x0 * dx + y0 * dy) / np.maximum(dx * dx + dy * dy, 1e-9), 0, 1)
        d = np.hypot(x0 + t * dx, y0 + t * dy).min()
        best = min(best, float(d))
    return best


def centroid(rings):
    r = max(rings, key=len)
    return float(r[:, 1].mean()), float(r[:, 0].mean())


# ── 노선 그래프 (정거장 사이 선로 거리, 최단 경로) ──
def rail_dist(st, edges):
    ids = list(st.index)
    ix = {s: i for i, s in enumerate(ids)}
    n = len(ids)
    D = np.full((n, n), np.inf)
    np.fill_diagonal(D, 0)
    for a, b in edges:
        if a in ix and b in ix:
            d = hav(st.at[a, "lat"], st.at[a, "lon"], st.at[b, "lat"], st.at[b, "lon"]) * RAIL_DETOUR
            D[ix[a], ix[b]] = D[ix[b], ix[a]] = min(D[ix[a], ix[b]], d)
    for k in range(n):
        D = np.minimum(D, D[:, [k]] + D[[k], :])
    return ids, D


def tram_edges(st):
    e = list(zip(LOOP, LOOP[1:] + LOOP[:1]))
    if BRANCH and BRANCH[0] in st.index:
        lat0, lon0 = st.at[BRANCH[0], "lat"], st.at[BRANCH[0], "lon"]
        loop = [s for s in LOOP if s in st.index]
        near = min(loop, key=lambda s: hav(lat0, lon0, st.at[s, "lat"], st.at[s, "lon"]))
        e += list(zip([near] + BRANCH[:-1], BRANCH))
    for anchor, stops in SPURS:
        e += list(zip([anchor] + stops[:-1], stops))
    return e


class Net:
    """한 노선의 '걸어서 타고 걸어서' 최단 시간."""

    def __init__(self, st, edges, kmh, wait):
        self.st = st
        self.ids, self.D = rail_dist(st, edges)
        self.lat = st.loc[self.ids, "lat"].to_numpy()
        self.lon = st.loc[self.ids, "lon"].to_numpy()
        self.kmh, self.wait = kmh, wait

    def minutes(self, lat1, lon1, lat2, lon2):
        a = hav(lat1, lon1, self.lat, self.lon)
        b = hav(lat2, lon2, self.lat, self.lon)
        ia, ib = np.where(a <= MAX_ACCESS_M)[0], np.where(b <= MAX_ACCESS_M)[0]
        if not len(ia) or not len(ib):
            return np.inf
        ride = self.D[np.ix_(ia, ib)] / 1000 / self.kmh * 60
        tot = walk_min(a[ia])[:, None] + self.wait + ride + walk_min(b[ib])[None, :]
        return float(tot.min())


def travel(o, j, l1, tram=None, bus_kmh=BUS_KMH, bus_fixed=BUS_FIXED):
    """o, j = (lat, lon). 지금(걷기·버스·1호선) / 트램 개통 뒤 (분)."""
    d = float(hav(o[0], o[1], j[0], j[1]))
    walk = walk_min(d)
    bus = bus_fixed + d * BUS_DETOUR / 1000 / bus_kmh * 60
    now = min(walk, bus, l1.minutes(*o, *j))
    return now if tram is None else min(now, tram.minutes(*o, *j))


# ── 입력 ──
def load_poi():
    T = csv(DATA / "tourism_poi.csv", dtype=str, keep_default_na=False)
    T = T[(T.lat != "") & (T.lon != "")].copy()
    T["lat"], T["lon"] = T.lat.astype(float), T.lon.astype(float)
    gw = T[T.get("gateway", "0") == "1"].copy()
    P = T[T.use_in_tourism == "1"].copy()
    P["w"] = P.tour_type.map(TYPE_W).fillna(0.0)
    P["big"] = P.name.apply(lambda s: any(k in s for k in BIG_WORDS))
    P["band"] = np.where(P.big, BIG_BAND_M, BAND_M)
    # 입장객: 2022~2025 중 10개월 이상 있는 해의 연평균 (통계 끊김은 제도 변경 → 있는 해만)
    V = csv(DATA / "tourism_visitors_monthly.csv")
    V = V[V.year.between(2022, 2025)]
    y = V.groupby(["site_key", "year"]).agg(n=("month", "nunique"), v=("visitors", "sum")).reset_index()
    y = y[y.n >= 10].groupby("site_key").v.mean()
    P["visitors_yr"] = P.visitor_site.map(y)
    return P, gw


def gateway_weights(gw):
    G = csv(DATA / "tourism_gateway_traffic.csv")
    G = G[G.year.isna() | (G.year >= 2023) | G.poi_id.isin(["G02", "G03"])]
    w = G.groupby("poi_id").use_per_day.mean()
    gw = gw.copy()
    gw["traffic"] = gw.poi_id.map(w)
    miss = gw.traffic.isna()
    if miss.any():                       # 자료 없는 관문은 있는 관문 평균으로 (표시)
        print("관문 이용객 없음 → 평균으로 채움:", ", ".join(gw[miss].name))
        gw.loc[miss, "traffic"] = gw.traffic.mean()
    gw["w_traffic"] = gw.traffic / gw.traffic.sum()
    gw["w_equal"] = 1 / len(gw)
    return gw


def params():
    P = csv(DATA / "tourism_params.csv", dtype=str).set_index("param_id").value
    f = lambda k, d: float(P.get(k, d))
    return dict(eps_low=f("TOUR_eps_low", 0), eps_base=f("TOUR_eps_base_arrivals", 0.726),
                eps_nights=f("TOUR_eps_base_nights", 0.532), eps_high=f("TOUR_eps_high", 1.0),
                ramp_mid=f("TOUR_ramp_midpoint", RAMP_MID))


def proxies():
    """행정동 대리지표: 방문 강도(유동÷주민), 주말 매출 비중, 숙박·음식 매출 비중. 8989 없으면 빈 표."""
    p = S8989 / "dong_8989_summary.csv"
    if not p.exists():
        print("8989 요약 없음 → 대리지표 건너뜀")
        return pd.DataFrame(columns=["adm_cd2"])
    S = csv(p, dtype={"plcCd": str, "adm_cd2": str, "adstrdCode": str})
    S["visit_intensity"] = S.floating_2026 / S.resident_2026
    S["lodging_share"] = S.share_숙박.fillna(0)
    S["lodging_food_share"] = S.share_숙박.fillna(0) + S.share_음식점.fillna(0)
    b = S8989 / "sales_breakdown.csv"
    if b.exists():
        B = csv(b, dtype={"plcCd": str})
        B = B[(B.anal == "dongAnal") & (B.dim == "dayw")]
        t = B.groupby(["plcCd", "key"]).useAmount.sum().unstack(fill_value=0)
        we = (t.get("토", 0) + t.get("일", 0)) / t.sum(axis=1)
        S["weekend_share"] = S.plcCd.map(we)
    return S[["adm_cd2", "adstrdCode", "visit_intensity", "weekend_share", "lodging_share", "lodging_food_share"]]


def main():
    prm = params()
    P, gw = load_poi()
    gw = gateway_weights(gw)
    tram_st = csv(DATA / "tram_stations.csv").set_index("station_no")
    l1_st = csv(DATA / "line1_stations.csv").set_index("station_no")
    l1_ids = sorted(l1_st.index)
    l1 = Net(l1_st, list(zip(l1_ids, l1_ids[1:])), L1_KMH, L1_WAIT)
    tram = Net(tram_st, tram_edges(tram_st), TRAM_KMH, TRAM_WAIT)

    areas = load_polys(OUT / "sangkwon_polygons.geojson", "code")
    dongs = load_polys(OUT / "dong_polygons.geojson", "id")
    places = []                                  # (kind, id, name, rings, (lat, lon))
    for c, (r, pr) in areas.items():
        places.append(("area", c, pr["name"], r, (float(pr["center_lat"]), float(pr["center_lon"]))))
    for i, (r, pr) in dongs.items():
        places.append(("dong", i, pr["name"], r, centroid(r)))

    near_rows, rows = [], []
    for kind, pid, name, rings, cen in places:
        # 관광지: 상권은 경계에서 500m(대형 1km), 행정동은 경계 안 + 대형은 1km
        dd = np.array([dist_to_poly(rings, la, lo) for la, lo in zip(P.lat, P.lon)])
        hit = P[dd <= P.band.to_numpy()].assign(dist_m=dd[dd <= P.band.to_numpy()].round())
        if kind == "dong":
            hit = hit[(hit.dist_m == 0) | hit.big]
        for h in hit.itertuples():
            near_rows.append(dict(kind=kind, id=pid, poi_id=h.poi_id, poi_name=h.name, tour_type=h.tour_type,
                                  w=h.w, big=h.big, dist_m=h.dist_m, visitors_yr=h.visitors_yr))
        score = float(hit.w.sum())
        vis = float(hit.visitors_yr.fillna(0).sum())
        n_fest = int((hit.tour_type == "축제장").sum())
        level = "강" if (score >= STRONG_SCORE or vis >= STRONG_VIS) else ("약" if score >= 1 else "없음")
        # 접근성: A = Σ w_o / TT_oj  (지금 vs 트램 뒤)
        tt_now = np.array([travel((g.lat, g.lon), cen, l1) for g in gw.itertuples()])
        tt_aft = np.array([travel((g.lat, g.lon), cen, l1, tram) for g in gw.itertuples()])
        r = dict(kind=kind, id=pid, name=name, tour_level=level,
                 tourism_type="관광자원형" if level != "없음" else "생활형",
                 tour_score=round(score, 1), n_poi=int((hit.w > 0).sum()), n_festival=n_fest,
                 visitors_yr=round(vis) if vis else np.nan,
                 top_poi=" · ".join(hit.sort_values(["w", "visitors_yr"], ascending=False).name.head(4)))
        for wname in ["w_traffic", "w_equal"]:
            w = gw[wname].to_numpy()
            a0, a1 = (w / tt_now).sum(), (w / tt_aft).sum()
            r[f"dlnA_{wname[2:]}"] = round(math.log(a1 / a0), 4)
        s0 = np.array([travel((g.lat, g.lon), cen, l1, None, *BUS_SLOW) for g in gw.itertuples()])
        s1 = np.array([travel((g.lat, g.lon), cen, l1, tram, *BUS_SLOW) for g in gw.itertuples()])
        w = gw.w_traffic.to_numpy()
        r["dlnA_busslow"] = round(math.log((w / s1).sum() / (w / s0).sum()), 4)
        r["tram_faster_n"] = int((tt_aft < tt_now - 0.05).sum())
        for g, t0, t1 in zip(gw.itertuples(), tt_now, tt_aft):
            r[f"tt_now_{g.poi_id}"], r[f"tt_tram_{g.poi_id}"] = round(t0, 1), round(t1, 1)
        rows.append(r)
    L = pd.DataFrame(rows)

    # 시나리오: 관광자원형만, Δln(방문) = ε × ΔlnA (관문 이용객 가중 기준), %로
    on = L.tourism_type == "관광자원형"
    for k in ["eps_low", "eps_base", "eps_nights"]:
        L["visit_" + k[4:] + "_pct"] = np.where(on, (np.exp(prm[k] * L.dlnA_traffic) - 1) * 100, 0.0).round(2)
    # 상한 = ε 1.0 × 버스가 느린 경우의 접근성 변화 (둘 다 불리하지 않은 쪽으로 최대)
    L["visit_high_pct"] = np.where(on, (np.exp(prm["eps_high"] * L.dlnA_busslow) - 1) * 100, 0.0).round(2)
    L["visit_equalw_base_pct"] = np.where(on, (np.exp(prm["eps_base"] * L.dlnA_equal) - 1) * 100, 0.0).round(2)
    L["scenario_note"] = np.where(on, "시나리오: 관광 접근성 변화 × 탄력성(해외 고속철 차용), 인과 측정 아님",
                                  "생활형(영향권 안 관광지 없음) → 관광 시나리오 0")

    # 대리지표 (행정동 → 상권은 점포 수 가중 평균), 대전 평균 대비 비율
    X = proxies()
    cols = ["visit_intensity", "weekend_share", "lodging_share", "lodging_food_share"]
    if len(X):
        dm = L[L.kind == "dong"][["id"]].merge(X, left_on="id", right_on="adm_cd2", how="left")
        ap = S8989 / "area_dong_share.csv"
        am = pd.DataFrame(columns=["area"] + cols)
        if ap.exists():
            A = csv(ap, dtype={"행정동코드": str})
            A = A.merge(X, left_on="행정동코드", right_on="adstrdCode", how="left")
            am = A.groupby("area").apply(
                lambda g: pd.Series({c: np.average(g[c].dropna(), weights=g.loc[g[c].notna(), "area_stores_in_dong"])
                                     if g[c].notna().any() else np.nan for c in cols}), include_groups=False).reset_index()
        for c in cols:
            v = dict(zip(dm.id, dm[c]))
            v.update(dict(zip(am.area, am[c])))
            L[c] = L.id.map(v)
            city = X[c].mean()
            L[c + "_vs_city"] = (L[c] / city).round(2)
        for c in cols:
            L[c] = L[c].round(4)

    L.to_csv(OUT / "tourism_layer.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(near_rows).to_csv(OUT / "tourism_poi_near.csv", index=False, encoding="utf-8-sig")

    # 정거장별 관광지
    srows = []
    for s, row in tram_st.iterrows():
        d = hav(row.lat, row.lon, P.lat.to_numpy(), P.lon.to_numpy())
        h = P[(d <= P.band.to_numpy()) & (P.w > 0)].assign(dist_m=d[(d <= P.band.to_numpy()) & (P.w > 0)].round())
        h = h.sort_values("dist_m")
        srows.append(dict(station_no=s, station_name=row.station_name, n_poi=len(h),
                          tour_score=round(float(h.w.sum()), 1),
                          visitors_yr=round(float(h.visitors_yr.fillna(0).sum())) or np.nan,
                          pois=" · ".join(f"{a}({int(b)}m)" for a, b in zip(h.name, h.dist_m))))
    S = pd.DataFrame(srows)
    S.to_csv(OUT / "tourism_station.csv", index=False, encoding="utf-8-sig")

    # S-커브: 효과 비율 f(t) = 1/(1+exp(-k(t-mid))), 개통 때 5%
    mid = prm["ramp_mid"]
    k = math.log(19) / mid
    t = np.arange(0, 61)
    pd.DataFrame({"month": t, "share": (1 / (1 + np.exp(-k * (t - mid)))).round(3)}).to_csv(
        OUT / "tourism_ramp.csv", index=False, encoding="utf-8-sig")

    # ── 요약 출력 ──
    print(f"관광지 {len(P)}곳(가중치>0 {int((P.w > 0).sum())}, 대형 1km {int(P.big.sum())}) · 관문 {len(gw)}곳 가중치: "
          + ", ".join(f"{a} {b:.2f}" for a, b in zip(gw.name, gw.w_traffic)))
    for kind in ["area", "dong"]:
        q = L[L.kind == kind]
        print(f"\n[{'상권' if kind == 'area' else '행정동'} {len(q)}] 관광자원형 {int((q.tourism_type == '관광자원형').sum())} "
              f"(강 {int((q.tour_level == '강').sum())}) · ΔlnA 중앙값 {q.dlnA_traffic.median():.3f} 최대 {q.dlnA_traffic.max():.3f}"
              f" · 버스 느린 경우 최대 {q.dlnA_busslow.max():.3f} · 트램이 더 빠른 관문이 1곳 이상인 곳 {int((q.tram_faster_n > 0).sum())}")
        show = q[q.tourism_type == "관광자원형"].sort_values("visit_base_pct", ascending=False).head(8)
        print(show[["id", "name", "tour_level", "tour_score", "dlnA_traffic", "dlnA_busslow", "visit_low_pct", "visit_base_pct",
                    "visit_high_pct", "top_poi"]].to_string(index=False))
    print(f"\n정거장 관광지 있는 곳 {int((S.n_poi > 0).sum())}/{len(S)}")
    print(S.sort_values("tour_score", ascending=False).head(6)[["station_no", "station_name", "n_poi", "pois"]].to_string(index=False))
    print("\n저장:", ", ".join(f"outputs/{n}" for n in ["tourism_layer.csv", "tourism_poi_near.csv", "tourism_station.csv", "tourism_ramp.csv"]))


if __name__ == "__main__":
    sys.exit(main())
