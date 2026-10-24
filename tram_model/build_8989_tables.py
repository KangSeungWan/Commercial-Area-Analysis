"""
8989 원본(json.gz) → 분석용 CSV 정리

입력: data/raw/8989/raw/<dongAnal|trdarAnal>/*.json.gz, data/raw/8989/meta/*
출력: outputs/8989/
  dong_code_map.csv          82개 행정동 코드 대응 (8989코드 admdstCd / 행안부 8자리 adstrdCode / 통계청 10자리 adm_cd2)
  sales_month.csv            월별 카드매출: level(sido/sgg/dong/trdar) × code × 업종소분류 × 월  (selng01)  ★ 추세 분석용
  sales_breakdown.csv        기준월 분해: 요일·성별·연령·시간대 매출 (selng03/04/05, cmmn02)      — 비율용 (합계 기준 다름)
  sales_detail_top.csv       기준월 세세분류 매출 상위 (cmmn03)
  store_detail.csv           기준월 세세분류 점포 수·폐업 수 (stor00)
  store_survived.csv         대분류 생존 점포 수 (stor01)
  closures_month.csv         월별 폐업 수·누적 (clsbizSmll) + 시·구·동 점포 총수 (total*)
  pop_month.csv              월별 일평균 유동인구(popul01) + 주민등록 인구(popul05): level × code × 월
  pop_breakdown.csv          기준월 유동인구 성·연령(popul02)·요일(popul03)·시간대(popul04), 주민 성·연령(popul06)
  income.csv                 행정동 고용보험·월소득 지표 (cmmn04)
  dong_panel_8989.csv        ★ 82개 행정동 × 월 패널: 대분류 8개 매출·건수, 유동인구, 주민인구, 점포·폐업
"""
import gzip, json, re
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw" / "8989"
OUT = HERE / "outputs" / "8989"; OUT.mkdir(parents=True, exist_ok=True)

ind = pd.read_csv(RAW/"meta"/"industry_opt.csv", dtype=str)
L_OF = dict(zip(ind.indutySclasCode, ind.indutyLclasCode))
LNAME = dict(zip(ind.indutyLclasCode, ind.indutyLclasNm))
dong_opt = pd.read_csv(RAW/"meta"/"dong_opt.csv", dtype=str)

def level_of(code, trd=False, plc=None):
    code = str(code)
    if trd:
        return "trdar" if code == str(plc) else f"trdar_ref{code}"   # -1/-2 = 사이트가 주는 비교군(의미는 확인 필요)
    return {2: "sido", 5: "sgg"}.get(len(code), "dong")

rows = {k: [] for k in ["sales_month","sales_breakdown","sales_detail_top","store_detail","store_survived","closures_month","pop_month","pop_breakdown","income"]}
files = sorted(RAW.glob("raw/*/*.json.gz"))
print("원본 파일", len(files))
for f in files:
    anal = f.parent.name
    plc, sclas, ym = re.match(r"(.+?)_(.+?)_(\d{6})\.json\.gz", f.name).groups()
    d = json.load(gzip.open(f, "rt", encoding="utf-8"))
    base = dict(anal=anal, plcCd=plc, sclasCd=sclas, baseYm=ym)
    trd = anal == "trdarAnal"
    for r in d.get("selng01", []):
        code = r.get("trdarNo", r.get("adstrdCode"))
        rows["sales_month"].append(dict(level=level_of(code, trd, plc), code=code, sclasCd=sclas, stdrYm=r["stdrYm"], useCo=r["useCo"], useAmount=r["useAmount"], plcCd=plc, anal=anal, baseYm=ym))
    for key, dim in [("selng03","dayw"),("selng04","sex"),("selng05","age"),("cmmn02","tmzon")]:
        for r in d.get(key, []):
            k = r.get("daywNm") or r.get("sexdstnCode") or r.get("ageCode") or r.get("tmzonNm")
            rows["sales_breakdown"].append(dict(base, dim=dim, key=k, useCo=r.get("useCo"), useAmount=r.get("useAmount", r.get("sum"))))
    for r in d.get("cmmn03", []):
        rows["sales_detail_top"].append(dict(base, detailCd=r["indutyDetailDtlclfc"], detailNm=r["ksicDetailDtlclfcNm"], useAmount=r["useAmount"]))
    for r in d.get("stor00", []):
        rows["store_detail"].append(dict(base, detailCd=r["indutyDetailDtlclfc"], detailNm=r["ksicDetailDtlclfcNm"], storCnt=r["storCnt"], clsbizCnt=r["clsbizCnt"]))
    for r in d.get("stor01", []):
        rows["store_survived"].append(dict(anal=anal, plcCd=plc, baseYm=ym, lclasCd=r["indutyLclasCode"], survivedCnt=r["survivedCnt"]))
    tot = {k: (d.get(k) or [{}])[0] for k in ["totalLrge","totalMddl","totalSmll"]}
    for r in d.get("clsbizSmll", []):
        rows["closures_month"].append(dict(base, stdrYm=r["yearmonth"], clsbizStorCo=r["clsbizStorCo"], clsbizAccmltCo=r["clsbizAccmltCo"],
                                           storCo_plc=tot["totalSmll"].get("storCo"), storCo_sgg=tot["totalMddl"].get("sum"), storCo_sido=tot["totalLrge"].get("sum")))
    for r in d.get("popul01", []):
        code = r.get("trdarNo", r.get("adstrdCode"))
        rows["pop_month"].append(dict(level=level_of(code, trd, plc), code=code, stdrYm=r["stdrYm"], var="floating_daily", value=r["dynmcPopltnValue"], plcCd=plc, anal=anal, baseYm=ym))
    for r in d.get("popul05", []):
        code = r.get("trdarNo", r.get("adstrdCode"))
        rows["pop_month"].append(dict(level=level_of(code, trd, plc), code=code, stdrYm=r["stdrYm"], var="resident", value=r["sum"], plcCd=plc, anal=anal, baseYm=ym))
    for r in d.get("popul02", []):
        for k, v in r.items():
            if k.startswith(("male","female")) and k not in ("maleTotal","femaleTotal"):
                rows["pop_breakdown"].append(dict(base, var="floating", dim="sex_age", key=k, value=v))
    for r in d.get("popul03", []): rows["pop_breakdown"].append(dict(base, var="floating", dim="dayw", key=r["daywNm"], value=r["dynmcPopltnValue"]))
    for r in d.get("popul04", []): rows["pop_breakdown"].append(dict(base, var="floating", dim="tmzon", key=r["tmzonNm"], value=r["dynmcPopltnValue"]))
    for r in d.get("popul06", []):
        for k, v in r.items():
            if k.startswith("popltnAge"): rows["pop_breakdown"].append(dict(base, var="resident", dim="sex_age", key=f"{'M' if r['mwmnSe']=='1' else 'F'}_{k[9:]}", value=v))
    for r in d.get("cmmn04", []):
        rows["income"].append(dict(base, name=r.get("admNm", r.get("trdarNm")), hireAssrncAmount=r.get("hireAssrncAmount"), mthtAmount=r.get("mthtAmount")))

dfs = {}
for k, v in rows.items():
    df = pd.DataFrame(v)
    if df.empty: print("비어 있음:", k); dfs[k] = df; continue
    sub = [c for c in df.columns if c not in ("plcCd","anal","baseYm")] if k in ("sales_month","pop_month") else None
    if sub:
        df["plcCd"] = df.apply(lambda r: r.plcCd if r.level in ("dong","trdar") else "", axis=1)
    if sub: df = df.sort_values("baseYm").drop_duplicates(subset=sub, keep="last")   # 13개월 창 겹침 제거
    df.to_csv(OUT/f"{k}.csv", index=False, encoding="utf-8-sig"); dfs[k] = df
    print(f"{k}: {len(df):,}행")

# ── 행정동 코드 대응표 (8989 → 행안부 8자리 → 통계청 10자리) ──
sm = dfs["sales_month"]; pm = dfs["pop_month"]
plc2adm = {}
for df in (sm, pm):
    sub = df[(df.anal=="dongAnal") & (df.level=="dong")]
    plc2adm.update(dict(zip(sub.plcCd.astype(str), sub.code.astype(str))))
cm = dong_opt.rename(columns={"mjrNm":"sgg","mnrCd":"admdstCd","mnrNm":"dong"})[["sgg","admdstCd","dong"]]
cm["adstrdCode"] = cm.admdstCd.map(plc2adm)
try:
    g = json.load(open(HERE/"data"/"daejeon_dong_2023.geojson", encoding="utf-8"))
    geo = pd.DataFrame([f["properties"] for f in g["features"]])[["adm_cd2","sggnm","dong"]].rename(columns={"sggnm":"sgg"})
    cm = cm.merge(geo, on=["sgg","dong"], how="left")
    print("통계청 코드 매칭 안 된 동:", cm[cm.adm_cd2.isna()][["sgg","dong"]].values.tolist())
except FileNotFoundError:
    print("daejeon_dong_2023.geojson 없음 → adm_cd2 생략")
cm.to_csv(OUT/"dong_code_map.csv", index=False, encoding="utf-8-sig")

# ── 82개 행정동 × 월 패널 ──
s = sm[(sm.anal=="dongAnal") & (sm.level=="dong")].copy()
s["lclasCd"] = s.sclasCd.map(L_OF)
s_l = s.groupby(["plcCd","stdrYm","lclasCd"], as_index=False)[["useCo","useAmount"]].sum()
wide = s_l.pivot(index=["plcCd","stdrYm"], columns="lclasCd", values=["useAmount","useCo"])
wide.columns = [f"{a}_{LNAME.get(b,b)}" for a, b in wide.columns]
wide = wide.reset_index()
wide["useAmount_합계"] = s.groupby(["plcCd","stdrYm"]).useAmount.sum().values if len(wide)==s.groupby(["plcCd","stdrYm"]).ngroups else wide.filter(like="useAmount_").sum(axis=1)
p = pm[(pm.anal=="dongAnal") & (pm.level=="dong")].pivot_table(index=["plcCd","stdrYm"], columns="var", values="value", aggfunc="first").reset_index()
panel = cm.rename(columns={"admdstCd":"plcCd"}).merge(p, on="plcCd", how="left").merge(wide, on=["plcCd","stdrYm"], how="left")
cl = dfs["closures_month"]; cl = cl[cl.anal=="dongAnal"]
cl_m = cl.drop_duplicates(["plcCd","sclasCd","stdrYm"]).groupby(["plcCd","stdrYm"], as_index=False).agg(clsbiz=("clsbizStorCo","sum"))   # 기준월 2개 창 겹침 제거
sv = dfs["store_survived"]; sv = sv[sv.anal=="dongAnal"].drop_duplicates(["plcCd","baseYm","lclasCd"]).groupby(["plcCd","baseYm"], as_index=False).survivedCnt.sum().rename(columns={"baseYm":"stdrYm","survivedCnt":"stores_survived_at_baseYm"})   # stor01은 업종과 무관하게 같은 값 → 중복 제거
panel = panel.merge(cl_m, on=["plcCd","stdrYm"], how="left").merge(sv, on=["plcCd","stdrYm"], how="left")
panel = panel.sort_values(["sgg","dong","stdrYm"])
panel.to_csv(OUT/"dong_panel_8989.csv", index=False, encoding="utf-8-sig")
print(f"dong_panel_8989: {panel.plcCd.nunique()}개 동 × {panel.stdrYm.nunique()}개월 = {len(panel):,}행")
print("매출 있는 월:", sorted(s.stdrYm.unique())[0], "~", sorted(s.stdrYm.unique())[-1])
