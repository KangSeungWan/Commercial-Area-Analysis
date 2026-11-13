"""한국부동산원 상업용부동산 임대동향 (대전 하위 상권, 2022Q1~2026Q2) → 표 + 핵심 상권 20 대응 + 검증

입력: data/raw/rent_survey/*.xlsx  (파일 이름의 '임대료'/'임대가격지수'/'공실률', 상가 유형 '중대형'/'소규모'/'집합'/'통합'/'일반 상가(1층)'/'일반 상가'로 구분)
      outputs/area_profile.csv, area_panel.csv, outputs/8989/area_sales_compare.csv(있으면), rent_pressure.csv(있으면)
출력: outputs/rent_survey_long.csv     지역 × 유형 × 지표 × 분기 (긴 표)
      outputs/rent_survey_area.csv     핵심 상권 20 × 최근 임대료·임대가격지수 변화·공실률 (대응 지역 있는 상권만 값)
      outputs/rent_survey_validation.csv  공실률·임대료 변화 vs 위험 점수·땅값 변화·8989 매출 (스피어만, n 작음 → 방향만)
주의
- 2024년 3분기에 표본 개편: 지역 이름 '원도심'→'대전원도심', 관평동 추가. 임대가격지수 파일은 개편 전후가 이어진 시계열(2024Q2=100)이라 추세는 지수로만 봄
- 임대료(천원/㎡·월)는 개편 전후 수준이 달라질 수 있어 2026Q2 수준만 사용
- 부동산원 상권 경계와 우리 상권 경계는 다름 → 이름으로 대응(아래 MATCH), 한 지역이 여러 상권에 쓰이기도 함(원도심, 둔산)
"""
import re
import unicodedata
import numpy as np
import pandas as pd

import config as C

RAW, OUT = C.RAW_DIR / "rent_survey", C.OUT_DIR
# 부동산원 지역 → 핵심 상권 코드 (이름·위치 기준 수기 대응)
MATCH = {"원도심": ["A04", "A05"], "대전원도심": ["A04", "A05"], "복합터미널": ["A01"], "서대전네거리": ["A06"],
         "용문/한민시장": ["A11"], "유성온천역": ["A14"], "노은": ["A16"], "둔산": ["A07", "A08"], "관평동": ["A15"],
         "가수원": ["A17"], "목원대": ["A17"], "동춘당공원": ["A18"], "대전동구청": ["A02"]}
NORM = {"원도심": "대전원도심"}


def ptype(name):
    for k in ("일반 상가(1층)", "일반 상가", "중대형", "소규모", "집합", "통합"):
        if k in name: return {"일반 상가(1층)": "일반(1층)", "일반 상가": "일반"}.get(k, k)
    return "기타"


def load():
    rows = []
    for f in sorted(RAW.glob("*.xlsx")):
        nm = unicodedata.normalize("NFC", f.stem)
        metric = "임대가격지수" if "지수" in nm else ("공실률" if "공실" in nm else ("임대료" if "임대료" in nm else None))
        if metric is None: continue
        df = pd.read_excel(f, header=None)
        hdr = df.iloc[0].astype(str).tolist()
        qcols = [(i, h) for i, h in enumerate(hdr) if re.match(r"\d{4}년 \d분기", h)]
        for _, r in df.iloc[2:].iterrows():
            region = str(r[2]).strip() if pd.notna(r[2]) else ""
            if not region or str(r[1]).strip() != "대전" or not str(r[0]).strip().isdigit(): continue
            for i, h in qcols:
                v = pd.to_numeric(r[i], errors="coerce")
                if pd.isna(v): continue
                y, q = re.findall(r"\d+", h)
                rows.append(dict(region=NORM.get(region, region), metric=metric, ptype=ptype(nm), year=int(y), q=int(q),
                                 period=f"{y}Q{q}", value=float(v), source=nm))
    L = pd.DataFrame(rows).drop_duplicates(["region", "metric", "ptype", "period"], keep="last")
    return L.sort_values(["metric", "ptype", "region", "period"])


def spearman(x, y):
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    return (round(d.x.rank().corr(d.y.rank()), 3) if len(d) >= 5 else np.nan), len(d)


def main():
    if not list(RAW.glob("*.xlsx")):
        print("data/raw/rent_survey 에 임대동향 엑셀 없음 → 건너뜀"); return
    L = load(); L.to_csv(OUT / "rent_survey_long.csv", index=False, encoding="utf-8-sig")
    print("지역:", sorted(L.region.unique()), "\n지표×유형:", L.groupby(["metric", "ptype"]).period.agg(["min", "max", "count"]).to_string())
    def last(metric, ptype, n=1):
        x = L[(L.metric == metric) & (L.ptype == ptype)]
        ps = sorted(x.period.unique())[-n:]
        return x[x.period.isin(ps)].groupby("region").value.mean()
    def idx_chg(ptype, a="2022Q1", b=None):
        x = L[(L.metric == "임대가격지수") & (L.ptype == ptype)].pivot(index="region", columns="period", values="value")
        b = b or x.columns.max(); a = a if a in x.columns else x.columns.min()
        return ((x[b] / x[a] - 1) * 100).round(2)
    R = pd.DataFrame({"rent_mid_2026q2": last("임대료", "중대형"), "rent_small_2026q2": last("임대료", "소규모"),
                      "rent_coll_2026q2": last("임대료", "집합"),
                      "idx_chg_mid_22_26": idx_chg("중대형"), "idx_chg_small_22_26": idx_chg("소규모"), "idx_chg_coll_22_26": idx_chg("집합"),
                      "idx_chg_all_24_26": idx_chg("통합", "2024Q2"),
                      "vac_mid_4q": last("공실률", "중대형", 4), "vac_small_4q": last("공실률", "소규모", 4),
                      "vac_gen1f_4q": last("공실률", "일반(1층)", 4), "vac_coll_4q": last("공실률", "집합", 4)})
    vm = L[(L.metric == "공실률") & (L.ptype == "중대형")].pivot(index="region", columns="period", values="value")
    R["vac_mid_chg_22_26"] = (vm.iloc[:, -4:].mean(axis=1) - vm.iloc[:, :4].mean(axis=1)).round(2)
    R.index.name = "region"
    # 상권 대응
    prof = pd.read_csv(OUT / "area_profile.csv", encoding="utf-8-sig").set_index("code")
    rows = []
    for reg, codes in MATCH.items():
        if reg not in R.index: continue
        for c in codes:
            rows.append(dict(code=c, region=reg, **R.loc[reg].to_dict()))
    A = pd.DataFrame(rows).groupby("code").agg(lambda v: v.mean() if v.dtype.kind in "fi" else " · ".join(sorted(set(v)))).reset_index()
    A.insert(1, "name", A.code.map(prof.name))
    A["quadrant"], A["risk_score"], A["growth_score"] = A.code.map(prof.quadrant), A.code.map(prof.risk_score), A.code.map(prof.growth_score)
    P = pd.read_csv(OUT / "area_panel.csv", encoding="utf-8-sig")
    li = P.pivot(index="code", columns="year", values="land_idx")
    A["land_chg_22_26"] = A.code.map(((li[2026] / li[2022] - 1) * 100).round(2))
    f = OUT / "8989" / "area_sales_compare.csv"
    if f.exists():
        S = pd.read_csv(f, encoding="utf-8-sig").set_index("code")
        A["sales_yoy_dong"] = A.code.map(S.dong_alloc_yoy)
        if "trdar_chg2y_all" in S: A["sales_chg2y_trdar"] = A.code.map(S.trdar_chg2y_all)
    f = OUT / "rent_pressure.csv"
    if f.exists():
        RP = pd.read_csv(f, dtype={"key": str}, encoding="utf-8-sig"); RP = RP[RP.level == "상권"].set_index("key")
        A["rent_pressure"], A["rent_pressure_score"] = A.code.map(RP.rent_pressure), A.code.map(RP.rent_pressure_score)
    A = A.round(2); A.to_csv(OUT / "rent_survey_area.csv", index=False, encoding="utf-8-sig")
    V = []
    for y, lab in [("vac_mid_4q", "중대형 공실률(최근 4분기)"), ("vac_gen1f_4q", "1층 공실률(최근 4분기)"), ("idx_chg_mid_22_26", "중대형 임대가격지수 변화 2022→2026"),
                   ("rent_mid_2026q2", "중대형 임대료 2026Q2")]:
        for x in ("risk_score", "growth_score", "land_chg_22_26", "sales_yoy_dong", "sales_chg2y_trdar", "rent_pressure_score"):
            if x in A:
                r, n = spearman(A[x], A[y]); V.append(dict(survey=lab, against=x, spearman=r, n=n))
    V = pd.DataFrame(V); V.to_csv(OUT / "rent_survey_validation.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 240)
    print("\n[지역별]\n", R.round(1).to_string())
    print("\n[핵심 상권 대응]\n", A[["code", "name", "region", "quadrant", "risk_score", "rent_mid_2026q2", "idx_chg_mid_22_26", "vac_mid_4q", "vac_gen1f_4q", "land_chg_22_26"] + [c for c in ("sales_yoy_dong", "rent_pressure") if c in A]].to_string(index=False))
    print("\n[검증] 상권 단위 (공유 지역 때문에 독립 표본은 더 적음)\n", V.to_string(index=False))
    dj = L[(L.region == "대전") & (L.metric == "임대가격지수")].pivot(index="period", columns="ptype", values="value")
    print("\n대전 전체 임대가격지수:\n", dj.iloc[[0, 4, 8, 9, 13, -1]].to_string())


if __name__ == "__main__":
    main()
