"""관광지 추가 후보(검증 2026-10-26)에 카카오 좌표를 붙여 data/tourism_poi.csv 에 더함 — 맥에서 실행.

입력  data/tourism_poi.csv                 기존 79곳 (geocode_tourism_poi_kakao.py 결과 + 검증 반영)
      data/tourism_poi_add_candidates.csv  include = 1 인 후보 (강력 12곳)
      data/tourism_poi_review.csv          검증 결정(이름 바꿈·제외·소규모 문화재 등) → 다시 적용
출력  data/tourism_poi.csv                 기존 + 추가(poi_id = A01…). 다시 돌리면 A 행을 지우고 새로 만듦

- A09 신세계 전망대 → P089 아쿠아리움과 같은 건물, A10 유성온천공원·축제 → P035 족욕체험장과 같은 공원:
  새 점을 만들지 않고 기존 점 이름만 넓힘 (review 파일의 rename)
- A04 0시 축제장 → tour_type '축제장'(상설 시설과 합산하지 않음, 연 1회 피크)
- 관문(교통) 3곳: 대전역(P010)·서대전역(G01)·대전복합터미널(G02) → gateway = 1, 관광 지표 제외, 접근성 출발점
실행: python tram_model/geocode_tourism_add.py   (새 질문 약 20번, 몇 초)
"""
import csv, json, sys
from pathlib import Path

import pandas as pd

from geocode_tourism_poi import DATA, OUT, load_dongs, which_dong
from geocode_tourism_poi_kakao import get_key, call, KW_URL, AD_URL, RECT, CACHE

CAND = DATA / "tourism_poi_add_candidates.csv"
REVIEW = DATA / "tourism_poi_review.csv"
MERGE = {"A09": "P089", "A10": "P035"}
# 카카오 상호에 맞춘 키워드 (앞에서부터 시도), 마지막은 주소 검색
QUERY = {
    "A01": ["대전한화생명볼파크", "한화생명볼파크"],
    "A02": ["대전중앙시장", "중앙시장 대전"],
    "A03": ["으능정이문화의거리", "으능정이 스카이로드", "스카이로드 대전"],
    "A04": ["중앙로역 대전 1호선", "목척교"],          # 축제장 대표점: 대전역~옛 충남도청 1km 가운데
    "A05": ["소제동 카페거리", "소제동 관사촌", "대전 소제동"],
    "A06": ["테미오래"],
    "A07": ["헤레디움"],
    "A08": ["한빛탑", "엑스포시민광장"],
    "A11": ["유림공원"],
    "A12": ["갑천생태호수공원", "갑천호수공원"],
}
GU_ANY = {"A04", "A05"}                                 # 구 경계에 걸침 (중구·동구)
# 관문(교통): 관광지가 아니라 관광객이 들어오는 곳 → 관광 지표에는 넣지 않고 접근성 계산의 출발점으로 씀 (10-26 결정)
#   대전역은 기존 P010 을 관문으로 바꿈(review 파일), 서대전역·대전복합터미널은 새로 찾음
GATEWAYS = {
    "G01": ("서대전역", "중구", ["서대전역"], "대전광역시 중구 오류로 23"),
    "G02": ("대전복합터미널", "동구", ["대전복합터미널"], "대전광역시 동구 동서대로 1689"),
}


def apply_review(R):
    if not REVIEW.exists():
        return R
    V = pd.read_csv(REVIEW, encoding="utf-8-sig", keep_default_na=False, dtype=str).set_index("poi_id")
    for i in R.index:
        pid = R.at[i, "poi_id"]
        if pid in V.index:
            v = V.loc[pid]
            for c in ["tour_type", "use_in_tourism", "poi_group", "verify_note"]:
                R.at[i, c] = v[c]
            if v["rename"]:
                R.at[i, "name"] = v["rename"]
    return R


def main():
    key = get_key()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    dongs = load_dongs()
    R = pd.read_csv(OUT, encoding="utf-8-sig", keep_default_na=False, dtype=str)
    for c in ["poi_group", "verify_note"]:
        if c not in R:
            R[c] = ""
    R = R[~R.poi_id.str.startswith("A")].copy()          # 다시 돌릴 때 이전 추가분 지움
    C = pd.read_csv(CAND, encoding="utf-8-sig", keep_default_na=False, dtype=str)
    C = C[C.include == "1"]
    new = []
    for _, c in C.iterrows():
        cid = c["cand_id"]
        if cid in MERGE:
            print(f"{cid} {c['name'][:24]:<24} → {MERGE[cid]} 와 합침 (이름 넓힘)")
            continue
        hit = None
        for q in QUERY.get(cid, [c["name"]]):
            for d in call(KW_URL, {"query": q, "rect": RECT, "size": 5}, key, cache):
                addr = d.get("road_address_name") or d.get("address_name", "")
                if "대전" in addr and (cid in GU_ANY or f" {c['gu']} " in f" {addr} "):
                    hit = ("이름", q, d.get("place_name", ""), addr, d.get("category_name", ""), float(d["y"]), float(d["x"]))
                    break
            if hit:
                break
        if not hit and c["address"]:
            docs = call(AD_URL, {"query": c["address"]}, key, cache)
            if docs:
                d = docs[0]
                hit = ("주소", c["address"], "", d.get("address_name", ""), d.get("address_type", ""), float(d["y"]), float(d["x"]))
        rec = dict(poi_id=cid, name=c["name"], category=c["category"], gu=c["gu"], address=c["address"], in_top40="False",
                   visitor_site="", source="검증 추가(2026-10-26): " + c["evidence"], status="못 찾음",
                   tour_type="축제장" if c["category"] == "축제장" else "관광지", use_in_tourism="0",
                   poi_group="", verify_note=c["evidence"], note="")
        if hit:
            level, q, pname, addr, cat, lat, lon = hit
            gu, dong = which_dong(lon, lat, dongs)
            rec.update(lat=round(lat, 6), lon=round(lon, 6), geo_level=level, geo_query=q, kakao_name=pname,
                       kakao_addr=addr, kakao_cat=cat[:40], dong=dong, dong_gu=gu,
                       status="ok" if dong and (cid in GU_ANY or gu == c["gu"]) else ("대전 밖" if not dong else "구 불일치"))
            rec["use_in_tourism"] = "1" if rec["status"] == "ok" else "0"
        new.append(rec)
        print(f"{cid} {c['name'][:24]:<24} {rec['status']:<5} {rec.get('kakao_name', '')[:20]:<20} {rec.get('dong_gu', '')} {rec.get('dong', '')}")
    for gid, (gname, ggu, queries, gaddr) in GATEWAYS.items():
        hit = None
        for q in queries:
            for d in call(KW_URL, {"query": q, "rect": RECT, "size": 5}, key, cache):
                addr = d.get("road_address_name") or d.get("address_name", "")
                if "대전" in addr and f" {ggu} " in f" {addr} ":
                    hit = (q, d.get("place_name", ""), addr, float(d["y"]), float(d["x"])); break
            if hit:
                break
        if not hit:
            docs = call(AD_URL, {"query": gaddr}, key, cache)
            if docs:
                hit = (gaddr, "", docs[0].get("address_name", ""), float(docs[0]["y"]), float(docs[0]["x"]))
        rec = dict(poi_id=gid, name=gname, category="관문(교통)", gu=ggu, address=gaddr, in_top40="False", visitor_site="",
                   source="관문 결정(2026-10-26)", status="못 찾음", tour_type="관문(교통)", use_in_tourism="0",
                   poi_group="", verify_note="관광지 아님. 접근성 계산의 출발점(관광객이 들어오는 곳)", note="")
        if hit:
            q, pname, addr, lat, lon = hit
            gu, dong = which_dong(lon, lat, dongs)
            rec.update(lat=round(lat, 6), lon=round(lon, 6), geo_level="이름" if pname else "주소", geo_query=q,
                       kakao_name=pname, kakao_addr=addr, dong=dong, dong_gu=gu, status="ok" if gu == ggu else "구 불일치")
        new.append(rec)
        print(f"{gid} {gname:<24} {rec['status']:<5} {rec.get('kakao_name', '')[:20]:<20} {rec.get('dong_gu', '')} {rec.get('dong', '')}  (관문)")
    R = R[~R.poi_id.str.startswith("G")]
    R = pd.concat([R, pd.DataFrame(new)], ignore_index=True).fillna("")
    R = apply_review(R)
    R["gateway"] = (R.tour_type == "관문(교통)").astype(int).astype(str)
    R.to_csv(OUT, index=False, encoding="utf-8-sig")
    use = R[R.use_in_tourism == "1"]
    print(f"\n저장: {OUT}  전체 {len(R)}곳, 관광 지표에 쓰는 곳 {len(use)}")
    print(use.tour_type.value_counts().to_string())
    print("관문(교통):", ", ".join(R[R.gateway == "1"].name))
    bad = [r for r in new if r["status"] != "ok"]
    if bad:
        print("\n── 확인 필요 ──")
        for r in bad:
            print(r["poi_id"], r["name"], r["status"], r.get("kakao_name", ""), r.get("kakao_addr", ""))


if __name__ == "__main__":
    sys.exit(main())
