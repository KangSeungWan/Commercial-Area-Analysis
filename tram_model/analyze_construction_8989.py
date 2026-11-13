"""공사 기간 피해 점검 (A4): 트램 공사 구간 행정동 vs 다른 동의 월별 카드매출 (8989, 2025-01~2026-08)

입력: data/construction_sections.csv  (section, start_ym, end_ym, stations(정거장 번호를 ; 로), source, note)
        - 공사 구간과 시기는 언론·대전시 발표로 정리(사용자·Claude). 정거장 번호로 적으면 500m 안 점포 비율이 큰 동을 자동으로 고름
      outputs/8989/dong_panel_8989.csv (동 × 월 카드매출 합계, 79개 업종), outputs/dong_station_summary.csv (정거장 → 동, 500m 비율)
방법: 처리 = 공사 구간 정거장이 동 안에 있거나 300m 안인 동, 비교 = 트램 정거장 500m 점포 비율 10% 미만 동
      log(월 카드매출)에 동 고정효과 + 월 고정효과, 처리 × 공사 중(달) 이중차분, 동 군집 표준오차. 사건연구(공사 시작 전후 달)
      대안 결과: 음식점 매출만, 도소매 매출만
출력: outputs/construction_8989_did.csv, outputs/construction_8989_es.csv
한계: 자료 시작(2025-01)이 공사 시작과 가까우면 개통 전 기간이 짧음. 카드 79업종·카드사 한정. 같은 시기 재개발 입주(주민 증가) 동은 섞임 → 주민 인구 통제
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import analyze_line1_permits as AP

OUT = C.OUT_DIR
SEC = C.ROOT / "data" / "construction_sections.csv"


def main():
    if not SEC.exists():
        print(f"공사 구간 표 없음({SEC}) → 건너뜀"); return
    S = pd.read_csv(SEC, encoding="utf-8-sig", dtype=str)
    P = pd.read_csv(OUT / "8989" / "dong_panel_8989.csv", dtype={"adm_cd2": str})
    P = P.dropna(subset=["useAmount_합계"])
    P = P[P["useAmount_합계"] > 0]
    DS = pd.read_csv(OUT / "dong_station_summary.csv", encoding="utf-8-sig", dtype={"dong_id": str})
    prof = pd.read_csv(OUT / "dong_map_profile.csv", encoding="utf-8-sig", dtype={"dong_id": str}).set_index("dong_id")
    tot = prof.tram500_share                                                # 동 점포 중 정거장 500m 안 비율
    rows_t = []
    for r in S.itertuples():
        stns = [int(x) for x in str(r.stations).split(";") if x.strip()]
        d = DS[DS.station_no.isin(stns) & ((DS.inside.astype(str) == "True") | (DS.dist_m <= 300))]      # 정거장이 동 안이거나 300m 안
        for k in d.dong_id.unique():
            rows_t.append(dict(dong_id=k, section=r.section, start=int(r.start_ym), end=int(r.end_ym) if str(r.end_ym) not in ("", "nan") else 999912))
    T = pd.DataFrame(rows_t).sort_values("start").drop_duplicates("dong_id")
    ctrl = set(tot[tot < 0.10].index)
    P = P[P.adm_cd2.isin(set(T.dong_id) | ctrl)].copy()
    P = P.merge(T[["dong_id", "start", "end", "section"]], left_on="adm_cd2", right_on="dong_id", how="left")
    P["treat"] = P.start.notna().astype(int)
    P["during"] = ((P.stdrYm >= P.start) & (P.stdrYm <= P.end)).astype(int) * P.treat
    P = P.rename(columns={"adm_cd2": "cell", "stdrYm": "year"})
    P["lres"] = np.log(P.resident.clip(lower=1))
    rows = []
    for y, lab in [("useAmount_합계", "전체 카드매출"), ("useAmount_음식점", "음식점 매출"), ("useAmount_도소매", "도소매 매출")]:
        d = P[P[y] > 0].assign(ly=lambda x: np.log(x[y]), D=lambda x: x.during.astype(float)).dropna(subset=["ly", "lres"])
        full = d.groupby("cell").year.nunique(); d = d[d.cell.isin(full[full == full.max()].index)]      # 균형 패널
        b, se, G = AP.twfe(d, "ly", ["D", "lres"])
        rows.append(dict(결과=lab, 효과_퍼센트=round(AP.pct(b[0]), 2), 하한=round(AP.pct(b[0] - 1.96 * se[0]), 2), 상한=round(AP.pct(b[0] + 1.96 * se[0]), 2),
                         p값=round(AP._pval(b[0] / se[0]), 4), 처리_동=int(d[d.treat == 1].cell.nunique()), 비교_동=int(d[d.treat == 0].cell.nunique()),
                         처리_동_목록=", ".join(sorted(P[P.treat == 1].dong.dropna().unique()))[:300]))
    R = pd.DataFrame(rows); R.to_csv(OUT / "construction_8989_did.csv", index=False, encoding="utf-8-sig")
    # 사건연구: 공사 시작 달 기준 상대 월
    months = sorted(P.year.unique()); idx = {m: i for i, m in enumerate(months)}
    P["rel"] = np.where(P.treat == 1, P.year.map(idx) - P.start.map(lambda s: idx.get(int(s), np.nan) if pd.notna(s) else np.nan), np.nan)
    d = P[P["useAmount_합계"] > 0].assign(ly=lambda x: np.log(x["useAmount_합계"])).dropna(subset=["ly", "lres"])
    full = d.groupby("cell").year.nunique(); d = d[d.cell.isin(full[full == full.max()].index)]
    xs = []
    for k in range(-6, 13):
        if k == -1: continue
        c = f"r{k}"; d[c] = (d.rel == k).astype(float); xs.append(c)
    keep = [c for c in xs if d[c].sum() > 0]
    b, se, _ = AP.twfe(d, "ly", keep + ["lres"])
    E = pd.DataFrame({"rel_month": [int(c[1:]) for c in keep], "effect_pct": [AP.pct(v) for v in b[:len(keep)]],
                      "lo": [AP.pct(v - 1.96 * s) for v, s in zip(b[:len(keep)], se[:len(keep)])], "hi": [AP.pct(v + 1.96 * s) for v, s in zip(b[:len(keep)], se[:len(keep)])]})
    E.to_csv(OUT / "construction_8989_es.csv", index=False, encoding="utf-8-sig")
    print(R.to_string(index=False)); print(E.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
