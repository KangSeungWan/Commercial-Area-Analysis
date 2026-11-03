"""B4: 서울 신림선(2022-05-28 개통) 역 주변 땅값(개별공시지가) 이중차분 — 매출 분석(analyze_seoul_newline_sales)과 같은 처리·비교 정의
질문: 같은 신림선 사례에서 '땅값은 오르고 점포당 매출은 그대로'인가? (사전 분석 계획 B4, tram_model/docs/사전분석계획_2차점검_1103.md)
입력 (data/raw/seoul/공시지가/, 커밋 안 함)
  - seoul_landprice_YYYY.zip (서울 열린데이터광장 개별공시지가 CSV, 2019~2024): 토지코드(PNU), 공시지가(원/㎡), 기준년월
  - AL_D002_11_*.zip (국가공간정보포털 연속지적도, 서울, EPSG:5186): A1=PNU, A5=지번+지목, 도형 → 필지 경계상자 중심
  - data/raw/seoul/ 역사마스터 CSV (위도·경도·호선)
설계: 처리군 = 신림선 역 500m 안 필지 중 다른 노선 역 500m 밖 / 비교군 = 신림선 역 1~3km 필지 (매출 분석과 같음)
      1월 1일 정기공시만, 6년 모두 있는 필지(균형 패널), 필지 고정효과 + 연도 고정효과, 표준오차는 법정동 군집
      개통 전 2019~2022(2022-01-01은 개통 전), 개통 후 2023~2024. 사건연구 기준 2022, 가짜 개통 2021(2019~2022만)
      보조: 지목 '대'(대지)만, 법정동 단위로 묶은 평균
판정(미리 정함): 땅값 효과 유의하게 양수 & 점포당 매출 유의하지 않음 → '같은 사례에서 확인'
                 땅값도 유의하지 않음 → '경전철은 땅값도 매출도 확실히 바꾸지 않았다', ①은 '방향만' 유지·기본값 그대로
출력: outputs/seoul_newline_land_did.csv, outputs/seoul_newline_land_es.csv
한계: 신림선은 지하 경전철(트램 아님), 착공(2017) 뒤라 개통 전 값에 기대가 이미 들어 있을 수 있음, 지적도는 2026년 기준(분할·합병 필지 제외)
"""
import glob, io, os, sys, zipfile
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import analyze_line1_permits as AP
import analyze_seoul_newline_sales as SN

LP = C.RAW_DIR / "seoul" / "공시지가"
OUT = C.OUT_DIR
GU = ("11620", "11590", "11560", "11530", "11545", "11650")   # 관악·동작·영등포 + 구로·금천·서초(비교 지역이 구 경계에서 잘리지 않게)
YEARS = list(range(2019, 2025)); OPEN = 2023; BASE = 2022


def load_prices():
    parts = []
    for y in YEARS:
        z = zipfile.ZipFile(LP / f"seoul_landprice_{y}.zip")
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        d = pd.read_csv(z.open(name), encoding="cp949", dtype=str, usecols=["시군구코드", "토지코드", "공시지가(원/㎡)", "기준년월"])
        d = d[d["시군구코드"].isin(GU) & d["기준년월"].str.endswith("01-01")]
        parts.append(pd.DataFrame({"pnu": d["토지코드"].str.strip(), "year": y, "price": pd.to_numeric(d["공시지가(원/㎡)"], errors="coerce")}))
    P = pd.concat(parts).dropna()
    P = P[P.price > 0].drop_duplicates(["pnu", "year"])
    return P


def load_parcels():
    z = zipfile.ZipFile(glob.glob(str(LP / "AL_D002_11_*.zip"))[0])
    nm = {os.path.splitext(n)[1].lower(): n for n in z.namelist()}
    shx = np.frombuffer(z.read(nm[".shx"]), dtype=np.uint8)
    n = (len(shx) - 100) // 8
    off = shx[100:100 + 8 * n].reshape(n, 8)[:, :4].copy().view(">i4").ravel().astype(np.int64) * 2
    shp = np.frombuffer(z.read(nm[".shp"]), dtype=np.uint8)
    idx = (off + 12)[:, None] + np.arange(32)[None, :]                      # 기록 머리 8 + 도형 종류 4 → 경계상자 4개 double
    box = shp[idx].copy().view("<f8").reshape(n, 4)
    del shp, idx
    dbf = z.read(nm[".dbf"])
    hl = int.from_bytes(dbf[8:10], "little"); rl = int.from_bytes(dbf[10:12], "little")
    R = np.frombuffer(dbf, dtype=np.uint8, count=n * rl, offset=hl).reshape(n, rl)
    pnu = R[:, 10:29].copy().view("S19").ravel().astype(str)                 # A0(9) 다음 A1(19)
    keep = np.isin(np.char.ljust(pnu, 5).astype("U5"), GU) if False else np.array([p[:5] in GU for p in pnu])
    jimok = np.array([R[i, 303:503].tobytes().decode("cp949", "ignore").strip()[-1:] for i in np.where(keep)[0]])
    G = pd.DataFrame({"pnu": pnu[keep], "x": (box[keep, 0] + box[keep, 2]) / 2, "y": (box[keep, 1] + box[keep, 3]) / 2, "jimok": jimok})
    return G.drop_duplicates("pnu")


def stations():
    f = SN._find_files("호선")[0]; ST = SN._read(f)
    ln = SN.col(ST, "호선"); la = [c for c in ST.columns if "위도" in c][0]; lo = [c for c in ST.columns if "경도" in c][0]
    ST = ST.assign(lat=pd.to_numeric(ST[la], errors="coerce"), lon=pd.to_numeric(ST[lo], errors="coerce")).dropna(subset=["lat", "lon"])
    sx, sy = SN.tm5181(ST.lat.values, ST.lon.values)
    ST["sx"], ST["sy"] = sx, sy + 100000                                    # EPSG:5181 → 5186 (가짜 북향 500000 → 600000)
    new = ST[ST[ln].astype(str).str.contains(SN.NEWLINE)]; old = ST[~ST[ln].astype(str).str.contains(SN.NEWLINE)]
    return new, old


def mindist(X, Y, s, chunk=20000):
    out = np.empty(len(X))
    for i in range(0, len(X), chunk):
        out[i:i + chunk] = np.min(np.hypot(X[i:i + chunk, None] - s.sx.values[None], Y[i:i + chunk, None] - s.sy.values[None]), axis=1)
    return out


def est(d, cluster="bjd"):
    d = d.assign(D=(d.treat * (d.year >= OPEN)).astype(float))
    b, se, G = AP.twfe(d, "ly", ["D"], cluster=cluster)
    pre = d[d.year < OPEN].assign(D=lambda x: (x.treat * (x.year >= 2021)).astype(float))
    bf, sef, _ = AP.twfe(pre, "ly", ["D"], cluster=cluster)
    return dict(효과=round(AP.pct(b[0]), 2), 하한=round(AP.pct(b[0] - 1.96 * se[0]), 2), 상한=round(AP.pct(b[0] + 1.96 * se[0]), 2),
                p값=round(AP._pval(b[0] / se[0]), 4), 가짜개통_2021=round(AP.pct(bf[0]), 2), 가짜개통_p=round(AP._pval(bf[0] / sef[0]), 4),
                처리=int(d[d.treat == 1].cell.nunique()), 비교=int(d[d.treat == 0].cell.nunique()), 군집=int(G))


def main():
    if not LP.exists() or not glob.glob(str(LP / "AL_D002_11_*.zip")):
        print(f"서울 공시지가·지적도 없음({LP}) → 건너뜀"); return
    P = load_prices(); G = load_parcels(); new, old = stations()
    ALLP = set(G.pnu)
    G["d_new"] = mindist(G.x.values, G.y.values, new)
    near = G.d_new <= 3000
    G = G[near].copy()
    old = old[(old.sx.between(G.x.min() - 600, G.x.max() + 600)) & (old.sy.between(G.y.min() - 600, G.y.max() + 600))]
    G["d_old"] = mindist(G.x.values, G.y.values, old)
    G["group"] = np.where((G.d_new <= 500) & (G.d_old > 500), "처리군", np.where(G.d_new > 1000, "비교군", None))
    GA = G.copy()
    G = G.dropna(subset=["group"])
    p19 = P[(P.year == 2019) & P.pnu.str[:5].isin(GU[:3])]
    n_map = p19.pnu.isin(ALLP).mean()
    D = P.merge(G[["pnu", "group", "jimok", "d_new"]], on="pnu")
    full = D.groupby("pnu").year.nunique(); D = D[D.pnu.isin(full[full == len(YEARS)].index)]
    D["treat"] = (D.group == "처리군").astype(int); D["ly"] = np.log(D.price)
    D["bjd"] = D.pnu.str[:10]
    D = D.rename(columns={"pnu": "cell"})
    rows = [dict(모형="기본: 필지 전체", **est(D)),
            dict(모형="지목 '대'(대지)만", **est(D[D.jimok == "대"])),
            dict(모형="역 500m 안 전체(다른 노선 역 근처 포함)", **{})]
    # 법정동 단위로 묶은 평균 (필지 수 차이 영향 제거): 법정동×처리 여부별 평균 log 지가
    B = D.groupby(["bjd", "treat", "year"]).ly.mean().reset_index()
    B["cell"] = B.bjd + "_" + B.treat.astype(str)
    rows.append(dict(모형="법정동 평균(법정동×처리 단위)", **est(B)))
    R = pd.DataFrame(rows)
    # 3번째 모형: 다른 노선 역 근처까지 처리군에 포함
    D2 = P.merge(GA.assign(group=np.where(GA.d_new <= 500, "처리군", np.where(GA.d_new > 1000, "비교군", None)))[["pnu", "group"]].dropna(), on="pnu")
    full2 = D2.groupby("pnu").year.nunique(); D2 = D2[D2.pnu.isin(full2[full2 == len(YEARS)].index)]
    D2 = D2.assign(treat=(D2.group == "처리군").astype(int), ly=np.log(D2.price), bjd=D2.pnu.str[:10]).rename(columns={"pnu": "cell"})
    e2 = est(D2)
    for k_, v_ in e2.items():
        R.at[2, k_] = v_
    land = R.iloc[0]
    sales = pd.read_csv(OUT / "seoul_newline_sales_did.csv")
    s = sales[sales["결과"] == "점포당 매출"].iloc[0]
    land_sig = land["p값"] < 0.05 and land["효과"] > 0
    sales_ns = s["p값"] >= 0.05
    if land_sig and sales_ns:
        verdict = "같은 사례에서 확인: 땅값 유의하게 양수, 점포당 매출 유의하지 않음"
    elif not (land["p값"] < 0.05):
        verdict = "땅값도 유의하지 않음 → '경전철은 땅값도 매출도 확실히 바꾸지 않았다', ①은 '방향만' 유지·기본값 그대로"
    else:
        verdict = "규칙 밖 결과(땅값 유의하게 음수 등) → 그대로 보고"
    R["판정"] = [verdict] + [""] * (len(R) - 1)
    R["지적도_연결률_2019_3개구"] = round(float(n_map), 3)
    for c_ in ("처리", "비교", "군집"):
        R[c_] = R[c_].astype(int)
    R.to_csv(OUT / "seoul_newline_land_did.csv", index=False, encoding="utf-8-sig")
    d = D.copy(); xc = []
    for y in YEARS:
        if y == BASE: continue
        d[f"e{y}"] = ((d.year == y) & (d.treat == 1)).astype(float); xc.append(f"e{y}")
    b, se, _ = AP.twfe(d, "ly", xc, cluster="bjd")
    E = pd.DataFrame({"year": [y for y in YEARS if y != BASE], "effect_pct": [AP.pct(v) for v in b],
                      "lo": [AP.pct(v - 1.96 * s_) for v, s_ in zip(b, se)], "hi": [AP.pct(v + 1.96 * s_) for v, s_ in zip(b, se)]})
    E.to_csv(OUT / "seoul_newline_land_es.csv", index=False, encoding="utf-8-sig")
    print(R.to_string(index=False)); print(E.round(2).to_string(index=False))
    print("점포당 매출(같은 사례):", s["효과"], s["하한"], s["상한"], "p", s["p값"])


if __name__ == "__main__":
    main()
