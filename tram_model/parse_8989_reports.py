"""
8989 월간 상권동향 PDF(data/raw/8989/reports/N월.pdf) → CSV
  outputs/8989/report_city_monthly.csv   대전 전체 월별 지표(카드매출·온통대전·결제건수·유동인구·사업자·창업·폐업, 전월/전년 대비)
  outputs/8989/report_gu_mom.csv         5개 구 전월 대비 매출 증감률
  outputs/8989/report_alley_monthly.csv  골목상권(전통시장·상점가·골목형상점가) × 월 × 신용카드/온통대전/유동인구 전월 대비 %
6월 PDF는 한글이 빠져 있어 (구, 유형, 순번)으로 5월 이름을 붙임.
"""
import re
from pathlib import Path
import pandas as pd, pdfplumber

HERE = Path(__file__).resolve().parent
RDIR = HERE / "data" / "raw" / "8989" / "reports"; OUT = HERE / "outputs" / "8989"; OUT.mkdir(parents=True, exist_ok=True)
import sys
if not list(RDIR.glob("*.pdf")):
    print("월간 보고서 PDF 없음 (data/raw/8989/reports) → 건너뜀"); sys.exit(0)
PCT = re.compile(r"^[+-]?\d+(\.\d+)?%$")
TYPES = ["전통시장", "상점가", "골목형상점가", "상권활성화구역"]

def words_lines(page, col_bounds):
    """단어를 열(col)별로 나누고 y로 묶어 줄 생성"""
    ws = [w for w in page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=2, y_tolerance=3) if w["top"] > 70]   # 제목·부제 줄 제외
    cols = {i: [] for i in range(len(col_bounds))}
    for w in ws:
        x = w["x0"]
        for i, (lo, hi) in enumerate(col_bounds):
            if lo <= x < hi: cols[i].append(w); break
    out = {}
    for i, wl in cols.items():
        wl.sort(key=lambda w: (round(w["top"] / 4), w["x0"]))
        lines, cur, cy = [], [], None
        for w in wl:
            if cy is None or abs(w["top"] - cy) <= 4: cur.append(w); cy = w["top"] if cy is None else cy
            else: lines.append(cur); cur = [w]; cy = w["top"]
        if cur: lines.append(cur)
        out[i] = [[w["text"] for w in sorted(l, key=lambda w: w["x0"])] for l in lines]
    return out

def parse_alley(pdf_path, month):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[1]; W = page.width
        cols = words_lines(page, [(0, W * 0.345), (W * 0.345, W * 0.655), (W * 0.655, W)])
    GU_SEQ = {0: ["중구", "대덕구"], 1: ["유성구"], 2: ["서구", "동구"]}
    rows = []
    has_korean = any(re.search("[가-힣]", " ".join(t)) for ls in cols.values() for t in ls)
    for ci, lines in cols.items():
        gu_i, sec_type = 0, None
        for toks in lines:
            txt = " ".join(toks).replace("▲", " ").replace("▼", " ")
            pcts = re.findall(r"[+-]?\d+\.\d+%", txt)
            m = re.search(r"([가-힣]*)\((\d+)\)", txt)
            if m and not pcts and not re.match(r"^\d+\s", txt):          # 섹션 헤더
                t = m.group(1) or None
                if t is None:
                    t = {None: "전통시장", "전통시장": "상점가", "상점가": "골목형상점가", "골목형상점가": "전통시장", "상권활성화구역": "골목형상점가"}[sec_type]
                if sec_type in ("골목형상점가",) and t == "전통시장": gu_i += 1
                sec_type = t; continue
            mi = re.match(r"^(\d+)\s+(.*)$", txt)
            if mi and len(pcts) >= 2 and sec_type:
                idx = int(mi.group(1)); rest = mi.group(2)
                name = rest.split(pcts[0])[0] if pcts[0] in rest else rest
                name = re.sub(r"[^가-힣A-Za-z0-9()]", "", name) if has_korean else ""
                if has_korean and not re.search("[가-힣]", name): name = ""
                vals = [float(x.rstrip("%")) for x in pcts]
                card, ontong, pop = vals[:3] if len(vals) >= 3 else (None, None, None)
                gu = GU_SEQ[ci][min(gu_i, len(GU_SEQ[ci]) - 1)]
                rows.append(dict(month=month, gu=gu, type=sec_type, idx=idx, name=name, card_mom=card, ontong_mom=ontong, pop_mom=pop, n_pct=len(vals), raw=txt if len(vals) != 3 else ""))
    return pd.DataFrame(rows)

CITY = [  # month, 카드매출(억), 카드mom, 온통(억), 온통mom, 결제(만건), 결제mom, 유동(만명), 유동mom, 사업자, 사업자mom, 사업자yoy, 생활밀접, 창업, 창업mom, 창업yoy, 폐업, 폐업mom, 폐업yoy
 ("202601",12085,-5.4,579,-19.2,2968,-4.3,348.9,-1.1,259349,0.1,1.9,87721,2875,6.1,16.0,2035,-27.1,19.3),
 ("202602",11410,-5.6,592,2.3,2722,-8.3,346.0,-0.8,259620,0.1,1.8,87745,2214,-23.0,-13.3,1547,-24.0,-6.5),
 ("202603",12479,9.4,634,7.0,3172,16.6,353.5,2.2,259813,0.1,1.6,87740,2764,24.8,-0.5,1951,26.1,11.5),
 ("202604",11978,-4.0,374,-41.0,3260,2.8,360.2,1.9,260358,0.2,1.6,87984,2647,-4.2,-5.6,1707,-12.5,0.8),
 ("202605",12679,5.9,366,-2.2,3429,5.2,357.8,-0.7,260546,0.1,1.5,87924,2185,-17.5,-14.3,1677,-1.8,-4.2),
 ("202606",12357,-2.5,304,-16.9,3285,-4.2,360.0,0.6,260728,0.1,1.4,87912,2569,17.6,1.2,2033,21.2,20.1),
 ("202607",12067,-2.4,64,-79.1,3356,2.2,338.3,-2.9,260816,0.0,1.3,87946,2591,0.9,-6.2,1847,-9.1,10.0),
]
CITY_COLS = ["month","card_sales_100m","card_mom","ontong_100m","ontong_mom","tx_10k","tx_mom","floating_10k","floating_mom","biz","biz_mom","biz_yoy","biz_life","opens","opens_mom","opens_yoy","closes","closes_mom","closes_yoy"]
GU_MOM = {"202601": {"유성구":-0.7,"동구":-2.9,"서구":-3.2,"중구":-3.5,"대덕구":-5.5}, "202602": {"유성구":-6.9,"서구":-7.0,"대덕구":-7.0,"동구":-9.2,"중구":-9.7},
          "202603": {"중구":11.3,"동구":9.8,"대덕구":9.5,"서구":7.8,"유성구":6.6}, "202604": {"유성구":-2.2,"동구":-2.9,"서구":-3.4,"대덕구":-4.2,"중구":-5.3},
          "202605": {"동구":7.7,"중구":7.6,"서구":7.5,"대덕구":7.1,"유성구":6.3}, "202606": {"유성구":-0.9,"서구":-2.6,"중구":-2.7,"대덕구":-3.2,"동구":-4.3},
          "202607": {"서구":3.4,"동구":1.7,"대덕구":0.6,"중구":-1.9,"유성구":-8.7}}
city, gus, alley = [], [], []
import unicodedata
files = sorted([p for p in RDIR.glob("*.pdf") if re.match(r"^\d+", unicodedata.normalize("NFC", p.stem))], key=lambda p: int(re.match(r"\d+", unicodedata.normalize("NFC", p.stem)).group()))
for f in files:
    mnum = int(re.match(r"\d+", unicodedata.normalize("NFC", f.stem)).group()); month = f"2026{mnum:02d}"
    a = parse_alley(f, month); alley.append(a); print(month, "상권 행:", len(a), "이름 없는 행:", int((a.name == "").sum()))
A = pd.concat(alley, ignore_index=True)
# 7월 PDF 동구 상점가 2행은 글자 사이 공백이 들어가 자동 추출 실패 → 수기 보정 (PDF 2쪽 확인값)
A = pd.concat([A, pd.DataFrame([
    dict(month="202607", gu="동구", type="상점가", idx=2, name="대전상가", card_mom=8.4, ontong_mom=-73.4, pop_mom=-0.2, n_pct=3, raw="manual"),
    dict(month="202607", gu="동구", type="상점가", idx=3, name="역전시장상점가", card_mom=-8.4, ontong_mom=-65.8, pop_mom=-1.6, n_pct=3, raw="manual"),
])], ignore_index=True)
# 6월 등 이름 없는 행 → 같은 (gu,type,idx)의 가장 가까운 달 이름으로 채움
key = ["gu", "type", "idx"]
names = A[A.name != ""].drop_duplicates(key, keep="last").set_index(key).name
A.loc[A.name == "", "name"] = A[A.name == ""].set_index(key).index.map(names).values
A["name_filled"] = A.name.isna() | (A.name == "")
A = A.sort_values(["month","gu","type","idx"])
A.to_csv(OUT / "report_alley_monthly.csv", index=False, encoding="utf-8-sig")
# 2025-12 → 2026-07 누적 변화율 (전월 대비 %를 곱함), 7개월 전부 있는 상권만
W = A.pivot_table(index=["gu","type","name"], columns="month", values="card_mom")
full = W.dropna()
cum = ((1 + full / 100).prod(axis=1) - 1) * 100
P = A.pivot_table(index=["gu","type","name"], columns="month", values="pop_mom").dropna()
cum_pop = ((1 + P / 100).prod(axis=1) - 1) * 100
C = pd.DataFrame({"card_cum_dec25_to_jul26_pct": cum.round(1), "card_mom_mean": full.mean(axis=1).round(2), "card_mom_std": full.std(axis=1).round(2)})
C["pop_cum_dec25_to_jul26_pct"] = cum_pop.round(1)
C = C.reset_index().sort_values("card_cum_dec25_to_jul26_pct", ascending=False)
C.to_csv(OUT / "report_alley_cumulative.csv", index=False, encoding="utf-8-sig")
print("누적 변화율 상권 수:", len(C)); print(C.head(8).to_string(index=False)); print(C.tail(5).to_string(index=False))
pd.DataFrame(CITY, columns=CITY_COLS).to_csv(OUT / "report_city_monthly.csv", index=False, encoding="utf-8-sig")
pd.DataFrame([dict(month=m, gu=g, sales_mom=v) for m, d in GU_MOM.items() for g, v in d.items()]).to_csv(OUT / "report_gu_mom.csv", index=False, encoding="utf-8-sig")
print(A.groupby(["month"]).size().to_dict()); print(A[A.name.isna() | (A.name=="")].shape, "이름 미확정")
print("3개 값이 아닌 행:"); print(A[A.n_pct != 3][["month","gu","type","idx","name","raw"]].to_string(index=False))
print("이름 미확정:"); print(A[A.name.isna() | (A.name == "")][["month","gu","type","idx"]].to_string(index=False))
print(A.groupby(["month","gu"]).size().unstack().to_string())

# ── 20개 상권 ↔ 골목상권 대응 (이름 키워드, 수기 검토 2026-10-24. A01 복합터미널·A03 소제동은 해당 골목상권 없음) ──
AREA_KW = {"A04": "중앙로지하|중앙상가|중앙종합|자유도매|정원시장|원동중앙로|신중앙|역전시장|역전지하|대전상가|대전도매|중앙도매|중앙메가|전통중앙|중앙시장활성화",
           "A05": "은행동|대흥동|선화|중앙로지하", "A06": "오류|문화1동|문화동|버드내|유천", "A18": "송촌|법동|중리", "A14": "유성온천|유성시장|봉명|유성문화원",
           "A13": "궁동|어은|한빛", "A17": "도안|목원대|목대|관저|가수원", "A09": "만년|샘머리", "A07": "둔산2동|둔산꽃길|향촌|누리종합|둔산3동",
           "A20": "신탄진|석봉", "A19": "오정", "A12": "도룡", "A15": "관평", "A08": "탄방|청사", "A11": "용문|탄방|괴정|갈마", "A10": "월평", "A16": "노은|지족|반석", "A02": "가오|효동"}
rows = []
for a, k in AREA_KW.items():
    for _, r in C[C.name.str.contains(k)].iterrows():
        rows.append(dict(area=a, alley=r["name"], gu=r.gu, type=r.type, card_cum=r.card_cum_dec25_to_jul26_pct, pop_cum=r.pop_cum_dec25_to_jul26_pct))
M = pd.DataFrame(rows); M.to_csv(OUT / "report_alley_area_match.csv", index=False, encoding="utf-8-sig")
print("상권별 골목상권 누적 카드매출 변화 평균:"); print(M.groupby("area").agg(n=("alley","size"), card_cum_mean=("card_cum","mean"), pop_cum_mean=("pop_cum","mean")).round(1).to_string())
