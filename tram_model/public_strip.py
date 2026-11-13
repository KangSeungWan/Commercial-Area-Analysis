"""공개본 정리 (2026-11-13 최종 검토 뒤 추가) — 공개 저장소에 복사한 결과 파일에서 8989 유래 열을 뺀다.

쓰는 법: python tram_model/public_strip.py <공개 저장소 폴더>   (예: ../Project-public)
- 대전신용보증재단 활용 조건(행정동·상권별 세부 매출 수치 비공개)에 따라, 공개본 CSV에서 아래 열을 지운다.
- 이름 규칙(s89_*, sales_yoy*)과 함께, 이름이 달라 예전 점검에서 빠졌던 열(값 대조로 찾음)을 목록으로 둔다.
- 새 결과 파일을 공개본에 넣을 때마다 이 스크립트를 돌리고, 법적 점검표 1번(값 대조)을 확인한다.
"""
import re, sys
from pathlib import Path
import pandas as pd

RULE = re.compile(r"^(s89_|sales_yoy)")                      # 이름 규칙
LISTED = {                                                     # 값 대조로 찾은 8989 유래 열 (2026-11-13)
    "tram_model/outputs/dong_scores.csv": ["sales_per_store"],
    "tram_model/outputs/dong_types.csv": ["sales_per_store"],
    "tram_model/outputs/dong_type_centers.csv": ["sales_per_store"],
    "tram_model/outputs/rent_survey_area.csv": ["sales_chg2y_trdar", "sales_yoy_dong"],
    "tram_model/outputs/dong_year_panel.csv": ["resident"],
}
DROP_FILES = ["tram_model/outputs/8989", "tram_model/outputs/station_sales_dong.csv", "tram_model/outputs/validation_closures_8989.csv",
              "tram_model/outputs/parcel_value.csv.gz"]                # 공개본에 있으면 안 되는 파일


def strip(root):
    root = Path(root); changed = []
    for f in root.glob("**/*.csv"):
        rel = f.relative_to(root).as_posix()
        if "/node_modules/" in rel or rel.startswith(".git/"):
            continue
        try:
            d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
        except Exception:
            continue
        cols = [c for c in d.columns if RULE.match(str(c))] + [c for c in LISTED.get(rel, []) if c in d.columns]
        if cols:
            d.drop(columns=cols).to_csv(f, index=False, encoding="utf-8-sig")
            changed.append((rel, cols))
    bad = [p for p in DROP_FILES if (root / p).exists()]
    return changed, bad


if __name__ == "__main__":
    ch, bad = strip(sys.argv[1] if len(sys.argv) > 1 else "../Project-public")
    for rel, cols in ch:
        print(f"  열 삭제 {rel}: {', '.join(cols)}")
    print(f"정리한 파일 {len(ch)}개" + (f" · 있으면 안 되는 파일: {bad}" if bad else " · 금지 파일 없음"))
