"""B7: 대전 카페는 이미 포화인가? → 1호선(2006) 카페 효과를 지금(2030 개통)에 그대로 써도 되는지 점검.

입력: data/raw/permits/*.csv (일반·휴게음식점·제과점 인허가), data/line1_stations.csv, data/tram_stations.csv,
      outputs/sector_evidence_checks.csv (카페 기본 효과)
출력 (outputs/)
- cafe_saturation_city.csv   : 대전 전체 연도별 영업 카페 수·개업·폐업·폐업률·순증·음식점 중 카페 비중 (2002~2025)
- cafe_saturation_checks.csv : ① 포화 지표 요약 ② 1호선 효과를 2005년 격자 카페 비중 높은/낮은 절반으로 나눈 이중차분
                               ③ 외삽 범위: 1호선 당시 처리 격자 카페 비중 vs 지금 트램 정거장 500m 격자 카페 비중
판단
- 포화 신호 = 최근 순증 둔화 + 폐업률 상승. 카페 비중이 이미 높던 격자에서 효과가 작았다면,
  지금처럼 비중이 높은 곳에 1호선 효과(+24.8%)를 그대로 쓰면 과대 → '높음' 시나리오를 줄이거나 외삽 한계로 표시
"""
import os

import numpy as np
import pandas as pd

import analyze_line1_permits as AP
import config as C
from check_sector_evidence import panel_all_cells

YEARS_CITY = list(range(2002, 2026))


def active_at(p, t):
    end = pd.Timestamp(f"{t}-12-31")
    return (p.open <= end) & (p.close.isna() | (p.close > end))


def city_series(p):
    rows = []
    cafe = p[p.sector == "카페"]
    prev = None
    for t in YEARS_CITY:
        a = int(active_at(cafe, t).sum()); f = int(active_at(p, t).sum())
        s, e = pd.Timestamp(f"{t}-01-01"), pd.Timestamp(f"{t}-12-31")
        op = int(cafe.open.between(s, e).sum()); cl = int(cafe.close.between(s, e).sum())
        rows.append({"year": t, "cafes": a, "food_all": f, "cafe_share_pct": round(a / f * 100, 2),
                     "opened": op, "closed": cl, "close_rate_pct": round(cl / prev * 100, 1) if prev else np.nan,
                     "net_growth_pct": round((a / prev - 1) * 100, 1) if prev else np.nan})
        prev = a
    return pd.DataFrame(rows)


def main():
    if not os.path.isdir(AP.RAW_DIR):
        print("인허가 자료 없음 → 건너뜀"); return
    p = AP.load_permits(); st = AP.load_stations(); p = AP.assign_space(p, st)
    p["sector"] = AP.sector_of(p)
    S = city_series(p)
    S.to_csv(C.OUT_DIR / "cafe_saturation_city.csv", index=False, encoding="utf-8-sig")
    print(S.to_string(index=False))

    rows = []
    def per(a, b, col):
        x = S[S.year.between(a, b)][col]; return round(float(x.mean()), 1)
    for lab, a, b in [("1호선 개통 전후(2003~2010)", 2003, 2010), ("확산기(2011~2018)", 2011, 2018), ("최근(2019~2025)", 2019, 2025)]:
        rows.append({"part": "① 포화 지표", "item": lab, "net_growth_pct": per(a, b, "net_growth_pct"),
                     "close_rate_pct": per(a, b, "close_rate_pct"),
                     "cafe_share_pct": float(S[S.year == b].cafe_share_pct.iloc[0])})

    # ② 1호선 카페 효과 이질성: 2005년 격자 '음식점 중 카페 비중' 높은/낮은 절반 (처리군 중앙값 기준)
    q = AP.build_sample(p); q["sector"] = AP.sector_of(q)
    sp = panel_all_cells(q, "카페")
    b05 = sp[sp.year == AP.BASE_YEAR].set_index("cell")
    share05 = b05.active / b05["all"].clip(lower=1)
    pos = share05[(b05.treat == 1) & (share05 > 0)]
    med = float(pos.median())                       # 2005년 카페가 있던 처리 격자의 비중 중앙값
    sp["s05"] = sp.cell.map(share05)
    for lab, m in [("전체(2005 음식점 있던 격자, 카페 0곳 포함)", np.ones(len(sp), bool)),
                   ("2005 카페 0곳 격자", (sp.s05 == 0).values),
                   (f"2005 카페 비중 낮음 (0 < 비중 ≤ {med * 100:.1f}%)", ((sp.s05 > 0) & (sp.s05 <= med)).values),
                   (f"2005 카페 비중 높음 (> {med * 100:.1f}%, 지금 정거장 주변과 비슷한 수준)", (sp.s05 > med).values)]:
        d = sp[m]
        b, se, G = AP.did(d, "treat", AP.OPEN_YEAR)
        rows.append({"part": "② 1호선 카페 효과 (비중별)", "item": lab, "effect_pct": round(AP.pct(b), 1),
                     "ci_lo": round(AP.pct(b - 1.96 * se), 1), "ci_hi": round(AP.pct(b + 1.96 * se), 1),
                     "p": round(AP._pval(b / se), 4) if se > 0 else np.nan, "cells": G,
                     "treat_cells": int(d[d.year == AP.BASE_YEAR].treat.sum())})

    # ③ 외삽 범위: 1호선 처리 격자(2005) vs 트램 정거장 500m 격자(2025) 카페 비중
    tr = pd.read_csv(C.ROOT / "data" / "tram_stations.csv", encoding="utf-8-sig")
    l1 = st
    p["d_tram"] = AP._min_dist(p.lat, p.lon, tr.lat, tr.lon)
    now = p[active_at(p, 2025) & (p.d_tram <= 500) & (p.d_any > 500)]           # 1호선 역 500m 밖 = 새 역세권
    g = now.groupby("cell").agg(all=("sector", "size"), cafe=("sector", lambda s: (s == "카페").sum()))
    g = g[g["all"] >= 1]
    sh_now = g.cafe / g["all"]
    sh_then = share05[b05.treat == 1]
    w_now = float(g.cafe.sum() / g["all"].sum()); w_then = float(b05[b05.treat == 1].active.sum() / b05[b05.treat == 1]["all"].sum())
    for lab, v, w in [("1호선 처리 격자 (2005)", sh_then, w_then), ("트램 정거장 500m 격자 (2025, 1호선 역세권 밖)", sh_now, w_now)]:
        rows.append({"part": "③ 외삽 범위", "item": lab, "cafe_share_pct": round(w * 100, 1),
                     "median_pct": round(float(v.median()) * 100, 1), "p90_pct": round(float(v.quantile(.9)) * 100, 1),
                     "cells": int(len(v))})
    out_range = float((sh_now > sh_then.quantile(.9)).mean())
    above_med = float((sh_now > med).mean())
    rows.append({"part": "③ 외삽 범위", "item": "지금 정거장 격자 중 1호선 당시 처리 격자 상위 10% 비중보다 높은 비율",
                 "share_pct": round(out_range * 100, 1)})
    rows.append({"part": "③ 외삽 범위", "item": "지금 정거장 격자 중 '비중 높음' 기준선을 넘는 비율",
                 "share_pct": round(above_med * 100, 1)})
    R = pd.DataFrame(rows)
    R.to_csv(C.OUT_DIR / "cafe_saturation_checks.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(R.to_string(index=False))
    print("→ outputs/cafe_saturation_city.csv, cafe_saturation_checks.csv")


if __name__ == "__main__":
    main()
