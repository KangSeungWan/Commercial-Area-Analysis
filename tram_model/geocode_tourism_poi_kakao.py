"""대전 관광지 좌표 붙이기 — 카카오 로컬 API (건물·시설 단위). 맥에서 실행.

OpenStreetMap 결과(geocode_tourism_poi.py)는 절반이 도로 중심에 찍혀 정거장 500m 판정에 못 씀 → 카카오로 다시 찾음.

입력  data/tourism_poi_input.csv            (103곳)
      data/tourism_poi.csv (있으면)          OSM 결과 → 처음 한 번 data/tourism_poi_osm.csv 로 보관, 비교용
출력  data/tourism_poi.csv                  최종 좌표 (관광호텔·선형은 '제외')
키    .streamlit/secrets.toml 의 KAKAO_REST_KEY (또는 환경변수). 키는 화면·파일에 남기지 않음
캐시  data/raw/tourism/kakao_cache.json      (질문 → 응답, 키 없음). 다시 돌리면 묻지 않음

찾는 순서: ① 짧은 이름 키워드 검색(대전 범위, 주소의 구와 같은 결과만) → ② 주소 검색 → ③ 이름만(구 불일치 표시)
실행: python tram_model/geocode_tourism_poi_kakao.py      (1분 안쪽)
"""
import json, math, os, re, sys, time, tomllib
from pathlib import Path

import pandas as pd
import requests

from geocode_tourism_poi import (DATA, INP, OUT, LINEAR, clean_addr, short_name, load_dongs, which_dong)

ROOT = DATA.parent.parent
OSM_COPY = DATA / "tourism_poi_osm.csv"
CACHE = DATA / "raw" / "tourism" / "kakao_cache.json"
KW_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
AD_URL = "https://dapi.kakao.com/v2/local/search/address.json"
RECT = "127.24,36.18,127.56,36.50"                    # 대전 범위 (왼쪽 아래 경도,위도, 오른쪽 위 경도,위도)
EXCLUDE_CAT = {"관광호텔"}                            # 관광지가 아님 (2026-10-25 결정)
# 카카오 상호명에 맞춘 검색어 (OSM 용 SHORT 와 다른 것만)
KAKAO_NAME = {
    "대전 아쿠아리움": "대전아쿠아리움",
    "계룡스파텔 대온천탕": "계룡스파텔",
    "꿈돌이랜드": "꿈돌이랜드",
    "대청호 자연생태관": "대청호자연생태관",
    "만인산 자연휴양림": "만인산자연휴양림",
    "보문산 보운대와 대동하늘공원": "대동하늘공원",
}


# 1차 실행(2026-10-25) 결과를 눈으로 대조해 고친 곳
#   addr  = 키워드 결과가 다른 기관이라 주소로 찾음
#   osm   = 카카오에 없음(폐업 등) → OSM 시설 단위 결과 사용
#   same  = 같은 장소의 다른 이름 → 그 poi 좌표를 그대로 씀 (note 에 이유)
OVERRIDE = {
    "한국원자력연구원(KAERI)": ("addr", "대전광역시 유성구 대덕대로989번길 111", "키워드가 한국수력원자력 중앙연구원으로 잘못 잡힘"),
    "유성유스호스텔": ("osm", None, "카카오는 중구 숙소로 잘못 잡힘, 2022년 이후 입장객 없음(폐업 추정)"),
    "장동삼림욕장": ("same", "계족산 황톳길", "계족산 황톳길 출발점(장동 산림욕장)과 같은 곳"),
    "로하스가족공원 캠핑장": ("same", "금강로하스 에코파크", "금강 로하스 공원 안 캠핑장, 공원 좌표로 근사"),
    "꿈돌이랜드": ("same", "엑스포과학공원과 세계엑스포 기념품박물관", "2012년 폐장, 엑스포과학공원 안에 있던 시설"),
}
# 관광 성격 표시 (제외하지 않고 표시만, 2단계에서 쓸지 결정)
def tour_type(name, category):
    if re.search(r"연구원|연구소|KAIST|카이스트", name) and category == "과학명소":
        return "견학형(일반 개방 제한)"
    if name in {"남선공원종합체육관"}:
        return "생활체육"
    return "관광지"


def get_key():
    k = os.environ.get("KAKAO_REST_KEY")
    if not k:
        p = ROOT / ".streamlit" / "secrets.toml"
        if p.exists():
            k = tomllib.loads(p.read_text(encoding="utf-8")).get("KAKAO_REST_KEY")
    if not k:
        sys.exit("KAKAO_REST_KEY 가 없습니다. .streamlit/secrets.toml 에 KAKAO_REST_KEY = \"키\" 한 줄을 넣으세요.")
    return k.strip()


def call(url, params, key, cache):
    ck = url.rsplit("/", 1)[1] + "|" + json.dumps(params, ensure_ascii=False, sort_keys=True)
    if ck in cache:
        return cache[ck]
    time.sleep(0.15)
    r = requests.get(url, params=params, headers={"Authorization": f"KakaoAK {key}"}, timeout=15)
    if r.status_code in (401, 403):
        sys.exit(f"카카오 API 거절({r.status_code}): 키가 맞는지, 앱 설정에서 '카카오맵' 사용이 켜져 있는지 확인하세요. "
                 f"응답: {r.text[:120]}")
    r.raise_for_status()
    docs = r.json().get("documents", [])
    cache[ck] = docs
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return docs


def norm(s):
    return re.sub(r"[\s\(\)·ㆍ,\-]", "", str(s))


def dist_m(a, b):
    (la1, lo1), (la2, lo2) = a, b
    return math.hypot((lo1 - lo2) * 111320 * math.cos(math.radians(36.35)), (la1 - la2) * 110940)


def main():
    key = get_key()
    P = pd.read_csv(INP, encoding="utf-8-sig", keep_default_na=False)
    if OUT.exists() and not OSM_COPY.exists():                     # 처음 한 번: OSM 결과 보관
        OUT.replace(OSM_COPY)
    osm = pd.read_csv(OSM_COPY, encoding="utf-8-sig", keep_default_na=False).set_index("poi_id") if OSM_COPY.exists() else None
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    dongs = load_dongs()
    rows = []
    for i, r in P.iterrows():
        rec = dict(r)
        rec.update(lat="", lon="", geo_level="", geo_query="", kakao_name="", kakao_addr="", kakao_cat="",
                   dong="", dong_gu="", status="", osm_gap_m="", note="", tour_type="")
        if r["category"] in EXCLUDE_CAT:
            rec["status"] = "제외(호텔)"; rows.append(rec); continue
        if r["name"] in LINEAR:
            rec["status"] = "제외(선형)"; rows.append(rec); continue
        sn = KAKAO_NAME.get(r["name"], short_name(r["name"]))
        want_gu = r["gu"]
        hit = fallback = None
        ov = OVERRIDE.get(r["name"])
        rec["note"] = ov[2] if ov else ""
        rec["tour_type"] = tour_type(r["name"], r["category"])
        if ov and ov[0] == "same":                        # 나중에 같은 장소 좌표를 복사 (아래 마무리 단계)
            rec["status"] = "같은 장소:" + ov[1]; rows.append(rec); continue
        if ov and ov[0] == "osm":
            o = osm[osm["name"] == r["name"]].iloc[0] if osm is not None and (osm["name"] == r["name"]).any() else None
            if o is not None and str(o["lat"]):
                lat, lon = float(o["lat"]), float(o["lon"])
                gu, dong = which_dong(lon, lat, dongs)
                rec.update(lat=round(lat, 6), lon=round(lon, 6), geo_level="OSM", geo_query=o["geo_query"],
                           dong=dong, dong_gu=gu, status="ok" if gu == want_gu else "구 불일치")
            else:
                rec["status"] = "못 찾음"
            rows.append(rec); continue
        kw_docs = [] if (ov and ov[0] == "addr") else call(KW_URL, {"query": sn, "rect": RECT, "size": 5}, key, cache)
        # ① 이름 키워드 (대전 범위)
        for d in kw_docs:
            addr = d.get("road_address_name") or d.get("address_name", "")
            item = ("이름", sn, d.get("place_name", ""), addr, d.get("category_name", ""), float(d["y"]), float(d["x"]))
            if "대전" not in addr:
                continue
            if not want_gu or f" {want_gu} " in f" {addr} ":
                hit = item; break
            fallback = fallback or item
        # ② 주소
        if not hit and (r["address"] or (ov and ov[0] == "addr")):
            q = ov[1] if (ov and ov[0] == "addr") else clean_addr(r["address"])
            docs = call(AD_URL, {"query": q}, key, cache)
            if docs:
                d = docs[0]
                hit = ("주소", q, "", d.get("address_name", ""), d.get("address_type", ""), float(d["y"]), float(d["x"]))
        hit = hit or fallback
        if hit:
            level, q, pname, addr, cat, lat, lon = hit
            gu, dong = which_dong(lon, lat, dongs)
            rec.update(lat=round(lat, 6), lon=round(lon, 6), geo_level=level, geo_query=q, kakao_name=pname,
                       kakao_addr=addr, kakao_cat=cat[:40], dong=dong, dong_gu=gu,
                       status="대전 밖" if not dong else ("ok" if (not want_gu or want_gu == gu) else "구 불일치"))
            if osm is not None and r["poi_id"] in osm.index and str(osm.loc[r["poi_id"], "lat"]):
                o = osm.loc[r["poi_id"]]
                rec["osm_gap_m"] = round(dist_m((lat, lon), (float(o["lat"]), float(o["lon"]))))
        else:
            rec["status"] = "못 찾음"
        rows.append(rec)
        print(f"[{i + 1}/{len(P)}] {r['name'][:22]:<22} {rec['status']:<6} {rec['geo_level']:<3} "
              f"{rec['kakao_name'][:18]:<18} {rec['dong_gu']} {rec['dong']}")
    R = pd.DataFrame(rows)
    for i in R.index[R.status.str.startswith("같은 장소:")]:     # 같은 장소 좌표 복사
        src = R[R["name"] == R.at[i, "status"].split(":", 1)[1]]
        if len(src) and str(src.iloc[0]["lat"]):
            s = src.iloc[0]
            for c in ["lat", "lon", "dong", "dong_gu", "kakao_name", "kakao_addr"]:
                R.at[i, c] = s[c]
            R.at[i, "geo_level"] = "같은 장소"
            R.at[i, "status"] = "ok" if R.at[i, "gu"] == s["dong_gu"] else "구 불일치"
        else:
            R.at[i, "status"] = "못 찾음"
    R.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT}")
    print(R.status.value_counts().to_string())
    print("찾은 방법:", R[R.lat != ""].geo_level.value_counts().to_dict())
    bad = R[R.status.isin(["못 찾음", "구 불일치", "대전 밖"])]
    if len(bad):
        print("\n── 확인 필요 ──")
        print(bad[["poi_id", "name", "gu", "status", "kakao_name", "kakao_addr", "dong_gu", "dong"]].to_string(index=False))
    gap = R[pd.to_numeric(R.osm_gap_m, errors="coerce") > 300]
    if len(gap):
        print("\n── OSM 과 300m 넘게 다른 곳 (카카오 값을 씀) ──")
        print(gap[["poi_id", "name", "kakao_name", "osm_gap_m"]].to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
