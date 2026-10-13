"""공공데이터포털 오픈API로 대전 음식점 인허가 데이터 내려받기.

받는 것 (행정안전부 조회서비스 3개, 영업 중 + 폐업 모두)
  general_restaurants  행정안전부_식품_일반음식점 조회서비스  (data.go.kr/data/15154916)
  rest_cafes           행정안전부_식품_휴게음식점 조회서비스  (data.go.kr/data/15154921)
  bakeries             행정안전부_식품_제과점영업 조회서비스  (data.go.kr/data/15155252)

준비
  1) 공공데이터포털 로그인 → 위 3개 페이지에서 각각 '활용신청' (자동승인)
  2) 마이페이지 → 개인 API 인증키(Decoding) 복사

실행
  python tram_model/download_permits_api.py 인증키
  → tram_model/data/raw/permits/<서비스>.csv (utf-8-sig)

대전 5개 구를 개방자치단체코드(3640000~3680000)로 하나씩 받습니다.
한 번에 100행, 하루 10,000번 호출 제한(개발계정) 안에서 충분합니다.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "data", "raw", "permits")
BASE = "https://apis.data.go.kr/1741000/{svc}/info"
SERVICES = {"general_restaurants": "일반음식점", "rest_cafes": "휴게음식점", "bakeries": "제과점영업"}
GU = {"3640000": "동구", "3650000": "중구", "3660000": "서구", "3670000": "유성구", "3680000": "대덕구"}
ROWS = 100


def call(svc, key, org, page):
    q = {"serviceKey": key, "pageNo": str(page), "numOfRows": str(ROWS), "returnType": "json",
         "cond[OPN_ATMY_GRP_CD::EQ]": org}
    url = BASE.format(svc=svc) + "?" + urllib.parse.urlencode(q)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                raw = r.read().decode("utf-8")
            data = json.loads(raw)
            break
        except Exception as e:  # 네트워크·일시 오류는 몇 번 다시 시도
            if attempt == 3:
                raise RuntimeError(f"{svc} {org} {page}쪽 실패: {e}\n응답 앞부분: {locals().get('raw', '')[:300]}")
            time.sleep(2 * (attempt + 1))
    resp = data.get("response", data)
    head = resp.get("header", {})
    code = str(head.get("resultCode", "00"))
    if code not in ("00", "0", "000"):
        raise RuntimeError(f"API 오류 {code}: {head.get('resultMsg')} (활용신청·인증키 확인)")
    body = resp.get("body", {})
    items = body.get("items") or {}
    item = items.get("item", []) if isinstance(items, dict) else items
    if isinstance(item, dict):
        item = [item]
    return int(body.get("totalCount", 0) or 0), item


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python tram_model/download_permits_api.py 인증키(Decoding)")
    key = sys.argv[1]
    os.makedirs(OUT_DIR, exist_ok=True)
    for svc, label in SERVICES.items():
        rows = []
        for org, gu in GU.items():
            total, first = call(svc, key, org, 1)
            rows += first
            pages = (total + ROWS - 1) // ROWS
            for p in range(2, pages + 1):
                _, it = call(svc, key, org, p)
                rows += it
                if p % 50 == 0:
                    print(f"    {label} {gu}: {p}/{pages}쪽")
            addr = next((r.get("LOTNO_ADDR") or r.get("ROAD_NM_ADDR") for r in first if r.get("LOTNO_ADDR") or r.get("ROAD_NM_ADDR")), "")
            print(f"  {label} {gu}: {total:,}건 (예: {addr[:20]})")
            if total and not str(addr).startswith("대전"):
                print("  경고: 주소가 대전이 아님 → 개방자치단체코드 확인 필요")
        if not rows:
            print(f"  {label}: 받은 데이터 없음")
            continue
        for r in rows:
            r["SERVICE"] = label
        cols = sorted({k for r in rows for k in r})
        path = os.path.join(OUT_DIR, f"{svc}_daejeon.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"저장: {path} ({len(rows):,}행)")


if __name__ == "__main__":
    main()
