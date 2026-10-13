"""대전 1호선 1단계 개통(2006-03-16) 전후 점포 변화 — 지방행정 인허가 데이터 이중차분.

입력
  tram_model/data/raw/permits/*.csv   공공데이터포털 행정안전부_식품_일반음식점·휴게음식점·제과점영업
                                      - 파일데이터 CSV(한글 열, 전국 파일 그대로) 또는
                                      - download_permits_api.py 로 받은 오픈API CSV(영문 열, 대전만) 둘 다 읽음
  tram_model/data/line1_stations.csv  1호선 22개 역 (역 이름 + 위도·경도 열)

출력 (tram_model/outputs/)
  line1_permits_series.csv   처리군·비교군 연도별 영업 점포·개업·폐업
  line1_permits_effects.csv  이중차분 효과(기본·강건성·가짜 검정·업종별)
  line1_permits_es.csv       연도별 효과(event study)
  line1_permits.png          그림 2개 (점포 지수 / 연도별 효과)

방법
  처리군 = 1단계 역 500m 안, 비교군 = 1호선 모든 역에서 1~3km (지가 분석과 같은 기준)
  단위 = 250m 격자 × 연도(연말 기준 영업 중 점포 수), 2002~2014 (폐업 기록이 2001년부터라 그 전은 제외)
  모형 = log(점포+1) ~ 격자 고정효과 + 연도 고정효과 + 처리×개통후, 격자 단위 군집 표준오차
  가짜 검정 = 가짜 개통연도 2004(개통 전 자료만), 가짜 처리군 = 비교군 안 무작위 격자

실행
  python tram_model/analyze_line1_permits.py
"""
from __future__ import annotations

import glob
import math
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "data", "raw", "permits")
STATIONS_CSV = os.path.join(HERE, "data", "line1_stations.csv")
OUT_DIR = os.path.join(HERE, "outputs")

OPEN_DATE = pd.Timestamp("2006-03-16")
OPEN_YEAR = 2006
YEARS = list(range(2002, 2015))  # 대전 인허가 데이터는 폐업일이 2001년 이후부터 기록됨 → 그 전 연도는 점포 수 과소
BASE_YEAR = 2005  # 개통 직전 연말
FAKE_YEAR = 2004
CELL_M = 250
TREAT_R = 500
CTRL_MIN, CTRL_MAX = 1000, 3000

PHASE1 = ["판암", "신흥", "대동", "대전역", "중앙로", "중구청", "서대전네거리", "오룡", "용문", "탄방", "시청", "정부청사"]
PHASE2 = ["갈마", "월평", "갑천", "유성온천", "구암", "현충원", "월드컵경기장", "노은", "지족", "반석"]


# ---------------------------------------------------------------- 좌표 변환
# 인허가 데이터 좌표 = EPSG:5174 (Bessel 1841, 중부원점 수정, 동 200,000 / 북 500,000)
_A_B, _F_B = 6377397.155, 1 / 299.1528128
_A_W, _F_W = 6378137.0, 1 / 298.257223563
_LAT0, _LON0, _K0, _X0, _Y0 = 38.0, 127.0028902777778, 1.0, 200000.0, 500000.0
_TOWGS84 = (-115.80, 474.99, 674.11, 1.16, -2.31, -1.63, 6.43)


def _meridian_arc(phi, a, e2):
    e4, e6 = e2 * e2, e2 * e2 * e2
    return a * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * np.sin(2 * phi)
                + (15 * e4 / 256 + 45 * e6 / 1024) * np.sin(4 * phi)
                - (35 * e6 / 3072) * np.sin(6 * phi))


def _tm_inverse(x, y):
    a, f = _A_B, _F_B
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    m0 = _meridian_arc(math.radians(_LAT0), a, e2)
    m = m0 + (y - _Y0) / _K0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * np.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * np.sin(6 * mu) + (1097 * e1 ** 4 / 512) * np.sin(8 * mu))
    c1 = ep2 * np.cos(phi1) ** 2
    t1 = np.tan(phi1) ** 2
    n1 = a / np.sqrt(1 - e2 * np.sin(phi1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * np.sin(phi1) ** 2) ** 1.5
    d = (x - _X0) / (n1 * _K0)
    lat = phi1 - (n1 * np.tan(phi1) / r1) * (
        d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = math.radians(_LON0) + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                                 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / np.cos(phi1)
    return lat, lon  # radians, Bessel


def _tm_forward(lat, lon):
    """시험용: Bessel 위경도(라디안) → EPSG:5174."""
    a, f = _A_B, _F_B
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    n = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    t = np.tan(lat) ** 2
    c = ep2 * np.cos(lat) ** 2
    aa = (lon - math.radians(_LON0)) * np.cos(lat)
    m = _meridian_arc(lat, a, e2)
    m0 = _meridian_arc(math.radians(_LAT0), a, e2)
    x = _X0 + _K0 * n * (aa + (1 - t + c) * aa ** 3 / 6 + (5 - 18 * t + t ** 2 + 72 * c - 58 * ep2) * aa ** 5 / 120)
    y = _Y0 + _K0 * (m - m0 + n * np.tan(lat) * (aa ** 2 / 2 + (5 - t + 9 * c + 4 * c ** 2) * aa ** 4 / 24
                                                  + (61 - 58 * t + t ** 2 + 600 * c - 330 * ep2) * aa ** 6 / 720))
    return x, y


def _geo_to_ecef(lat, lon, a, f):
    e2 = f * (2 - f)
    n = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    return n * np.cos(lat) * np.cos(lon), n * np.cos(lat) * np.sin(lon), n * (1 - e2) * np.sin(lat)


def _ecef_to_geo(x, y, z, a, f):
    e2 = f * (2 - f)
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1 - e2))
    for _ in range(6):
        n = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1 - e2 * n / (n + h)))
    return lat, lon


def _helmert(x, y, z, sign=1):
    tx, ty, tz, rx, ry, rz, s = _TOWGS84
    k = math.pi / 180 / 3600
    rx, ry, rz = sign * rx * k, sign * ry * k, sign * rz * k
    tx, ty, tz, s = sign * tx, sign * ty, sign * tz, 1 + sign * s * 1e-6
    return (tx + s * (x - rz * y + ry * z), ty + s * (rz * x + y - rx * z), tz + s * (-ry * x + rx * y + z))


def epsg5174_to_wgs84(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    try:
        from pyproj import Transformer
        tr = Transformer.from_crs(5174, 4326, always_xy=True)
        lon, lat = tr.transform(x, y)
        return np.asarray(lat), np.asarray(lon)
    except Exception:
        lat, lon = _tm_inverse(x, y)
        X, Y, Z = _geo_to_ecef(lat, lon, _A_B, _F_B)
        X, Y, Z = _helmert(X, Y, Z)
        lat, lon = _ecef_to_geo(X, Y, Z, _A_W, _F_W)
        return np.degrees(lat), np.degrees(lon)


def wgs84_to_epsg5174(lat, lon):
    """시험용 역변환 (근사 역 Helmert)."""
    lat, lon = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    X, Y, Z = _geo_to_ecef(lat, lon, _A_W, _F_W)
    X, Y, Z = _helmert(X, Y, Z, sign=-1)
    blat, blon = _ecef_to_geo(X, Y, Z, _A_B, _F_B)
    return _tm_forward(blat, blon)


# ---------------------------------------------------------------- 읽기
def _find(cols, *keys, exclude=()):
    for c in cols:
        cc = str(c).replace(" ", "")
        if all(k in cc for k in keys) and not any(e in cc for e in exclude):
            return c
    return None


# 공공데이터포털 오픈API(행정안전부_식품_*_조회서비스) 영문 열 이름 → CSV 한글 열 이름
API_COLS = {
    "MNG_NO": "관리번호", "LCPMT_YMD": "인허가일자", "CLSBIZ_YMD": "폐업일자",
    "SALS_STTS_NM": "영업상태명", "DTL_SALS_STTS_NM": "상세영업상태명",
    "LOTNO_ADDR": "소재지전체주소", "ROAD_NM_ADDR": "도로명전체주소",
    "CRD_INFO_X": "좌표정보(X)", "CRD_INFO_Y": "좌표정보(Y)",
    "BZSTAT_SE_NM": "업태구분명", "BPLC_NM": "사업장명", "OPN_ATMY_GRP_CD": "개방자치단체코드",
    "SERVICE": "개방서비스명",
}


DAEJEON_ORG = {"3640000", "3650000", "3660000", "3670000", "3680000"}  # 대전 동·중·서·유성·대덕구 (2026-10 실제 파일로 확인)


def _guess_service(kind, path):
    """개방서비스명 열이 없을 때 업태구분명으로 업종 추정 (파일 이름이 깨져도 되도록)."""
    if kind is not None:
        top = kind.fillna("").value_counts()
        k = set(top.head(10).index)
        if "제과점영업" in k and top.index[0] == "제과점영업":
            return "제과점영업"
        if k & {"커피숍", "다방", "편의점", "기타 휴게음식점", "패스트푸드"}:
            return "휴게음식점"
        if k & {"한식", "호프/통닭", "분식", "경양식"}:
            return "일반음식점"
    return os.path.splitext(os.path.basename(path))[0]


def _read_csv(path):
    for enc in ("cp949", "utf-8-sig", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"인코딩을 알 수 없음: {path}")


def _parse_date(s):
    s = s.astype(str).str.replace(r"[^0-9]", "", regex=True).str[:8]
    return pd.to_datetime(s.where(s.str.len() == 8), format="%Y%m%d", errors="coerce")


def load_permits():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "**", "*.csv"), recursive=True))
    if not files:
        sys.exit(f"인허가 파일이 없습니다: {RAW_DIR} 에 csv 를 넣어 주세요.")
    frames = []
    for path in files:
        df = _read_csv(path)
        df = df.rename(columns={k: v for k, v in API_COLS.items() if k in df.columns})
        cols = list(df.columns)
        c_open = _find(cols, "인허가일자", exclude=("취소",))
        c_close = _find(cols, "폐업일자")
        c_state = _find(cols, "영업상태명", exclude=("상세",)) or _find(cols, "영업상태")
        c_addr = _find(cols, "소재지전체주소") or _find(cols, "지번") or _find(cols, "주소")
        c_road = _find(cols, "도로명전체주소") or _find(cols, "도로명")
        c_x = _find(cols, "좌표", "X") or _find(cols, "좌표", "x")
        c_y = _find(cols, "좌표", "Y") or _find(cols, "좌표", "y")
        c_id = _find(cols, "관리번호")
        c_svc = _find(cols, "개방서비스명")
        c_kind = _find(cols, "업태구분명")
        missing = [n for n, c in [("인허가일자", c_open), ("좌표X", c_x), ("좌표Y", c_y)] if c is None]
        if missing:
            print(f"  건너뜀 {os.path.basename(path)}: 열 없음 {missing}")
            continue
        addr = df[c_addr].fillna("") if c_addr else pd.Series("", index=df.index)
        if c_road:
            addr = addr.where(addr.str.len() > 0, df[c_road].fillna(""))
        keep = addr.str.startswith("대전")
        c_org = _find(cols, "개방자치단체코드")
        if c_org:
            keep = keep | df[c_org].astype(str).str.strip().isin(DAEJEON_ORG)
        d = pd.DataFrame({
            "id": (df[c_id] if c_id else df.index.astype(str)),
            "service": (df[c_svc] if c_svc else _guess_service(df[c_kind] if c_kind else None, path)),
            "kind": (df[c_kind] if c_kind else ""),
            "open": _parse_date(df[c_open]),
            "close": _parse_date(df[c_close]) if c_close else pd.NaT,
            "state": (df[c_state] if c_state else ""),
            "x": pd.to_numeric(df[c_x], errors="coerce"),
            "y": pd.to_numeric(df[c_y], errors="coerce"),
        })[keep.values]
        print(f"  {os.path.basename(path)}: 전체 {len(df):,}행 → 대전 {len(d):,}행")
        frames.append(d)
    if not frames:
        sys.exit("읽을 수 있는 인허가 파일이 없습니다.")
    p = pd.concat(frames, ignore_index=True)
    p["service"] = p["service"].fillna("기타").astype(str)
    n0 = len(p)
    p = p.drop_duplicates(subset=["service", "id"])
    closed_state = p["state"].fillna("").str.contains("폐업|취소|말소|폐쇄")
    bad = p["open"].isna() | p["x"].isna() | p["y"].isna() | (closed_state & p["close"].isna())
    print(f"  대전 합계 {n0:,}행, 중복 제거 후 {len(p):,}행, 날짜·좌표 없는 행 {int(bad.sum()):,} 제외")
    p = p[~bad].copy()
    p["lat"], p["lon"] = epsg5174_to_wgs84(p["x"].values, p["y"].values)
    return p


def load_stations():
    st = pd.read_csv(STATIONS_CSV, encoding="utf-8-sig")
    cols = list(st.columns)
    c_name = _find(cols, "역") or _find(cols, "name") or _find(cols, "station") or cols[0]
    c_lat = _find(cols, "위도") or _find(cols, "lat")
    c_lon = _find(cols, "경도") or _find(cols, "lon") or _find(cols, "lng")
    if c_lat is None or c_lon is None:
        sys.exit(f"역 파일에서 위도·경도 열을 찾지 못함: {cols}")
    s = pd.DataFrame({"name": st[c_name].astype(str), "lat": st[c_lat].astype(float), "lon": st[c_lon].astype(float)})
    base = s["name"].str.replace("역", "", regex=False).str.strip()
    base = base.where(base != "대전", "대전역")
    s["phase"] = np.where(base.isin(PHASE1) | s["name"].isin(PHASE1), 1,
                          np.where(base.isin(PHASE2) | s["name"].isin(PHASE2), 2, 0))
    if (s["phase"] == 0).any():
        print("  단계 판정 안 된 역:", s.loc[s["phase"] == 0, "name"].tolist())
    print(f"  1호선 역 {len(s)}개 (1단계 {int((s.phase == 1).sum())}, 2단계 {int((s.phase == 2).sum())})")
    return s


# ---------------------------------------------------------------- 공간
LAT_REF = 36.35
M_PER_DEG_LAT = 111_000.0
M_PER_DEG_LON = 111_000.0 * math.cos(math.radians(LAT_REF))


def _xy_m(lat, lon):
    return np.asarray(lon) * M_PER_DEG_LON, np.asarray(lat) * M_PER_DEG_LAT


def _min_dist(lat, lon, slat, slon):
    x, y = _xy_m(lat, lon)
    sx, sy = _xy_m(slat, slon)
    d = np.full(len(x), np.inf)
    for a, b in zip(sx, sy):
        d = np.minimum(d, np.hypot(x - a, y - b))
    return d


def assign_space(p, st):
    s1, sall = st[st.phase == 1], st
    p["d_p1"] = _min_dist(p.lat, p.lon, s1.lat, s1.lon)
    p["d_any"] = _min_dist(p.lat, p.lon, sall.lat, sall.lon)
    x, y = _xy_m(p.lat, p.lon)
    p["cell"] = (np.floor(x / CELL_M).astype(int)).astype(str) + "_" + (np.floor(y / CELL_M).astype(int)).astype(str)
    med = float(np.median(p["d_any"]))
    print(f"  점포-가장 가까운 역 거리 중앙값 {med:,.0f}m")
    if med > 6000:
        print("  경고: 거리가 너무 멂 → 좌표계 확인 필요 (인허가 좌표가 EPSG:5174 가 아닐 수 있음)")
    return p


# ---------------------------------------------------------------- 패널
def year_counts(df, years):
    rows = []
    for t in years:
        end = pd.Timestamp(f"{t}-12-31")
        start = pd.Timestamp(f"{t}-01-01")
        active = (df["open"] <= end) & (df["close"].isna() | (df["close"] > end))
        rows.append({"year": t,
                     "active": int(active.sum()),
                     "opened": int(((df["open"] >= start) & (df["open"] <= end)).sum()),
                     "closed": int(((df["close"] >= start) & (df["close"] <= end)).sum())})
    return pd.DataFrame(rows)


def cell_panel(p, years):
    cells = pd.Index(sorted(p["cell"].unique()), name="cell")
    out = []
    for t in years:
        end = pd.Timestamp(f"{t}-12-31")
        start = pd.Timestamp(f"{t}-01-01")
        active = (p["open"] <= end) & (p["close"].isna() | (p["close"] > end))
        opened = (p["open"] >= start) & (p["open"] <= end)
        closed = (p["close"] >= start) & (p["close"] <= end)
        g = pd.DataFrame({"cell": p["cell"], "active": active, "opened": opened, "closed": closed})
        c = g.groupby("cell")[["active", "opened", "closed"]].sum().reindex(cells, fill_value=0).astype(int)
        c["year"] = t
        out.append(c.reset_index())
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------- 회귀 (두 방향 고정효과, 균형 패널)
def _demean2(v, cell_idx, year_idx):
    v = v.astype(float)
    for _ in range(3):
        v = v - pd.Series(v).groupby(cell_idx).transform("mean").values
        v = v - pd.Series(v).groupby(year_idx).transform("mean").values
    return v


def twfe(panel, ycol, xcols, cluster="cell"):
    cell_idx = panel["cell"].values
    year_idx = panel["year"].values
    y = _demean2(panel[ycol].values, cell_idx, year_idx)
    X = np.column_stack([_demean2(panel[c].values, cell_idx, year_idx) for c in xcols])
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    u = y - X @ b
    meat = np.zeros((X.shape[1], X.shape[1]))
    groups = pd.Series(np.arange(len(y))).groupby(panel[cluster].values).indices
    for idx in groups.values():
        s = X[idx].T @ u[idx]
        meat += np.outer(s, s)
    G, N = len(groups), len(y)
    K = X.shape[1] + panel["cell"].nunique() + panel["year"].nunique() - 1
    adj = G / max(G - 1, 1) * (N - 1) / max(N - K, 1)
    V = adj * XtX_inv @ meat @ XtX_inv
    se = np.sqrt(np.diag(V))
    return b, se, G


def did(panel, treat_col, open_year, ycol="ly", years=None):
    d = panel if years is None else panel[panel.year.isin(years)]
    d = d.copy()
    d["D"] = (d[treat_col] * (d["year"] >= open_year)).astype(float)
    b, se, G = twfe(d, ycol, ["D"])
    return float(b[0]), float(se[0]), G


def pct(b):
    return 100 * (math.exp(b) - 1)


# ---------------------------------------------------------------- 메인
def build_sample(p, treat_r=TREAT_R, ctrl_min=CTRL_MIN, ctrl_max=CTRL_MAX):
    q = p.copy()
    q["group"] = np.where(q.d_p1 <= treat_r, "처리군",
                          np.where((q.d_any > ctrl_min) & (q.d_any <= ctrl_max), "비교군", None))
    q = q[q.group.notna()]
    # 격자는 점포 다수결로 한 그룹에 배정
    cg = q.groupby("cell")["group"].agg(lambda s: s.value_counts().index[0])
    q = q[q["group"] == q["cell"].map(cg)]
    return q


def panel_for(q, years=YEARS):
    cp = cell_panel(q, years)
    grp = q.groupby("cell")["group"].first()
    cp["treat"] = (cp["cell"].map(grp) == "처리군").astype(int)
    base = cp[cp.year == BASE_YEAR].set_index("cell")["active"]
    keep = base[base >= 1].index  # 개통 직전 점포가 있던 격자만
    cp = cp[cp.cell.isin(keep)].copy()
    cp["ly"] = np.log(cp["active"] + 1)
    cp["lo"] = np.log(cp["opened"] + 1)
    return cp


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("1) 인허가 데이터 읽기")
    p = load_permits()
    print("2) 1호선 역")
    st = load_stations()
    p = assign_space(p, st)
    print(f"  인허가일자 범위 {p.open.min():%Y-%m-%d} ~ {p.open.max():%Y-%m-%d}")

    closed_by_year = p["close"].dt.year.value_counts().sort_index()
    print("  연도별 폐업 기록 수(1996~2004):", {int(k): int(v) for k, v in closed_by_year.loc[1996:2004].items()})
    q = build_sample(p)
    print(f"3) 표본: 처리군 점포 {int((q.group == '처리군').sum()):,}, 비교군 {int((q.group == '비교군').sum()):,}")

    # 그룹별 연도 시계열
    series = []
    for gname, g in q.groupby("group"):
        c = year_counts(g, YEARS)
        c["group"] = gname
        series.append(c)
    series = pd.concat(series, ignore_index=True)
    series["active_start"] = series.groupby("group")["active"].shift(1)
    series["open_rate"] = series["opened"] / series["active_start"]
    series["close_rate"] = series["closed"] / series["active_start"]
    base = series[series.year == BASE_YEAR].set_index("group")["active"]
    series["index_2005"] = 100 * series["active"] / series["group"].map(base)
    series.to_csv(os.path.join(OUT_DIR, "line1_permits_series.csv"), index=False, encoding="utf-8-sig")

    cp = panel_for(q)
    print(f"  격자 {cp.cell.nunique()}개 (처리 {cp[cp.treat == 1].cell.nunique()}, 비교 {cp[cp.treat == 0].cell.nunique()})")

    rows = []

    def add(label, b, se, G, note=""):
        lo, hi = b - 1.96 * se, b + 1.96 * se
        rows.append({"분석": label, "효과_%": round(pct(b), 1), "하한_%": round(pct(lo), 1),
                     "상한_%": round(pct(hi), 1), "p값": round(_pval(b / se), 3) if se > 0 else np.nan,
                     "격자수": G, "비고": note})
        print(f"  {label}: {pct(b):+.1f}% [{pct(lo):+.1f}, {pct(hi):+.1f}]  {note}")

    print("4) 이중차분 (영업 중 점포 수, 로그)")
    add("기본: 역 500m vs 1~3km", *did(cp, "treat", OPEN_YEAR), f"{YEARS[0]}~{YEARS[-1]}")
    add("개통 후 4년만 (2006~2009)", *did(cp, "treat", OPEN_YEAR, years=range(YEARS[0], 2010)))
    add("개업 수 (로그)", *did(cp, "treat", OPEN_YEAR, ycol="lo"), "개업 흐름")

    print("5) 강건성")
    for r in (300, 750):
        add(f"처리 반경 {r}m", *did(panel_for(build_sample(p, treat_r=r)), "treat", OPEN_YEAR))
    add("비교군 1~2km", *did(panel_for(build_sample(p, ctrl_max=2000)), "treat", OPEN_YEAR))

    print("6) 가짜 검정")
    add(f"가짜 개통연도 {FAKE_YEAR} ({YEARS[0]}~2005)", *did(cp, "treat", FAKE_YEAR, years=range(YEARS[0], 2006)), "0 근처여야 통과")
    rng = np.random.default_rng(0)
    ctrl_cells = cp.loc[cp.treat == 0, "cell"].unique()
    fake = set(rng.choice(ctrl_cells, size=min(len(ctrl_cells) // 3, max(1, cp[cp.treat == 1].cell.nunique())), replace=False))
    pc = cp[cp.treat == 0].copy()
    pc["fake"] = pc.cell.isin(fake).astype(int)
    add("가짜 처리군 (비교군 안 무작위)", *did(pc, "fake", OPEN_YEAR), "0 근처여야 통과")

    print("7) 업종별")
    for svc, g in q.groupby("service"):
        if g.cell.nunique() < 30:
            continue
        sp = panel_for(g)
        if sp.treat.nunique() < 2:
            continue
        add(f"업종: {svc}", *did(sp, "treat", OPEN_YEAR))

    eff = pd.DataFrame(rows)
    eff.to_csv(os.path.join(OUT_DIR, "line1_permits_effects.csv"), index=False, encoding="utf-8-sig")

    print("8) 연도별 효과")
    es_years = [t for t in YEARS if t != BASE_YEAR]
    d = cp.copy()
    xcols = []
    for t in es_years:
        c = f"e{t}"
        d[c] = ((d.year == t) & (d.treat == 1)).astype(float)
        xcols.append(c)
    b, se, _ = twfe(d, "ly", xcols)
    es = pd.DataFrame({"year": es_years, "b": b, "se": se})
    es = pd.concat([es, pd.DataFrame({"year": [BASE_YEAR], "b": [0.0], "se": [0.0]})]).sort_values("year")
    es["효과_%"] = [pct(v) for v in es.b]
    es["하한_%"] = [pct(v - 1.96 * s) for v, s in zip(es.b, es.se)]
    es["상한_%"] = [pct(v + 1.96 * s) for v, s in zip(es.b, es.se)]
    es.to_csv(os.path.join(OUT_DIR, "line1_permits_es.csv"), index=False, encoding="utf-8-sig")

    plot(series, es)
    print("완료 →", OUT_DIR)


def _pval(z):
    return math.erfc(abs(z) / math.sqrt(2))


def plot(series, es):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("AppleGothic", "Apple SD Gothic Neo", "NanumGothic", "Noto Sans CJK KR", "Malgun Gothic"):
        if any(f == x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = f
            break
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    for g, color in (("처리군", "#2a6fdb"), ("비교군", "#9a9a9a")):
        s = series[series.group == g]
        label = "1단계 역 500m 안" if g == "처리군" else "역에서 1~3km"
        ax[0].plot(s.year, s.index_2005, marker="o", ms=3, color=color, label=label)
    ax[0].axvline(OPEN_YEAR, color="#444", ls="--", lw=1)
    ax[0].text(OPEN_YEAR + 0.2, ax[0].get_ylim()[1] * 0.97, "1단계 개통 2006-03", fontsize=9, va="top")
    ax[0].set_title("영업 중 점포 수 (2005년 = 100)")
    ax[0].legend(frameon=False)
    ax[1].axhline(0, color="#444", lw=0.8)
    ax[1].axvline(OPEN_YEAR - 0.5, color="#444", ls="--", lw=1)
    ax[1].errorbar(es.year, es["효과_%"], yerr=[es["효과_%"] - es["하한_%"], es["상한_%"] - es["효과_%"]],
                   fmt="o", color="#2a6fdb", ecolor="#9fb9ea", capsize=2)
    ax[1].set_title("연도별 효과: 역 500m 안 점포, 비교군 대비 % (2005 기준)")
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "line1_permits.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
