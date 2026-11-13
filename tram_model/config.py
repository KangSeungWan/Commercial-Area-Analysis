"""경로·상수 설정. 원본 파일 이름이 다르면 RAW 딕셔너리만 고치면 됩니다."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "outputs"

RAW = {
    # 소상공인시장진흥공단 상가(상권)정보 대전 2026-06 (csv, utf-8)
    "stores": RAW_DIR / "소상공인시장진흥공단_상가_상권_정보_대전_202606.csv",
    # 국토교통부 전국 버스정류장 위치정보 2025-10-31 (xlsx) — 대전BIS만 사용
    "bus_national": RAW_DIR / "국토교통부_전국_버스정류장_위치정보_20251031.xlsx",
    # 대전 중구 행정동별 일평균 유동인구 2021-2024 (csv, utf-8)
    "foot_traffic": RAW_DIR / "대전_중구_행정동별_유동인구_20241231.csv",
    # KB국민카드 대전 구별·업종별 월매출 2019-2020 3~7월 (csv, cp949, 억원)
    "kb_sales": RAW_DIR / "대전_KB카드_업종별_매출_20200801.csv",
    # 한국부동산원 상업용부동산 임대동향 2024Q1 중대형상가 (xlsx, 천원/㎡)
    "rent": RAW_DIR / "부동산원_중대형상가_임대료_2024Q1.xlsx",
}

LIT_PARAMS = ROOT / "literature_params.csv"
AREAS_CSV = ROOT / "data" / "sangkwon_areas.csv"   # 대전 20개 상권 정의 (build_areas.py)

# 파일 이름이 위와 조금 달라도 찾을 수 있도록, 이름에 들어간 키워드로 다시 찾음
RAW_KEYWORDS = {   # (이름에 들어갈 키워드들, 허용 확장자)
    "stores": (["상가", "202606"], {".csv", ".xlsx"}),   # csv 우선
    "bus_national": (["버스정류장", "20251031"], {".xlsx"}),
    "foot_traffic": (["20241231"], {".csv"}),
    "kb_sales": (["KB"], {".csv"}),
    "rent": (["임대"], {".xlsx"}),
}


def raw_path(key):
    """RAW[key] 가 있으면 그대로, 없으면 data/raw 안에서 키워드로 검색."""
    import unicodedata
    p = RAW[key]
    if p.exists():
        return p
    files = [f for f in RAW_DIR.glob("*") if f.is_file()] if RAW_DIR.exists() else []
    kws, exts = RAW_KEYWORDS[key]
    hits = [f for f in files if f.suffix.lower() in exts
            and all(k in unicodedata.normalize("NFC", f.name) for k in kws)]
    if len(hits) > 1:   # 같은 자료의 csv·xlsx 가 둘 다 있으면 csv 사용
        csv = [h for h in hits if h.suffix.lower() == ".csv"]
        hits = csv if len(csv) == 1 else hits
    if len(hits) == 1:
        return hits[0]
    listing = "\n  ".join(unicodedata.normalize("NFC", f.name) for f in files) or "(비어 있음 / 폴더 없음)"
    raise FileNotFoundError(
        f"[{key}] 원본 파일을 찾지 못했습니다.\n"
        f"찾는 위치: {RAW_DIR}\n찾는 이름: {p.name} (또는 이름에 {kws} 포함, 확장자 {sorted(exts)})\n"
        f"{'후보가 여러 개: ' + str([h.name for h in hits]) if hits else ''}\n"
        f"현재 data/raw 안의 파일:\n  {listing}")

# 격자·구역
LAT0 = 36.34          # 평면 근사 기준 위도
CELL_M = 250          # 격자 크기
ZONE_BUFFER_M = 1000  # 구역 정거장 반경 (P3 2차 상권 1km)
STORE_MONTH = "2026-06"

# 분석 단위: 20개 상권 (data/sangkwon_areas.csv). 격자 셀 중심이 상권 반경 + AREA_CELL_PAD_M 안이면 그 상권 셀
#   - p6_zone(core/secondary/periphery) : P6 고베 중심·주변 구분 → 트램 효과 가중
#   - rent_area : 부동산원 하위상권 이름 (없으면 '대전' 평균)
AREA_CELL_PAD_M = 125

# (예전) 4개 구역 — 지금은 쓰지 않음. 비교용으로 남겨 둠
ZONES = {"Z1": [206, 207], "Z2": [201, 202], "Z3": [212, 213], "Z4": [224, 225]}
ZONE_NAME = {"Z1": "대전역(중앙시장)·대전역(혁신도시)", "Z2": "서대전역·서대전네거리",
             "Z3": "중리(중리시장)·용전", "Z4": "유성온천·궁동(카이스트)"}
# 분석구역 개요(매트릭스) + P6(고베) 핵심/주변 구분 + P4(서울) 상업/주거 구분
ZONE_TYPE = {"Z1": "core", "Z2": "secondary", "Z3": "periphery", "Z4": "core"}
# 부동산원 하위상권 매핑 (Z3 중리는 조사 상권이 없어 가장 가까운 복합터미널 사용)
ZONE_RENT_AREA = {"Z1": "원도심", "Z2": "서대전네거리", "Z3": "복합터미널", "Z4": "유성온천역"}

# 2호선 환승 정거장(1호선·국철·광역철도·BRT) — P7: 소매는 환승·종점 정거장으로 재배치
TRANSFER_STATIONS = {201, 202, 206, 207, 208, 214, 218, 225, 237}
# 기존 교통 거점(P6 '중심-주변' 구분용): 대전역, 정부청사(둔산), 유성온천
HUB_STATIONS = {206, 218, 225}
