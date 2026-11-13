"""트램 효과를 체감되는 단위로 보여 주기 (v24).

같은 효과(낮음·기본·높음 %, tram_effect.py)를 바꾸지 않고 '보여 주는 단위'만 바꿈.
  1) 금액   : 정거장 500m 안 필지 공시지가 총액(2026) × 효과 % → 땅값 증가액(억 원)
  2) 거리   : 대전 1호선 역에서 100m 띠별 효과 → 효과가 정거장 바로 앞에 몰리는지
  3) 경로   : 업종 변화 큰 상권(먼저 지원·변화 관찰)의 '트램 없을 때 vs 있을 때' 땅값 지수 + 그 차이의 금액

입력
- data/raw/공시지가/ 의 최신 개별공시지가 shp(+dbf) : 필지 면적(폴리곤) + 2026 공시지가
- outputs/landprice_parcels.csv.gz, landprice_long.pkl  (build_landprice)
- outputs/forecast_land.csv (forecast_areas), area_scores.csv (score_areas), tram_scenarios.csv
출력 (outputs/)
- parcel_value.csv.gz          : 필지 × 면적(㎡)·2026 공시지가(원/㎡)·총액(원)  ← 무거워서 있으면 다시 안 만듦
- tram_impact_money.csv        : 대전 전체 / 상권별 정거장 500m 안 공시지가 총액과 증가액(낮음·기본·높음)
- tram_impact_station.csv      : 정거장 45개별 같은 표
- tram_distance_bands.csv      : 1호선 역 거리 띠별 효과(%, 95% 구간) + 트램 시나리오에 옮긴 띠별 효과
- tram_with_without.csv        : 업종 변화 큰 상권 × 연도 지수(트램 없음/낮음/기본/높음) + 차이 금액(억 원)
- tram_impact_money.png, tram_distance_bands.png, tram_with_without.png

주의 (발표 문구에 그대로 쓸 것)
- 금액은 '공시지가 기준'. 공시지가는 시세보다 낮게 매겨지므로 시세 기준 금액은 이보다 큼
- 효과 %는 대전 1호선 실측(기본 1.8%)과 해외 트램 범위(analyze_tram_meta)를 그대로 씀 — 크기를 키우지 않음
- 증가액은 개통 초기(1~4년) 최대치. 시간 경로상 6년 뒤에는 약 35% 수준으로 줄어듦
- 도로·하천·구거·철도·제방·유지·공원(공공 시설 땅)은 합계에서 뺌
"""
import struct
import sys

import numpy as np
import pandas as pd

import config as C
import tram_effect as TE

PUBLIC_JIMOK = {"도", "천", "구", "철", "제", "유", "공"}
BANDS = [(0, 100), (100, 200), (200, 300), (300, 400), (400, 500), (500, 750), (750, 1000)]
EOK = 1e8


def load_long(years, pnus=None):
    """필지 × 연도 공시지가 (landprice_long.pkl). pyarrow 가 없어 피클을 못 열면 원본 D151 csv/zip 에서 필요한 연도만 읽음."""
    try:
        L = pd.read_pickle(C.OUT_DIR / "landprice_long.pkl")
    except ImportError:
        import zipfile
        from build_landprice import _std_cols, file_date, lp_files
        print("  (pyarrow 없음 → 원본 D151 에서 필요한 연도만 읽음)", flush=True)
        keep = {"고유번호", "기준년도", "기준연도", "기준월", "공시지가", "개별공시지가"}
        parts = []
        for f in sorted([*lp_files("D151", ".csv"), *lp_files("D151", ".zip")], key=file_date, reverse=True):
            srcs = ([(lambda n=n, z=zipfile.ZipFile(f): z.open(n)) for n in zipfile.ZipFile(f).namelist()
                     if n.lower().endswith(".csv")] if f.suffix.lower() == ".zip" else [lambda f=f: open(f, "rb")])
            for src in srcs:
                for enc in ("cp949", "utf-8-sig"):
                    try:
                        for ch in pd.read_csv(src(), encoding=enc, dtype=str, usecols=lambda c: c in keep, chunksize=2_000_000):
                            ch = _std_cols(ch)
                            ch = ch[ch.year.isin([str(y) for y in years]) & (ch.month.fillna("01").str.zfill(2) == "01")]
                            parts.append(ch[["pnu", "year", "price"]])
                        break
                    except UnicodeDecodeError:
                        continue
        L = pd.concat(parts)
        L = L[L.pnu.str.match(r"^\d{19}$")]
        L = L.assign(pnu=L.pnu.astype("int64"), year=L.year.astype(int), price=pd.to_numeric(L.price, errors="coerce"))
        L = L[L.price > 0].drop_duplicates(["pnu", "year"])
    L = L[L.year.isin(list(years))]
    return L[L.pnu.isin(pnus)] if pnus is not None else L


# ------------------------------------------------------------------ 1) 필지 면적·가격
def _polygon_areas(shp):
    """shp 각 레코드의 면적(㎡). 좌표가 미터 단위 TM(EPSG:5186/5174)이어야 함."""
    data = shp.read_bytes()
    offs = np.frombuffer(shp.with_suffix(".shx").read_bytes()[100:], ">i4").reshape(-1, 2)[:, 0].astype(np.int64) * 2
    out = np.full(len(offs), np.nan)
    for i, p in enumerate(offs):
        st = struct.unpack("<i", data[p + 8:p + 12])[0]
        if st not in (5, 15, 25):            # polygon 계열만
            continue
        nparts, npts = struct.unpack("<2i", data[p + 44:p + 52])
        parts = np.frombuffer(data, "<i4", nparts, p + 52)
        pts = np.frombuffer(data, "<f8", npts * 2, p + 52 + 4 * nparts).reshape(-1, 2)
        tot = 0.0
        for k in range(nparts):
            a, b = parts[k], parts[k + 1] if k + 1 < nparts else npts
            x, y = pts[a:b, 0], pts[a:b, 1]
            tot += 0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])
        out[i] = -tot                         # 바깥 고리 시계 방향 → 양수, 구멍(반시계)은 빠짐
    return out


def parcel_value(force=False):
    f = C.OUT_DIR / "parcel_value.csv.gz"
    if f.exists() and not force:
        return pd.read_csv(f, encoding="utf-8-sig")
    from build_landprice import file_date, lp_files, read_dbf
    shp = sorted(lp_files("D150", ".shp"), key=file_date)[-1]   # 가장 최근 공시분
    print(f"  필지 면적: {shp.name} 폴리곤에서 계산 (1~2분) ...", flush=True)
    d, fields = read_dbf(shp.with_suffix(".dbf"), {"A0", "A7", "A9", "A16", "A17"})
    area = _polygon_areas(shp)
    n = min(len(d), len(area))
    d = d.iloc[:n].assign(area_m2=area[:n])
    d = d[d.A0.str.match(r"^\d{19}$")].copy()
    d["pnu"] = d.A0.astype("int64")                                 # 19자리: float 변환 금지
    yr = pd.to_numeric(d.A7, errors="coerce")
    num = lambda c: pd.to_numeric(d[c], errors="coerce") if c in d else np.nan
    # 2026 공시가 우선, 없으면 같은 dbf 의 1·2년 전 값(A16=전년, A17=2년 전)으로 보충
    d["price"] = num("A9").where(yr == 2026)
    for k, col in [(1, "A16"), (2, "A17")]:
        d["price"] = d.price.fillna(num(col).where(yr == 2026))
        d["price"] = d.price.fillna(num("A9").where(yr == 2026 - k))
    d = d.drop_duplicates("pnu")[["pnu", "area_m2", "price"]]
    d = d[(d.area_m2 > 0) & (d.price > 0)]
    d["value"] = d.area_m2 * d.price
    d.to_csv(f, index=False, encoding="utf-8-sig")
    print(f"  필지 {len(d):,}개, 면적 합 {d.area_m2.sum() / 1e6:,.1f}㎢, 총액 {d.value.sum() / 1e12:,.1f}조 원", flush=True)
    return d


def money_tables(G, L, B=None):
    """대전 전체·상권별·정거장별 500m 안 총액과 증가액.
    B(거리 띠 결과)가 있으면 '영향권 750m' 변형도 계산: 500~750m 필지에는 1호선 띠 비율(500~750m ÷ 0~500m, 1 넘으면 1)을 곱함."""
    pct = {s: L[s]["pct"] / 100 for s in TE.SCEN}
    G = G[~G.jimok.isin(PUBLIC_JIMOK)]
    near = G[G.d_tram <= 500]
    names = pd.read_csv(C.AREAS_CSV, encoding="utf-8-sig").set_index("code").name

    def row(df, **kw):
        v = df.value.sum()
        r = dict(**kw, n_parcels=len(df), area_km2=round(df.area_m2.sum() / 1e6, 3), value_eok=round(v / EOK, 1))
        for s in TE.SCEN:
            r[f"gain_{s}_eok"] = round(v * pct[s] / EOK, 1)
        return r

    rows = [row(near, unit="대전 전체", code="ALL", name="정거장 45개 500m 안"),
            row(near[near.d_l1 > 500], unit="대전 전체", code="ALL_new",
                name="정거장 500m 안 (1호선 역 500m 밖, 새로 역세권이 되는 땅)"),
            row(G, unit="대전 전체", code="CITY", name="대전 전체 (비교용, 효과 적용 대상 아님)")]
    for c, g in near.groupby("area"):
        rows.append(row(g, unit="상권", code=c, name=names.get(c, c)))
    if B is not None:
        ring = G[(G.d_tram > 500) & (G.d_tram <= 750)]
        r750 = dict(unit="대전 전체", code="ALL_750", name="정거장 750m 안 (500~750m 는 1호선 띠 비율 적용, 변형)",
                    n_parcels=len(near) + len(ring), area_km2=round((near.area_m2.sum() + ring.area_m2.sum()) / 1e6, 3),
                    value_eok=round((near.value.sum() + ring.value.sum()) / EOK, 1))
        for s_, lab in [("low", "1호선 1·2단계 합산"), ("base", "1호선 1·2단계 합산"), ("high", "1호선 1단계")]:
            e = B[B.line1 == lab].set_index("band_m").effect_pct
            ratio = float(np.clip(e["500-750"] / e["0-500"], 0, 1)) if e["0-500"] > 0.5 else 0.0
            r750[f"gain_{s_}_eok"] = round((near.value.sum() * pct[s_] + ring.value.sum() * pct[s_] * ratio) / EOK, 1)
            r750[f"ratio_500_750_{s_}"] = round(ratio, 2)
        rows.insert(2, r750)
    M = pd.DataFrame(rows)
    M.loc[M.code == "CITY", [f"gain_{s}_eok" for s in TE.SCEN]] = np.nan          # 비교용 총액만
    st = pd.read_csv(C.ROOT / "data" / "tram_stations.csv", encoding="utf-8-sig").set_index("station_no").station_name
    S = pd.DataFrame([row(g, unit="정거장", code=int(k), name=st.get(int(k), str(k))) for k, g in near.groupby("tram_no")])
    S = S.sort_values("gain_base_eok", ascending=False)
    return M, S


# ------------------------------------------------------------------ 2) 거리 띠별 효과
def distance_bands(G, L):
    import analyze_landprice as AL
    Gd = G[G.is_dae == 1].set_index("pnu")
    Gd = Gd[Gd.d_l1 <= 3000]                                                 # 처리·비교군만 (메모리 절약)
    LL = load_long(range(2005, 2012), set(Gd.index))
    W = np.log(LL.pivot(index="pnu", columns="year", values="price"))
    Gd = Gd.loc[W.index]
    ctrl = (Gd.d_l1 > 1000) & (Gd.d_l1 <= 3000)
    rows = []
    for ph, label, post in [(1, "1호선 1단계", range(2007, 2011)), ("12", "1호선 1·2단계 합산", range(2008, 2012))]:
        sel_ph = Gd.l1_phase == 1 if ph == 1 else Gd.l1_phase.isin([1, 2])
        for a, b in BANDS + [(0, 500)]:
            tr = sel_ph & (Gd.d_l1 > a) & (Gd.d_l1 <= b)
            es, boot, yrs = AL.event_study(Gd, W, tr, ctrl, 2005, list(post))
            m, lo, hi = AL.window_mean(es, boot, yrs, post)
            rows.append({"line1": label, "band_m": f"{a}-{b}", "d_mid": (a + b) / 2 if (a, b) != (0, 500) else np.nan,
                         "effect_pct": AL.pct(m), "ci_lo_pct": AL.pct(lo), "ci_hi_pct": AL.pct(hi),
                         "n_parcels": int(es.n_treat.max())})
    B = pd.DataFrame(rows)
    return B


# ------------------------------------------------------------------ 3) 트램 없을 때 vs 있을 때
def with_without(G):
    F = pd.read_csv(C.OUT_DIR / "forecast_land.csv", encoding="utf-8-sig")
    Sc = pd.read_csv(C.OUT_DIR / "area_scores.csv", encoding="utf-8-sig")
    import policy_quadrant as PQ
    codes = list(Sc[Sc.quadrant.isin(PQ.CHANGE_BIG)].code)
    val = G[~G.jimok.isin(PUBLIC_JIMOK)].groupby("area").value.sum()      # 상권 전체 공시지가 총액(2026)
    F = F[F.code.isin(codes)].copy()
    F["area_value_eok"] = F.code.map(val) / EOK
    for s in TE.SCEN:
        F[f"gap_{s}_eok"] = ((F[f"tram_{s}"] / F.base_path - 1) * F.area_value_eok).round(1)
    A = pd.read_csv(C.OUT_DIR / "landprice_area_panel.csv", encoding="utf-8-sig")
    H = A[A.code.isin(codes) & (A.year >= 2005)].pivot(index="year", columns="code", values="idx")
    H = H / H.loc[H.index.max()] * 100                                      # 2026 = 100 으로 이어 붙임
    return F, H, codes


# ------------------------------------------------------------------ 그림
def _font(plt):
    from matplotlib import font_manager as fm
    for f in fm.findSystemFonts():
        if any(k in f for k in ("AppleSDGothicNeo", "AppleGothic", "NanumGothic", "NotoSansCJK", "Malgun")):
            fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False


INK, MUTED, GRID, ACCENT, ACCENT2 = "#1f2a1c", "#8a9682", "#e4e7e0", "#2f5d8a", "#b0563a"


def _clean(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(MUTED)
    ax.tick_params(colors=INK, labelsize=9)


def fig_money(M, L, plt):
    tot = M[M.code == "ALL"].iloc[0]
    A = M[M.unit == "상권"].sort_values("gain_base_eok")
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(A) + 1.8))
    y = np.arange(len(A))
    ax.barh(y, A.gain_base_eok, color=ACCENT, height=0.6, label=f"기본 ({L['base']['pct']}%)")
    ax.errorbar(A.gain_base_eok, y, xerr=[A.gain_base_eok - A.gain_low_eok, A.gain_high_eok - A.gain_base_eok],
                fmt="none", ecolor=INK, lw=1, capsize=3, label=f"낮음~높음 ({L['low']['pct']}~{L['high']['pct']}%)")
    for yi, (b, h) in enumerate(zip(A.gain_base_eok, A.gain_high_eok)):
        ax.text(h + A.gain_high_eok.max() * 0.015, yi, f"{b:,.0f}억", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(y); ax.set_yticklabels(A.name, fontsize=9)
    ax.set_xlabel("정거장 500m 안 땅값 증가액 (억 원, 2026 공시지가 기준, 개통 1~4년)")
    ax.set_title(f"트램 개통으로 정거장 500m 안 땅값 약 {tot.gain_base_eok / 1e4:,.2f}조 원 증가 (기본)\n"
                 f"낮음 {tot.gain_low_eok / 1e4:,.2f}조 ~ 높음 {tot.gain_high_eok / 1e4:,.2f}조 · "
                 f"500m 안 공시지가 총액 {tot.value_eok / 1e4:,.1f}조 원", loc="left", fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    _clean(ax); ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(C.OUT_DIR / "tram_impact_money.png", dpi=150); plt.close(fig)


def fig_bands(B, plt):
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    for lab, col, off in [("1호선 1단계", ACCENT, -12), ("1호선 1·2단계 합산", MUTED, 12)]:
        b = B[(B.line1 == lab) & B.d_mid.notna()]
        ax.errorbar(b.d_mid + off, b.effect_pct, yerr=[b.effect_pct - b.ci_lo_pct, b.ci_hi_pct - b.effect_pct],
                    fmt="o-", color=col, ms=6, lw=1.6, capsize=3, label=lab)
    for x, t in [(500, "현재 효과 적용 반경 500m")]:
        ax.axvline(x, color=MUTED, ls=":", lw=1); ax.text(x + 8, ax.get_ylim()[1] * 0.92, t, fontsize=8.5, color=MUTED)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xlabel("1호선 역에서 거리 (m, 띠 가운데)"); ax.set_ylabel("개통 후 땅값 효과 (%), 95% 구간")
    e = B[B.line1 == "1호선 1단계"].set_index("band_m").effect_pct
    near_peak = e["0-100"] > e["0-500"] + 1.0
    head = "효과가 역 바로 앞에 몰림" if near_peak else "효과는 역 바로 앞만이 아니라 넓게 퍼짐"
    ax.set_title(f"{head}\n1호선 1단계: 100m 안 {e['0-100']:+.1f}%, 500m 평균 {e['0-500']:+.1f}%, "
                 f"500~750m {e['500-750']:+.1f}%, 750~1,000m {e['750-1000']:+.1f}%", loc="left", fontsize=10.5, color=INK)
    ax.legend(frameon=False, fontsize=9); _clean(ax); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(C.OUT_DIR / "tram_distance_bands.png", dpi=150); plt.close(fig)


def fig_paths(F, H, codes, plt, open_year):
    names = F.drop_duplicates("code").set_index("code").name
    fig, axes = plt.subplots(1, len(codes), figsize=(3.3 * len(codes), 4.2), sharey=False)
    axes = np.atleast_1d(axes)
    for ax, c in zip(axes, codes):
        h = H[c].dropna(); f = F[F.code == c]
        ax.plot(h.index, h.values, color=INK, lw=1.4)
        ax.plot(f.year, f.base_path, color=MUTED, ls="--", lw=1.4, label="트램 없을 때")
        ax.fill_between(f.year, f.tram_low, f.tram_high, color=ACCENT, alpha=0.15, lw=0, label="트램 낮음~높음")
        ax.plot(f.year, f.tram_base, color=ACCENT, lw=2, label="트램 있을 때 (기본)")
        ax.axvline(open_year, color=MUTED, lw=0.8, ls=":")
        end = f[f.year == f.year.max()].iloc[0]
        ax.text(0.03, 0.97, f"{int(end.year)}년 차이\n+{end.gap_base_eok:,.0f}억 원\n(높음 +{end.gap_high_eok:,.0f}억)",
                transform=ax.transAxes, va="top", fontsize=9, color=ACCENT, fontweight="bold")
        ax.set_title(names[c].split("(")[0], fontsize=10, color=INK)
        h2 = h[h.index >= 2016]
        lo = min(h2.min(), f.base_path.min(), f.tram_low.min()); hi = max(h2.max(), f.tram_high.max())
        ax.set_ylim(lo - (hi - lo) * 0.05, hi + (hi - lo) * 0.45)
        ax.set_xlim(2016, f.year.max() + 0.5); ax.set_xticks([2016, 2020, 2026, 2030, 2034])
        _clean(ax); ax.grid(axis="y", color=GRID, lw=0.8)
    axes[0].set_ylabel("공시지가 지수 (2026 = 100)")
    axes[-1].legend(frameon=False, fontsize=8, loc="lower right")
    tot = F[F.year == F.year.max()]
    fig.suptitle(f"업종 변화 큰 {len(codes)}곳: 트램이 있으면 {int(F.year.max())}년 땅값이 합계 {tot.gap_base_eok.sum():,.0f}억 원 더 높음 "
                 f"(높음 {tot.gap_high_eok.sum():,.0f}억) · 점선 = {open_year} 개통", x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(); fig.savefig(C.OUT_DIR / "tram_with_without.png", dpi=150); plt.close(fig)


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _font(plt)
    force = "--force" in sys.argv
    L = TE.levels()
    G0 = pd.read_csv(C.OUT_DIR / "landprice_parcels.csv.gz", encoding="utf-8-sig")
    pd.set_option("display.width", 220)

    print("1/3 거리 띠별 효과 (1호선, 약 30초) ...", flush=True)
    B = distance_bands(G0, L)                                               # 1호선 분석은 모든 필지(옛 필지 포함)
    B.to_csv(C.OUT_DIR / "tram_distance_bands.csv", index=False, encoding="utf-8-sig")
    print(B.to_string(index=False))
    fig_bands(B, plt)

    print("\n2/3 필지 공시지가 총액 → 증가액 ...", flush=True)
    V = parcel_value(force)
    G = G0.merge(V, on="pnu", how="inner")                                  # 2026 면적·가격이 있는 필지
    M, S = money_tables(G, L, B)
    M.to_csv(C.OUT_DIR / "tram_impact_money.csv", index=False, encoding="utf-8-sig")
    S.to_csv(C.OUT_DIR / "tram_impact_station.csv", index=False, encoding="utf-8-sig")
    print(M.to_string(index=False))
    print("\n정거장 증가액 상위 8\n", S.head(8).to_string(index=False))
    fig_money(M, L, plt)

    print("\n3/3 트램 없을 때 vs 있을 때 ...", flush=True)
    from forecast_areas import OPEN_YEAR
    F, H, codes = with_without(G)
    F.to_csv(C.OUT_DIR / "tram_with_without.csv", index=False, encoding="utf-8-sig")
    print(F[F.year == F.year.max()][["name", "base_path", "tram_base", "area_value_eok", "gap_low_eok",
                                     "gap_base_eok", "gap_high_eok"]].round(1).to_string(index=False))
    fig_paths(F, H, codes, plt, OPEN_YEAR)
    print("→ outputs/tram_impact_money.csv/.png, tram_impact_station.csv, tram_distance_bands.csv/.png, "
          "tram_with_without.csv/.png")


if __name__ == "__main__":
    main()
