"""상가(상권)정보 과거 분기 파일 → 20개 상권 × 분기 패널 (점포 수·개폐업·업종 구성·사건 변수).

입력
- data/raw/상가_과거/  : 소상공인시장진흥공단_상가(상권)정보_대전_YYYYMM.csv  (여러 분기)
- outputs/sangkwon_anchors.csv : build_areas.py 가 만든 상권 기준점(보정 후)
- data/area_events.csv : 상권별 과거 사건

출력
- outputs/store_panel.csv         : 상권 × 분기 패널
- outputs/store_panel_city.csv    : 대전 전체 분기별 합계 (자료 단절 확인용)

주의 (자료 특성)
- 2015-12 ~ 2016-12 : 직전 분기 점포가 100% 유지 → 폐업이 기록되지 않음(소급 생성 자료로 보임) → 폐업률 결측 처리
- 2023-03, 2024-12, 2026-06 : 대전 전체 점포 수가 한 분기에 ±10% 이상 변하는 '자료 단절' → data_break=1
  → 상권 비교는 '대전 전체 대비 비중(share)'과 분기 고정효과로 단절을 상쇄
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

import config as C
from build_dataset import to_xy
from build_areas import assign

HIST_DIR = C.RAW_DIR / "상가_과거"
COLS = ["상가업소번호", "지점명", "상권업종대분류명", "상권업종중분류명", "경도", "위도"]


def load_snapshots():
    files = sorted(HIST_DIR.glob("*.csv"))
    snaps = {}
    for f in files:
        m = re.search(r"(20\d{4})", f.name)
        if not m:
            continue
        d = pd.read_csv(f, dtype=str, usecols=COLS)
        d["lat"] = pd.to_numeric(d["위도"], errors="coerce")
        d["lon"] = pd.to_numeric(d["경도"], errors="coerce")
        snaps[m.group(1)] = d.dropna(subset=["lat", "lon"])
        print(f"  {m.group(1)}: {len(d):,}", flush=True)
    if not snaps:
        raise FileNotFoundError(f"{HIST_DIR} 에 상가정보 과거 csv 가 없습니다")
    snaps = dict(sorted(snaps.items()))
    # 좌표가 대전 밖으로 잘못 들어간 분기(예: 2025-03 은 주소는 대전, 좌표는 강원도) → 앞뒤 분기의 같은 점포 좌표로 복원
    keys = list(snaps)
    for i, k in enumerate(keys):
        d = snaps[k]
        bad = ~(d.lat.between(36.1, 36.6) & d.lon.between(127.2, 127.65))
        if bad.mean() < 0.5:
            continue
        ref = pd.concat([snaps[keys[j]][["상가업소번호", "lat", "lon"]] for j in (i - 1, i + 1) if 0 <= j < len(keys)])
        ref = ref.drop_duplicates("상가업소번호").set_index("상가업소번호")
        d["lat"] = d["상가업소번호"].map(ref.lat); d["lon"] = d["상가업소번호"].map(ref.lon)
        miss = d.lat.isna().mean()
        print(f"  ⚠ {k}: 좌표 {bad.mean():.0%} 가 대전 밖 → 앞뒤 분기 좌표로 복원 (복원 못 한 점포 {miss:.1%} 제외)")
        snaps[k] = d.dropna(subset=["lat", "lon"]).assign(coord_fixed=1)
    return snaps


def shannon(counts):
    p = counts / counts.sum()
    return float(-(p * np.log(p)).sum()) if len(p) else 0.0


def main():
    C.OUT_DIR.mkdir(exist_ok=True)
    anc = pd.read_csv(C.OUT_DIR / "sangkwon_anchors.csv", encoding="utf-8-sig")
    anc["x"], anc["y"] = to_xy(anc.lat, anc.lon)
    areas = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig")
    codes = list(areas.code)

    print("상가정보 과거 파일 읽는 중 ...", flush=True)
    snaps = load_snapshots()

    rows, city, prev_ids, prev_area = [], [], None, None
    for per, d in snaps.items():
        x, y = to_xy(d.lat.values, d.lon.values)
        lab, _ = assign(x, y, anc, codes)
        d = d.assign(area=np.where(lab >= 0, np.array(codes)[np.clip(lab, 0, None)], None))
        ids = set(d["상가업소번호"])
        keep = len(ids & prev_ids) / len(prev_ids) if prev_ids else np.nan
        city.append({"period": per, "n_city": len(d), "keep_rate": keep,
                     "coord_fixed": int("coord_fixed" in d.columns)})
        cur_area = dict(zip(d["상가업소번호"], d["area"]))
        for code, g in d[d.area.notna()].groupby("area"):
            r = {"period": per, "code": code, "n_stores": len(g)}
            vc = g["상권업종대분류명"].value_counts()
            for cat, col in [("음식", "n_food"), ("소매", "n_retail"), ("수리·개인", "n_personal"),
                             ("교육", "n_edu"), ("보건의료", "n_health"), ("숙박", "n_lodging")]:
                r[col] = int(vc.get(cat, 0))
            r["diversity_mid"] = round(shannon(g["상권업종중분류명"].value_counts()), 4)
            r["hhi_major"] = round(float(((vc / vc.sum()) ** 2).sum()), 4)
            r["branch_share"] = round(float(g["지점명"].fillna("").str.strip().ne("").mean()), 4)
            if prev_ids is not None:
                gid = set(g["상가업소번호"])
                prev_here = {i for i, a in prev_area.items() if a == code}
                r["n_open"] = len(gid - prev_ids)                 # 이번 분기에 새로 나타난 점포
                r["n_close"] = len(prev_here - ids)               # 직전 분기에 있었는데 사라진 점포
                r["n_prev"] = len(prev_here)
            rows.append(r)
        prev_ids, prev_area = ids, cur_area

    P = pd.DataFrame(rows)
    Cy = pd.DataFrame(city)
    Cy["chg_city"] = Cy.n_city.pct_change()
    Cy["data_break"] = ((Cy.chg_city.abs() > 0.08) | (Cy.keep_rate < 0.9)).astype(int)
    Cy["no_closure_info"] = (Cy.keep_rate >= 0.999).astype(int)          # 폐업이 기록되지 않은 분기
    P = P.merge(Cy, on="period")
    P["date"] = pd.to_datetime(P.period, format="%Y%m")
    P["share"] = P.n_stores / P.n_city                                     # 대전 전체 대비 비중 (단절 상쇄)
    base = P[P.period == "201912"].set_index("code").share                 # 코로나 직전 = 100
    P["share_idx"] = (P.share / P.code.map(base) * 100).round(2)
    P["food_ratio"] = (P.n_food / P.n_stores).round(4)
    P["open_rate"] = np.where(P.n_prev > 0, P.n_open / P.n_prev, np.nan)
    P["close_rate"] = np.where((P.n_prev > 0) & (P.no_closure_info == 0) & (P.data_break == 0),
                               P.n_close / P.n_prev, np.nan)
    P.loc[P.data_break == 1, "open_rate"] = np.nan
    P = P.merge(areas[["code", "name", "gu", "type"]], on="code")
    # 자료 구간: 단절 분기마다 새 구간 시작 (A: ~2022-12, B: 2023-03~2024-09, C: 2024-12~ …)
    #  → 구간이 다르면 같은 상권도 수집 기준이 달라 직접 비교하면 안 됨 (예: 도룡동 신세계 입점점포가 B 구간에서 누락)
    reg = Cy.assign(regime=Cy.data_break.cumsum().map(lambda i: "ABCDEFG"[i]))[["period", "regime"]]
    P = P.merge(reg, on="period")
    # 단절 분기에서 상권 비중이 20% 넘게 튀면 그 상권은 단절 영향이 큰 곳으로 표시
    P = P.sort_values(["code", "period"])
    P["break_jump"] = np.where(P.data_break == 1, P.groupby("code").share.pct_change().round(3), np.nan)
    sens = P[P.break_jump.abs() > 0.2].groupby("code").period.apply(list)
    P["break_sensitive"] = P.code.isin(sens.index).astype(int)
    if len(sens):
        print("단절 분기에 비중이 20% 넘게 튄 상권(해석 주의):", sens.to_dict())

    # 사건 변수: 사건 이후 경과 분기 (사건 전 음수)
    ev = pd.read_csv(C.ROOT / "data" / "area_events.csv", encoding="utf-8-sig")
    ev["date"] = pd.to_datetime(ev.date)
    for _, e in ev.iterrows():
        tgt = codes if e.area_codes == "ALL" else e.area_codes.split(";")
        col = f"ev_{e.event_id}"
        q = ((P.date.dt.year - e.date.year) * 4 + (P.date.dt.month - e.date.month) // 3)
        P[col] = np.where(P.code.isin(tgt), q, np.nan)
    P = P.sort_values(["code", "period"])
    P.to_csv(C.OUT_DIR / "store_panel.csv", index=False, encoding="utf-8-sig")
    Cy.to_csv(C.OUT_DIR / "store_panel_city.csv", index=False, encoding="utf-8-sig")
    print(f"\n패널 {P.code.nunique()}개 상권 × {P.period.nunique()}개 분기 = {len(P)}행 → outputs/store_panel.csv")
    print("자료 단절 분기:", Cy[Cy.data_break == 1].period.tolist(),
          "| 폐업 미기록 분기:", Cy[Cy.no_closure_info == 1].period.tolist())
    return P, Cy


if __name__ == "__main__":
    main()
