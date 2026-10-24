"""대전 1호선 역세권 매출 차이 (8989 실측 카드매출, 행정동 82개 단면) → 땅값 효과의 매출 환산 근거

질문: 1호선 역 500m 안 점포 비중이 높은 동은, 원도심·인구·규모·업종 구성을 통제해도 점포당 카드매출이 높은가?
      같은 식으로 땅값(공시지가 중앙값)에서도 역세권 차이를 재서, 두 값의 비율 = '역세권 효과가 땅값 1%일 때 매출 몇 %'
입력: outputs/8989/sales_month.csv (동 × 소분류 × 월), dong_code_map.csv, outputs/dong_year_panel.csv, dong_profile.csv,
      data/raw/…상가_상권_정보_대전_2026….csv (점포 좌표), data/line1_stations.csv, data/tram_stations.csv
출력: outputs/station_sales_premium.csv (모형별 계수·95% 구간·n), outputs/station_sales_dong.csv (동별 변수)
모형: OLS + HC1 강건 표준오차.  y = log(점포당 월 카드매출, 2026-01~08 평균)
      처리 = 1호선 역 500m 안 점포 비율(0~1), 통제 = 원도심(동·중·대덕), log 주민 인구, log 점포 수, 음식점 비율
      위약(placebo) = 트램 정거장 500m 비율 (아직 개통 전 → 효과가 있으면 '역'이 아니라 '간선 도로변' 효과일 수 있음)
업종: 음식(음식점업+주점·음료), 전문 소매(종합소매·연료·무점포 제외), 전체
"""
import numpy as np
import pandas as pd

import config as C

OUT = C.OUT_DIR
M26 = [f"2026{m:02d}" for m in range(1, 9)]
GROUPS = {"음식": (["I2561", "I2562"], "음식"),
          "소매(전문)": (["G0472", "G0473", "G0474", "G0475", "G0476", "G0478"], "소매"),
          "전체": (None, None)}


def hav(lat1, lon1, lat2, lon2):
    R = 6371000; p1, p2 = np.radians(lat1), np.radians(lat2); dp = p2 - p1; dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def nearest(lat, lon, st):
    d = hav(lat[:, None], lon[:, None], st.lat.values[None], st.lon.values[None]); return d.min(1)


def ols_hc1(y, X, names):
    X = np.column_stack([np.ones(len(y))] + X); n, k = X.shape
    b = np.linalg.lstsq(X, y, rcond=None)[0]; e = y - X @ b
    XtXi = np.linalg.inv(X.T @ X); meat = (X * e[:, None] ** 2).T @ X
    V = XtXi @ meat @ XtXi * n / (n - k); se = np.sqrt(np.diag(V))
    r2 = 1 - e @ e / ((y - y.mean()) @ (y - y.mean()))
    return dict(zip(["const"] + names, b)), dict(zip(["const"] + names, se)), r2, n


def main():
    cm = pd.read_csv(OUT / "8989" / "dong_code_map.csv", dtype=str)
    s = pd.read_csv(OUT / "8989" / "sales_month.csv", dtype={"code": str, "stdrYm": str, "sclasCd": str})
    s = s[(s.level == "dong") & s.stdrYm.isin(M26)].merge(cm[["adstrdCode", "adm_cd2"]], left_on="code", right_on="adstrdCode")
    raw = next((C.ROOT / "data" / "raw").glob("*상가_상권_정보_대전_2026*.csv"))
    st = pd.read_csv(raw, dtype=str, usecols=["상권업종대분류명", "행정동코드", "경도", "위도"]).dropna(subset=["경도", "위도"])
    st = st.merge(cm[["adstrdCode", "adm_cd2"]], left_on="행정동코드", right_on="adstrdCode")
    lat, lon = st.위도.astype(float).values, st.경도.astype(float).values
    L1 = pd.read_csv(C.ROOT / "data" / "line1_stations.csv", encoding="utf-8-sig")
    TR = pd.read_csv(C.ROOT / "data" / "tram_stations.csv", encoding="utf-8-sig")
    st["d_l1"], st["d_tram"] = nearest(lat, lon, L1), nearest(lat, lon, TR)
    P = pd.read_csv(OUT / "dong_year_panel.csv", dtype={"dong_id": str})
    p26 = P[P.year == 2026].set_index("dong_id")

    D = pd.DataFrame(index=sorted(set(st.adm_cd2)))
    g = st.groupby("adm_cd2")
    D["n_stores"] = g.size(); D["l1_500"] = g.d_l1.apply(lambda v: (v <= 500).mean()); D["l1_1000"] = g.d_l1.apply(lambda v: (v <= 1000).mean())
    D["tram_500"] = g.d_tram.apply(lambda v: (v <= 500).mean())
    D["food_ratio"] = g.상권업종대분류명.apply(lambda v: (v == "음식").mean())
    D["old_town"] = p26.old_town.reindex(D.index); D["resident"] = p26.resident.reindex(D.index); D["land"] = p26.land_median.reindex(D.index)
    D["name"] = (p26.si + " " + p26.dong).reindex(D.index)
    for gname, (codes, cat) in GROUPS.items():
        ss = s if codes is None else s[s.sclasCd.isin(codes)]
        sales = ss.groupby(["adm_cd2", "stdrYm"]).useAmount.sum().groupby("adm_cd2").mean()
        n = D.n_stores if cat is None else st[st.상권업종대분류명 == cat].groupby("adm_cd2").size().reindex(D.index)
        D[f"sps_{gname}"] = sales.reindex(D.index) / n
        D[f"n_{gname}"] = n
    D.to_csv(OUT / "station_sales_dong.csv", encoding="utf-8-sig")

    rows = []
    def run(label, y, treat, df, extra=None, controls=True):
        d = df.dropna(subset=[y, treat, "resident", "land"]).copy()
        d = d[(d[y] > 0) & np.isfinite(np.log(d[y]))]
        X, nm = [d[treat].values], [treat]
        if controls:
            X += [d.old_town.values, np.log(d.resident.values), np.log(d.n_stores.values), d.food_ratio.values]; nm += ["old_town", "log_resident", "log_stores", "food_ratio"]
        if extra:
            for e_ in extra: X.append(d[e_].values); nm.append(e_)
        b, se, r2, n = ols_hc1(np.log(d[y].values), X, nm)
        rows.append(dict(model=label, y=y, treat=treat, coef=b[treat], se=se[treat], lo=b[treat] - 1.96 * se[treat], hi=b[treat] + 1.96 * se[treat],
                         premium_pct=(np.exp(b[treat]) - 1) * 100, r2=r2, n=n, **({f"coef_{e_}": b[e_] for e_ in (extra or [])})))
    base = D[D.n_stores >= 200]                       # 점포 적은 동 제외
    for gname in GROUPS:
        y = f"sps_{gname}"
        run(f"{gname}: 통제 없음", y, "l1_500", base, controls=False)
        run(f"{gname}: 기본", y, "l1_500", base)
        run(f"{gname}: + 트램 500m (위약 검정)", y, "l1_500", base, extra=["tram_500"])
        run(f"{gname}: 반경 1km", y, "l1_1000", base)
        run(f"{gname}: 점포당 금액 하위 동 제외", y, "l1_500", base[base[y] > base[y].quantile(.1)])
    # 같은 식으로 땅값 (공시지가 중앙값, 원/㎡)
    run("땅값: 기본", "land", "l1_500", base)
    run("땅값: + 트램 500m", "land", "l1_500", base, extra=["tram_500"])
    R = pd.DataFrame(rows).round(4)
    lb = R[R.model == "땅값: 기본"].coef.iloc[0]
    R["ratio_to_land"] = (R.coef / lb).round(3)
    R.to_csv(OUT / "station_sales_premium.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(R[["model", "coef", "se", "lo", "hi", "premium_pct", "r2", "n", "ratio_to_land"] + [c for c in R.columns if c.startswith("coef_")]].to_string(index=False))
    print("\n1호선 500m 비율 분포:", D.l1_500.describe().round(2)[["mean", "50%", "max"]].to_dict(), " 비율>0 동:", int((D.l1_500 > 0).sum()))


if __name__ == "__main__":
    main()
