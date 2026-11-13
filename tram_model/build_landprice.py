"""개별공시지가(1990~2026) → 필지 위치 + 연도별 가격 → 상권·격자 단위 패널.

입력: data/raw/공시지가/ 에 국가공간정보포털 '개별공시지가정보' 대전 파일을 이름 그대로 넣기
- 속성(CSV) : AL_*D151*.csv 또는 그 csv 가 든 .zip  (예: AL_30_D151_20200925_csv.zip = 1990~2020 전 연도)
- 공간(SHP) : AL_*D150*.shp + 같은 이름의 .dbf/.prj  (필지 폴리곤 → 위치. 최신 파일 우선, 없는 필지는 옛 파일로 보충)
  2025·2026년 공시분 dbf 는 최근 5년 가격도 들어 있음 (A9=당해, A16~A19=1~4년 전)
- data/line1_stations.csv  : 도시철도 1호선 22개 역 (역명 버스정류장 평균, ±100m)
- outputs/sangkwon_anchors.csv : build_areas.py 결과 (없으면 sangkwon_areas.csv 원래 기준점)

출력 (outputs/)
- landprice_parcels.csv.gz : 필지별 위치·지목·상권·1호선/트램 거리
- landprice_long.pkl       : 필지 × 연도 가격 (1월 1일 기준 정기공시, 원/㎡)
- landprice_area_panel.csv : 20개 상권(+대전 전체) × 연도  — 중앙값, 연쇄지수(2015=100)
- landprice_cells.csv      : 250m 격자별 최근 가격·5년/10년 상승률 → build_dataset.py 가 피처로 사용

주의
- 2006년은 시가지 필지의 약 27% 가 빠져 있음 → 지수는 2005→2007 을 직접 잇고, 2006 은 있는 필지로만 계산
- 위치는 필지 고유번호로 붙임. 그 사이 분할·합병된 필지는 위치가 없어 빠짐 (1990년 값 기준 약 50% 연결)
"""
import re
import struct
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import config as C
from build_dataset import to_xy
from build_areas import assign, load_areas
from import_stations_dxf import CRS, tm_inverse

LP_DIR = C.RAW_DIR / "공시지가"


def lp_files(kind, ext):
    """공시지가 폴더(하위 폴더 포함)에서 이름에 kind(D150/D151)가 든 ext 파일. 대소문자·한글 정규화 무관.
    shp 묶음이 zip 으로 들어 있으면 _unzipped/ 에 자동으로 풀어서 사용."""
    import unicodedata
    if not LP_DIR.exists():
        raise FileNotFoundError(f"{LP_DIR} 폴더가 없습니다. data/raw 안에 '공시지가' 폴더를 만들고 파일을 넣어 주세요")
    if ext == ".shp":                                   # 다운로드한 zip 안에 shp 가 있으면 풀기
        for z in LP_DIR.rglob("*"):
            if z.suffix.lower() == ".zip" and "_unzipped" not in z.parts:
                try:
                    names = zipfile.ZipFile(z).namelist()
                except zipfile.BadZipFile:
                    continue
                if any(n.lower().endswith(".shp") for n in names):
                    dest = LP_DIR / "_unzipped" / z.stem
                    if not dest.exists():
                        print(f"  {z.name} 압축 풀기 → _unzipped/{z.stem}", flush=True)
                        zipfile.ZipFile(z).extractall(dest)
    out = []
    for f in LP_DIR.rglob("*"):
        n = unicodedata.normalize("NFC", f.name)
        if f.is_file() and f.suffix.lower() == ext and kind in n.upper() and "__MACOSX" not in f.parts \
                and not n.startswith("._"):
            out.append(f)
    return sorted(out, key=file_date, reverse=True)


def lp_listing():
    fs = [str(f.relative_to(LP_DIR)) for f in LP_DIR.rglob("*") if f.is_file()] if LP_DIR.exists() else []
    return "\n  ".join(sorted(fs)[:40]) or "(비어 있음)"
GAP_YEARS = {2006}          # 필지가 많이 빠진 해 → 지수 연결에서 건너뜀
BASE_YEAR = 2015
MIN_PAIRS = 10          # 연도 쌍에 같은 필지가 이보다 적으면 지수를 끊음
MIN_DAE = 30            # 상권 안 지목 '대' 필지가 이보다 적으면(예: 도룡동) 모든 지목 사용


# ------------------------------------------------------------------ 파일 읽기
def read_dbf(path, cols):
    with open(path, "rb") as f:
        h = f.read(32)
        nrec, hlen, rlen = struct.unpack("<IHH", h[4:12])
        fl, o = [], 1
        while True:
            b = f.read(32)
            if b[0] == 0x0D:
                break
            nm = b[:11].split(b"\0")[0].decode()
            fl.append((nm, o, b[16])); o += b[16]
        f.seek(hlen)
        a = np.frombuffer(f.read(rlen * nrec), np.uint8)[: rlen * nrec].reshape(-1, rlen)
    out = {}
    for nm, o, l in fl:
        if nm in cols:
            s = pd.Series(a[:, o:o + l].copy().view(f"S{l}").ravel())
            out[nm] = s.str.decode("cp949", errors="replace").str.strip()
    return pd.DataFrame(out), [x[0] for x in fl]


def read_shp_centers(path):
    """각 레코드 bbox 중심 (필지 크기에서는 무게중심과 거의 같음). 빈 도형은 NaN."""
    shx = path.with_suffix(".shx")
    data = path.read_bytes()
    if shx.exists():
        s = shx.read_bytes()
        offs = np.frombuffer(s[100:], ">i4").reshape(-1, 2)[:, 0].astype(np.int64) * 2
    else:
        offs, p = [], 100
        while p < len(data):
            _, ln = struct.unpack(">ii", data[p:p + 8]); offs.append(p); p += 8 + ln * 2
        offs = np.array(offs)
    cx = np.full(len(offs), np.nan); cy = np.full(len(offs), np.nan)
    for i, p in enumerate(offs):
        st = struct.unpack("<i", data[p + 8:p + 12])[0]
        if st == 0:
            continue
        x0, y0, x1, y1 = struct.unpack("<4d", data[p + 12:p + 44])
        cx[i], cy[i] = (x0 + x1) / 2, (y0 + y1) / 2
    return cx, cy


def detect_crs(shp, cy):
    prj = shp.with_suffix(".prj")
    if prj.exists():
        t = prj.read_text(errors="ignore")
        if "600000" in t:
            return "EPSG:5186"
        if "127.00289" in t:
            return "EPSG:5174"
        return "EPSG:2097"
    return "EPSG:5186" if np.nanmedian(cy) > 550_000 else "EPSG:5174"   # prj 없으면 북좌표 크기로 추정


def file_date(p):
    m = re.search(r"(20\d{6})", p.name)
    return m.group(1) if m else "0"


def load_geometry():
    shps = lp_files("D150", ".shp")
    if not shps:
        raise FileNotFoundError(f"{LP_DIR} 에 개별공시지가 shp(이름에 D150 이 들어간 .shp)가 없습니다.\n"
                                f"지금 폴더 안 파일:\n  {lp_listing()}")
    parts, seen = [], set()
    for shp in shps:
        d, _ = read_dbf(shp.with_suffix(".dbf"), {"A0", "A6"})
        cx, cy = read_shp_centers(shp)
        n = min(len(d), len(cx))
        d = d.iloc[:n].assign(cx=cx[:n], cy=cy[:n]).dropna(subset=["cx"])
        crs = detect_crs(shp, d.cy.values)
        d["lat"], d["lon"] = tm_inverse(d.cx.values, d.cy.values, CRS[crs])
        d = d[d.lat.between(36.15, 36.55) & d.lon.between(127.2, 127.65)]
        d = d[d.A0.str.match(r"^\d{19}$")]
        d["pnu"] = d.A0.astype("int64")                                 # 19자리 → float 로 바꾸면 끝자리가 깨짐
        d = d.drop_duplicates("pnu")
        new = d[~d.pnu.isin(seen)]
        seen |= set(new.pnu)
        new = new.assign(jimok=new.A6.str.extract(r"([가-힣]+)\s*$")[0], geom_src=shp.stem)
        parts.append(new[["pnu", "lat", "lon", "jimok", "geom_src"]])
        print(f"  위치 {shp.name} ({crs}): {len(d):,} 필지, 새로 추가 {len(new):,}", flush=True)
    g = pd.concat(parts, ignore_index=True)
    g["pnu"] = g.pnu.astype("int64")
    return g


def _std_cols(df):
    ren = {}
    for c in df.columns:
        if c in ("기준년도", "기준연도"):
            ren[c] = "year"
        elif c in ("공시지가", "개별공시지가"):
            ren[c] = "price"
        elif c == "고유번호":
            ren[c] = "pnu"
        elif c == "기준월":
            ren[c] = "month"
    return df.rename(columns=ren)


def _read_csv(src):
    use = lambda c: c in ("고유번호", "기준년도", "기준연도", "기준월", "공시지가", "개별공시지가")
    for enc in ("cp949", "utf-8-sig"):
        try:
            return _std_cols(pd.read_csv(src() if callable(src) else src, encoding=enc, dtype=str, usecols=use))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩을 알 수 없음: {src}")


def load_prices():
    parts = []
    files = sorted([*lp_files("D151", ".csv"), *lp_files("D151", ".zip")], key=file_date, reverse=True)
    for f in files:
        if f.suffix.lower() == ".zip":
            z = zipfile.ZipFile(f)
            for n in [n for n in z.namelist() if n.lower().endswith(".csv")]:
                parts.append(_read_csv(lambda n=n: z.open(n)).assign(src=f.name))
        else:
            parts.append(_read_csv(f).assign(src=f.name))
        p = parts[-1]
        print(f"  가격 {f.name}: {len(p):,}행, {p.year.min()}~{p.year.max()}", flush=True)
    # shp 의 dbf: 당해(A9) + 다년도(A16~A19, 있으면)
    for shp in lp_files("D150", ".dbf"):
        d, fields = read_dbf(shp, {"A0", "A7", "A8", "A9", "A16", "A17", "A18", "A19"})
        d = d[d.A7.str.match(r"^\d{4}$")]
        y = d.A7.astype(int)
        rows = [pd.DataFrame({"pnu": d.A0, "year": y.astype(str), "month": d.A8, "price": d.A9})]
        for k, col in enumerate(["A16", "A17", "A18", "A19"], start=1):
            if col in fields:
                rows.append(pd.DataFrame({"pnu": d.A0, "year": (y - k).astype(str), "month": "01", "price": d[col]}))
        p = pd.concat(rows).assign(src=shp.name)
        parts.append(p)
        print(f"  가격 {shp.name}: {len(p):,}행, {p.year.min()}~{p.year.max()}", flush=True)
    L = pd.concat(parts, ignore_index=True)
    L = L[L.month.fillna("01").str.zfill(2) == "01"]                 # 1월 1일 기준 정기공시만
    L = L[L.pnu.astype(str).str.match(r"^\d{19}$")]
    L["pnu"] = L.pnu.astype("int64")                                  # float 변환 금지 (19자리)
    L["year"] = pd.to_numeric(L.year, errors="coerce")
    L["price"] = pd.to_numeric(L.price, errors="coerce")
    L = L.dropna(subset=["year", "price"])
    L = L[L.price > 0]
    L = L.drop_duplicates(["pnu", "year"])                            # 최신 공시분 파일 값 우선
    L = L.astype({"pnu": "int64", "year": "int16", "price": "int64"})[["pnu", "year", "price"]]
    return L.reset_index(drop=True)


# ------------------------------------------------------------------ 지수
def chain_index(L, groups, base=BASE_YEAR):
    """같은 필지의 전년 대비 log 변화 중앙값을 연쇄 → 필지 구성이 바뀌어도 흔들리지 않는 지수."""
    W = L.pivot(index="pnu", columns="year", values="price")
    years = sorted(W.columns)
    chain_years = [y for y in years if y not in GAP_YEARS]
    lw = np.log(W)
    out = []
    for gname, pnus in groups.items():
        w = lw.loc[lw.index.intersection(pnus)]
        r = {}                                    # r[b] = 직전 연결연도 → b 로그 변화 중앙값
        for a, b in zip(chain_years[:-1], chain_years[1:]):
            d = (w[b] - w[a]).dropna()
            r[b] = d.median() if len(d) >= MIN_PAIRS else np.nan
        b0 = base if base in chain_years else chain_years[-1]
        k0 = chain_years.index(b0)
        idx = {b0: 0.0}
        for k in range(k0 + 1, len(chain_years)):                 # 기준연도 → 이후
            idx[chain_years[k]] = idx[chain_years[k - 1]] + r[chain_years[k]]
        for k in range(k0 - 1, -1, -1):                           # 기준연도 → 이전 (자료 없는 해에서 끊김)
            idx[chain_years[k]] = idx[chain_years[k + 1]] - r[chain_years[k + 1]]
        for y in GAP_YEARS & set(years):
            prev = max([c for c in chain_years if c < y], default=None)
            if prev is not None:
                d = (w[y] - w[prev]).dropna()
                idx[y] = idx[prev] + (d.median() if len(d) >= MIN_PAIRS else np.nan)
        s = pd.Series(idx).sort_index()
        s = np.exp(s) * 100
        med = W.loc[W.index.intersection(pnus)].median()
        cnt = W.loc[W.index.intersection(pnus)].notna().sum()
        out.append(pd.DataFrame({"code": gname, "year": s.index, "idx": s.values.round(2),
                                 "median_price": med.reindex(s.index).values, "n_parcels": cnt.reindex(s.index).values}))
    return pd.concat(out, ignore_index=True)


def main():
    C.OUT_DIR.mkdir(exist_ok=True)
    print("1/4 필지 위치 읽는 중 ...", flush=True)
    G = load_geometry()
    print("2/4 연도별 공시지가 읽는 중 (1~3분) ...", flush=True)
    L = load_prices()
    L = L[L.pnu.isin(G.pnu)]
    yrs = L.groupby("year").size()
    print(f"   위치가 붙은 가격 {len(L):,}행, {yrs.index.min()}~{yrs.index.max()}년")

    print("3/4 상권·역 거리 계산 ...", flush=True)
    G["x"], G["y"] = to_xy(G.lat, G.lon)
    anc_f = C.OUT_DIR / "sangkwon_anchors.csv"
    areas = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig")
    codes = list(areas.code)
    if anc_f.exists():
        anc = pd.read_csv(anc_f, encoding="utf-8-sig")
        anc["x"], anc["y"] = to_xy(anc.lat, anc.lon)
    else:
        _, anc = load_areas(); anc["x"], anc["y"] = anc.x0, anc.y0
    lab, _ = assign(G.x.values, G.y.values, anc, codes)
    G["area"] = np.where(lab >= 0, np.array(codes)[np.clip(lab, 0, None)], None)

    l1 = pd.read_csv(C.ROOT / "data" / "line1_stations.csv", encoding="utf-8-sig")
    l1["x"], l1["y"] = to_xy(l1.lat, l1.lon)
    d, i = cKDTree(l1[["x", "y"]].values).query(G[["x", "y"]].values)
    G["d_l1"], G["l1_no"], G["l1_phase"] = d.round(0), l1.station_no.values[i], l1.phase.values[i]

    exact = C.ROOT / "data" / "tram_stations.csv"
    tr = pd.read_csv(exact if exact.exists() else C.ROOT / "data" / "tram_stations_approx.csv", encoding="utf-8-sig")
    tr["x"], tr["y"] = to_xy(tr.lat, tr.lon)
    d, i = cKDTree(tr[["x", "y"]].values).query(G[["x", "y"]].values)
    G["d_tram"], G["tram_no"] = d.round(0), tr.station_no.values[i]
    G["gx"] = np.floor(G.x / C.CELL_M).astype(int)
    G["gy"] = np.floor(G.y / C.CELL_M).astype(int)
    G["dong_code"] = (G.pnu // 10 ** 9).astype("int64")          # 법정동 코드 10자리 (군집 단위)
    G["is_dae"] = (G.jimok == "대").astype(int)                    # 지목 '대'(건축물 부지) — 상업 분석 기본 표본

    print("4/4 상권·격자 지수 ...", flush=True)
    Ld = L[L.pnu.isin(G.pnu[G.is_dae == 1])]
    groups, sample = {"ALL": G.pnu[G.is_dae == 1].values}, {"ALL": "대"}
    for c in codes:
        dae = G.pnu[(G.area == c) & (G.is_dae == 1)].values
        if len(dae) >= MIN_DAE:
            groups[c], sample[c] = dae, "대"
        else:
            groups[c], sample[c] = G.pnu[G.area == c].values, "전체지목"
    A = chain_index(L, groups)
    A["sample"] = A.code.map(sample)
    A = A.merge(areas[["code", "name", "type"]], on="code", how="left")
    A.loc[A.code == "ALL", ["name", "type"]] = ["대전 전체", "전체"]
    A["rel_idx"] = (A.idx / A.year.map(A[A.code == "ALL"].set_index("year").idx) * 100).round(2)  # 대전 전체 대비

    # 격자 피처 (최근 연도 가격, 5·10년 상승률) — 같은 필지 기준
    ly = int(Ld.year.max())
    W = Ld[Ld.year.isin([ly, ly - 5, ly - 10])].pivot(index="pnu", columns="year", values="price")
    W = W.join(G.set_index("pnu")[["gx", "gy"]])
    W["g5"] = np.log(W[ly] / W[ly - 5]); W["g10"] = np.log(W[ly] / W[ly - 10])
    cells = W.groupby(["gx", "gy"]).agg(land_price=(ly, "median"), land_growth_5y=("g5", "median"),
                                        land_growth_10y=("g10", "median"), lp_n=(ly, "count")).reset_index()
    cells = cells[cells.lp_n >= 3]
    cells["land_price"] = cells.land_price.round(0)
    for c in ("land_growth_5y", "land_growth_10y"):
        cells[c] = (np.exp(cells[c]) - 1).round(4)
    cells["lp_year"] = ly

    G.drop(columns=["x", "y"]).to_csv(C.OUT_DIR / "landprice_parcels.csv.gz", index=False, encoding="utf-8-sig")
    L.to_pickle(C.OUT_DIR / "landprice_long.pkl")
    A.to_csv(C.OUT_DIR / "landprice_area_panel.csv", index=False, encoding="utf-8-sig")
    cells.to_csv(C.OUT_DIR / "landprice_cells.csv", index=False, encoding="utf-8-sig")
    yr = Ld.groupby("year").size()
    print(f"\n필지 {len(G):,}개 (지목 '대' {G.is_dae.sum():,}) | 연도 {yr.index.min()}~{yr.index.max()}"
          f" | 상권 패널 {A.code.nunique()}개 × {A.year.nunique()}년 | 격자 {len(cells):,}개")
    print("→ outputs/landprice_parcels.csv.gz, landprice_long.pkl, landprice_area_panel.csv, landprice_cells.csv")
    return G, L, A, cells


if __name__ == "__main__":
    main()
