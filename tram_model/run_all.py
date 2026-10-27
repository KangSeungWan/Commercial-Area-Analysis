"""전체 파이프라인을 순서대로 실행.

사용 (프로젝트 폴더에서):
  python tram_model/run_all.py            # 무거운 단계는 결과가 이미 있으면 건너뜀
  python tram_model/run_all.py --full     # 처음부터 전부 다시 (상가 과거 패널·공시지가 포함, 5~10분)
  python tram_model/run_all.py --from train_analyze   # 그 단계부터 끝까지

중간에 실패하면 그 단계 이름과 오류를 보여 주고 멈춤.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # 프로젝트 폴더 (map_data.csv 위치)
OUT = HERE / "outputs"

# (스크립트, 설명, 무거운 단계면 '이 파일이 있으면 건너뜀')
STEPS = [
    ("build_areas", "20개 상권 경계", None),
    ("build_area_regions", "대전 전체 상권 권역 (지도 색칠용)", None),
    ("build_store_panel", "상가 과거 패널 (42개 분기)", OUT / "store_panel.csv"),
    ("analyze_store_panel", "상가 사건 효과", OUT / "panel_event_effects.csv"),
    ("build_landprice", "공시지가 1990~2026", OUT / "landprice_long.pkl"),
    ("analyze_landprice", "1호선·트램 지가 효과", None),
    ("build_dataset", "학습 데이터셋 (293개 격자)", None),
    ("train_analyze", "모델 학습 + 트램 시나리오", None),
    ("make_map_data", "지도용 데이터 (1차)", None),
    ("build_area_panel", "상권 × 연도 패널", None),
    ("cluster_areas", "상권 유형 (K-means)", None),
    ("make_map_data", "지도용 데이터 (유형 반영)", None),
    ("analyze_robustness", "트램 효과 강건성 검정", None),
    ("analyze_line1_trend", "1호선 효과 추세 보정·매칭", None),
    ("analyze_line1_permits", "1호선 개통 전후 점포 이중차분 (인허가, data/raw/permits 있으면)", None),
    ("check_sector_evidence", "업종 근거 추가 점검: 사전 추세·비중·거리·2단계 재현·밀도 맞춤 (약 3분)", None),
    ("check_other_sectors", "비음식 업종(미용·세탁·숙박 등) 인허가 같은 점검 (data/raw/permits_other 있으면, 약 1분)", None),
    ("build_dong_layer", "행정동 82개 지표", None),
    ("build_dong_panel", "행정동 지가·점포 패널 (약 1분)", OUT / "dong_panel_store.csv"),
    ("analyze_dong_events", "행정동 단위 사건 효과", None),
    ("analyze_tram_benchmark", "트램 효과 문헌 비교", None),
    ("analyze_tram_meta", "해외 트램 개통 효과 메타분석 (10곳)", None),
    ("analyze_factors", "요인 분석 (약 1분)", None),
    ("analyze_industry", "업종별 분석", None),
    ("forecast_areas", "예측 모델 비교 + 2030 개통 트램 시나리오(~2034) (약 1분)", None),
    ("score_areas", "쇠퇴 위험·성장 가능 점수", None),
    ("analyze_tram_impact", "트램 효과 금액·거리별·있을 때/없을 때 (처음 1회 약 1분)", None),
    ("score_industry", "상권 × 업종 점수 (100점, 트램 전·후)", None),
    ("analyze_survey_sales", "실태조사·업종 매출 (data/raw/매출 있으면)", None),
    ("build_station_summary", "정거장 45개 500m 영향권 요약", None),
    ("build_8989_tables", "8989 상권분석 서비스 원본 → 표 (data/raw/8989/raw 있으면)", None),
    ("analyze_8989", "8989 실측 카드매출: 행정동 요약·검증·상권 배분", None),
    ("analyze_station_sales", "1호선 역세권 매출 차이 (8989, 땅값 환산 비율)", None),
    ("analyze_seoul_newline_sales", "서울 신림선 개통 전후 상권 매출 이중차분 (data/raw/seoul 있으면)", None),
    ("analyze_8989_trdar", "8989 골목상권 144곳 매출 증감·핵심 상권 대응", None),
    ("parse_8989_reports", "8989 월간 상권동향 PDF (data/raw/8989/reports 있으면)", None),
    ("build_dong_year_panel", "행정동 82개 × 연도 패널", None),
    ("cluster_dongs", "행정동 유형 (K-means)", None),
    ("forecast_dongs", "행정동 지가·점포 예측 + 트램 시나리오 (약 1분)", None),
    ("score_dongs", "행정동 쇠퇴 위험·성장 점수·진단", None),
    ("analyze_tram_impact_dongs", "행정동 트램 효과 금액 (약 1분)", None),
    ("build_dong_map_profile", "지도용 행정동 요약표·GeoJSON·정거장 요약", None),
    ("validate_closures_8989", "진단 외부 검증: 8989 폐업률(2025) ↔ 82개 동 위험 점수", None),
    ("analyze_construction_8989", "공사 기간 점검: 공사 구간 동 vs 정거장 먼 동 월별 카드매출 (data/construction_sections.csv)", None),
    ("analyze_construction_density", "공사 기간 점검 강건성(B4): 상업 밀도 맞춘 비교군 4가지", None),
    ("analyze_construction_trdar", "공사 기간 점검(골목상권 144 × 월, 2024-01~): 공사 전 14개월 확보, 가짜 공사 시작", None),
    ("analyze_cafe_saturation", "카페 포화 점검: 대전 카페 순증·폐업률, 카페 비중 높던 격자의 1호선 효과 → '높음' 조정 (약 1분)", None),
    ("build_composition", "업종 구성 현재·트램 개통 후 예상 (카페·빵집, 1호선 인허가 근거)", None),
    ("build_rent_pressure", "임대료 부담 위험 순위 (상권·행정동)", None),
    ("build_rent_survey", "부동산원 임대동향(임대료·지수·공실률) 상권 대응 (data/raw/rent_survey 있으면)", None),
    ("build_rent_long", "임대료 장기 흐름(R-ONE 2013~2026) vs 같은 기간 땅값 (data/raw/rent_survey_long 있으면)", None),
    ("check_rent_signal_history", "임대료 부담 신호 ↔ 지난 13년 지역 임대료 흐름 대조 (참고, 지역 6~7곳)", None),
    ("analyze_station_sensitivity", "정거장 추정 좌표 민감도: 28곳을 0~300m 옮겨 500m 판정·진단 다시 계산 (약 1분)", None),
    ("analyze_assumption_sensitivity", "가정 민감도: 1호선 효과 기준별 금액·진단 변화, 임대료 신호 가중치 안정도", None),
    ("analyze_development_trend", "트램 없어도 오르는 곳: 신도시·택지 개발 동 표시, 개발지 뺀 1호선 효과 (약 1분)", None),
    ("build_tourism_layer", "관광(보조): 관광지·대리지표·관문 접근성 변화 시나리오 (상권·행정동·정거장)", None),
    ("make_map_data", "지도용 데이터 (점수 반영)", None),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="무거운 단계도 다시 실행")
    ap.add_argument("--from", dest="start", default=None, help="이 단계부터 실행 (예: train_analyze)")
    a = ap.parse_args()
    names = [s[0] for s in STEPS]
    if a.start and a.start not in names:
        sys.exit(f"단계 이름이 없습니다: {a.start}\n가능: {', '.join(dict.fromkeys(names))}")
    i0 = names.index(a.start) if a.start else 0
    t_all = time.time()
    for i, (name, desc, skip_if) in enumerate(STEPS):
        if i < i0:
            continue
        tag = f"[{i + 1}/{len(STEPS)}] {name} — {desc}"
        if skip_if is not None and skip_if.exists() and not a.full and not (a.start and i == i0):
            print(f"{tag}: 결과 있음 → 건너뜀 (다시 하려면 --full)")
            continue
        print(f"\n{tag}", flush=True)
        t = time.time()
        r = subprocess.run([sys.executable, str(HERE / f"{name}.py")], cwd=ROOT)
        if r.returncode != 0:
            sys.exit(f"\n✖ {name} 단계에서 멈춤 (위 오류 확인). 고친 뒤:  python tram_model/run_all.py --from {name}")
        print(f"   ✓ {time.time() - t:.0f}초")
    print(f"\n완료 ({time.time() - t_all:.0f}초). 지도: streamlit run app.py")


if __name__ == "__main__":
    main()
