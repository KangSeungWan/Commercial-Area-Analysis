"""대전 소상공인 실태조사(2021, 행정동) + 월별 업종 매출(2020-05~2021-09) 분석.

입력: data/raw/매출/ 의 csv (파일 이름은 상관없음, 열 이름으로 자동 구분 · cp949)
- 실태조사(행정동): '행정동명', '영업상황(성장단계)' 열이 있는 파일 (약 3.1만 사업체)
- 월별 업종 매출 : '업종명', '매출액' 열이 있는 파일 (186개 업종, 2020-05 시작 → 지역화폐 결제액으로 보임, 확인 필요)
※ 위치별 매출 금액은 없음 → 격자 매출 합성값을 대체하지는 못함. 대신
  ① 행정동별 '매출 감소' 응답률로 우리 쇠퇴 지표를 외부 검증
  ② 업종별 매출 구성·추이로 업종 분석 보강

출력 (outputs/)
- survey_dong.csv        : 행정동별 응답 수, 매출/이익 감소 %, 폐업·업종전환 고려 %, 손익분기점 넘음 %, 업종별 감소 %
- survey_validation.csv  : 감소·폐업고려 응답률 vs 우리 지표(점포 비중·지가·폐업률·원도심, 20개 상권 위험 점수) 순위 상관
- sales_industry.csv     : 업종 대분류(10개)별 월 매출·구성비, 2021년 1~9월 점포당 월 매출(상가정보 2021-09 점포 수 기준)
- survey_sales.png
"""
import glob

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import config as C

SALES_DIR = C.RAW_DIR / "매출"
# 카드 업종코드 앞 2자리 → 상가정보 대분류 (근사)
CODE2CAT = {11: "소매", 12: "소매", 13: "수리·개인", 14: "소매", 15: "소매", 16: "수리·개인", 17: "수리·개인",
            21: "소매", 22: "소매", 23: "음식", 24: "음식", 25: "음식", 26: "음식", 31: "소매", 32: "소매", 33: "소매",
            34: "소매", 35: "수리·개인", 36: "부동산", 38: "수리·개인", 41: "보건의료", 42: "보건의료", 44: "보건의료",
            45: "보건의료", 46: "보건의료", 51: "소매", 52: "소매", 53: "소매", 54: "소매", 56: "소매", 61: "숙박",
            62: "시설관리·임대", 64: "소매", 65: "수리·개인", 66: "소매", 67: "수리·개인", 71: "교육", 72: "교육",
            73: "교육", 81: "소매", 82: "예술·스포츠", 83: "예술·스포츠", 84: "예술·스포츠", 85: "예술·스포츠",
            92: "기타", 93: "기타", 94: "과학·기술", 95: "과학·기술", 96: "기타", 98: "기타", 99: "기타"}
FIX = {"8113": "수리·개인", "8114": "수리·개인", "8115": "보건의료", "8406": "수리·개인", "8405": "수리·개인",
       "3503": "시설관리·임대", "6204": "시설관리·임대", "6502": "수리·개인", "6702": "수리·개인", "7301": "보건의료"}


def find_files():
    out = {}
    for f in sorted(glob.glob(str(SALES_DIR / "*.csv"))):
        for enc in ("cp949", "utf-8-sig"):
            try:
                cols = [c.strip() for c in pd.read_csv(f, encoding=enc, nrows=0).columns]
                break
            except UnicodeDecodeError:
                continue
        if "영업상황(성장단계)" in cols and "행정동명" in cols:
            out["survey"] = (f, enc)
        elif "업종명" in cols and "매출액" in cols:
            out["sales_ind"] = (f, enc)
    if "survey" not in out:
        raise FileNotFoundError(f"{SALES_DIR} 에 '행정동명'·'영업상황(성장단계)' 열이 있는 실태조사 csv 가 없습니다")
    return out


def survey(path, enc):
    s = pd.read_csv(path, encoding=enc, dtype=str)
    s.columns = [c.strip() for c in s.columns]
    st = s["영업상황(성장단계)"]
    v = s[st != "999"].copy()
    v["decline"] = (v["영업상황(성장단계)"] == "매출/이익 감소").astype(int)
    v["closing"] = (v["영업상황(성장단계)"] == "업종전환/폐업고려").astype(int)
    v["profit"] = (v["영업상황(성장단계)"] == "손익분기점 넘음").astype(int)
    v["bad"] = v.decline | v.closing
    g = v.groupby("동코드")
    D = pd.DataFrame({"gu": g["구"].first(), "dong": g["행정동명"].first(), "n_valid": g.size(),
                      "decline_pct": g.decline.mean() * 100, "closing_pct": g.closing.mean() * 100,
                      "bad_pct": g.bad.mean() * 100, "profit_pct": g.profit.mean() * 100})
    for lab, key in [("food", "숙박 및 음식점업"), ("retail", "도매 및 소매업")]:
        sub = v[v["대분류 업종"] == key].groupby("동코드")
        D[f"bad_pct_{lab}"] = sub.bad.mean() * 100
        D[f"n_{lab}"] = sub.size()
    D["n_all"] = s.groupby("동코드").size()
    by_type = v.groupby("입지형태").bad.agg(["mean", "size"]).assign(mean=lambda d: d["mean"] * 100)
    by_ind = v.groupby("대분류 업종").bad.agg(["mean", "size"]).assign(mean=lambda d: d["mean"] * 100)
    return D.round(2), by_type, by_ind, v


def main():
    if not SALES_DIR.exists() or not list(SALES_DIR.glob("*.csv")):
        print(f"{SALES_DIR} 에 파일이 없어 건너뜀")
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False

    files = find_files()
    D, by_type, by_ind, V = survey(*files["survey"])
    print(f"실태조사: 사업체 {int(D.n_all.sum()):,}곳, 영업상황 응답 {int(D.n_valid.sum()):,}곳, 행정동 {len(D)}개")
    print(f"  대전 전체: 매출/이익 감소 {V.decline.mean() * 100:.1f}%, 폐업·업종전환 고려 {V.closing.mean() * 100:.1f}%, "
          f"손익분기점 넘음 {V.profit.mean() * 100:.1f}%")
    print("  입지별 어려움(감소+폐업고려) %:", by_type[by_type["size"] >= 100]["mean"].round(1).to_dict())

    # 우리 지표와 비교 (행정동)
    F = pd.read_csv(C.OUT_DIR / "factors_data.csv", encoding="utf-8-sig")
    prof = pd.read_csv(C.OUT_DIR / "dong_profile.csv", encoding="utf-8-sig")
    F["id"] = prof.id.astype(str).values[F.iloc[:, 0].astype(int)] if "id" not in F else F.id
    S = pd.read_csv(C.OUT_DIR / "dong_panel_store.csv", dtype={"period": str}, encoding="utf-8-sig")
    s16 = S[S.period == "201612"].set_index("k").share_chain
    s21 = S[S.period == "202109"].set_index("k").share_chain
    F["store_g_16_21"] = np.log(s21 / s16).reindex(F.iloc[:, 0].astype(int)).values
    L = pd.read_csv(C.OUT_DIR / "dong_panel_land.csv", encoding="utf-8-sig").pivot(index="k", columns="year", values="rel_idx")
    F["land_g_16_21"] = np.log(L[2021] / L[2016]).reindex(F.iloc[:, 0].astype(int)).values
    D.index = D.index.astype(str)
    M = F.merge(D, left_on="id", right_index=True, how="inner")
    M = M[M.n_valid >= 30]
    checks = {"점포 비중 변화 2016→2021": "store_g_16_21", "지가 대전 대비 변화 2016→2021": "land_g_16_21",
              "분기 폐업률(2017~25)": "close_rate", "원도심(동·중·대덕)": "old_town", "1호선 역 거리": "d_line1"}
    rows = []
    for lab, col in checks.items():
        for yv, ylab in [("bad_pct", "어려움(감소+폐업고려) %"), ("decline_pct", "매출 감소 %"), ("closing_pct", "폐업·전환 고려 %")]:
            ok = M[[col, yv]].dropna()
            r, p = spearmanr(ok[col], ok[yv])
            rows.append({"level": "행정동", "our_metric": lab, "survey": ylab, "spearman": round(r, 3), "p": round(p, 4),
                         "n": len(ok)})
    # 20개 상권: 상권 기준점이 있는 행정동의 응답률 vs 위험 점수
    sc = C.OUT_DIR / "area_scores.csv"
    if sc.exists():
        import json
        from build_dong_layer import DONG, label_points
        gj = json.load(open(DONG, encoding="utf-8"))
        A = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig")
        cen = A.anchors.str.split(";").str[0].str.split(expand=True).astype(float)
        A["k"] = label_points(gj, cen[1].values, cen[0].values)
        A["id"] = prof.id.astype(str).values[A.k]
        Sx = pd.read_csv(sc, encoding="utf-8-sig").merge(A[["code", "id"]], on="code").merge(D, left_on="id", right_index=True)
        Sx.to_csv(C.OUT_DIR / "survey_area.csv", index=False, encoding="utf-8-sig")
        for col, lab in [("risk_score", "쇠퇴 위험 점수"), ("growth_score", "성장 가능 점수")]:
            for yv, ylab in [("bad_pct", "어려움(감소+폐업고려) %"), ("decline_pct", "매출 감소 %")]:
                r, p = spearmanr(Sx[col], Sx[yv])
                rows.append({"level": "20개 상권(소속 행정동)", "our_metric": lab, "survey": ylab, "spearman": round(r, 3),
                             "p": round(p, 4), "n": len(Sx)})
    Vt = pd.DataFrame(rows)
    Vt.to_csv(C.OUT_DIR / "survey_validation.csv", index=False, encoding="utf-8-sig")
    D.to_csv(C.OUT_DIR / "survey_dong.csv", encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print("\n[외부 검증] 순위 상관 (+ = 우리 지표가 높을수록 실태조사 응답률도 높음)\n", Vt.to_string(index=False))

    # 업종별 매출 (월)
    if "sales_ind" in files:
        f, enc = files["sales_ind"]
        Q = pd.read_csv(f, encoding=enc)
        Q.columns = [c.strip() for c in Q.columns]
        Q["cat"] = Q["업종코드"].astype(str).map(FIX).fillna((Q["업종코드"] // 100).map(CODE2CAT)).fillna("기타")
        Q["ym"] = Q["년"].astype(str) + Q["월"].astype(int).astype(str).str.zfill(2)
        mon = Q.pivot_table(index="ym", columns="cat", values="매출액", aggfunc="sum").fillna(0)
        comp = mon.div(mon.sum(axis=1), axis=0) * 100
        y21 = mon.loc[[m for m in mon.index if m.startswith("2021")]].mean()
        st = pd.read_csv(C.OUT_DIR / "dong_panel_store.csv", dtype={"period": str}, encoding="utf-8-sig")
        cnt = st[st.period == "202109"][[c for c in st.columns if c.startswith("n_") and c not in
                                         ("n_stores", "n_open", "n_close", "n_prev", "n_city")]].sum()
        cnt.index = [c[2:] for c in cnt.index]
        T = pd.DataFrame({"월평균 매출 2021(억원)": (y21 / 1e8).round(1), "구성비 2021(%)": (y21 / y21.sum() * 100).round(1),
                          "점포 수 2021-09": cnt.reindex(y21.index)})
        T["점포당 월 매출(만원)"] = (y21 / T["점포 수 2021-09"] / 1e4).round(0)
        top = Q[Q["년"] == 2021].groupby("업종명")["매출액"].sum().sort_values(ascending=False).head(8) / 1e8
        T.sort_values("월평균 매출 2021(억원)", ascending=False).to_csv(C.OUT_DIR / "sales_industry.csv", encoding="utf-8-sig")
        print("\n[업종 대분류별 매출 (2021년 1~9월 월평균)]\n", T.sort_values("월평균 매출 2021(억원)", ascending=False).to_string())
        print("\n[2021년 매출 상위 세부 업종 (억원, 1~9월 합)]\n", top.round(0).to_string())

    # 그림
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2))
    ax = axes[0]
    ax.scatter(np.expm1(M.land_g_16_21) * 100, M.bad_pct, s=M.n_valid / 8, c=np.where(M.old_town == 1, "C3", "C0"), alpha=.7)
    r = Vt[(Vt.our_metric.str.startswith("지가")) & (Vt.survey.str.startswith("어려움"))].iloc[0]
    ax.set_xlabel("공시지가 대전 대비 변화 2016→2021 (%)"); ax.set_ylabel("실태조사: 매출 감소 + 폐업 고려 응답(%)")
    ax.set_title(f"행정동: 지가 상대 하락할수록 어려움 응답↑ (순위상관 {r.spearman:+.2f}, p {r.p:.3f})\n빨강 = 원도심 · 점 크기 = 응답 수", fontsize=10)
    ax = axes[1]
    if sc.exists():
        ax.scatter(Sx.risk_score, Sx.bad_pct, c="C3")
        for _, rr in Sx.iterrows():
            ax.annotate(rr["name"].split("(")[0], (rr.risk_score, rr.bad_pct), fontsize=7, xytext=(3, 2), textcoords="offset points")
        r = Vt[(Vt.our_metric == "쇠퇴 위험 점수") & (Vt.survey.str.startswith("어려움"))].iloc[0]
        ax.set_xlabel("우리 쇠퇴 위험 점수"); ax.set_ylabel("소속 행정동 실태조사 어려움 응답(%)")
        ax.set_title(f"20개 상권: 위험 점수 vs 실태조사 (순위상관 {r.spearman:+.2f}, p {r.p:.3f})", fontsize=10)
    ax = axes[2]
    if "sales_ind" in files:
        for c in comp.columns[comp.mean().argsort()[::-1][:6]]:
            ax.plot(pd.to_datetime(comp.index, format="%Y%m"), comp[c], label=c)
        ax.set_title("업종별 매출 구성비 (%, 월)"); ax.legend(fontsize=8)
    plt.tight_layout(); plt.savefig(C.OUT_DIR / "survey_sales.png", dpi=130)
    print("→ outputs/survey_dong.csv, survey_area.csv, survey_validation.csv, sales_industry.csv, survey_sales.png")


if __name__ == "__main__":
    main()
