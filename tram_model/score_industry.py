"""20개 상권 × 6개 업종 '업종 상권 점수' (100점, 트램 건설 전·후).

입력: outputs/store_panel.csv (상권 × 분기 × 업종 점포 수), dong_panel_store.csv (대전 전체 업종 합계용),
      area_profile.csv (폐업률·땅값), robust_radius.csv (정거장 500m 비율), tram_effect.py (트램 효과 수준·업종 비율)
출력: outputs/industry_scores.csv          (상권 × 업종: 원래 값 + 항목 점수 + 전·후 점수 + 순위)
      outputs/industry_score_weights.csv   (항목·가중치·데이터·계산·근거·한계)

항목 점수 = 그 업종 안에서 20개 상권을 줄 세운 백분위(0~100). 즉 '대전 20개 상권 중 상대 위치'.
점수 = Σ 가중치 × 항목 점수 / Σ 가중치(값이 있는 항목만). 건설 후 = 트램 항목(10점)을 넣고 나머지를 0.9배.
"""
import numpy as np
import pandas as pd

import config as C
import tram_effect as TE

IND = {"음식": ("n_food", "I2"), "소매": ("n_retail", "G2"), "수리·개인": ("n_personal", "S2"),
       "교육": ("n_edu", "P1"), "보건의료": ("n_health", "Q1"), "숙박": ("n_lodging", "I1")}
NOW, PAST = "202606", "202106"          # 최근 · 5년 전 (같은 2분기끼리)
MIN_N = 5                               # 업종 점포가 이보다 적으면 성장·특화 계산 안 함 (표본 부족)
ARTIFACT = {"A12"}                      # 도룡동: 신세계 입점점포 등록으로 점포 지표 왜곡 → 성장·생존 제외

# 항목: (이름, 건설 전 가중치, 방향, 데이터, 계산, 근거, 한계)
COMP = {
    "growth": ("성장", 30, 1, "상가정보 2021-06·2026-06",
               "그 업종의 대전 내 점포 비중 5년 변화(%)",
               "수요가 어디로 옮겨 가는지 가장 직접 보여줌. 업종 분석에서 원도심→신도심 이동 확인",
               "자료 수집 기준 변경(2026-06)은 대전 전체 대비 비중이라 상당 부분 상쇄"),
    "size": ("규모", 20, 1, "상가정보 2026-06", "그 업종 점포 수 (로그)",
             "점포가 모인 곳 = 손님이 모이는 곳 (집적 효과)", "많을수록 경쟁도 큼 — 포화 여부는 반영 못 함"),
    "lq": ("특화도", 15, 1, "상가정보 2026-06", "입지계수 = (상권 안 업종 비율) ÷ (대전 업종 비율)",
           "1보다 크면 그 업종이 특히 모이는 상권 (업종 특화 상권)", "특화 = 과포화일 수도 있음"),
    "survival": ("생존", 20, -1, "상가정보 2023~2026 분기 개·폐업", "상권 분기 폐업률(%), 낮을수록 높은 점수",
                 "문 닫는 가게가 적은 상권이 버티기 쉬움", "업종별 폐업률 자료가 없어 상권 공통값"),
    "land": ("땅값 흐름", 15, 1, "개별공시지가 2021·2026", "상권 땅값 5년 상승률(%)",
             "입지 가치·수요가 오르는 신호", "임대료 부담이 커질 수도 있음 (상권 공통값)"),
    "tram": ("트램 효과", 0, 1, "대전 1호선 개통 전후 땅값 + 정거장 좌표",
             "정거장 500m 안 비율 × 업종 민감도(음식 0.99·소매 0.86·기타 0.24) → 0~100",
             "트램이 닿는 정도. 대전 1호선에서 역 500m 땅값이 개통 초기 +1.8%(기본) 더 오름",
             "건설 후에만 반영(10점). 지하철 효과를 빌려 써 과대 가능, 공사 기간 손실은 반영 안 함"),
}
TRAM_W = 10


def pct_rank(s):
    """0~100 백분위 (값 없는 곳은 NaN). 동점은 평균 순위."""
    r = s.rank(method="average")
    n = s.notna().sum()
    return (r - 1) / (n - 1) * 100 if n > 1 else r * 0 + 50


def main():
    sp = pd.read_csv(C.OUT_DIR / "store_panel.csv", dtype={"period": str}, encoding="utf-8-sig")
    dp = pd.read_csv(C.OUT_DIR / "dong_panel_store.csv", dtype={"period": str}, encoding="utf-8-sig")
    prof = pd.read_csv(C.OUT_DIR / "area_profile.csv", encoding="utf-8-sig").set_index("code")
    rr = pd.read_csv(C.OUT_DIR / "robust_radius.csv", encoding="utf-8-sig").set_index("zone")
    city = dp.groupby("period")[["n_stores"] + [f"n_{k}" for k in IND]].sum()
    L = TE.levels()
    max_ratio = max(TE.cat_ratio(c) for _, c in IND.values())

    now = sp[sp.period == NOW].set_index("code")
    past = sp[sp.period == PAST].set_index("code")
    rows = []
    for ind, (col, cat) in IND.items():
        cn, cp = city.loc[NOW, f"n_{ind}"], city.loc[PAST, f"n_{ind}"]
        ratio = TE.cat_ratio(cat)
        for code in prof.index:
            n1 = float(now.loc[code, col]) if code in now.index else np.nan
            n0 = float(past.loc[code, col]) if code in past.index else np.nan
            tot = float(now.loc[code, "n_stores"]) if code in now.index else np.nan
            ok = (n1 >= MIN_N) and (n0 >= MIN_N)
            in500 = float(rr.in500.get(code, 0))
            rows.append({
                "code": code, "name": prof.loc[code, "name"], "industry": ind, "n_stores": n1, "n_stores_5y_ago": n0,
                "growth": (n1 / cn / (n0 / cp) - 1) * 100 if ok and code not in ARTIFACT else np.nan,
                "size": np.log1p(n1) if pd.notna(n1) else np.nan,
                "lq": (n1 / tot) / (cn / city.loc[NOW, "n_stores"]) if n1 >= MIN_N and tot > 0 else np.nan,
                "survival": prof.loc[code, "close_rate_q_pct"] if code not in ARTIFACT else np.nan,
                "land": prof.loc[code, "land_chg_5y_pct"],
                "tram": in500 * ratio / max_ratio * 100,
                "in500": in500,
                **{f"tram_effect_{s}": round(in500 * np.expm1(L[s]["log"] * ratio) * 100, 2) for s in TE.SCEN},
                "flag": ("점포 지표 왜곡(신세계 입점 등록)" if code in ARTIFACT else
                         (f"업종 점포 {MIN_N}개 미만 → 성장·특화 제외" if not ok else "")),
            })
    D = pd.DataFrame(rows)

    # 항목 점수: 업종 안에서 20개 상권 백분위 (트램은 절대 척도 0~100)
    for k, (_, _, sign, *_r) in COMP.items():
        if k == "tram":
            D["s_tram"] = D.tram.round(1)
        else:
            D[f"s_{k}"] = D.groupby("industry")[k].transform(lambda s: pct_rank(s * sign)).round(1)

    def total(df, w):
        S = df[[f"s_{k}" for k in w]]
        W = pd.DataFrame({f"s_{k}": np.where(S[f"s_{k}"].notna(), v, 0.0) for k, v in w.items()}, index=df.index)
        return ((S.fillna(0) * W).sum(axis=1) / W.sum(axis=1)).round(1)

    w_before = {k: v[1] for k, v in COMP.items() if k != "tram"}
    w_after = {k: v * (100 - TRAM_W) / 100 for k, v in w_before.items()} | {"tram": TRAM_W}
    D["score_before"] = total(D, w_before)
    D["score_after"] = total(D, w_after)
    few = D.n_stores.fillna(0) < MIN_N                      # 업종 점포가 거의 없으면 점수 안 매김
    D.loc[few, ["score_before", "score_after"]] = np.nan
    D.loc[few, "flag"] = f"업종 점포 {MIN_N}개 미만 → 점수 없음"
    D["score_change"] = (D.score_after - D.score_before).round(1)
    for t in ("before", "after"):
        D[f"rank_{t}"] = D.groupby("industry")[f"score_{t}"].rank(ascending=False, method="min").astype("Int64")
    D["rank_change"] = D.rank_before - D.rank_after          # + = 트램 후 순위 상승
    D = D.sort_values(["industry", "score_before"], ascending=[True, False])
    D.round(4).to_csv(C.OUT_DIR / "industry_scores.csv", index=False, encoding="utf-8-sig")

    W = pd.DataFrame([{"key": k, "item": v[0], "weight_before": v[1], "weight_after": round(w_after[k], 1),
                       "data": v[3], "method": v[4], "rationale": v[5], "limit": v[6]} for k, v in COMP.items()])
    W.to_csv(C.OUT_DIR / "industry_score_weights.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 220)
    for ind in IND:
        g = D[D.industry == ind].sort_values("score_after", ascending=False).head(5)
        print(f"\n[{ind}] 상위 5 (건설 후)\n", g[["name", "n_stores", "score_before", "score_after", "rank_change",
                                              "flag"]].to_string(index=False))
    print("\n가중치\n", W[["item", "weight_before", "weight_after"]].to_string(index=False))
    print("→ outputs/industry_scores.csv, industry_score_weights.csv")


if __name__ == "__main__":
    main()
