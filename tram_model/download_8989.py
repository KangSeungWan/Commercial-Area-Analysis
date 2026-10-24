"""
대전 소상공인 상권분석 서비스(8989.daejeon.go.kr) 데이터 수집

수집 대상 (로그인 불필요, 익명 세션 쿠키만 필요)
  1) 코드표: 행정동 82, 골목상권 164, 업종 소분류 79        → data/raw/8989/meta/
  2) 경계: 행정동·상권 폴리곤(GeoJSON)                          → data/raw/8989/meta/
  3) 분석 데이터 /map/getAnalInfo.json  (지역 × 업종 소분류 × 기준월)
       - 응답 하나에 기준월 포함 13개월치가 들어 있음
       - 카드매출은 2025-01부터, 유동인구는 2024-01부터 존재
       → data/raw/8989/raw/<dongAnal|trdarAnal>/<지역코드>_<업종>_<기준월>.json.gz

사용 (Project 폴더, 가상환경 켠 상태)
  python tram_model/download_8989.py --meta            # 코드표·경계만 (1분)
  python tram_model/download_8989.py                   # 행정동 82 × 업종 79 × 기준월 2 (약 1.3만 회, 2시간 안팎)
  python tram_model/download_8989.py --industries core # 핵심 업종 27개만 (약 40분)
  python tram_model/download_8989.py --trdar           # 골목상권 164개도 수집 (오래 걸림)
  python tram_model/download_8989.py --workers 2 --sleep 0.5
이미 받은 파일은 건너뛰므로 끊겨도 다시 실행하면 이어서 받음.

주의: 사이트 이용약관에 사전 승낙 없는 복제·제공 금지 조항이 있음.
      대회 활용·공개 전에 대전신용보증재단(042-380-3942)에 활용 승낙을 받을 것.
"""
import argparse, gzip, json, time, sys, random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests, pandas as pd

BASE = "https://8989.daejeon.go.kr"
ROOT = Path(__file__).resolve().parent / "data" / "raw" / "8989"
META, RAW = ROOT / "meta", ROOT / "raw"

# 기준월: 2026-08 호출 → 2025-08~2026-08, 2026-01 호출 → 2025-01~2026-01 (매출 전 기간 커버)
#         2024-12 호출 → 2024-01~2024-12 (유동인구만, 업종 무관 → 업종 1개로 1회)
YM_MAIN = ["202608", "202601"]
YM_POP_ONLY = ["202412"]

CORE_INDUSTRIES = [  # 상권 분석에 쓰는 소매·음식·생활서비스 중심 27개
    "G0471","G0472","G0473","G0474","G0475","G0476","G0478",   # 소매
    "I1551","I1559","I2561","I2562",                           # 숙박·음식·주점
    "L0681","L0682",                                           # 부동산
    "P0855","P0856",                                           # 교육
    "Q0861","Q0862","Q0869",                                   # 보건
    "R0901","R0911","R0912",                                   # 여가
    "S0951","S0952","S0953","S0961","S0969","S0752",           # 수리·미용·개인서비스·여행
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh) daejeon-tram-research/1.0",
           "Referer": BASE + "/map/anals_info.do?currentMapAnal=dongAnal",
           "X-Requested-With": "XMLHttpRequest"}


def new_session():
    s = requests.Session(); s.headers.update(HEADERS)
    s.get(BASE + "/main.do", timeout=30)                      # 익명 세션 쿠키 발급
    return s


def post_json(s, path):
    r = s.post(BASE + path, headers={"Content-Type": "application/json"}, timeout=60)
    r.raise_for_status(); return r.json()


def fetch_meta(s):
    META.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(post_json(s, "/map/getAdstrdOpt.json")["opt"]).to_csv(META/"dong_opt.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(post_json(s, "/map/getTrdarOpt.json")["opt"]).to_csv(META/"trdar_opt.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(post_json(s, "/map/getIndustOpt.json")["opt"]).to_csv(META/"industry_opt.csv", index=False, encoding="utf-8-sig")
    for path, name, key in [("/map/getAdstrdInfo.json", "dong", "admdstCd"), ("/map/getTrdarInfo.json", "trdar", "trdarNo")]:
        rows = post_json(s, path)["data"]
        feats = []
        for r in rows:
            coords = json.loads(r.pop("coordinates"))
            if "centroid" in r and isinstance(r["centroid"], str):
                r["centroid"] = json.loads(r["centroid"])
            depth = 0; c = coords
            while isinstance(c, list): c = c[0]; depth += 1
            gtype = "Polygon" if depth == 3 else "MultiPolygon"
            feats.append({"type": "Feature", "properties": r, "geometry": {"type": gtype, "coordinates": coords}})
        json.dump({"type": "FeatureCollection", "features": feats}, open(META/f"{name}_polygons.geojson", "w", encoding="utf-8"), ensure_ascii=False)
        pd.DataFrame([f["properties"] for f in feats]).drop(columns=["centroid"], errors="ignore").to_csv(META/f"{name}_geo_attr.csv", index=False, encoding="utf-8-sig")
    print("meta 저장:", META)


def out_path(anal, plc, ind, ym):
    d = RAW / anal; d.mkdir(parents=True, exist_ok=True)
    return d / f"{plc}_{ind}_{ym}.json.gz"


def fetch_one(s, anal, plc, ind, ym, sleep):
    p = out_path(anal, plc, ind, ym)
    if p.exists(): return "skip"
    for attempt in range(4):
        try:
            r = s.get(BASE + "/map/getAnalInfo.json", params=dict(currentMapAnal=anal, stdrYm=ym, plcCd=plc, sclasCd=ind), timeout=60)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                with gzip.open(p, "wt", encoding="utf-8") as f: f.write(r.text)
                time.sleep(sleep + random.random() * 0.2); return "ok"
            if r.status_code in (429, 503): time.sleep(30 * (attempt + 1)); continue
            if "<!DOCTYPE" in r.text[:200]:          # 세션 만료 → 다시 발급
                s.get(BASE + "/main.do", timeout=30); time.sleep(2); continue
            return f"fail{r.status_code}"
        except requests.RequestException as e:
            time.sleep(5 * (attempt + 1))
    return "fail"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", action="store_true", help="코드표·경계만")
    ap.add_argument("--trdar", action="store_true", help="골목상권 164개도 수집")
    ap.add_argument("--industries", default="all", choices=["all", "core"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--limit", type=int, default=0, help="시험용: 앞에서 n건만")
    a = ap.parse_args()

    s = new_session()
    if not (META/"industry_opt.csv").exists() or a.meta: fetch_meta(s)
    if a.meta: return

    dong = pd.read_csv(META/"dong_opt.csv", dtype=str)
    ind = pd.read_csv(META/"industry_opt.csv", dtype=str)
    inds = list(ind.indutySclasCode) if a.industries == "all" else CORE_INDUSTRIES
    jobs = []
    for plc in dong.mnrCd:
        for ym in YM_POP_ONLY: jobs.append(("dongAnal", plc, inds[0], ym))
        for i in inds:
            for ym in YM_MAIN: jobs.append(("dongAnal", plc, i, ym))
    if a.trdar:
        trdar = pd.read_csv(META/"trdar_opt.csv", dtype=str)
        trdar = trdar[trdar.mjrNm != "축제"]
        for plc in trdar.mnrCd:
            for ym in YM_POP_ONLY: jobs.append(("trdarAnal", plc, inds[0], ym))
            for i in inds:
                for ym in YM_MAIN: jobs.append(("trdarAnal", plc, i, ym))
    if a.limit: jobs = jobs[:a.limit]
    todo = [j for j in jobs if not out_path(*j).exists()]
    print(f"전체 {len(jobs)}건, 남은 {len(todo)}건, workers={a.workers}")

    sessions = [new_session() for _ in range(a.workers)]
    stats = {}; t0 = time.time(); done = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(fetch_one, sessions[k % a.workers], *j, a.sleep): j for k, j in enumerate(todo)}
        for f in as_completed(futs):
            r = f.result(); stats[r] = stats.get(r, 0) + 1; done += 1
            if done % 100 == 0 or done == len(todo):
                el = time.time() - t0
                print(f"{done}/{len(todo)}  {el/60:.1f}분 경과, 남은 예상 {el/done*(len(todo)-done)/60:.0f}분  {stats}", flush=True)
    print("완료", stats)


if __name__ == "__main__":
    main()
