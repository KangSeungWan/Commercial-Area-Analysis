"""관광지·관문 좌표를 '저장해도 되는 공공데이터'로 다시 잡기 (2026-10-28)

왜: 기존 좌표는 카카오 로컬 API 결과였는데, 카카오는 좌표·주소를 저장해 쓰는 것을 허용하지 않음
    (카카오 데브톡 공식 답변 2026-09-04, 2026-10-19·20). → 카카오 결과는 버리고 아래 공공데이터로만 다시 계산.

방법 (주소 → 좌표, 인터넷 없이)
  1) 지번 주소  → 법정동코드(국토부 개별공시지가 속성 AL_D151) + 산/본번/부번 = 필지 고유번호(PNU)
                → 필지 중심점(국토부 개별공시지가 공간정보 AL_D150 → outputs/landprice_parcels.csv.gz)
  2) 도로명 주소 → 소상공인시장진흥공단 상가(상권)정보 2026-06 에서 같은 '구+도로명+건물번호' 점포들의 좌표 중앙값
                  (없으면 같은 건물의 지번코드 → 필지 중심점, 그래도 없으면 같은 도로의 가장 가까운 건물번호)
  3) 길·구역만 있는 곳(수향길, 공원) → 그 길 점포 좌표 중앙값 / 그 동의 '공원' 지목 필지 중심
  주소가 없던 곳은 data/tourism_poi_address_fix.csv 에 공식 관광정보(한국관광공사 관광정보 기반 페이지)에서 찾은 주소와 출처를 적어 둠.

검증: ① 좌표가 주소의 구 안에 있는지(행정동 경계) ② OpenStreetMap 좌표(tourism_poi_osm.csv)와 거리 — 500m 넘으면 표시
출력: data/tourism_poi.csv 의 lat·lon 교체(카카오 열 삭제) + data/tourism_poi_coords_check.csv (방법·출처·검증)
실행: python tram_model/geocode_tourism_public.py
"""
import gzip
import json
import math
import re
import sys

import numpy as np
import pandas as pd
from matplotlib.path import Path as MPath

from config import ROOT

DATA = ROOT / "data"
RAW = DATA / "raw"
GU = ["동구", "중구", "서구", "유성구", "대덕구"]


def read_csv_any(p, **kw):
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(p, encoding=enc, **kw)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(p)


def dist_m(a, b, c, d):
    k = math.pi / 180
    x = (d - b) * k * math.cos((a + c) / 2 * k)
    y = (c - a) * k
    return 6371000 * math.hypot(x, y)


def norm_addr(s):
    s = str(s or "").strip()
    s = s.replace("대전시 ", "대전광역시 ").replace("대전 ", "대전광역시 ", 1) if not s.startswith("대전광역시") else s
    s = re.sub(r"\(.*?\)", " ", s)                          # (송촌동) 같은 괄호
    s = re.sub(r"(\d+)\s+(번(?:안)?길)", r"\1\2", s)          # '480 번길' → '480번길'
    s = re.sub(r"(로|길)(\d+번(?:안)?길)", r"\1\2", s)
    s = re.sub(r"(로|길)\s+(\d+번(?:안)?길)", r"\1\2", s)     # '자운로 245번길' → '자운로245번길'
    s = re.sub(r"(로|길)(\d+)$", r"\1 \2", s)                 # '현충원로251' → '현충원로 251'
    s = re.sub(r"(로|길)(\d+)(\s)", r"\1 \2\3", s)
    return re.sub(r"\s+", " ", s).strip()


ROAD_RE = re.compile(r"(동구|중구|서구|유성구|대덕구)\s+(\S+?(?:로|길))\s*(\d+)(?:-(\d+))?(?:\s|$)")
JIBUN_RE = re.compile(r"(동구|중구|서구|유성구|대덕구)\s+(\S+?(?:동|가|리))\s+(산\s*)?(\d+)(?:-(\d+))?(?:\s|$)")
ROADONLY_RE = re.compile(r"(동구|중구|서구|유성구|대덕구)\s+(?:\S+동\s+)?(\S+?(?:로|길))\s*$")


def main():
    poi = pd.read_csv(DATA / "tourism_poi.csv", dtype=str, keep_default_na=False)
    fix = pd.read_csv(DATA / "tourism_poi_address_fix.csv", dtype=str, keep_default_na=False)
    fixm = {r.poi_id: r for r in fix.itertuples()}

    # ── 필지: 법정동명 → 코드, PNU → 중심점 ──
    d151 = read_csv_any(RAW / "공시지가" / "AL_D151_30_20260526.csv", usecols=["법정동코드", "법정동명"], dtype=str).drop_duplicates()
    bjd = {}
    for r in d151.itertuples():
        parts = r.법정동명.split()
        if len(parts) >= 3:
            bjd[(parts[1], parts[2])] = r.법정동코드
    with gzip.open(ROOT / "outputs" / "landprice_parcels.csv.gz", "rt", encoding="utf-8-sig") as g:
        par = pd.read_csv(g, usecols=["pnu", "lat", "lon", "jimok", "dong_code"], dtype={"pnu": str, "dong_code": str})
    par = par.dropna(subset=["lat", "lon"])
    pnu_xy = dict(zip(par.pnu, zip(par.lat, par.lon)))

    # ── 상가정보: 도로명+건물번호 → 점포 좌표 ──
    sg = read_csv_any(RAW / "소상공인시장진흥공단_상가_상권_정보_대전_202606.csv",
                      usecols=["시군구명", "도로명", "건물본번지", "건물부번지", "지번코드", "경도", "위도"], dtype=str)
    sg["road"] = sg["도로명"].str.split().str[-1]
    sg["b1"] = pd.to_numeric(sg["건물본번지"], errors="coerce")
    sg["b2"] = pd.to_numeric(sg["건물부번지"], errors="coerce").fillna(0)
    sg["lat"] = pd.to_numeric(sg["위도"], errors="coerce")
    sg["lon"] = pd.to_numeric(sg["경도"], errors="coerce")
    sg = sg.dropna(subset=["b1", "lat", "lon"])

    def by_road(gu, road, b1, b2):
        s = sg[(sg["시군구명"] == gu) & (sg["road"] == road)]
        if s.empty:
            m = re.match(r"(.+?(?:로|길))(\d+)번(?:안)?길$", road)   # 'OO로229번길' 점포가 없으면 갈라지는 곳(OO로 229)으로
            if m:
                r2 = by_road(gu, m.group(1), int(m.group(2)), 0)
                if r2:
                    return r2[0], r2[1], r2[2] + f" — {road} 시작점(건물 {b1}번까지 약 {b1 * 10}m 오차 가능)"
            return None
        e = s[(s.b1 == b1) & (s.b2 == b2)]
        if len(e):
            return float(e.lat.median()), float(e.lon.median()), f"상가정보 같은 건물 점포 {len(e)}곳 중앙값"
        e = s[s.b1 == b1]
        if len(e):
            return float(e.lat.median()), float(e.lon.median()), f"상가정보 같은 본번 건물 점포 {len(e)}곳 중앙값"
        # 같은 도로에 그 번호 건물 점포가 없으면: 도로명 건물번호는 도로 시작점에서의 거리(약 10m 단위)라서
        # 같은 쪽(홀짝) 앞뒤 번호 점포 위치로 선형 보간. 한쪽만 있으면 가장 가까운 두 번호로 외삽(500m 넘으면 표시)
        # 홀짝(길 양쪽)은 무시: 길 건너편은 10~20m 차이뿐이고, 한쪽만 보면 먼 번호로 외삽하게 됨
        pts = s.groupby("b1")[["lat", "lon"]].median().sort_index()
        lo_ = pts[pts.index < b1]; hi_ = pts[pts.index > b1]
        if len(lo_) and len(hi_):
            n1, n2 = lo_.index[-1], hi_.index[0]
        elif len(pts) >= 2:
            near2 = pts.index[np.argsort(np.abs(pts.index - b1))[:2]]
            n1, n2 = sorted(near2)
        else:
            n = pts.index[0]
            return float(pts.loc[n, "lat"]), float(pts.loc[n, "lon"]), f"상가정보 같은 도로 유일한 번호 {int(n)} (요청 {b1})"
        t = (b1 - n1) / (n2 - n1)
        la = pts.loc[n1, "lat"] + t * (pts.loc[n2, "lat"] - pts.loc[n1, "lat"])
        lo = pts.loc[n1, "lon"] + t * (pts.loc[n2, "lon"] - pts.loc[n1, "lon"])
        kind = "보간" if 0 <= t <= 1 else f"외삽 {abs(b1 - (n1 if t < 0 else n2)) * 10}m"
        return float(la), float(lo), f"상가정보 같은 도로 건물번호 {int(n1)}·{int(n2)} 사이 {kind} (요청 {b1})"

    def by_jibun(gu, dong, san, b1, b2):
        code = bjd.get((gu, dong))
        if not code:
            return None
        base = f"{code}{2 if san else 1}{b1:04d}"
        p = base + f"{b2:04d}"
        if p in pnu_xy:
            la, lo = pnu_xy[p]
            return la, lo, f"필지 {p} 중심점"
        cand = [k for k in pnu_xy if k.startswith(base)]
        if cand:
            la = np.median([pnu_xy[k][0] for k in cand]); lo = np.median([pnu_xy[k][1] for k in cand])
            return float(la), float(lo), f"같은 본번 필지 {len(cand)}개 중심 (부번 {b2} 없음)"
        return None

    def by_road_only(gu, road):
        s = sg[(sg["시군구명"] == gu) & (sg["road"] == road)]
        if len(s):
            return float(s.lat.median()), float(s.lon.median()), f"상가정보 {road} 점포 {len(s)}곳 중앙값"
        return None

    def by_park(gu, dong):
        code = bjd.get((gu, dong))
        if not code:
            return None
        s = par[(par.pnu.str[:10] == code) & (par.jimok.astype(str) == "공")]
        if len(s):
            # 동 안 작은 어린이공원들을 빼려고 '공원 필지가 가장 몰린 곳'(반경 300m 안 공원 필지 수 최대)의 주변 중앙값
            la, lo = s.lat.values, s.lon.values
            cnt = [int(((la - a) ** 2 * 1.23e10 + ((lo - b) * math.cos(math.radians(a))) ** 2 * 1.23e10 < 300 ** 2).sum()) for a, b in zip(la, lo)]
            i = int(np.argmax(cnt)); a, b = la[i], lo[i]
            m = ((la - a) ** 2 * 1.23e10 + ((lo - b) * math.cos(math.radians(a))) ** 2 * 1.23e10) < 300 ** 2
            return float(np.median(la[m])), float(np.median(lo[m])), f"{dong} 공원 지목 필지가 가장 몰린 곳 {int(m.sum())}개 중앙"
        return None

    # ── 행정동 경계 (구 확인용) ──
    gj = json.load(open(DATA / "daejeon_dong_2023.geojson", encoding="utf-8"))
    polys = []
    for f in gj["features"]:
        pr = f["properties"]
        name = " ".join(str(v) for v in pr.values())
        gu = next((g for g in GU if g in name), None)
        geom = f["geometry"]
        rings = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
        for ring in rings:
            polys.append((gu, MPath(np.array(ring)[:, :2])))

    def gu_of(lat, lon):
        for gu, pth in polys:
            if pth.contains_point((lon, lat)):
                return gu
        return None

    osm = pd.read_csv(DATA / "tourism_poi_osm.csv", dtype=str, keep_default_na=False)
    osm_xy = {r.poi_id: (float(r.lat), float(r.lon)) for r in osm.itertuples() if r.lat and r.lon}

    out, rows = [], []
    for r in poi.itertuples():
        f = fixm.get(r.poi_id)
        addr = f.address if f is not None and f.address else r.address
        mode = f.mode if f is not None else ""
        src_note = f.source if f is not None else "원래 목록 주소"
        a = norm_addr(addr)
        res = None
        if mode == "osm":   # 주소 번지까지 맞은 OpenStreetMap 좌표 (ODbL, 저장·재사용 허용 — 출처 표시)
            o = osm_xy.get(r.poi_id)
            res = (o[0], o[1], "OpenStreetMap(ODbL) 번지까지 일치") if o else None
        elif mode == "park":
            m = re.search(r"(동구|중구|서구|유성구|대덕구)\s+(\S+동)", a)
            res = by_park(m.group(1), m.group(2)) if m else None
        elif mode == "roadonly":
            m = ROADONLY_RE.search(a)
            res = by_road_only(m.group(1), m.group(2)) if m else None
        if res is None:
            m = JIBUN_RE.search(a)
            if m and not re.search(r"(로|길)$", m.group(2)):
                res = by_jibun(m.group(1), m.group(2), bool(m.group(3)), int(m.group(4)), int(m.group(5) or 0))
        if res is None:
            m = ROAD_RE.search(a)
            if m:
                res = by_road(m.group(1), m.group(2), int(m.group(3)), int(m.group(4) or 0))
        if res is None and (r.use_in_tourism == "1" or r.gateway == "1"):
            print("좌표 못 찾음:", r.poi_id, r.name, "|", a, file=sys.stderr)
        lat, lon, how = res if res else (None, None, "")
        want_gu = next((g for g in GU if g in a), None)
        got_gu = gu_of(lat, lon) if lat else None
        o = osm_xy.get(r.poi_id)
        gap = round(dist_m(lat, lon, o[0], o[1])) if (lat and o) else None
        rows.append(dict(poi_id=r.poi_id, name=r.name, address_used=a, address_source=src_note, method=how,
                         lat=lat, lon=lon, gu_addr=want_gu, gu_point=got_gu, gu_ok=(want_gu == got_gu) if lat else None,
                         osm_gap_m=gap, check=("확인" if (lat and ((want_gu and got_gu != want_gu) or (gap and gap > 500) or "외삽" in how)) else "")))
        out.append((lat, lon, how))

    chk = pd.DataFrame(rows)
    chk.to_csv(DATA / "tourism_poi_coords_check.csv", index=False, encoding="utf-8-sig")
    poi["lat"] = [f"{x[0]:.6f}" if x[0] else "" for x in out]
    poi["lon"] = [f"{x[1]:.6f}" if x[1] else "" for x in out]
    poi["geo_level"] = [x[2] for x in out]
    poi["coord_source"] = [("OpenStreetMap(ODbL)" if "OpenStreetMap" in x[2] else "상가정보·개별공시지가 공간정보(공공데이터)") if x[0] else "" for x in out]
    drop = [c for c in poi.columns if c.startswith("kakao_") or c in ("geo_query",)]
    poi = poi.drop(columns=drop)
    poi.to_csv(DATA / "tourism_poi.csv", index=False, encoding="utf-8-sig")
    used = chk[chk.poi_id.isin(poi[(poi.use_in_tourism == "1") | (poi.gateway == "1")].poi_id)]
    print(f"좌표 {chk.lat.notna().sum()}/{len(chk)} · 공개 대상 {used.lat.notna().sum()}/{len(used)} · 확인 필요 {int((used.check == '확인').sum())}")
    print(used[used.check == "확인"][["poi_id", "name", "method", "gu_addr", "gu_point", "osm_gap_m"]].to_string())


if __name__ == "__main__":
    main()
