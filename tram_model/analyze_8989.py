"""
8989 실측 카드매출·유동인구 활용 분석 (2026-10-24)

입력: outputs/8989/dong_panel_8989.csv, sales_month.csv, dong_code_map.csv (build_8989_tables.py)
      outputs/dong_profile.csv, survey_dong.csv, dong_panel_land.csv, area_scores.csv, area_profile.csv, sangkwon_polygons.geojson
      data/raw/소상공인…상가_상권_정보_대전_202606.csv (점포 좌표·행정동코드)
출력: outputs/8989/
  dong_8989_summary.csv     82개 행정동 요약: 2026 월평균 매출, 전년 대비 증감, 점포당 매출, 업종 비중, 유동인구, 폐업률 + 기존 지표(트램 500m 점포 비율, 땅값, 실태조사)
  validation_8989.csv       실측 매출·유동인구 증감 vs 기존 쇠퇴 지표 스피어만 상관 (외부 검증)
  tram_zone_compare.csv     정거장 500m 점포 비율로 나눈 동 그룹별 매출·유동인구 증감 비교
  area_dong_share.csv       상권 20개 × 행정동: 상권 안 점포 수, 해당 동 점포 중 비율 (배분 가중치)
  area_sales_8989.csv       상권 20개 × 월 × 대분류 매출 (행정동 실측을 점포 비율로 배분한 추정치)
  area_sales_summary.csv    상권 20개 요약 (2026 월평균, 전년 대비, 점포당, 기존 위험·성장 점수와 비교)
  *.png (matplotlib 있을 때)
배분 방식: 상권 매출(업종 i, 월 t) = Σ_동 [동 매출(i,t) × (상권 안 그 동 점포 수 / 그 동 전체 점포 수)]  — 점포 수는 상가정보 2026-06, 업종 구분 없이 동일 비율 적용
"""
import json, re
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
O8 = HERE / "outputs" / "8989"; OUT = HERE / "outputs"
LCL = ["도소매", "숙박", "음식점", "부동산", "교육", "보건의료", "여가 스포츠", "서비스"]
P25 = [f"2025{m:02d}" for m in range(1, 9)]; P26 = [f"2026{m:02d}" for m in range(1, 9)]  # 1~8월 동월 비교
import sys
if not (O8 / "dong_panel_8989.csv").exists():
    print("outputs/8989/dong_panel_8989.csv 없음 → 건너뜀"); sys.exit(0)

panel = pd.read_csv(O8 / "dong_panel_8989.csv", dtype={"plcCd": str, "stdrYm": str, "adstrdCode": str, "adm_cd2": str})
cmap = pd.read_csv(O8 / "dong_code_map.csv", dtype=str)
prof = pd.read_csv(OUT / "dong_profile.csv", dtype={"id": str})
survey = pd.read_csv(OUT / "survey_dong.csv", dtype={"동코드": str})
land = pd.read_csv(OUT / "dong_panel_land.csv", dtype={"dong_id": str})

# ── 1. 행정동 요약 ──
def avg(df, months, col): return df[df.stdrYm.isin(months)].groupby("plcCd")[col].mean()
g = panel.groupby("plcCd")
S = cmap.rename(columns={"admdstCd": "plcCd"}).set_index("plcCd")
S["sales_2026_m"] = avg(panel, P26, "useAmount_합계")
S["sales_2025_m"] = avg(panel, P25, "useAmount_합계")
S["sales_yoy_pct"] = (S.sales_2026_m / S.sales_2025_m - 1) * 100
S["cnt_yoy_pct"] = (avg(panel, P26, "useCo_도소매") + avg(panel, P26, "useCo_음식점")) / (avg(panel, P25, "useCo_도소매") + avg(panel, P25, "useCo_음식점")) * 100 - 100
for l in LCL: S[f"share_{l}"] = avg(panel, P26, f"useAmount_{l}") / S.sales_2026_m
S["stores_202608"] = panel[panel.stdrYm == "202608"].set_index("plcCd").stores_survived_at_baseYm
S["sales_per_store_2026"] = S.sales_2026_m / S.stores_202608
S["floating_2026"] = avg(panel, P26, "floating_daily"); S["floating_2025"] = avg(panel, P25, "floating_daily")
S["floating_2024"] = avg(panel, [f"2024{m:02d}" for m in range(1, 9)], "floating_daily")
S["floating_yoy_pct"] = (S.floating_2026 / S.floating_2025 - 1) * 100
S["floating_chg_24_26_pct"] = (S.floating_2026 / S.floating_2024 - 1) * 100
S["resident_2026"] = avg(panel, P26, "resident"); S["resident_chg_24_26_pct"] = (S.resident_2026 / avg(panel, [f"2024{m:02d}" for m in range(1, 9)], "resident") - 1) * 100
cl = panel[panel.stdrYm.between("202509", "202608")].groupby("plcCd").clsbiz.sum()
S["closure_rate_12m_pct"] = cl / S.stores_202608 * 100
S = S.reset_index()
# 기존 지표 붙이기 (통계청 코드 adm_cd2 = dong_profile.id)
S = S.merge(prof[["id", "nearest_tram", "nearest_tram_m", "n_stores", "tram500_share", "land_price", "land_chg_5y_pct", "land_chg_10y_pct", "tram_effect", "areas"]].rename(columns={"id": "adm_cd2", "n_stores": "n_stores_profile"}), on="adm_cd2", how="left")
S = S.merge(survey[["동코드", "n_valid", "decline_pct", "closing_pct", "bad_pct"]].rename(columns={"동코드": "adm_cd2"}), on="adm_cd2", how="left")
lr = land.sort_values("year").groupby("dong_id").rel_idx.last().rename("land_rel_idx_latest")
S = S.merge(lr, left_on="adm_cd2", right_index=True, how="left")
S["old_town"] = S.sgg.isin(["동구", "중구"]).astype(int)   # 원도심 대용(동구·중구). analyze_factors 의 원도심 정의와 다를 수 있음
S["tram_zone"] = pd.cut(S.tram500_share.fillna(0), [-0.01, 0.1, 0.5, 1.01], labels=["영향권 밖(<10%)", "일부(10~50%)", "영향권(≥50%)"])
S = S.sort_values("sales_yoy_pct", ascending=False)
S.to_csv(O8 / "dong_8989_summary.csv", index=False, encoding="utf-8-sig")
print("dong_8989_summary:", S.shape)
print(S[["sgg", "dong", "sales_2026_m", "sales_yoy_pct", "floating_yoy_pct", "tram500_share", "bad_pct"]].head(8).round(1).to_string(index=False))

# ── 2. 외부 검증: 스피어만 상관 ──
def spearman(x, y):
    d = pd.DataFrame({"x": x, "y": y}).dropna(); n = len(d)
    if n < 5: return np.nan, np.nan, n
    r = d.x.rank().corr(d.y.rank())
    t = r * np.sqrt((n - 2) / max(1e-9, 1 - r * r))
    # t 분포 양측 p (정규 근사 대신 간단한 t 근사: scipy 없이)
    from math import erf, sqrt
    p = 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2))))  # 정규 근사(n≥30이면 충분)
    return round(r, 3), round(p, 4), n
rows = []
for y in ["sales_yoy_pct", "cnt_yoy_pct", "floating_yoy_pct", "floating_chg_24_26_pct", "closure_rate_12m_pct", "sales_per_store_2026"]:
    for x in ["tram500_share", "nearest_tram_m", "land_chg_5y_pct", "land_chg_10y_pct", "land_rel_idx_latest", "bad_pct", "decline_pct", "old_town", "resident_chg_24_26_pct", "share_음식점", "share_도소매"]:
        r, p, n = spearman(S[x], S[y]); rows.append(dict(y=y, x=x, spearman=r, p_normal_approx=p, n=n))
V = pd.DataFrame(rows); V.to_csv(O8 / "validation_8989.csv", index=False, encoding="utf-8-sig")
print("\n[검증] |ρ|≥0.25 인 조합")
print(V[V.spearman.abs() >= 0.25].to_string(index=False))

# ── 3. 트램 영향권 그룹 비교 ──
T = S.groupby("tram_zone", observed=True).agg(n=("dong", "size"), sales_yoy_mean=("sales_yoy_pct", "mean"), sales_yoy_median=("sales_yoy_pct", "median"),
    floating_yoy_mean=("floating_yoy_pct", "mean"), floating_24_26_mean=("floating_chg_24_26_pct", "mean"), closure_mean=("closure_rate_12m_pct", "mean"),
    sales_per_store_mean=("sales_per_store_2026", "mean"), bad_pct_mean=("bad_pct", "mean")).round(2).reset_index()
T.to_csv(O8 / "tram_zone_compare.csv", index=False, encoding="utf-8-sig"); print("\n[트램 영향권 비교]\n", T.to_string(index=False))

# ── 4. 상권 20개 ← 행정동 매출 배분 ──
def point_in_poly(lon, lat, poly):          # ray casting (shapely 없이)
    x, y = np.asarray(lon), np.asarray(lat); inside = np.zeros(len(x), bool)
    px, py = np.array(poly)[:, 0], np.array(poly)[:, 1]; n = len(px)
    j = n - 1
    for i in range(n):
        cond = ((py[i] > y) != (py[j] > y)) & (x < (px[j] - px[i]) * (y - py[i]) / (py[j] - py[i] + 1e-12) + px[i])
        inside ^= cond; j = i
    return inside
raw = next(p for p in (HERE / "data" / "raw").glob("*상가_상권_정보_대전_2026*.csv"))
st = pd.read_csv(raw, dtype=str, usecols=["상권업종대분류명", "행정동코드", "경도", "위도"]).dropna(subset=["경도", "위도"])
st["lon"] = st.경도.astype(float); st["lat"] = st.위도.astype(float)
gj = json.load(open(OUT / "sangkwon_polygons.geojson", encoding="utf-8"))
st["area"] = None
for f in gj["features"]:
    geom = f["geometry"]; polys = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
    m = np.zeros(len(st), bool)
    for poly in polys: m |= point_in_poly(st.lon.values, st.lat.values, poly)
    st.loc[m & st.area.isna(), "area"] = f["properties"]["code"]
dong_tot = st.groupby("행정동코드").size().rename("dong_stores")
AD = st.dropna(subset=["area"]).groupby(["area", "행정동코드"]).size().rename("area_stores_in_dong").reset_index()
AD = AD.merge(dong_tot, left_on="행정동코드", right_index=True); AD["weight"] = AD.area_stores_in_dong / AD.dong_stores
AD = AD.merge(cmap[["adstrdCode", "sgg", "dong"]], left_on="행정동코드", right_on="adstrdCode", how="left").drop(columns="adstrdCode")
AD.to_csv(O8 / "area_dong_share.csv", index=False, encoding="utf-8-sig")
print("\n상권별 걸친 행정동 수:", AD.groupby("area").size().to_dict())

pm = panel.merge(cmap[["admdstCd", "adstrdCode"]].rename(columns={"admdstCd": "plcCd"}), on="plcCd", how="left") if "adstrdCode" not in panel or panel.adstrdCode.isna().all() else panel
cols = [f"useAmount_{l}" for l in LCL] + [f"useCo_{l}" for l in LCL] + ["useAmount_합계"]
A = AD.merge(pm[["adstrdCode", "stdrYm"] + cols], left_on="행정동코드", right_on="adstrdCode", how="left")
for c in cols: A[c] = A[c] * A.weight
AS = A.groupby(["area", "stdrYm"], as_index=False)[cols].sum(min_count=1)
AS = AS[AS.stdrYm >= "202501"]
AS.to_csv(O8 / "area_sales_8989.csv", index=False, encoding="utf-8-sig")

scores = pd.read_csv(OUT / "area_scores.csv"); aprof = pd.read_csv(OUT / "area_profile.csv")
R = scores[["code", "name", "type", "type_name", "risk_score", "growth_score", "quadrant", "in500"]].copy()
a26 = AS[AS.stdrYm.isin(P26)].groupby("area")["useAmount_합계"].mean(); a25 = AS[AS.stdrYm.isin(P25)].groupby("area")["useAmount_합계"].mean()
R["sales_2026_m"] = R.code.map(a26); R["sales_yoy_pct"] = (R.code.map(a26) / R.code.map(a25) - 1) * 100
R["n_stores"] = R.code.map(AD.groupby("area").area_stores_in_dong.sum()); R["sales_per_store_2026"] = R.sales_2026_m / R.n_stores
for l in ["음식점", "도소매"]: R[f"share_{l}"] = R.code.map(AS[AS.stdrYm.isin(P26)].groupby("area")[f"useAmount_{l}"].mean()) / R.sales_2026_m
R["main_dong"] = R.code.map(AD.sort_values("area_stores_in_dong", ascending=False).groupby("area").dong.first())
R["main_dong_weight"] = R.code.map(AD.sort_values("area_stores_in_dong", ascending=False).groupby("area").weight.first())
R = R.sort_values("sales_yoy_pct", ascending=False)
R.to_csv(O8 / "area_sales_summary.csv", index=False, encoding="utf-8-sig")
print("\n[상권 20개 배분 매출]\n", R[["code", "name", "quadrant", "risk_score", "growth_score", "sales_2026_m", "sales_yoy_pct", "sales_per_store_2026", "main_dong", "main_dong_weight"]].round(2).to_string(index=False))
for y in ["sales_yoy_pct", "sales_per_store_2026"]:
    for x in ["risk_score", "growth_score"]:
        print(f"상권 {x} vs {y}: spearman ρ, p, n =", spearman(R[x], R[y]))
print("진단별 매출 증감 평균:\n", R.groupby("quadrant").sales_yoy_pct.agg(["mean", "median", "size"]).round(1))

# ── 5. 그림 ──
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    try: plt.rcParams["font.family"] = ["AppleGothic", "NanumGothic", "Malgun Gothic"]; plt.rcParams["axes.unicode_minus"] = False
    except Exception: pass
    fig, ax = plt.subplots(1, 2, figsize=(12, 5))
    ax[0].scatter(S.tram500_share, S.sales_yoy_pct, c=S.old_town, cmap="coolwarm"); ax[0].set_xlabel("정거장 500m 안 점포 비율"); ax[0].set_ylabel("카드매출 증감 2025→2026 1~8월 (%)"); ax[0].axhline(0, c="gray", lw=.5)
    for _, r in S.nlargest(5, "sales_yoy_pct").iterrows(): ax[0].annotate(r.dong, (r.tram500_share, r.sales_yoy_pct), fontsize=8)
    ax[1].scatter(S.bad_pct, S.sales_yoy_pct, c=S.old_town, cmap="coolwarm"); ax[1].set_xlabel("실태조사 어려움 응답률 2021 (%)"); ax[1].set_ylabel("카드매출 증감 (%)"); ax[1].axhline(0, c="gray", lw=.5)
    plt.tight_layout(); plt.savefig(O8 / "dong_sales_validation.png", dpi=150); plt.close()
    fig, ax = plt.subplots(figsize=(10, 6)); Rp = R.sort_values("sales_yoy_pct")
    import policy_quadrant as PQ
    colors = Rp.quadrant.map(PQ.HEX).fillna("#888")
    ax.barh(Rp.name, Rp.sales_yoy_pct, color=colors); ax.axvline(0, c="gray", lw=.5); ax.set_xlabel("카드매출 증감 2025→2026 1~8월 (%) — 행정동 실측을 점포 비율로 배분")
    plt.tight_layout(); plt.savefig(O8 / "area_sales_yoy.png", dpi=150); plt.close(); print("그림 저장")
except ImportError:
    print("matplotlib 없음 → 그림 생략")
