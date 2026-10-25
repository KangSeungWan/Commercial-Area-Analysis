"""매출 인과 근거 보강 (A2): 서울 신림선(2022-05-28 개통) 역 주변 상권의 개통 전후 매출·점포당 매출 이중차분

질문: 새 철도역이 생기면 주변 상권의 '점포당 매출'이 오르나? (대전 1호선은 매출 자료가 없어 단면 비교만 했음)
입력 (사용자가 서울 열린데이터광장에서 받아 data/raw/seoul/ 에 넣음; 파일 이름은 상관없음, 열 이름으로 찾음)
  - 추정매출-상권 (OA-15572) 2021·2022·2023년 CSV : 기준_년분기_코드, 상권_코드, 서비스_업종_코드(_명), 당월_매출_금액
  - 점포-상권 (OA-15577) 2021·2022·2023년 CSV     : 기준_년분기_코드, 상권_코드, 서비스_업종_코드, 점포_수
  - 영역-상권 (OA-15560) CSV 또는 shapefile(.dbf) : 상권_코드, 엑스좌표_값, 와이좌표_값 / TRDAR_CD, XCNTS_VALU, YDNTS_VALU (EPSG:5181)
  - 역사마스터 (OA-21232) CSV                      : 역사명, 호선, 위도, 경도
  * 2024년부터 상권 단위가 표준단위구역으로 바뀌어 코드가 이어지지 않음 → 2021~2023만 사용
설계: 처리군 = 신림선 역 500m 안 상권 중 다른 노선 역 500m 밖(환승역 주변 제외 = 새 역 효과만)
      비교군 = 신림선 역 1~3km 상권 중 모든 역 500m 밖이 아닌 곳도 포함(같은 생활권 대조)
      개통 전 2021Q1~2022Q1, 개통 분기 2022Q2 제외, 개통 후 2022Q3~2023Q4. 상권 고정효과 + 분기 고정효과, 상권 군집 표준오차
      결과: log(점포당 매출), log(매출 합), log(점포 수), 커피·음료 업종 매출 비중. 사건연구(분기별), 가짜 개통(2021Q3)
출력: outputs/seoul_newline_sales_did.csv, outputs/seoul_newline_sales_es.csv
한계: 신림선은 지하 경전철(트램 아님), 개통 전 기간이 5분기·코로나 회복기와 겹침, 추정매출은 카드 기반 추정치
"""
import glob, math, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import analyze_line1_permits as AP

RAW = C.RAW_DIR / "seoul"
OUT = C.OUT_DIR
OPEN_Q = 20222                      # 2022년 2분기(5/28 개통) → 제외
NEWLINE = "신림선"


def _read(path):
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(path)


def _find_files(*must):
    out = []
    for f in glob.glob(str(RAW / "**" / "*.csv"), recursive=True):
        cols = list(_read(f).columns[:60]) if os.path.getsize(f) < 5e8 else []
        if all(any(m in c for c in cols) for m in must):
            out.append(f)
    return out


def tm5181(lat, lon):
    """WGS84(GRS80 동일 취급) → EPSG:5181 (중부원점, 위도 38, 경도 127, FE 200000, FN 500000, k 1)."""
    a, f = 6378137.0, 1 / 298.257222101
    e2 = f * (2 - f); ep2 = e2 / (1 - e2)
    lat, lon = np.radians(lat), np.radians(lon)
    lat0, lon0 = math.radians(38), math.radians(127)
    def M(p):
        return a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * p - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * np.sin(2 * p)
                    + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * np.sin(4 * p) - (35 * e2 ** 3 / 3072) * np.sin(6 * p))
    N = a / np.sqrt(1 - e2 * np.sin(lat) ** 2); T = np.tan(lat) ** 2; Cc = ep2 * np.cos(lat) ** 2; A = (lon - lon0) * np.cos(lat)
    x = N * (A + (1 - T + Cc) * A ** 3 / 6 + (5 - 18 * T + T ** 2 + 72 * Cc - 58 * ep2) * A ** 5 / 120)
    y = M(lat) - M(lat0) + N * np.tan(lat) * (A ** 2 / 2 + (5 - T + 9 * Cc + 4 * Cc ** 2) * A ** 4 / 24 + (61 - 58 * T + T ** 2 + 600 * Cc - 330 * ep2) * A ** 6 / 720)
    return x + 200000, y + 500000


def read_dbf(path):
    """shapefile 의 .dbf 속성표만 읽음 (외부 라이브러리 없이). 문자열은 .cpg 인코딩, 없으면 cp949."""
    import struct
    enc = "cp949"
    cpg = os.path.splitext(path)[0] + ".cpg"
    if os.path.exists(cpg):
        enc = open(cpg).read().strip() or enc
    with open(path, "rb") as f:
        h = f.read(32); n = struct.unpack("<I", h[4:8])[0]; hl = struct.unpack("<H", h[8:10])[0]; rl = struct.unpack("<H", h[10:12])[0]
        fields = []
        while True:
            fd = f.read(32)
            if fd[0] == 0x0D: break
            fields.append((fd[:11].split(b"\x00")[0].decode("ascii", "ignore"), chr(fd[11]), fd[16]))
        f.seek(hl); rows = []
        for _ in range(n):
            rec = f.read(rl)
            if not rec or rec[0] == 0x2A: continue
            pos = 1; row = {}
            for name, typ, ln in fields:
                raw = rec[pos:pos + ln]; pos += ln
                row[name] = raw.decode(enc, "ignore").strip() if typ == "C" else raw.decode("ascii", "ignore").strip()
            rows.append(row)
    return pd.DataFrame(rows)


def col(df, *keys):
    """열 찾기: 키워드가 모두 들어간 열 중 가장 짧은 이름 (예: '상권_구분_코드'가 아니라 '상권_코드')."""
    hits = [c for c in df.columns if all(k in c for k in keys)]
    if not hits:
        raise KeyError(keys)
    return min(hits, key=len)


def main():
    if not RAW.exists():
        print(f"서울 상권 자료 없음({RAW}) → 건너뜀"); return
    f_sales = _find_files("당월_매출_금액"); f_store = _find_files("점포_수", "서비스_업종")
    f_area = _find_files("엑스좌표"); f_stn = _find_files("호선")
    f_dbf = [f for f in glob.glob(str(RAW / "**" / "*.dbf"), recursive=True)]
    if not f_area and f_dbf:
        A_dbf = read_dbf(f_dbf[0])
        A_dbf = A_dbf.rename(columns={"TRDAR_CD": "상권_코드", "XCNTS_VALU": "엑스좌표_값", "YDNTS_VALU": "와이좌표_값"})
        f_area = ["<dbf>"]
    if not (f_sales and f_store and f_area and f_stn):
        print("필요한 파일이 다 있지 않음 → 건너뜀:", dict(매출=len(f_sales), 점포=len(f_store), 영역=len(f_area), 역=len(f_stn))); return
    S = pd.concat([_read(f) for f in f_sales]); P = pd.concat([_read(f) for f in f_store])
    A = A_dbf if f_area == ["<dbf>"] else _read(f_area[0]); ST = _read(f_stn[0])
    q = col(S, "기준", "분기"); k = col(S, "상권", "코드"); u = col(S, "서비스_업종_코드"); amt = col(S, "당월_매출_금액")
    S = S[[q, k, u, amt] + [c for c in S.columns if "업종_코드_명" in c][:1]].copy()
    S.columns = ["q", "k", "u", "amt"] + (["uname"] if S.shape[1] == 5 else [])
    S["q"] = S.q.astype(int); S["amt"] = pd.to_numeric(S.amt, errors="coerce")
    S = S[S.q.between(20211, 20234)]
    P = P[[col(P, "기준", "분기"), col(P, "상권", "코드"), col(P, "서비스_업종_코드"), col(P, "점포_수")]].copy()
    P.columns = ["q", "k", "u", "n"]; P["q"] = P.q.astype(int); P["n"] = pd.to_numeric(P.n, errors="coerce")
    # 매출이 추정된 업종만 점포 수에 포함 (분모·분자 같은 업종)
    P = P.merge(S[["q", "k", "u"]].drop_duplicates(), on=["q", "k", "u"])
    cafe = S.get("uname", pd.Series("", index=S.index)).astype(str).str.contains("커피|음료")
    G = S.groupby(["k", "q"]).amt.sum().to_frame("sales").join(S[cafe].groupby(["k", "q"]).amt.sum().rename("cafe")).join(
        P.groupby(["k", "q"]).n.sum().rename("stores")).reset_index().fillna({"cafe": 0})
    # 위치
    A = A[[col(A, "상권", "코드"), col(A, "엑스좌표"), col(A, "와이좌표")]].drop_duplicates(subset=[col(A, "상권", "코드")])
    A.columns = ["k", "x", "y"]; A["x"] = pd.to_numeric(A.x); A["y"] = pd.to_numeric(A.y)
    ln, la, lo = col(ST, "호선"), [c for c in ST.columns if "위도" in c][0], [c for c in ST.columns if "경도" in c][0]
    ST = ST.assign(lat=pd.to_numeric(ST[la], errors="coerce"), lon=pd.to_numeric(ST[lo], errors="coerce")).dropna(subset=["lat", "lon"])
    ST["sx"], ST["sy"] = tm5181(ST.lat.values, ST.lon.values)
    new = ST[ST[ln].astype(str).str.contains(NEWLINE)]; old = ST[~ST[ln].astype(str).str.contains(NEWLINE)]
    if new.empty:
        print("역사마스터에서 신림선 역을 찾지 못함 → 건너뜀"); return
    dist = lambda X, Y, s: np.min(np.hypot(X[:, None] - s.sx.values[None], Y[:, None] - s.sy.values[None]), axis=1)
    A["d_new"] = dist(A.x.values, A.y.values, new); A["d_old"] = dist(A.x.values, A.y.values, old)
    A["group"] = np.where((A.d_new <= 500) & (A.d_old > 500), "처리군", np.where((A.d_new > 1000) & (A.d_new <= 3000), "비교군", None))
    G = G.merge(A[["k", "group", "d_new"]], on="k").dropna(subset=["group"])
    G = G[(G.q != OPEN_Q) & (G.stores > 0) & (G.sales > 0)]
    full = G.groupby("k").q.nunique(); G = G[G.k.isin(full[full == full.max()].index)]       # 균형 패널
    G["treat"] = (G.group == "처리군").astype(int); G["post"] = (G.q > OPEN_Q).astype(int)
    G["ly_sps"] = np.log(G.sales / G.stores); G["ly_sales"] = np.log(G.sales); G["ly_stores"] = np.log(G.stores)
    G["cafe_share"] = G.cafe / G.sales
    G = G.rename(columns={"k": "cell", "q": "year"})               # AP.twfe 는 cell·year 이름을 씀
    qs = sorted(G.year.unique()); G["t"] = G.year.map({v: i for i, v in enumerate(qs)})
    rows = []
    for y, lab, unit in [("ly_sps", "점포당 매출", "%"), ("ly_sales", "상권 매출 합", "%"), ("ly_stores", "점포 수", "%"), ("cafe_share", "커피·음료 매출 비중", "%p")]:
        d = G.assign(D=(G.treat * G.post).astype(float))
        b, se, ng = AP.twfe(d, y, ["D"])
        v = (lambda z: z * 100) if unit == "%p" else AP.pct
        pre = G[G.year < OPEN_Q].assign(D=lambda x: (x.treat * (x.year >= 20213)).astype(float))
        bf, sef, _ = AP.twfe(pre, y, ["D"])
        rows.append(dict(결과=lab, 단위=unit, 효과=round(v(b[0]), 2), 하한=round(v(b[0] - 1.96 * se[0]), 2), 상한=round(v(b[0] + 1.96 * se[0]), 2),
                         p값=round(AP._pval(b[0] / se[0]), 4), 가짜개통_2021Q3=round(v(bf[0]), 2), 가짜개통_p=round(AP._pval(bf[0] / sef[0]), 4),
                         처리_상권=int(G[G.treat == 1].cell.nunique()), 비교_상권=int(G[G.treat == 0].cell.nunique())))
    R = pd.DataFrame(rows); R.to_csv(OUT / "seoul_newline_sales_did.csv", index=False, encoding="utf-8-sig")
    base = max(q_ for q_ in qs if q_ < OPEN_Q); xc = []
    d = G.copy()
    for q_ in qs:
        if q_ == base: continue
        d[f"e{q_}"] = ((d.year == q_) & (d.treat == 1)).astype(float); xc.append(f"e{q_}")
    b, se, _ = AP.twfe(d, "ly_sps", xc)
    E = pd.DataFrame({"quarter": [q_ for q_ in qs if q_ != base], "effect_pct": [AP.pct(v) for v in b],
                      "lo": [AP.pct(v - 1.96 * s) for v, s in zip(b, se)], "hi": [AP.pct(v + 1.96 * s) for v, s in zip(b, se)]})
    E.to_csv(OUT / "seoul_newline_sales_es.csv", index=False, encoding="utf-8-sig")
    print(R.to_string(index=False)); print(E.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
