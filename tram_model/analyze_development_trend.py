"""B6: '트램 없어도 오르는 곳' — 신도시·택지 개발 때문에 땅값이 오르는 동을 따로 표시하고,
트램(1호선) 효과 추정이 개발지에 끌려가지 않았는지 점검.

입력: outputs/dong_panel_land.csv, dong_scores.csv, dong_tram_money.csv, landprice_parcels.csv.gz, landprice_long.pkl
출력 (outputs/)
- development_trend_dong.csv   : 82개 동별 필지 수 증가(새 택지), 트램 확정 전 땅값 추세, 표시(flag)와 이유
- development_trend_checks.csv : 개발지를 뺀 1호선 효과·트램 확정 효과, 트램 금액 중 개발지 몫
  dev_kind: '개발지'(새 택지·확정 사업) / '트램 전 상승'(개발 표시는 없지만 트램 확정 전부터 더 오름)

표시 기준 ('트램 없어도 오르는 곳')
 1) 새 택지: '대' 필지 수가 2010→2026 1.5배 이상 (논·밭이 택지로 바뀌어 필지가 쪼개짐 = 신도시 개발)
 2) 트램 전 상승: 2014→2019 (2019-01 예타 면제 전 5년) 땅값이 대전 평균보다 10% 이상 더 오름
 3) 확정된 개발 사업이 있는 동 (아래 PROJECTS, 기사 출처)
"""
import numpy as np
import pandas as pd

import config as C
from analyze_landprice import event_study, load, pct, window_mean

PG_MIN = 1.5            # 필지 수 증가 배수
PRE_MIN = 0.10          # 트램 확정 전 대전 대비 초과 상승

# 동 이름 → (사업, 시기, 출처). 동 경계와 사업 구역이 정확히 같지는 않음(일원 기준)
PROJECTS = {
    "학하동": ("도안 2단계(용계·학하·복용 일원)", "2022-10 분양 시작, 일부 2029 입주 예정",
            "뉴데일리 2022-10-06, 한경비즈니스 2026-06"),
    "상대동": ("도안 2단계 인접(용계동 일원)", "2022~ 분양, 도안자이 센텀리체 2029 입주 예정", "한경비즈니스 2026-06"),
    "관저1동": ("도안 2단계(관저 일원)", "2022~", "한경비즈니스 2026-06"),
    "관저2동": ("도안 2단계(관저 일원)", "2022~", "한경비즈니스 2026-06"),
    "도안동": ("갑천지구 친수구역(도안 3단계 쪽, 트리풀시티)", "2018·2020·2022 분양", "딜사이트, MTN 2020-10"),
    "원신흥동": ("갑천지구 친수구역(트리풀시티)", "2018·2020·2022 분양", "딜사이트, MTN 2020-10"),
    "회덕동": ("연축 도시개발(연축동, 1,359호·혁신도시 병행)", "2024-04 실시계획 인가, 아직 땅값에 반영 전",
            "뉴스서울 2024-04-28"),
}


def dong_table():
    p = pd.read_csv(C.OUT_DIR / "dong_panel_land.csv", encoding="utf-8-sig")
    q = p[p["sample"] == "대"]
    n = q.pivot_table(index="dong_id", columns="year", values="n_parcels")
    r = q.pivot_table(index="dong_id", columns="year", values="rel_idx")
    s = pd.read_csv(C.OUT_DIR / "dong_scores.csv", encoding="utf-8-sig").set_index("dong_id")
    d = pd.DataFrame({
        "name": s["name"], "dong": s["dong"],
        "parcel_x_2010_26": (n[2026] / n[2010]).round(2),
        "pre_rise_2014_19": (r[2019] / r[2014] - 1).round(3),
        "post_rise_2019_26": (r[2026] / r[2019] - 1).round(3),
        "in500": s["in500"], "quadrant": s["quadrant"],
    })
    reasons, proj = [], []
    for _, x in d.iterrows():
        why = []
        if x.parcel_x_2010_26 >= PG_MIN:
            why.append(f"새 택지(필지 {x.parcel_x_2010_26:.1f}배)")
        if x.pre_rise_2014_19 >= PRE_MIN:
            why.append(f"트램 확정 전 5년 대전보다 {x.pre_rise_2014_19 * 100:+.0f}%")
        pj = PROJECTS.get(x.dong)
        if pj:
            why.append(pj[0])
        reasons.append(" · ".join(why))
        proj.append(f"{pj[0]} — {pj[1]} ({pj[2]})" if pj else "")
    d["dev_flag"] = [bool(w) for w in reasons]
    d["dev_kind"] = ["개발지" if (x.parcel_x_2010_26 >= PG_MIN or x.dong in PROJECTS) else ("트램 전 상승" if w else "")
                     for (_, x), w in zip(d.iterrows(), reasons)]
    d["dev_reason"] = reasons
    d["project"] = proj
    return d


def parcel_checks(d):
    G, W = load()
    cnt = W.notna().groupby(G.dong_code.reindex(W.index).values).sum()        # 법정동 × 연도 '대' 필지 수
    def ratio(a, b):
        return (cnt[b] / cnt[a].replace(0, np.nan)).fillna(np.inf)
    dev_old = set(cnt.index[(ratio(1996, 2005) >= PG_MIN) | (ratio(2005, 2011) >= PG_MIN)])  # 1호선 당시 택지
    dev_new = set(cnt.index[ratio(2010, 2026) >= PG_MIN])                                    # 트램 시기 택지
    in_old = G.dong_code.isin(dev_old)
    in_new = G.dong_code.isin(dev_new)
    old_parcel = W[1996].notna().reindex(G.index)

    rows = []
    ctrl = (G.d_l1 > 1000) & (G.d_l1 <= 3000)
    tr = (G.l1_phase == 1) & (G.d_l1 <= 500)
    for lab, keep in [("1호선 1단계 기본 (역 500m vs 1~3km)", None),
                      ("개발지 법정동 제외 (1996~2011 필지 1.5배 이상)", ~in_old),
                      ("1996년에 이미 있던 필지만", old_parcel)]:
        t, c = (tr, ctrl) if keep is None else (tr & keep, ctrl & keep)
        es, boot, yrs = event_study(G, W, t, c, 2005, list(range(2000, 2011)))
        m, lo, hi = window_mean(es, boot, yrs, range(2007, 2011))
        rows.append({"check": "1호선 땅값 효과", "variant": lab, "effect_pct": pct(m), "ci_lo": pct(lo),
                     "ci_hi": pct(hi), "n_treat": int(es.n_treat.max()), "n_ctrl": int(es.n_ctrl.max())})

    far = G.d_l1 > 500
    tr2 = (G.d_tram <= 500) & far
    ct2 = (G.d_tram > 1000) & (G.d_tram <= 3000) & far
    for lab, keep in [("트램 확정(2019) 뒤 2023~26 기본", None),
                      ("새 택지 법정동 제외 (2010~26 필지 1.5배 이상)", ~in_new)]:
        t, c = (tr2, ct2) if keep is None else (tr2 & keep, ct2 & keep)
        es, boot, yrs = event_study(G, W, t, c, 2019, list(range(2014, 2027)))
        m, lo, hi = window_mean(es, boot, yrs, range(2023, 2027))
        pm, *_ = window_mean(es, boot, yrs, range(2014, 2017))
        rows.append({"check": "트램 확정 뒤 땅값(기대 효과)", "variant": lab, "effect_pct": pct(m), "ci_lo": pct(lo),
                     "ci_hi": pct(hi), "pre_2014_16_pct": pct(pm),
                     "n_treat": int(es.n_treat.max()), "n_ctrl": int(es.n_ctrl.max())})

    money = pd.read_csv(C.OUT_DIR / "dong_tram_money.csv", encoding="utf-8-sig").set_index("dong_id")
    kind = d.dev_kind.reindex(money.index).fillna("")
    tot = money.gain_base_eok.sum()
    for k in ("개발지", "트램 전 상승"):
        g = money.gain_base_eok[kind == k]
        rows.append({"check": "트램 효과 금액(기본)", "variant": f"{k} 동의 몫",
                     "effect_pct": round(g.sum() / tot * 100, 1), "n_treat": int((kind == k).sum()),
                     "note": f"{g.sum():,.0f}억 / {tot:,.0f}억"})
    return pd.DataFrame(rows)


def main():
    d = dong_table()
    d.to_csv(C.OUT_DIR / "development_trend_dong.csv", encoding="utf-8-sig")
    f = d[d.dev_flag]
    print(f"[트램 없어도 오르는 곳] {len(f)}개 동 (정거장 500m 걸친 곳 {int((f.in500 > 0).sum())}곳)")
    print(f[["name", "dev_reason", "in500", "quadrant"]].to_string())
    print("\n필지 자료로 점검 중 ...", flush=True)
    R = parcel_checks(d)
    R.to_csv(C.OUT_DIR / "development_trend_checks.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print(R.to_string(index=False))
    print("→ outputs/development_trend_dong.csv, development_trend_checks.csv")


if __name__ == "__main__":
    main()
