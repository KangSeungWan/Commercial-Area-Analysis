"""설계 도면(DXF)에서 트램 2호선 정거장 좌표 추출 → data/tram_stations.csv

DWG 는 직접 못 읽으므로 먼저 DXF(ASCII)로 변환:
  ODA File Converter(무료, 맥 지원) → Output version "ACAD2018", type "DXF"  (또는 AutoCAD: DXFOUT)

사용:
  python tram_model/import_stations_dxf.py 도면1.dxf 도면2.dxf ...
  python tram_model/import_stations_dxf.py data/dxf/*.dxf --crs auto

하는 일
1) DXF 의 TEXT / MTEXT / INSERT(+ATTRIB) 에서 정거장 번호(201~245)·정거장 이름이 든 글자와 그 좌표를 모음
2) 좌표계 판별: 한국 TM 좌표(EPSG:5186/5185/5187 GRS80, 5174/2097 Bessel) 후보를 모두 경위도로 바꿔 보고,
   기존 추정 좌표(data/tram_stations_approx.csv)와 가장 잘 맞는 좌표계를 고름 (--crs 로 직접 지정 가능)
3) 정거장별 좌표 = 같은 번호가 여러 번 나오면 중앙값
4) 출력
   - data/tram_stations.csv              : 확정 좌표 (build_dataset.py·build_areas.py 가 우선 사용)
   - outputs/station_dxf_candidates.csv  : 찾은 글자 전부 (검토용)
   - outputs/station_dxf_report.csv      : 정거장별 새 좌표 vs 기존 추정 좌표 차이

외부 라이브러리 없이 동작 (ezdxf·pyproj 불필요).
"""
import argparse
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
APPROX = ROOT / "data" / "tram_stations_approx.csv"
OUT_ST = ROOT / "data" / "tram_stations.csv"
OUT_DIR = ROOT / "outputs"

# ------------------------------------------------------------------ 좌표계 (TM 역변환, Snyder 1987)
GRS80 = (6378137.0, 1 / 298.257222101)
BESSEL = (6377397.155, 1 / 299.1528128)
CRS = {
    "EPSG:5186": dict(ell=GRS80, lat0=38, lon0=127, FE=200000, FN=600000, towgs84=None),     # 중부원점 (현행)
    "EPSG:5185": dict(ell=GRS80, lat0=38, lon0=125, FE=200000, FN=600000, towgs84=None),     # 서부원점
    "EPSG:5187": dict(ell=GRS80, lat0=38, lon0=129, FE=200000, FN=600000, towgs84=None),     # 동부원점
    "EPSG:5174": dict(ell=BESSEL, lat0=38, lon0=127 + 10.405 / 3600, FE=200000, FN=500000,   # 구 중부원점(보정)
                      towgs84=(-115.80, 474.99, 674.11, 1.16, -2.31, -1.63, 6.43)),
    "EPSG:2097": dict(ell=BESSEL, lat0=38, lon0=127, FE=200000, FN=500000,
                      towgs84=(-115.80, 474.99, 674.11, 1.16, -2.31, -1.63, 6.43)),
}


def _M(phi, a, e2):
    e4, e6 = e2 * e2, e2 ** 3
    return a * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * np.sin(2 * phi)
                + (15 * e4 / 256 + 45 * e6 / 1024) * np.sin(4 * phi)
                - (35 * e6 / 3072) * np.sin(6 * phi))


def tm_inverse(x, y, p):
    a, f = p["ell"]; e2 = 2 * f - f * f; ep2 = e2 / (1 - e2); k0 = 1.0
    x = np.asarray(x, float) - p["FE"]; y = np.asarray(y, float) - p["FN"]
    M = _M(math.radians(p["lat0"]), a, e2) + y / k0
    mu = M / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * np.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * np.sin(6 * mu) + (1097 * e1 ** 4 / 512) * np.sin(8 * mu))
    s, c, t = np.sin(phi1), np.cos(phi1), np.tan(phi1)
    C1 = ep2 * c * c; T1 = t * t
    N1 = a / np.sqrt(1 - e2 * s * s); R1 = a * (1 - e2) / (1 - e2 * s * s) ** 1.5
    D = x / (N1 * k0)
    lat = phi1 - (N1 * t / R1) * (D ** 2 / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * ep2) * D ** 4 / 24
                                  + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * ep2 - 3 * C1 ** 2) * D ** 6 / 720)
    lon = math.radians(p["lon0"]) + (D - (1 + 2 * T1 + C1) * D ** 3 / 6
                                     + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * ep2 + 24 * T1 ** 2) * D ** 5 / 120) / c
    lat, lon = np.degrees(lat), np.degrees(lon)
    if p["towgs84"] is not None:
        lat, lon = helmert_to_wgs84(lat, lon, p["ell"], p["towgs84"])
    return lat, lon


def helmert_to_wgs84(lat, lon, ell, tw):
    """Bessel → WGS84(≈GRS80) 7변수 변환 (position vector)."""
    a, f = ell; e2 = 2 * f - f * f
    la, lo = np.radians(lat), np.radians(lon)
    N = a / np.sqrt(1 - e2 * np.sin(la) ** 2)
    X = N * np.cos(la) * np.cos(lo); Y = N * np.cos(la) * np.sin(lo); Z = N * (1 - e2) * np.sin(la)
    tx, ty, tz, rx, ry, rz, ds = tw
    rx, ry, rz = [math.radians(v / 3600) for v in (rx, ry, rz)]; m = 1 + ds * 1e-6
    X2 = tx + m * (X - rz * Y + ry * Z)
    Y2 = ty + m * (rz * X + Y - rx * Z)
    Z2 = tz + m * (-ry * X + rx * Y + Z)
    a2, f2 = GRS80; e22 = 2 * f2 - f2 * f2
    p = np.sqrt(X2 ** 2 + Y2 ** 2); lon2 = np.arctan2(Y2, X2)
    lat2 = np.arctan2(Z2, p * (1 - e22))
    for _ in range(5):
        N2 = a2 / np.sqrt(1 - e22 * np.sin(lat2) ** 2)
        lat2 = np.arctan2(Z2 + e22 * N2 * np.sin(lat2), p)
    return np.degrees(lat2), np.degrees(lon2)


# ------------------------------------------------------------------ DXF (ASCII) 읽기
def read_dxf_texts(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8", "cp949", "latin-1"):
        try:
            txt = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    lines = txt.splitlines()
    if len(lines) < 4 or lines[0].strip() != "0":
        raise ValueError(f"{path}: ASCII DXF 가 아닙니다 (바이너리 DXF/DWG 이면 ASCII DXF 로 다시 저장)")
    pairs = [(lines[i].strip(), lines[i + 1]) for i in range(0, len(lines) - 1, 2)]

    out, in_entities, ent = [], False, None
    def flush():
        if ent and ent.get("text") and "x" in ent and not ent.get("paper"):
            out.append(ent)
    for code, val in pairs:
        if code == "2" and val.strip() == "ENTITIES":
            in_entities = True
        if code == "0":
            if val.strip() == "ENDSEC":
                flush(); ent = None; in_entities = False; continue
            if not in_entities:
                continue
            flush()
            et = val.strip()
            ent = {"type": et, "layer": "", "text": ""} if et in ("TEXT", "MTEXT", "ATTRIB", "INSERT") else None
            continue
        if ent is None or not in_entities:
            continue
        if code == "8":
            ent["layer"] = val.strip()
        elif code == "67" and val.strip() == "1":          # 도면 시트(paper space) 글자는 실제 위치가 아님
            ent["paper"] = True
        elif code == "10":
            ent["x"] = float(val)
        elif code == "20":
            ent["y"] = float(val)
        elif code in ("1", "3") and ent["type"] != "INSERT":
            ent["text"] += val
        elif code == "2" and ent["type"] == "INSERT":
            ent["text"] = "BLOCK:" + val.strip()
    flush()
    df = pd.DataFrame(out)
    if len(df):
        df["text"] = (df.text.str.replace(r"\\[A-Za-z][^;]*;", "", regex=True)       # MTEXT 서식코드 제거
                      .str.replace(r"[{}]|\\P", " ", regex=True).str.strip())
        df["file"] = Path(path).name
    return df


# "201", "제201정거장", "201 정거장", "STA.201", "201(서대전역)" 처럼 정거장 번호로 쓰인 글자만 (치수·표고 숫자 제외)
STNO = re.compile(r"^(?:제|STA\.?|NO\.?|#)?\s*(2(?:0[1-9]|[1-3]\d|4[0-5]))\s*(?:번)?\s*(?:정거장|정류장|역|STA(?:TION)?)?\s*(?:\(.*\))?$",
                  re.IGNORECASE)


NAME_RE = re.compile(r"([가-힣A-Za-z0-9·()]+?)\s*(?:\((?:일반|특화)\))?\s*정거장")


def build_name_index(approx):
    """정거장 이름 → 번호. '대전역(중앙시장)' 전체, 괄호 앞 이름, 괄호 안 별칭을 모두 등록 (겹치면 전체 이름 우선)."""
    idx, full = {}, {}
    for _, r in approx.iterrows():
        nm = str(r.station_name).replace(" ", "")
        full[nm] = int(r.station_no)
        base = re.sub(r"\(.*?\)", "", nm)
        alts = [base] + [a for g in re.findall(r"\((.*?)\)", nm) for a in re.split(r"[·,]", g)]
        for a in alts:
            if a:
                idx.setdefault(a, set()).add(int(r.station_no))
    return full, {k: v for k, v in idx.items()}


def find_station_texts(df, approx):
    full, idx = build_name_index(approx)
    rows = []
    for _, r in df.iterrows():
        t = re.sub(r"\s+", " ", str(r.text)).strip()
        m = STNO.match(t)
        if m:
            rows.append({**r.to_dict(), "station_no": int(m.group(1)), "match": "번호", "name_in_drawing": t})
            continue
        if "정거장" not in t or len(t) > 40:
            continue
        for nm in set(NAME_RE.findall(t.replace(" ", ""))):
            nm = re.sub(r"^(?:제)?", "", nm)
            if nm in full:
                nos = {full[nm]}
            elif nm in idx and len(idx[nm]) == 1:
                nos = idx[nm]
            else:
                rows.append({**r.to_dict(), "station_no": -1, "match": "이름(미확인)", "name_in_drawing": nm})
                continue
            for no in nos:
                rows.append({**r.to_dict(), "station_no": int(no), "match": "이름", "name_in_drawing": nm})
    return pd.DataFrame(rows)


# 측량 좌표 주기: "X=414,523.123", "Y : 234567.89", "N=...", "E=..." (한국 도면은 보통 X=북, Y=동)
COORD_RE = re.compile(r"([XYNE])\s*[=:：]\s*([0-9]{3},?[0-9]{3}(?:\.[0-9]+)?)", re.IGNORECASE)


def find_coord_labels(df):
    """글자에서 측량 좌표 주기를 찾아 (도면 x,y, 북 N, 동 E) 목록으로. X·Y 가 따로 쓰였으면 가까운 것끼리 짝지음."""
    singles, pairs = [], []
    for _, r in df.iterrows():
        hits = COORD_RE.findall(str(r.text))
        if not hits:
            continue
        vals = {k.upper(): float(v.replace(",", "")) for k, v in hits}
        n = vals.get("X", vals.get("N")); e = vals.get("Y", vals.get("E"))
        if n is not None and e is not None:
            pairs.append({"file": r.file, "x": r.x, "y": r.y, "N": n, "E": e, "text": r.text})
        else:
            singles.append({"file": r.file, "x": r.x, "y": r.y, "axis": "N" if n is not None else "E",
                            "v": n if n is not None else e})
    s = pd.DataFrame(singles)
    if len(s):
        for f, g in s.groupby("file"):
            Ns, Es = g[g.axis == "N"], g[g.axis == "E"]
            if Ns.empty or Es.empty:
                continue
            # 서로 가장 가까운 X(북)·Y(동) 글자끼리 짝 (mutual nearest neighbour)
            d = np.hypot(Ns.x.values[:, None] - Es.x.values, Ns.y.values[:, None] - Es.y.values)
            jn = d.argmin(1); ie = d.argmin(0)
            for i, j in enumerate(jn):
                if ie[j] == i:
                    pairs.append({"file": f, "x": Ns.x.values[i], "y": Ns.y.values[i],
                                  "N": Ns.v.values[i], "E": Es.v.values[j], "text": "X/Y 따로"})
    return pd.DataFrame(pairs)


# ------------------------------------------------------------------ 좌표 맞추기
LAT_C, LON_C = 36.35, 127.39
KX, KY = 111320 * math.cos(math.radians(LAT_C)), 111320.0
DJ_BOX = (36.20, 36.52, 127.20, 127.60)        # 대전 범위 (이 밖이면 실패로 판단)


def to_local(lat, lon):
    return (np.asarray(lon) - LON_C) * KX, (np.asarray(lat) - LAT_C) * KY


def from_local(x, y):
    return np.asarray(y) / KY + LAT_C, np.asarray(x) / KX + LON_C


def fit_similarity(P, Q):
    """P(도면 xy) → Q(현지 m) 2D 닮음변환 (복소수 최소제곱)."""
    p = P[:, 0] + 1j * P[:, 1]; q = Q[:, 0] + 1j * Q[:, 1]
    pm, qm = p.mean(), q.mean()
    a = np.vdot(p - pm, q - qm) / np.vdot(p - pm, p - pm)
    b = qm - a * pm
    return a, b


def apply_sim(a, b, P):
    z = a * (P[:, 0] + 1j * P[:, 1]) + b
    return np.c_[z.real, z.imag]


def ransac_similarity(P, Q, tol=500, iters=2000, seed=0):
    rng = np.random.default_rng(seed); n = len(P); best = None
    for _ in range(iters):
        i, j = rng.choice(n, 2, replace=False)
        if np.hypot(*(P[i] - P[j])) < 1e-6:
            continue
        a, b = fit_similarity(P[[i, j]], Q[[i, j]])
        res = np.hypot(*(apply_sim(a, b, P) - Q).T)
        inl = res < tol
        if best is None or inl.sum() > best.sum():
            best = inl
    if best is None or best.sum() < 4:
        return None
    a, b = fit_similarity(P[best], Q[best])
    res = np.hypot(*(apply_sim(a, b, P) - Q).T)
    return a, b, res


SCALES = {"m": 1.0, "mm": 1e-3, "cm": 1e-2}
ORIENT = {                                  # 도면 x,y → (동쪽 E, 북쪽 N)
    "그대로": lambda x, y: (x, y),
    "90°": lambda x, y: (-y, x),
    "180°": lambda x, y: (-x, -y),
    "270°": lambda x, y: (y, -x),
    "x↔y": lambda x, y: (y, x),
    "x↔y·180°": lambda x, y: (-y, -x),
    "좌우반전": lambda x, y: (-x, y),
    "상하반전": lambda x, y: (x, -y),
}


def solve_file(c, ap_xy):
    """한 도면 파일의 정거장 후보 → (방법, 정거장별 위경도). 실패하면 None."""
    best = None
    # ① 한국 TM 좌표계 × 단위(m/mm/cm) × 도면 회전·뒤집기(90° 단위)
    #    배치도는 mm 단위로 그리거나 용지에 맞춰 90° 돌려 그린 경우가 많음
    for sname, s in SCALES.items():
        for oname, f in ORIENT.items():
            E, N = f(c.x.values * s, c.y.values * s)
            if not (np.nanmedian(E) > 1e5 and np.nanmedian(E) < 4e5 and np.nanmedian(N) > 2e5 and np.nanmedian(N) < 8e5):
                continue
            for code, p in CRS.items():
                lat, lon = tm_inverse(E, N, p)
                cc = c.assign(lat=lat, lon=lon).join(ap_xy, on="station_no", rsuffix="_ap")
                cc["d"] = np.hypot((cc.lat - cc.lat_ap) * KY, (cc.lon - cc.lon_ap) * KX)
                g = cc[cc.d <= 1000].groupby("station_no")[["lat", "lon", "d"]].median()   # 정거장별 가까운 글자만
                if g.empty:
                    continue
                score = (len(g), -float(g.d.median()))
                if best is None or score > best[0]:
                    best = (score, f"{code}·{sname}·{oname}", g[["lat", "lon"]], float(g.d.median()))
    if best and best[3] <= 600:
        return best[1], best[2], best[3]
    med = c.groupby("station_no")[["x", "y"]].median()
    common = med.join(ap_xy, how="inner")                         # ② 지역 좌표 → 닮음변환 정합
    if len(common) >= 4:
        Q = np.c_[to_local(common.lat.values, common.lon.values)]
        r = ransac_similarity(common[["x", "y"]].values, Q)
        if r is not None:
            a, b, res = r
            inl = res < 500
            scale = abs(a)
            need = max(4, math.ceil(0.6 * len(common)))     # 우연히 맞는 경우를 막기 위해 60% 이상이 맞아야 함
            # 실제 지형 도면이면 축척이 m·mm·cm 중 하나(±15%). 아니면 도면 시트를 나란히 배치한 것 → 거부
            unit_ok = any(abs(scale / u - 1) < 0.15 for u in (1.0, 1e-3, 1e-2))
            if inl.sum() >= need and np.median(res[inl]) <= 300 and unit_ok:
                XY = apply_sim(a, b, med[["x", "y"]].values)
                lat, lon = from_local(XY[:, 0], XY[:, 1])
                out = pd.DataFrame({"lat": lat, "lon": lon}, index=med.index)
                out.loc[common.index[~inl]] = np.nan                  # 변환과 안 맞는 글자는 버림
                return f"상대좌표정합(n={int(inl.sum())}/{len(common)})", out.dropna(), float(np.median(res[inl]))
    return None, None, best[3] if best else np.inf


# ------------------------------------------------------------------ 노선 중심선(선 도형) 읽기
CL_LAYER = re.compile(r"선형\s*_*\s*중심선|선형중심|ALIGNMENT", re.IGNORECASE)   # 도로중심선 등은 제외


def _parse_geometry(path):
    """DXF 의 BLOCKS·ENTITIES 에서 선 도형(LINE/LWPOLYLINE/POLYLINE/ARC)과 INSERT(블록 배치)를 읽음."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8", "cp949", "latin-1"):
        try:
            txt = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    L = txt.splitlines()
    pairs = [(L[i].strip(), L[i + 1].strip()) for i in range(0, len(L) - 1, 2)]
    blocks, base = {}, {}
    section, blk, cur = None, None, None
    container = lambda: blocks.setdefault(blk, []) if section == "BLOCKS" and blk else blocks.setdefault("*ENT", [])
    def flush():
        nonlocal cur
        if cur is None:
            return
        if cur.get("paper"):
            cur = None; return
        k = cur["kind"]
        if k == "poly" and len(cur["pts"]) >= 2:
            container().append(("poly", cur["layer"], cur["pts"]))
        elif k == "arc" and "r" in cur:
            a0, a1 = math.radians(cur.get("a0", 0)), math.radians(cur.get("a1", 360))
            if a1 <= a0:
                a1 += 2 * math.pi
            ang = np.linspace(a0, a1, 9)
            container().append(("poly", cur["layer"], list(zip(cur["cx"] + cur["r"] * np.cos(ang),
                                                               cur["cy"] + cur["r"] * np.sin(ang)))))
        elif k == "insert" and "name" in cur and "x" in cur:
            container().append(("insert", cur["layer"], cur["name"], cur["x"], cur["y"],
                                cur.get("sx", 1.0), cur.get("sy", cur.get("sx", 1.0)), cur.get("rot", 0.0)))
        cur = None
    px = None
    for code, val in pairs:
        if code == "0":
            if val == "SECTION":
                flush(); section = "pending"; continue
            if val == "ENDSEC":
                flush(); section = None; continue
            if section == "BLOCKS" and val == "BLOCK":
                flush(); blk = "__new__"; continue
            if section == "BLOCKS" and val == "ENDBLK":
                flush(); blk = None; continue
            if val == "VERTEX" and cur and cur["kind"] == "poly" and cur.get("pl"):
                cur["vtx"] = True; continue
            if val == "SEQEND":
                continue
            flush()
            if section in ("BLOCKS", "ENTITIES") and (section == "ENTITIES" or (blk and blk != "__new__")):
                if val in ("LINE", "LWPOLYLINE"):
                    cur = {"kind": "poly", "layer": "", "pts": []}
                elif val == "POLYLINE":
                    cur = {"kind": "poly", "layer": "", "pts": [], "pl": True}
                elif val == "ARC":
                    cur = {"kind": "arc", "layer": ""}
                elif val == "INSERT":
                    cur = {"kind": "insert", "layer": ""}
            continue
        if section == "pending" and code == "2":
            section = val; continue
        if section == "BLOCKS" and blk == "__new__":
            if code == "2":
                blk = val; base[blk] = [0.0, 0.0]
            continue
        if section == "BLOCKS" and blk and cur is None and code in ("10", "20") and blk in base and not blocks.get(blk):
            base[blk][0 if code == "10" else 1] = float(val); continue
        if cur is None:
            continue
        if code == "8" and not cur.get("layer"):
            cur["layer"] = val
        elif code == "67" and val == "1":
            cur["paper"] = True
        elif cur["kind"] == "poly":
            if code in ("10", "11"):
                try: px = float(val)
                except ValueError: px = None
            elif code in ("20", "21") and px is not None:
                if not cur.get("pl") or cur.get("vtx"):
                    cur["pts"].append((px, float(val)))
                px = None
        elif cur["kind"] == "arc":
            f = {"10": "cx", "20": "cy", "40": "r", "50": "a0", "51": "a1"}.get(code)
            if f:
                cur[f] = float(val)
        elif cur["kind"] == "insert":
            f = {"2": "name", "10": "x", "20": "y", "41": "sx", "42": "sy", "50": "rot"}.get(code)
            if f:
                cur[f] = val if f == "name" else float(val)
    flush()
    return blocks, base


def read_dxf_lines(path, layer_re=CL_LAYER, max_depth=4):
    """노선 중심선 레이어의 선 도형 꼭짓점 (블록 안에 들어 있으면 INSERT 의 위치·축척·회전을 적용해 펼침)."""
    blocks, base = _parse_geometry(path)
    has_cl = {}
    def block_has_cl(name, depth=0):
        if name in has_cl:
            return has_cl[name]
        has_cl[name] = False
        if depth > max_depth:
            return False
        for prim in blocks.get(name, []):
            if layer_re.search(prim[1]) or (prim[0] == "insert" and block_has_cl(prim[2], depth + 1)):
                has_cl[name] = True; break
        return has_cl[name]
    out, lid = [], [0]
    fname = Path(path).name
    def emit(pts, layer):
        lid[0] += 1
        for k, (x, y) in enumerate(pts):
            out.append({"file": fname, "layer": layer, "line": f"{fname}#{lid[0]}", "k": k, "x": x, "y": y})
    def walk(name, T, inherited, depth):
        for prim in blocks.get(name, []):
            if prim[0] == "poly":
                if inherited or layer_re.search(prim[1]):
                    P = np.array(prim[2], float)
                    emit(T(P), prim[1] if layer_re.search(prim[1]) else inherited)
            elif depth < max_depth:
                _, lay, bn, ix, iy, sx, sy, rot = prim
                cl_here = layer_re.search(lay)
                if not (cl_here or inherited or block_has_cl(bn)):
                    continue
                bx, by = base.get(bn, [0.0, 0.0]); c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
                def T2(P, T=T, bx=bx, by=by, sx=sx, sy=sy, c=c, s=s, ix=ix, iy=iy):
                    X = (P[:, 0] - bx) * sx; Y = (P[:, 1] - by) * sy
                    return T(np.c_[ix + c * X - s * Y, iy + s * X + c * Y])
                walk(bn, T2, inherited or (lay if cl_here else ""), depth + 1)
    walk("*ENT", lambda P: P, "", 0)
    return pd.DataFrame(out)


def georef_lines(L):
    """파일별로 단위·회전 조합 중 대전 안에 떨어지는 꼭짓점이 가장 많은 것을 골라 위경도로."""
    res = []
    for f, g in L.groupby("file"):
        best = None
        for sname, s in SCALES.items():
            for oname, fn in ORIENT.items():
                E, N = fn(g.x.values * s, g.y.values * s)
                ok = (E > 1.5e5) & (E < 3e5) & (N > 3.5e5) & (N < 5.5e5)
                if ok.sum() < 10:
                    continue
                lat, lon = tm_inverse(E, N, CRS["EPSG:5186"])
                inb = ok & (lat > DJ_BOX[0]) & (lat < DJ_BOX[1]) & (lon > DJ_BOX[2]) & (lon < DJ_BOX[3])
                if best is None or inb.sum() > best[0]:
                    best = (int(inb.sum()), g.assign(lat=lat, lon=lon, transform=f"{sname}·{oname}")[inb])
        if best and best[0] >= 10:
            res.append(best[1])
    if not res:
        return pd.DataFrame()
    r = pd.concat(res, ignore_index=True).sort_values(["line", "k"])
    # 한 도형 안에서 1km 넘게 튀는 곳은 끊음
    parts = []
    for ln, g in r.groupby("line", sort=False):
        x, y = to_local(g.lat.values, g.lon.values)
        jump = np.r_[True, np.hypot(np.diff(x), np.diff(y)) > 1000]
        parts += list(ln + "." + pd.Series(np.cumsum(jump)).astype(str))
    return r.assign(line=parts)


# ------------------------------------------------------------------ 노선 IP(교점) 좌표 → 노선 선형
IP_NUM = re.compile(r"^\s*([1-5][0-9]{5}(?:\.[0-9]+)?)\s*$")


def find_ip_route(texts, crs="EPSG:5186"):
    """'418021.29511' 처럼 숫자만 적힌 북(X)·동(Y) 좌표 쌍(노선 교점 IP 주기)을 찾아 파일별 노선 꺾은선으로.
    도면에 적힌 순서 = 노선 진행 순서로 봄. 3km 넘게 튀면 다른 노선으로 끊음."""
    t = texts[texts.text.astype(str).str.match(IP_NUM)].copy()
    if t.empty:
        return pd.DataFrame()
    t["v"] = t.text.astype(str).str.strip().astype(float)
    t["axis"] = np.where(t.v.between(3.5e5, 5.5e5), "N", np.where(t.v.between(1.5e5, 3.0e5), "E", ""))
    t = t[t.axis != ""]
    rows = []
    for f, g in t.groupby("file", sort=False):
        Ns, Es = g[g.axis == "N"], g[g.axis == "E"]
        if Ns.empty or Es.empty:
            continue
        d = np.hypot(Ns.x.values[:, None] - Es.x.values, Ns.y.values[:, None] - Es.y.values)
        jn, ie = d.argmin(1), d.argmin(0)
        for i, j in enumerate(jn):
            if ie[j] == i:
                rows.append({"file": f, "order": Ns.index[i], "N": Ns.v.values[i], "E": Es.v.values[j]})
    r = pd.DataFrame(rows)
    if r.empty:
        return r
    lat, lon = tm_inverse(r.E.values, r.N.values, CRS[crs])
    r = r.assign(lat=lat, lon=lon)
    r = r[r.lat.between(DJ_BOX[0], DJ_BOX[1]) & r.lon.between(DJ_BOX[2], DJ_BOX[3])].sort_values(["file", "order"])
    seg = []
    for f, g in r.groupby("file", sort=False):
        x, y = to_local(g.lat.values, g.lon.values)
        jump = np.r_[True, np.hypot(np.diff(x), np.diff(y)) > 3000]
        seg += list(f + "#" + pd.Series(np.cumsum(jump)).astype(str))
    return r.assign(line=seg, crs=crs).reset_index(drop=True)


def snap_to_route(lat, lon, route):
    """점 → 노선 꺾은선 위 가장 가까운 점 (위경도, 거리 m)."""
    px, py = to_local(np.atleast_1d(lat), np.atleast_1d(lon))
    best = (np.full(len(px), np.inf), np.zeros(len(px)), np.zeros(len(px)))
    for _, g in route.groupby("line"):
        x, y = to_local(g.lat.values, g.lon.values)
        for k in range(len(x) - 1):
            ax_, ay_, bx, by = x[k], y[k], x[k + 1], y[k + 1]
            dx, dy = bx - ax_, by - ay_
            L2 = dx * dx + dy * dy
            u = np.clip(((px - ax_) * dx + (py - ay_) * dy) / L2, 0, 1) if L2 > 0 else np.zeros(len(px))
            qx, qy = ax_ + u * dx, ay_ + u * dy
            d = np.hypot(px - qx, py - qy)
            better = d < best[0]
            best[0][better], best[1][better], best[2][better] = d[better], qx[better], qy[better]
    la, lo = from_local(best[1], best[2])
    return la, lo, best[0]


# ------------------------------------------------------------------ 실제 측량 위치에 놓인 글자 찾기
def find_geo_texts(texts):
    """파일별로 단위·회전을 바꿔 가며, 변환하면 대전 안에 떨어지는 글자(=실좌표로 배치된 글자)를 찾음.
    파일마다 이런 글자가 가장 많은 변환을 고름."""
    out = []
    for f, g in texts.groupby("file", sort=False):
        best = None
        for sname, s in SCALES.items():
            for oname, fn in ORIENT.items():
                E, N = fn(g.x.values * s, g.y.values * s)
                m = (E > 1.5e5) & (E < 3e5) & (N > 3.5e5) & (N < 5.5e5)
                if m.sum() == 0:
                    continue
                lat, lon = tm_inverse(E[m], N[m], CRS["EPSG:5186"])
                inb = (lat > DJ_BOX[0]) & (lat < DJ_BOX[1]) & (lon > DJ_BOX[2]) & (lon < DJ_BOX[3])
                if best is None or inb.sum() > best[0]:
                    sel = g[m][inb]
                    best = (int(inb.sum()), sel.assign(lat=lat[inb], lon=lon[inb], transform=f"EPSG:5186·{sname}·{oname}"))
        if best and best[0] > 0:
            out.append(best[1])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def stations_from_geo_texts(geo, cand, approx):
    """① 실좌표 글자 중 정거장 이름/번호 글자 → 그 위치
       ② 정거장 하나짜리 배치도(A-xx)인데 이름 글자는 없으면 → 실좌표 글자들의 중심 (도면이 정거장 주변을 그리므로)"""
    if geo.empty:
        return pd.DataFrame()
    ap_xy = approx.set_index("station_no")[["lat", "lon"]]
    rows = []
    named = find_station_texts(geo, approx)
    named = named[named.station_no > 0] if len(named) else named
    for (f, no), g in (named.groupby(["file", "station_no"]) if len(named) else []):
        rows.append({"station_no": no, "lat": g.lat.median(), "lon": g.lon.median(), "file": f,
                     "method": "도면 실좌표 정거장 글자(" + g["transform"].iloc[0] + ")", "n": len(g)})
    done = {(r["file"], r["station_no"]) for r in rows}
    for f, g in geo.groupby("file"):
        nos = cand[cand.file == f].station_no.unique() if len(cand) else []
        if len(nos) != 1 or (f, nos[0]) in done or len(g) < 5:
            continue
        x, y = to_local(g.lat.values, g.lon.values)
        cx, cy = np.median(x), np.median(y)
        spread = float(np.median(np.hypot(x - cx, y - cy)))
        if spread > 600:                      # 글자가 넓게 흩어져 있으면 중심이 정거장이라고 보기 어려움
            continue
        la, lo = from_local(cx, cy)
        rows.append({"station_no": int(nos[0]), "lat": float(la), "lon": float(lo), "file": f,
                     "method": f"도면 실좌표 범위 중심({g["transform"].iloc[0]}, 글자 {len(g)}개)", "n": len(g)})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf", nargs="+")
    ap.add_argument("--max-move", type=float, default=1000, help="기존 추정 위치에서 이보다 멀면 채택 안 함(m)")
    ap.add_argument("--snap-max", type=float, default=700, help="노선 선형에서 이보다 먼 추정 정거장은 보정 안 함(m)")
    a = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)

    approx = pd.read_csv(APPROX)
    ap_xy = approx.set_index("station_no")[["lat", "lon"]]

    frames = []
    for p in a.dxf:
        try:
            frames.append(read_dxf_texts(p))
        except Exception as e:
            print(f"  {Path(p).name}: 읽기 실패 ({e})")
    texts = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    print(f"글자 {len(texts)}개 읽음 ({len(a.dxf)}개 파일)")
    if texts.empty:
        return
    # 진단용: 파일별 좌표 범위 (한국 TM 이면 X≈20만대, Y≈40만대(GRS80) 또는 30만대(Bessel))
    ext = texts.groupby("file").agg(n=("x", "size"), x_min=("x", "min"), x_max=("x", "max"),
                                    y_min=("y", "min"), y_max=("y", "max")).round(1)
    ext.to_csv(OUT_DIR / "station_dxf_extents.csv", encoding="utf-8-sig")
    texts.sample(min(1000, len(texts)), random_state=0).to_csv(OUT_DIR / "station_dxf_texts_sample.csv",
                                                               index=False, encoding="utf-8-sig")
    print(ext.to_string())

    # 진단용: 측량 좌표처럼 보이는 6자리 숫자가 든 글자 (X=… 형식이 아닐 때 규칙을 맞추기 위함)
    num = texts[texts.text.astype(str).str.contains(r"[1-5][0-9]{2},?[0-9]{3}\.[0-9]", regex=True)]
    num.head(2000).to_csv(OUT_DIR / "station_dxf_numbers_sample.csv", index=False, encoding="utf-8-sig")
    print(f"측량 좌표처럼 보이는 숫자 글자 {len(num)}개 → outputs/station_dxf_numbers_sample.csv")

    cand = find_station_texts(texts, approx)
    if cand.empty:
        cand = pd.DataFrame(columns=["station_no", "file", "x", "y", "match", "name_in_drawing"])
    unk = cand[cand.station_no < 0]
    if len(unk):
        print("\n목록에 없는 정거장 이름(설계 단계 이름일 수 있음):", sorted(unk.name_in_drawing.unique()))
    cand = cand[cand.station_no > 0]

    # ★ 측량 좌표 주기(X=, Y=)가 있으면 그것이 가장 정확 → 같은 도면 시트(가장 가까운 정거장 제목)에 배정
    labels = find_coord_labels(texts)
    coord_sols = []
    if len(labels):
        for code in ("EPSG:5186", "EPSG:5174"):
            lat, lon = tm_inverse(labels.E.values, labels.N.values, CRS[code])
            ok = (lat > DJ_BOX[0]) & (lat < DJ_BOX[1]) & (lon > DJ_BOX[2]) & (lon < DJ_BOX[3])
            if ok.mean() > 0.5:
                labels = labels.assign(lat=lat, lon=lon, crs=code)[ok]
                break
        labels.to_csv(OUT_DIR / "station_dxf_coords.csv", index=False, encoding="utf-8-sig")
        print(f"\n측량 좌표 주기 {len(labels)}개 발견 → outputs/station_dxf_coords.csv")
        if "lat" in labels and len(cand):
            for f, L in labels.groupby("file"):
                C_ = cand[cand.file == f]
                if C_.empty:
                    continue
                # 각 좌표 주기 → 도면상 가장 가까운 정거장 글자
                d = np.hypot(L.x.values[:, None] - C_.x.values, L.y.values[:, None] - C_.y.values)
                L = L.assign(station_no=C_.station_no.values[d.argmin(1)])
                L = L.join(ap_xy, on="station_no", rsuffix="_ap")
                L["dist"] = np.hypot((L.lat - L.lat_ap) * KY, (L.lon - L.lon_ap) * KX)
                g = L[L.dist <= 1500].groupby("station_no")[["lat", "lon"]].median()
                if len(g):
                    coord_sols.append(g.assign(method="측량좌표주기(" + L.crs.iloc[0] + ")", file=f,
                                               n=L[L.dist <= 1500].groupby("station_no").size()))
                    print(f"  {f}: 측량 좌표로 정거장 {len(g)}개 위치 확인")
    cand.to_csv(OUT_DIR / "station_dxf_candidates.csv", index=False, encoding="utf-8-sig")
    if cand.empty:
        print("\n정거장 번호/이름 글자를 찾지 못했습니다 → tram_stations.csv 를 만들지 않았습니다.")
        print("outputs/station_dxf_texts_sample.csv, station_dxf_extents.csv 를 보내 주세요.")
        return

    # 파일별로 좌표 맞추기 (도면마다 좌표계가 다를 수 있음)
    sols = list(coord_sols)
    done_files = {s.file.iloc[0] for s in coord_sols}
    for f, c in cand.groupby("file"):
        if f in done_files:
            continue
        method, ll, err = solve_file(c, ap_xy)
        print(f"  {f}: 정거장 후보 {c.station_no.nunique()}개 → "
              f"{method + f' (기존 위치와 차이 중앙값 {err:.0f}m)' if method else f'좌표 맞추기 실패 (최소 차이 {err:.0f}m)'}")
        if method:
            sols.append(ll.assign(method=method, file=f, n=c.groupby('station_no').size()))
    # 실제 측량 위치에 놓인 글자 (A 배치도처럼 제목란은 원점, 도면 내용은 실좌표인 경우)
    geo = find_geo_texts(texts)
    if len(geo):
        geo.to_csv(OUT_DIR / "station_dxf_geotexts.csv", index=False, encoding="utf-8-sig")
        print("\n실제 측량 위치에 놓인 글자:", geo.groupby("file").size().to_dict(), "→ outputs/station_dxf_geotexts.csv")
        gs = stations_from_geo_texts(geo, cand, approx)
        if len(gs):
            have = set(pd.concat(sols).index) if sols else set()
            for _, r in gs.iterrows():
                if r.station_no not in have:
                    sols.append(pd.DataFrame({"lat": [r.lat], "lon": [r.lon], "method": [r.method], "file": [r.file],
                                              "n": [r.n]}, index=pd.Index([r.station_no], name="station_no")))
                    print(f"  {r.file}: {r.station_no}번 ← {r.method}")

    # 노선 IP 좌표 (도면에 숫자로 적힌 교점 좌표)
    route = find_ip_route(texts)
    if len(route):
        route.to_csv(OUT_DIR / "tram_route_ip.csv", index=False, encoding="utf-8-sig")
        print(f"\n노선 교점(IP) 좌표 {len(route)}개, 선형 {route.line.nunique()}개 → outputs/tram_route_ip.csv")
    # 노선 중심선 도형 (레이어 이름에 '중심선/선형' 등) → 실좌표로 그려져 있으면 노선으로 사용
    cl = []
    for pth in a.dxf:
        try:
            cl.append(read_dxf_lines(pth))
        except Exception as e:
            print(f"  {Path(pth).name}: 중심선 읽기 실패 ({e})")
    cl = pd.concat(cl, ignore_index=True) if cl else pd.DataFrame()
    if len(cl):
        print("\n중심선으로 보이는 도형 꼭짓점:", cl.groupby("file").size().to_dict(),
              "| 레이어:", sorted(cl.layer.unique())[:15])
        clg = georef_lines(cl)
        if len(clg):
            clg.to_csv(OUT_DIR / "tram_route_centerline.csv", index=False, encoding="utf-8-sig")
            print("  실좌표로 확인된 중심선:", clg.groupby("file").agg(n=("k", "size"), 변환=("transform", "first")).to_dict("index"),
                  "→ outputs/tram_route_centerline.csv")
            route = pd.concat([route, clg[["file", "line", "lat", "lon"]]], ignore_index=True) if len(route) else clg
        else:
            print("  중심선이 실좌표로 그려져 있지 않음. 파일별 좌표 범위:")
            print(cl.groupby("file").agg(n=("x", "size"), x_min=("x", "min"), x_max=("x", "max"),
                                         y_min=("y", "min"), y_max=("y", "max")).round(0).to_string())

    if sols:
        S = pd.concat(sols).reset_index()
        S = S.groupby("station_no").agg(lat=("lat", "median"), lon=("lon", "median"),
                                        method=("method", "first"), files=("file", lambda v: ";".join(sorted(set(v)))))
    else:
        S = pd.DataFrame(columns=["lat", "lon", "method", "files"], index=pd.Index([], name="station_no"))

    rep = approx[["station_no", "station_name", "lat", "lon"]].merge(S.reset_index(), on="station_no", how="left",
                                                                     suffixes=("_approx", ""))
    rep["lat"] = rep.lat.astype(float); rep["lon"] = rep.lon.astype(float)
    rep["moved_m"] = np.hypot((rep.lat - rep.lat_approx) * KY, (rep.lon - rep.lon_approx) * KX).round(0)
    inbox = rep.lat.between(DJ_BOX[0], DJ_BOX[1]) & rep.lon.between(DJ_BOX[2], DJ_BOX[3])
    ok = rep.lat.notna() & inbox & (rep.moved_m <= a.max_move)
    rep["status"] = np.select([ok, rep.lat.notna()], ["채택(도면 정거장 위치)", f"제외(대전 밖 또는 {a.max_move:.0f}m 초과)"], "도면에 없음")

    # 정거장 위치를 못 찾은 정거장 → 노선 IP 선형 위 가장 가까운 점으로 보정 (노선을 가로지르는 방향 오차 제거)
    rep["snap_m"] = np.nan
    if len(route):
        la, lo, dist = snap_to_route(rep.lat_approx.values, rep.lon_approx.values, route)
        rep["snap_m"] = dist.round(0)
        snap = (~ok) & (dist <= a.snap_max)
        rep.loc[snap, "lat"] = la[snap]; rep.loc[snap, "lon"] = lo[snap]
        rep.loc[snap, "method"] = "노선IP선형 보정"
        rep.loc[snap, "status"] = "노선 위로 보정"
        rep.loc[snap, "moved_m"] = rep.loc[snap, "snap_m"]
        ok = ok | snap
    rep.to_csv(OUT_DIR / "station_dxf_report.csv", index=False, encoding="utf-8-sig")
    print("\n" + rep[["station_no", "station_name", "method", "moved_m", "snap_m", "status"]].to_string(index=False))

    if ok.sum() == 0:
        print("\n채택·보정된 정거장이 없습니다 → tram_stations.csv 를 만들지 않았습니다 (기존 추정 좌표 유지).")
        if OUT_ST.exists():
            print(f"  (이전에 만든 {OUT_ST.name} 은 그대로 있으니 잘못된 값이면 지우세요)")
        return
    final = rep.copy()
    final["coord_source"] = np.where(ok, "설계도면(" + final.method.fillna("") + ")", "추정(기존)")
    final["lat"] = np.where(ok, final.lat, final.lat_approx).round(6)
    final["lon"] = np.where(ok, final.lon, final.lon_approx).round(6)
    final[["station_no", "station_name", "lat", "lon", "coord_source"]].to_csv(OUT_ST, index=False, encoding="utf-8-sig")
    print(f"\n도면 위치 {int((rep.status == '채택(도면 정거장 위치)').sum())}개 + 노선 보정 "
          f"{int((rep.status == '노선 위로 보정').sum())}개 → {OUT_ST}")
    print("다음: build_dataset.py → build_areas.py → train_analyze.py → make_map_data.py 다시 실행")


if __name__ == "__main__":
    main()
