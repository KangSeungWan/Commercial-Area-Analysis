"""대전 관광지 좌표 붙이기 (OpenStreetMap Nominatim, 키 없음) — 맥에서 실행.

입력  data/tourism_poi_input.csv  (대전시 명소 60곳 + 문체부 주요관광지점 입장객 지점, 103곳)
출력  data/tourism_poi.csv        (lat, lon, 찾은 방법, 들어간 행정동, 상태)
      화면에 '못 찾음 · 구 불일치' 목록

찾는 순서: ① 주소 → ② 짧은 이름 + 구 + 대전 → ③ 짧은 이름만 (모두 대전 범위 안으로 제한)
검사: 점이 대전 행정동 82개 안에 있는지, 주소의 구와 같은지
규칙: Nominatim 이용 정책에 따라 1.1초에 1번만 묻고, 결과는 data/raw/tourism/nominatim_cache.json 에 저장 (다시 돌리면 묻지 않음)

실행: python tram_model/geocode_tourism_poi.py          (약 3~6분)
"""
import json, re, sys, time
from pathlib import Path

import pandas as pd
import requests
from matplotlib.path import Path as MPath

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
INP, OUT = DATA / "tourism_poi_input.csv", DATA / "tourism_poi.csv"
CACHE = DATA / "raw" / "tourism" / "nominatim_cache.json"
DONG = DATA / "daejeon_dong_2023.geojson"
URL = "https://nominatim.openstreetmap.org/search"
HEAD = {"User-Agent": "daejeon-tram-commercial-study/1.0 (student research, low volume)"}
VIEWBOX = "127.24,36.50,127.56,36.18"          # 대전 범위 (서,북,동,남)

# 선(길·하천)이라 점 하나로 둘 수 없는 곳 → 좌표 붙이지 않음
LINEAR = {"3대 하천과 자전거길", "대전둘레산길 300리", "대청호 오백리길"}
# 소개 문구가 섞인 이름 → 검색용 짧은 이름
SHORT = {
    "대한민국 3대 빵집 성심당(聖心堂)": "성심당 본점",
    "대전역과 추억의 가락국수": "대전역",
    "옛 충남도청과 근현대사전시관": "대전근현대사전시관",
    "뿌리공원과 족보박물관": "뿌리공원",
    "보문산 보운대와 대동하늘공원": "대동하늘공원",
    "엑스포과학공원과 세계엑스포 기념품박물관": "엑스포과학공원",
    "국립중앙과학관과 천체투영기": "국립중앙과학관",
    "대전시민천문대와 굴절망원경": "대전시민천문대",
    "한국표준과학연구원과 해시계": "한국표준과학연구원",
    "한국항공우주연구원과 나로호": "한국항공우주연구원",
    "유성온천과 족욕체험장": "유성온천 족욕체험장",
    "고전 종악기 카리용": "카리용",
    "수운교의 성지 천단": "수운교",
    "이사동 민속마을": "이사동",
    "옛 대전형무소 망루, 우물": "대전형무소 망루",
    "단재 신채호 선생 생가터": "신채호 생가",
    "전통시장 유성5일장": "유성시장",
    "종합테마파크 오-월드": "대전오월드",
    "카이스트(KAIST)": "한국과학기술원",
    "㈜제이에이치레전드호텔": "레전드호텔",
}


def clean_addr(a):
    a = re.sub(r"\(.*?\)", "", str(a))                    # (송촌동) 같은 괄호 빼기
    a = re.sub(r"\s*일원$|\s+[가-힣]*연구원$|\s+한국과학기술원$|\s+국립중앙과학관$|\s+대전시민천문대$", "", a)
    a = a.replace("대전시 ", "대전광역시 ").replace("대전 ", "대전광역시 ", 1) if not a.startswith("대전광역시") else a
    return re.sub(r"\s+", " ", a).strip()


def short_name(n):
    if n in SHORT:
        return SHORT[n]
    return re.sub(r"\(.*?\)", "", n).strip()


def load_dongs():
    g = json.load(open(DONG, encoding="utf-8"))
    out = []
    for f in g["features"]:
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for p in polys:
            out.append((f["properties"]["sggnm"], f["properties"]["dong"], MPath(p[0])))
    return out


def which_dong(lon, lat, dongs):
    for gu, dong, path in dongs:
        if path.contains_point((lon, lat)):
            return gu, dong
    return "", ""


def ask(q, cache):
    if q in cache:
        return cache[q]
    time.sleep(1.1)
    try:
        r = requests.get(URL, params={"q": q, "format": "jsonv2", "countrycodes": "kr", "limit": 3,
                                      "accept-language": "ko", "viewbox": VIEWBOX, "bounded": 1},
                         headers=HEAD, timeout=20)
        r.raise_for_status()
        res = r.json()
    except Exception as e:                                 # 네트워크 오류는 저장하지 않음 → 다시 돌리면 재시도
        print(f"  (오류: {q} → {e})")
        return None
    cache[q] = res
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return res


def main():
    P = pd.read_csv(INP, encoding="utf-8-sig", keep_default_na=False)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    dongs = load_dongs()
    rows = []
    for i, r in P.iterrows():
        rec = dict(r)
        rec.update(lat="", lon="", geo_level="", geo_query="", osm_name="", dong="", dong_gu="", status="")
        if r["name"] in LINEAR:
            rec["status"] = "제외(선형)"
            rows.append(rec); continue
        sn = short_name(r["name"])
        tries = []
        if r["address"]:
            tries.append(("주소", clean_addr(r["address"])))
        tries.append(("이름+구", f"{sn} 대전광역시 {r['gu']}".strip()))
        tries.append(("이름", sn))
        fallback = None                                     # 대전 안이지만 구가 다른 첫 결과 (다른 방법이 다 실패할 때만 씀)
        for level, q in tries:
            hit = None
            for cand in ask(q, cache) or []:               # 결과 최대 3개 중 구가 맞는 것 우선
                lat, lon = float(cand["lat"]), float(cand["lon"])
                gu, dong = which_dong(lon, lat, dongs)
                if not dong:                                # 대전 밖
                    continue
                item = (level, q, cand, lat, lon, gu, dong)
                if not r["gu"] or r["gu"] == gu:
                    hit = item; break
                fallback = fallback or item
            if hit:
                break
        hit = hit or fallback
        if hit:
            level, q, cand, lat, lon, gu, dong = hit
            rec.update(lat=round(lat, 6), lon=round(lon, 6), geo_level=level, geo_query=q,
                       osm_name=cand.get("display_name", "")[:80], dong=dong, dong_gu=gu,
                       status="ok" if (not r["gu"] or r["gu"] == gu) else "구 불일치")
        else:
            rec["status"] = "못 찾음"
        rows.append(rec)
        print(f"[{i + 1}/{len(P)}] {r['name'][:22]:<22} {rec['status']:<6} {rec['geo_level']:<5} {rec['dong_gu']} {rec['dong']}")
    R = pd.DataFrame(rows)
    R.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT}")
    print(R.status.value_counts().to_string())
    print("찾은 방법:", R[R.lat != ""].geo_level.value_counts().to_dict())
    bad = R[R.status.isin(["못 찾음", "구 불일치"])]
    if len(bad):
        print("\n── 확인 필요 ──")
        print(bad[["poi_id", "name", "category", "gu", "address", "status", "dong_gu", "dong"]].to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
