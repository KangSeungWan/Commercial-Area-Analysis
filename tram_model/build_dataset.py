"""대전 트램 2호선 상권 데이터셋 구축.

출력
- outputs/daejeon_tram_area_dataset.csv : 학습용 9개 컬럼
  (area_id, month, sales, foot_traffic, dist_transit_m, dist_tram_m, n_stores, n_same_type, rent)
- outputs/features_ext.csv : area_id(셀×업종) 단위 논문 기반 추가 피처 (정적)
- outputs/area_lookup.csv  : area_id → 구역·셀·업종·행정동·좌표

논문 기반 추가 피처 (literature_params.csv 참조)
- in_tram_500, tram_band          : P2 Lan 2025 / P5 Reyes-Schade 2025 의 500m 정거장 권역
- bus_stops_300m, bus_dense       : P4 정은애·성현곤 2018 버스 300m 집수권, P2 버스밀도 조절효과
- stores_500m, stores_1km,
  same_type_500m                  : P3 김용래 외 2016 1차(500m)·2차(1km) 상권
- large_retail_1km, brand_share_500m : P3 대형상업시설수·상권브랜드지수 대용
- is_transfer_station             : P7 양충헌·김진국 2020 (소매 → 환승·종점 정거장 재배치)
- dist_hub_m, zone_type           : P6 Kakutani 2025 (중심/주변 상권별 효과 차이)
"""
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import config as C

MX = 111_320.0 * np.cos(np.radians(C.LAT0))
MY = 111_320.0


def to_xy(lat, lon):
    return (np.asarray(lon, float) - 127.0) * MX, (np.asarray(lat, float) - C.LAT0) * MY


# ------------------------------------------------------------------ loaders
def load_area_anchors():
    """20개 상권 정의 + 기준점. build_areas.py 가 보정한 기준점(outputs/sangkwon_anchors.csv)이 있으면 그것을 사용."""
    areas = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig", dtype={"line1_station": str})
    f = C.OUT_DIR / "sangkwon_anchors.csv"
    if f.exists():
        anc = pd.read_csv(f, encoding="utf-8-sig")
    else:
        rows = []
        for _, r in areas.iterrows():
            for p in str(r.anchors).split(";"):
                lat, lon = map(float, p.split())
                rows.append({"code": r.code, "lat": lat, "lon": lon, "radius_m": r.radius_m})
        anc = pd.DataFrame(rows)
        print("  (build_areas.py 를 먼저 돌리면 보정된 상권 기준점을 씁니다)", flush=True)
    if "radius_m" not in anc.columns:
        anc = anc.merge(areas[["code", "radius_m"]], on="code")
    anc["x"], anc["y"] = to_xy(anc.lat, anc.lon)
    return areas, anc


def assign_area(px, py, anc, codes):
    """점 → 상권 번호 (기준점까지 거리/반경 이 가장 작은 상권, 1 넘으면 -1). build_areas.assign 과 같은 규칙."""
    best = np.full(len(px), np.inf); lab = np.full(len(px), -1)
    for k, c in enumerate(codes):
        g = anc[anc.code == c]
        d = np.min(np.hypot(px[:, None] - g.x.values, py[:, None] - g.y.values) / g.radius_m.values, axis=1)
        b = d < best
        best[b], lab[b] = d[b], k
    lab[best > 1] = -1
    return lab


def load_stations():
    # 설계도면에서 뽑은 확정 좌표(import_stations_dxf.py)가 있으면 우선 사용, 없으면 추정 좌표
    exact = C.ROOT / "data" / "tram_stations.csv"
    st = pd.read_csv(exact if exact.exists() else C.ROOT / "data" / "tram_stations_approx.csv", encoding="utf-8-sig")
    print(f"정거장 좌표: {'설계도면 확정' if exact.exists() else '추정(버스정류장 기준)'}", flush=True)
    st["x"], st["y"] = to_xy(st.lat, st.lon)
    return st


def load_stores():
    path = C.raw_path("stores")
    if path.suffix.lower() == ".xlsx":
        print("상가 정보를 xlsx 로 읽는 중 (1~2분 걸림) ...", flush=True)
        s = pd.read_excel(path, dtype=str)
    else:
        s = pd.read_csv(path, dtype=str)
    s["lat"] = pd.to_numeric(s["위도"], errors="coerce")
    s["lon"] = pd.to_numeric(s["경도"], errors="coerce")
    s = s.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    s["x"], s["y"] = to_xy(s.lat, s.lon)
    s["gx"] = np.floor(s.x / C.CELL_M).astype(int)
    s["gy"] = np.floor(s.y / C.CELL_M).astype(int)
    # P3 대형상업시설 대용: 백화점·대형마트·아울렛 상호
    # (중분류 '종합 소매' 안에서 대형 브랜드 상호만; 입점 매장·'○○아울렛' 소형점 제외)
    pat = r"^(?:이마트(?!24|\s*에브리|노브랜드)|홈플러스(?!\s*익스프레스)|롯데마트|코스트코|트레이더스|세이브존)|백화점|하나로마트|프리미엄아울렛"
    s["is_large_retail"] = (s["상권업종중분류명"] == "종합 소매") & s["상호명"].fillna("").str.contains(pat, regex=True)
    # P3 브랜드지수 대용: 지점명이 있는(=체인) 점포
    s["is_branch"] = s["지점명"].fillna("").str.strip() != ""
    return s


def load_bus():
    b = pd.read_excel(C.raw_path("bus_national"))
    b = b[b["관리도시명"] == "대전BIS"]
    x, y = to_xy(b["위도"], b["경도"])
    return np.c_[x, y]


def load_foot_traffic():
    ft = pd.read_csv(C.raw_path("foot_traffic")).dropna()
    ft = ft[ft["기준연월"].astype(str).str.match(r"^[A-Z][a-z]{2}-\d{2}$")]  # 깨진 2022-13 등 제거
    ft["dt"] = pd.to_datetime(ft["기준연월"], format="%b-%y")
    ft = ft.drop_duplicates(["dt", "행정동"], keep="last")
    return ft


# ------------------------------------------------------------------ build
def build():
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    st = load_stations()
    s = load_stores()
    bus_xy = load_bus()

    # 1) 분석 셀: 20개 상권(data/sangkwon_areas.csv) 안의 250m 격자. zone = 상권 코드(A01~A20)
    areas, anc = load_area_anchors()
    cells = s[["gx", "gy"]].drop_duplicates().copy()
    cells["cx"] = (cells.gx + 0.5) * C.CELL_M
    cells["cy"] = (cells.gy + 0.5) * C.CELL_M
    codes = list(areas.code)
    lab = assign_area(cells.cx.values, cells.cy.values, anc.assign(radius_m=anc.radius_m + C.AREA_CELL_PAD_M), codes)
    cells["zone"] = np.where(lab >= 0, np.array(codes)[np.clip(lab, 0, None)], None)
    cells = cells[cells.zone.notna()].copy()
    print(f"분석 셀: 20개 상권 안 {len(cells)}개 격자 "
          f"(상권별 {cells.zone.value_counts().min()}~{cells.zone.value_counts().max()}개)", flush=True)
    cells["lon"] = cells.cx / MX + 127.0
    cells["lat"] = cells.cy / MY + C.LAT0
    cells["cell_id"] = cells.zone + "_" + (cells.gx + 1000).astype(str) + (cells.gy + 1000).astype(str)
    cxy = cells[["cx", "cy"]].values

    # 2) 트램 거리 (45개 정거장 전체)
    tt = cKDTree(st[["x", "y"]].values)
    dt, it = tt.query(cxy)
    cells["dist_tram_m"] = dt.round(0)
    cells["nearest_tram"] = st.station_no.values[it]
    cells["is_transfer_station"] = cells.nearest_tram.isin(C.TRANSFER_STATIONS).astype(int)
    hub = st[st.station_no.isin(C.HUB_STATIONS)][["x", "y"]].values
    cells["dist_hub_m"] = cKDTree(hub).query(cxy)[0].round(0)

    # 3) 버스: 최근접 거리 + 300m 내 정류장 수
    bt = cKDTree(bus_xy)
    cells["dist_transit_m"] = bt.query(cxy)[0].round(0)
    cells["bus_stops_300m"] = [len(v) for v in bt.query_ball_point(cxy, 300)]

    # 4) 점포 기반 피처 (P3 500m/1km 상권)
    stree = cKDTree(s[["x", "y"]].values)
    nb500 = stree.query_ball_point(cxy, 500)
    nb1k = stree.query_ball_point(cxy, 1000)
    cells["stores_500m"] = [len(v) for v in nb500]
    cells["stores_1km"] = [len(v) for v in nb1k]
    lr = s.is_large_retail.values
    br = s.is_branch.values
    cells["large_retail_1km"] = [int(lr[v].sum()) for v in nb1k]
    cells["brand_share_500m"] = [float(br[v].mean()) if len(v) else 0.0 for v in nb500]

    # 5) 셀 행정동
    sc = s.merge(cells[["gx", "gy", "cell_id"]], on=["gx", "gy"])
    dong = sc.groupby("cell_id").agg(sigungu=("시군구명", lambda v: v.mode()[0]),
                                     dong=("행정동명", lambda v: v.mode()[0]))
    cells = cells.merge(dong, left_on="cell_id", right_index=True)

    # 5-1) 공시지가 (build_landprice.py 결과가 있으면): 셀 중앙값, 없으면 가장 가까운 자료 셀 값
    lp_f = C.OUT_DIR / "landprice_cells.csv"
    if lp_f.exists():
        lp = pd.read_csv(lp_f, encoding="utf-8-sig")
        lxy = np.c_[(lp.gx + 0.5) * C.CELL_M, (lp.gy + 0.5) * C.CELL_M]
        dd, ii = cKDTree(lxy).query(cxy)
        for c in ("land_price", "land_growth_5y", "land_growth_10y"):
            cells[c] = lp[c].values[ii]
        cells.loc[dd > 750, ["land_price", "land_growth_5y", "land_growth_10y"]] = np.nan
        print(f"공시지가 피처 추가 ({int(lp.lp_year.iloc[0])}년 기준, 셀 {int((dd < 1).sum())}/{len(cells)} 직접 매칭)", flush=True)
    else:
        print("공시지가 피처 없음 (build_landprice.py 를 먼저 돌리면 추가됨)", flush=True)

    # 6) 유동인구 (중구만 존재) — 2024 평균
    ft = load_foot_traffic()
    ft24 = ft[ft.dt.dt.year == 2024].groupby("행정동")["일평균"].mean().round(0)
    cells["foot_traffic"] = np.where(cells.sigungu == "중구", cells.dong.map(ft24), np.nan)

    # 7) 셀 × 업종 대분류
    cats = (s[["상권업종대분류코드", "상권업종대분류명"]].drop_duplicates()
            .rename(columns={"상권업종대분류코드": "cat", "상권업종대분류명": "cat_name"}).sort_values("cat"))
    grid = cells.merge(cats, how="cross")
    grid = grid.merge(sc.groupby("cell_id").size().rename("n_stores"), left_on="cell_id", right_index=True)
    same = sc.groupby(["cell_id", "상권업종대분류코드"]).size().rename("n_same_type")
    grid = grid.merge(same, left_on=["cell_id", "cat"], right_index=True, how="left")
    grid["n_same_type"] = grid.n_same_type.fillna(0).astype(int)
    # 같은 업종 500m (P3 경쟁/집적)
    cat_arr = s["상권업종대분류코드"].values
    same500 = {}
    for cid, v in zip(cells.cell_id, nb500):
        vc = pd.Series(cat_arr[v]).value_counts()
        for c, n in vc.items():
            same500[(cid, c)] = n
    grid["same_type_500m"] = [same500.get((a, b), 0) for a, b in zip(grid.cell_id, grid.cat)]
    grid["area_id"] = grid.cell_id + "_" + grid.cat

    # 8) 논문 기반 범주 피처
    grid["in_tram_500"] = (grid.dist_tram_m <= 500).astype(int)                       # P2/P5
    grid["tram_band"] = pd.cut(grid.dist_tram_m, [-1, 300, 500, 1000, 1e9],
                               labels=["0-300", "300-500", "500-1000", "1000+"]).astype(str)  # P4/P3
    grid["bus_dense"] = (grid.bus_stops_300m > grid.bus_stops_300m.mean()).astype(int)  # P2 Table 9 (평균 기준)
    ar = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig").set_index("code")
    grid["zone_type"] = grid.zone.map(ar.p6_zone)                                    # P6 중심/2차/주변

    # 9) 임대료 (구역 단위, 2024Q1)
    r = pd.read_excel(C.raw_path("rent"), dtype={"지역코드": str}).set_index("지역이름")["임대료(천원/㎡)"]
    grid["rent"] = grid.zone.map(ar.rent_area).map(r).fillna(r.get("대전"))

    # 10) 매출 (KB 구×업종 월매출 → 점포 수 비례 배분; 위치별 실측 아님!)
    panel = attach_sales(grid, s, sc)

    cols = ["area_id", "month", "sales", "foot_traffic", "dist_transit_m", "dist_tram_m",
            "n_stores", "n_same_type", "rent"]
    out = panel[cols].copy()
    for c in ["sales", "foot_traffic", "dist_transit_m", "dist_tram_m"]:
        out[c] = out[c].astype("Int64")
    out.to_csv(C.OUT_DIR / "daejeon_tram_area_dataset.csv", index=False, encoding="utf-8-sig")

    ext_cols = ["area_id", "zone", "zone_type", "cat", "cat_name", "sigungu", "dong", "lat", "lon",
                "nearest_tram", "is_transfer_station", "in_tram_500", "tram_band", "dist_hub_m",
                "bus_stops_300m", "bus_dense", "stores_500m", "stores_1km", "same_type_500m",
                "large_retail_1km", "brand_share_500m"]
    ext_cols += [c for c in ("land_price", "land_growth_5y", "land_growth_10y") if c in grid.columns]
    ext = grid[ext_cols].copy()
    ext["lat"] = ext.lat.round(6); ext["lon"] = ext.lon.round(6)
    ext["brand_share_500m"] = ext.brand_share_500m.round(4)
    ext.to_csv(C.OUT_DIR / "features_ext.csv", index=False, encoding="utf-8-sig")

    lk = grid[["area_id", "zone", "cell_id", "cat", "cat_name", "sigungu", "dong", "lat", "lon", "nearest_tram"]].copy()
    lk["zone_name"] = lk.zone.map(pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig").set_index("code").name)
    lk.to_csv(C.OUT_DIR / "area_lookup.csv", index=False, encoding="utf-8-sig")

    ft.assign(month=ft.dt.dt.strftime("%Y-%m"))[["month", "행정동", "일평균"]] \
      .sort_values(["month", "행정동"]).to_csv(C.OUT_DIR / "foot_traffic_junggu_monthly.csv",
                                              index=False, encoding="utf-8-sig")
    print(f"dataset {out.shape}, features_ext {ext.shape}, large_retail stores={int(s.is_large_retail.sum())}")
    return out, ext


KB2CAT = {"일반음식점": "I2", "휴게음식점": "I2", "유흥": "I2", "숙박": "I1",
          "소매": "G2", "음식료품": "G2", "의류": "G2", "신변잡화": "G2", "전자제품": "G2", "주방용품": "G2",
          "가구": "G2", "직물/침구류": "G2", "학습자재": "G2", "악기": "G2", "기타유통": "G2", "사무기기": "G2",
          "운송기구판매": "G2", "연료판매": "G2", "주유": "G2",
          "학원": "P1", "유아교육기관": "P1", "의료기관/제약": "Q1", "레저/스포츠": "R1", "문화/취미": "R1",
          "미용": "S2", "수리서비스": "S2", "자동차정비/유지": "S2", "가례서비스": "S2",
          "관광여행": "N1", "용역서비스": "N1", "건축관련업": "M1"}
# 제외: 대형유통, 전자상거래, 보험, 회비, 학교, 비영리유통, 기타제조/도매 (소상공인 점포 매출 아님)


def attach_sales(grid, s, sc):
    kb = pd.read_csv(C.raw_path("kb_sales"), encoding="cp949")
    kb["cat"] = kb["업종"].map(KB2CAT)
    kb = kb.dropna(subset=["cat"])
    mcols = [c for c in kb.columns if c.endswith("(억원)")]
    kbl = kb.melt(id_vars=["기준년도", "구", "cat"], value_vars=mcols, var_name="m", value_name="eok")
    kbl["eok"] = kbl.eok.fillna(0)
    kbl["month"] = kbl["기준년도"].str[:4] + "-" + kbl.m.str.extract(r"(\d+)월")[0].str.zfill(2)
    gs = kbl.groupby(["구", "cat", "month"])["eok"].sum().reset_index()

    gcount = s.groupby(["시군구명", "상권업종대분류코드"]).size().rename("N_gu").reset_index()
    cg = sc.groupby(["cell_id", "시군구명", "상권업종대분류코드"]).size().rename("n").reset_index()
    cg = cg.merge(gcount, on=["시군구명", "상권업종대분류코드"]) \
           .merge(gs, left_on=["시군구명", "상권업종대분류코드"], right_on=["구", "cat"])
    cg["sales_manwon"] = cg.eok * 1e4 * cg.n / cg.N_gu
    cs = cg.groupby(["cell_id", "cat", "month"])["sales_manwon"].sum().reset_index()

    months = sorted(gs.month.unique())
    panel = grid.merge(pd.DataFrame({"month": months}), how="cross")
    panel = panel.merge(cs, on=["cell_id", "cat", "month"], how="left")
    has = panel.cat.isin(set(KB2CAT.values()))
    panel["sales"] = np.where(has, panel.sales_manwon.fillna(0).round(0), np.nan)
    return panel.sort_values(["zone", "gy", "gx", "cat", "month"])


if __name__ == "__main__":
    build()
