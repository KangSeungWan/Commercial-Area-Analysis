"""요인 분석: 무엇이 행정동 상권의 성장·쇠퇴를 만드나 (대전 82개 행정동, 2016 → 2026).

입력: outputs/dong_panel_land.csv, dong_panel_store.csv (build_dong_panel.py), data/daejeon_dong_2023.geojson,
      data/line1_stations.csv, 트램 정거장, 버스정류장(data/raw)
출력: outputs/factors_ols.csv, factors_rf.csv, factors_data.csv, factors.png

결과 변수 (2016 → 2026)
- land_rel_g : 공시지가 대전 대비 변화 (log)
- store_g    : 대전 내 점포 비중 변화 (log, 자료 단절 보정)
- close_rate : 분기 폐업률 평균 (2017~2025)
설명 변수 (2016년 시점 = 결과보다 앞선 값만 → 역인과 줄임)
- 규모 log(점포 수), 음식 비율, 소매 비율, 업종 다양성(섀넌), 체인 비율, log(공시지가 중앙값),
  지가 사전 추세(2010→2016), 1호선 역 거리, 트램 정거장 거리, 도심(대전역·정부청사) 거리, 버스정류장 밀도, 원도심(동·중·대덕구)
방법
- 표준화 다중회귀 (계수 = 설명 변수 1 표준편차 변화당 결과 변화, 표준편차 단위) + VIF(>5 이면 다중공선성 주의)
- 랜덤포레스트 + 순열 중요도 (5겹 교차검증 R² 함께 보고)
※ 관측 82개 → 인과가 아니라 '함께 움직이는 요인' 으로 해석
"""
import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.model_selection import KFold, cross_val_score

import config as C
from build_dataset import to_xy
from build_dong_layer import DONG, label_points, polygons
from build_dong_panel import CATS

LABEL = {"log_stores": "규모(점포 수)", "food_ratio": "음식점 비율", "retail_ratio": "소매 비율",
         "diversity": "업종 다양성", "branch_share": "체인 비율", "log_land": "지가 수준",
         "land_pre": "지가 사전 추세(2010→16)", "d_line1": "1호선 역 거리", "d_tram": "트램 정거장 거리",
         "d_center": "도심 거리", "bus_density": "버스정류장 밀도", "old_town": "원도심(동·중·대덕)"}
OUTCOMES = {"land_rel_g": "지가(대전 대비) 10년 변화", "store_g": "점포 비중 10년 변화", "close_rate": "폐업률"}


def shoelace_km2(ring):
    x, y = to_xy(ring[:, 1], ring[:, 0])
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 1e6


def build():
    gj = json.load(open(DONG, encoding="utf-8"))
    L = pd.read_csv(C.OUT_DIR / "dong_panel_land.csv", encoding="utf-8-sig")
    S = pd.read_csv(C.OUT_DIR / "dong_panel_store.csv", dtype={"period": str}, encoding="utf-8-sig")
    lr = L.pivot(index="k", columns="year", values="rel_idx")
    lm = L.pivot(index="k", columns="year", values="median_price")
    last = S.period.max()
    s16 = S[S.period == "201612"].set_index("k")
    sl = S[S.period == last].set_index("k")
    X = pd.DataFrame(index=sorted(L.k.unique()))
    X["si"] = L.drop_duplicates("k").set_index("k").si
    X["dong"] = L.drop_duplicates("k").set_index("k").dong
    # 결과
    X["land_rel_g"] = np.log(lr[2026] / lr[2016])
    X["store_g"] = np.log(sl.share_chain / s16.share_chain)
    X["close_rate"] = S[(S.period >= "201701") & (S.period <= "202512")].groupby("k").close_rate.mean() * 100
    # 설명 (2016)
    X["log_stores"] = np.log(s16.n_stores)
    cat = s16[[f"n_{c}" for c in CATS]]
    p = cat.div(cat.sum(axis=1), axis=0)
    X["food_ratio"] = p["n_음식"]
    X["retail_ratio"] = p["n_소매"]
    X["diversity"] = -(p * np.log(p.where(p > 0))).sum(axis=1)
    X["branch_share"] = s16.branch_share
    X["log_land"] = np.log(lm[2016])
    X["land_pre"] = np.log(lr[2016] / lr[2010])
    # 위치
    cen, area = {}, {}
    for k, f in enumerate(gj["features"]):
        ps = polygons(f["geometry"])
        ring = np.asarray(max(ps, key=lambda p_: len(p_[0]))[0])
        x, y = to_xy(ring[:, 1], ring[:, 0])
        area[k] = sum(shoelace_km2(np.asarray(pp[0])) for pp in ps)
        cen[k] = (x.mean(), y.mean())
    cxy = np.array([cen[k] for k in X.index])
    l1 = pd.read_csv(C.ROOT / "data" / "line1_stations.csv", encoding="utf-8-sig")
    exact = C.ROOT / "data" / "tram_stations.csv"
    tr = pd.read_csv(exact if exact.exists() else C.ROOT / "data" / "tram_stations_approx.csv", encoding="utf-8-sig")
    hubs = pd.DataFrame({"lat": [36.3321, 36.3587], "lon": [127.4348, 127.3829]})   # 대전역, 정부청사(둔산)
    for col, t in [("d_line1", l1), ("d_tram", tr), ("d_center", hubs)]:
        xy = np.c_[to_xy(t.lat, t.lon)]
        X[col] = cKDTree(xy).query(cxy)[0] / 1000
    b = pd.read_excel(C.raw_path("bus_national"))
    b = b[b["관리도시명"] == "대전BIS"]
    bk = pd.Series(label_points(gj, b["경도"].values, b["위도"].values))
    X["bus_density"] = bk[bk >= 0].value_counts().reindex(X.index).fillna(0) / pd.Series(area).reindex(X.index)
    X["old_town"] = X.si.isin(["동구", "중구", "대덕구"]).astype(int)
    X["area_km2"] = pd.Series(area).reindex(X.index)
    return X


def vif(Z):
    out = {}
    for c in Z.columns:
        o = Z.drop(columns=c).values
        A = np.c_[np.ones(len(Z)), o]
        b, *_ = np.linalg.lstsq(A, Z[c].values, rcond=None)
        r2 = 1 - ((Z[c].values - A @ b) ** 2).sum() / ((Z[c].values - Z[c].mean()) ** 2).sum()
        out[c] = 1 / max(1 - r2, 1e-6)
    return pd.Series(out)


def ols(y, Z):
    A = np.c_[np.ones(len(Z)), Z.values]
    b, *_ = np.linalg.lstsq(A, y, rcond=None)
    e = y - A @ b
    n, k = A.shape
    s2 = (e ** 2).sum() / (n - k)
    # HC1 강건 표준오차
    XtXi = np.linalg.pinv(A.T @ A)
    V = XtXi @ (A.T * e ** 2) @ A @ XtXi * n / (n - k)
    se = np.sqrt(np.diag(V))
    r2 = 1 - (e ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return pd.DataFrame({"coef": b[1:], "se": se[1:], "t": b[1:] / se[1:]}, index=Z.columns), r2


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

    X = build()
    X.round(4).to_csv(C.OUT_DIR / "factors_data.csv", encoding="utf-8-sig")
    feats = list(LABEL)
    D = X.dropna(subset=feats + list(OUTCOMES))
    # 극단값(행정동 1~2곳) 영향 줄이기: 결과·설명 변수를 1~99% 로 자름
    for c in feats + list(OUTCOMES):
        D[c] = D[c].clip(D[c].quantile(0.02), D[c].quantile(0.98))
    Z = (D[feats] - D[feats].mean()) / D[feats].std()
    V = vif(Z)
    print(f"관측 행정동 {len(D)}개 | VIF 최대 {V.max():.1f} ({LABEL[V.idxmax()]})")
    rows_o, rows_r = [], []
    fig, axes = plt.subplots(1, 3, figsize=(17, 6), sharey=True)
    for ax, (yc, yl) in zip(axes, OUTCOMES.items()):
        y = ((D[yc] - D[yc].mean()) / D[yc].std()).values
        T, r2 = ols(y, Z)
        T["vif"] = V
        for c, r in T.iterrows():
            rows_o.append({"outcome": yl, "factor": LABEL[c], "std_coef": r.coef, "se": r.se, "t": r.t, "vif": r.vif,
                           "sig": "**" if abs(r.t) > 2.58 else ("*" if abs(r.t) > 1.96 else ""), "r2": r2})
        rf = RandomForestRegressor(n_estimators=500, min_samples_leaf=3, random_state=42)
        cv = cross_val_score(rf, Z, y, cv=KFold(5, shuffle=True, random_state=42), scoring="r2").mean()
        rf.fit(Z, y)
        pi = permutation_importance(rf, Z, y, n_repeats=30, random_state=42)
        for c, m, s in zip(Z.columns, pi.importances_mean, pi.importances_std):
            # 방향: 상위 25% vs 하위 25% 의 부분 의존 차이
            lo, hi = Z[c].quantile(.25), Z[c].quantile(.75)
            Zl, Zh = Z.copy(), Z.copy(); Zl[c] = lo; Zh[c] = hi
            dirn = rf.predict(Zh).mean() - rf.predict(Zl).mean()
            rows_r.append({"outcome": yl, "factor": LABEL[c], "importance": m, "imp_sd": s, "direction": dirn, "cv_r2": cv})
        T = T.sort_values("coef")
        cols = ["C3" if abs(t) > 1.96 else "lightgray" for t in T.t]
        ax.barh([LABEL[c] for c in T.index], T.coef, xerr=1.96 * T.se, color=cols, ecolor="gray")
        ax.axvline(0, c="k", lw=.6)
        ax.set_title(f"{yl}\n회귀 R² {r2:.2f} · RF 교차검증 R² {cv:.2f}", fontsize=10)
    fig.suptitle("행정동 82개: 2016년 조건이 이후 10년 변화와 어떻게 함께 움직였나 (표준화 계수, 빨강 = 5% 유의)")
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "factors.png", dpi=130)
    O = pd.DataFrame(rows_o).round(3)
    R = pd.DataFrame(rows_r).round(4)
    O.to_csv(C.OUT_DIR / "factors_ols.csv", index=False, encoding="utf-8-sig")
    R.to_csv(C.OUT_DIR / "factors_rf.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    for yl in OUTCOMES.values():
        o = O[O.outcome == yl].set_index("factor")
        r = R[R.outcome == yl].set_index("factor")
        t = o[["std_coef", "t", "sig"]].join(r[["importance", "direction"]]).sort_values("importance", ascending=False)
        print(f"\n[{yl}] 회귀 R² {o.r2.iloc[0]:.2f}, RF 교차검증 R² {r.cv_r2.iloc[0]:.2f}")
        print(t.head(6).to_string())
    print("\n→ outputs/factors_ols.csv, factors_rf.csv, factors_data.csv, factors.png")


if __name__ == "__main__":
    main()
