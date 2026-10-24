"""업종 구성: 현재(상가정보 2026-06) + 트램 개통 후 예상 (대전 1호선 인허가 업종 효과) + 근거 표

입력: data/raw/…상가_상권_정보_대전_2026….csv (점포 좌표·업종), data/tram_stations.csv,
      outputs/sangkwon_polygons.geojson (핵심 상권 20), outputs/8989/dong_code_map.csv (행정동 82),
      outputs/line1_permits_sector.csv (업종별 효과·신뢰구간), outputs/line1_permits_es.csv (연차별 모양), outputs/line1_permits_effects.csv
출력: outputs/composition_now.csv       단위(대전·상권·행정동) × 업종 그룹 점포 수·비중, 업종별 정거장 500m 안 비율
      outputs/composition_forecast.csv  단위 × 시나리오(low/base/high) × 연도(2026, 2030~2034): 카페·빵집 예상 점포 수·비중, 늘어나는 수
      outputs/composition_evidence.csv  업종 효과 근거 한 표 (대전 1호선 + 해외)
방법
- 업종 그룹: 카페(비알코올/카페), 빵·과자(빵/도넛), 식사·주점(그 밖의 음식), 소매, 생활서비스(수리·개인), 교육, 보건의료, 기타
- 트램 효과는 1호선 인허가 이중차분 근거 점검(check_sector_evidence.py) 결과대로
  · 카페 = 주 효과: 개수 +24.8% [8.0, 44.2] (낮음=하한·기본·높음=상한). 비중 +1.4%p(1단계)·+4.0%p(2단계 독립 재현), 사전 추세 없음
  · 빵·과자 = 참고: 개수 +18.3%지만 음식점 중 비중은 변화 없음 → 낮음·기본 0, 높음에만 개수 효과
  · 나머지 업종 0 (전체 점포 수 효과는 불확실: 기본 +4.7% 유의 X, 번화도 맞춤 +12.4%) → 기준은 다른 업종 수 유지
- 단위 효과 = 그 업종 점포 중 정거장 500m 안 비율 × 업종 효과 × 연차 모양(카페 고유 사건연구: 개통 후 계속 커짐, 2006~2014 평균=1)
- 기준(트램 없음) = 현재 점포 수 유지 → '트램 때문에 달라지는 몫'만 보여 줌. 지하철 근거라 트램에서는 더 작을 수 있음(낮음 시나리오 참고)
"""
import json
import numpy as np
import pandas as pd

import config as C

OUT = C.OUT_DIR
OPEN_YEAR, YEARS = 2030, [2026, 2030, 2031, 2032, 2033, 2034]
GROUPS = ["카페", "빵·과자", "식사·주점", "소매", "생활서비스", "교육", "보건의료", "기타"]
EFFECT_GROUPS = {"카페": "카페", "빵·과자": "빵·과자"}          # 이 프로젝트 그룹 → line1_permits_sector 업종


def group_of(df):
    g = pd.Series("기타", index=df.index)
    big, mid, small = df.상권업종대분류명, df.상권업종중분류명.str.strip(), df.상권업종소분류명.str.strip()
    g[big == "음식"] = "식사·주점"
    g[(big == "음식") & (mid == "비알코올") & (small == "카페")] = "카페"
    g[(big == "음식") & (small == "빵/도넛")] = "빵·과자"
    g[big == "소매"] = "소매"; g[big == "수리·개인"] = "생활서비스"; g[big == "교육"] = "교육"; g[big == "보건의료"] = "보건의료"
    return g


def hav(lat1, lon1, lat2, lon2):
    R = 6371000; p1, p2 = np.radians(lat1), np.radians(lat2); dp, dl = p2 - p1, np.radians(lon2 - lon1)
    return 2 * R * np.arcsin(np.sqrt(np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2))


def pip(x, y, poly):
    px, py = np.array(poly)[:, 0], np.array(poly)[:, 1]; inside = np.zeros(len(x), bool); j = len(px) - 1
    for i in range(len(px)):
        inside ^= ((py[i] > y) != (py[j] > y)) & (x < (px[j] - px[i]) * (y - py[i]) / (py[j] - py[i] + 1e-12) + px[i]); j = i
    return inside


def shape_years():
    """개통 후 k년 효과 비율 (개통 후 2006~2014 평균 = 1). 카페 고유 사건연구(check_sector_evidence.py) 우선:
    개통 해 +4% → 8년 뒤 +56%로 줄지 않고 커짐. 없으면 1호선 전체 점포 사건연구."""
    f = OUT / "sector_evidence_es.csv"
    if f.exists():
        E = pd.read_csv(f, encoding="utf-8-sig"); E = E[(E.업종 == "카페") & (E.정의 == "기존")].set_index("year").b
        src = "카페 고유"
    else:
        E = pd.read_csv(OUT / "line1_permits_es.csv", encoding="utf-8-sig").set_index("year").b; src = "전체 점포"
    post = E[(E.index >= 2006) & (E.index <= 2014)]
    s_ = (post / post.mean()).clip(lower=0); s_.index = s_.index - 2006
    fn = lambda k: 0.0 if k < 0 else float(s_.get(min(k, s_.index.max()), s_.iloc[-1]))
    fn.src = src
    return fn


def main():
    raw = next((C.ROOT / "data" / "raw").glob("*상가_상권_정보_대전_2026*.csv"))
    st = pd.read_csv(raw, dtype=str, usecols=["상권업종대분류명", "상권업종중분류명", "상권업종소분류명", "행정동코드", "경도", "위도"]).dropna(subset=["경도", "위도"])
    st["grp"] = group_of(st); st["lon"], st["lat"] = st.경도.astype(float), st.위도.astype(float)
    TR = pd.read_csv(C.ROOT / "data" / "tram_stations.csv", encoding="utf-8-sig")
    d = np.full(len(st), np.inf)
    for _, r in TR.iterrows(): d = np.minimum(d, hav(st.lat.values, st.lon.values, r.lat, r.lon))
    st["near500"] = d <= 500
    fcm = OUT / "8989" / "dong_code_map.csv"                 # 8989 코드표가 없으면 행정동 단위는 건너뜀
    if fcm.exists():
        cm = pd.read_csv(fcm, dtype=str)
        st = st.merge(cm[["adstrdCode", "adm_cd2", "sgg", "dong"]], left_on="행정동코드", right_on="adstrdCode", how="left")
    else:
        print("outputs/8989/dong_code_map.csv 없음 → 행정동 단위 생략"); st["adm_cd2"] = None; st["sgg"] = st["dong"] = None
    st["area"] = None
    for f in json.load(open(OUT / "sangkwon_polygons.geojson", encoding="utf-8"))["features"]:
        g = f["geometry"]; polys = [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]
        m = np.zeros(len(st), bool)
        for p in polys: m |= pip(st.lon.values, st.lat.values, p)
        st.loc[m & st.area.isna(), "area"] = f["properties"]["code"]

    units = [("대전", "30", "대전 전체", st)]
    names_area = {f["properties"]["code"]: f["properties"].get("name") for f in json.load(open(OUT / "sangkwon_polygons.geojson", encoding="utf-8"))["features"]}
    units += [("상권", k, names_area.get(k, k), g) for k, g in st.dropna(subset=["area"]).groupby("area")]
    units += [("행정동", k, f"{g.sgg.iloc[0]} {g.dong.iloc[0]}", g) for k, g in st.dropna(subset=["adm_cd2"]).groupby("adm_cd2")]
    rows = []
    for lvl, key, name, g in units:
        r = dict(level=lvl, key=key, name=name, n_stores=len(g), near500_share=round(g.near500.mean(), 3))
        cnt = g.grp.value_counts()
        for gr in GROUPS:
            r[f"n_{gr}"] = int(cnt.get(gr, 0)); r[f"share_{gr}"] = round(cnt.get(gr, 0) / len(g), 4)
        for gr in EFFECT_GROUPS:
            sub = g[g.grp == gr]; r[f"near500_{gr}"] = round(sub.near500.mean(), 3) if len(sub) else 0.0
        rows.append(r)
    N = pd.DataFrame(rows)
    N.to_csv(OUT / "composition_now.csv", index=False, encoding="utf-8-sig")

    eff = pd.read_csv(OUT / "line1_permits_sector.csv", encoding="utf-8-sig").set_index("업종")
    E = {gr: {"low": eff.loc[s, "하한_%"] / 100, "base": eff.loc[s, "효과_%"] / 100, "high": eff.loc[s, "상한_%"] / 100} for gr, s in EFFECT_GROUPS.items()}
    # 빵·과자: 개수는 늘었지만 음식점 중 비중은 1·2단계 모두 변화 없음(sector_evidence_share.csv) → 구성 변화 근거로는 약함
    E["빵·과자"] = {"low": 0.0, "base": 0.0, "high": eff.loc["빵·과자", "효과_%"] / 100}
    shp = shape_years(); out = []
    for _, r in N.iterrows():
        for sc in ("low", "base", "high"):
            for y in YEARS:
                w = shp(y - OPEN_YEAR) if y >= OPEN_YEAR else 0.0
                o = dict(level=r.level, key=r.key, name=r["name"], scenario=sc, year=y)
                add_total = 0.0
                for gr in EFFECT_GROUPS:
                    add = r[f"n_{gr}"] * r[f"near500_{gr}"] * max(E[gr][sc], 0) * w
                    o[f"add_{gr}"] = round(add, 1); o[f"n_{gr}"] = round(r[f"n_{gr}"] + add, 1); add_total += add
                tot = r.n_stores + add_total                       # 다른 업종 수는 그대로 → 전체에 더해짐
                for gr in EFFECT_GROUPS:
                    o[f"share_{gr}"] = round(o[f"n_{gr}"] / tot, 4)
                o["cafe_bakery_share"] = round((o["n_카페"] + o["n_빵·과자"]) / tot, 4)
                o["cafe_bakery_share_now"] = round((r["n_카페"] + r["n_빵·과자"]) / r.n_stores, 4)
                o["cafe_bakery_pp"] = round((o["cafe_bakery_share"] - o["cafe_bakery_share_now"]) * 100, 3)
                o["cafe_bakery_add"] = round(add_total, 1)
                out.append(o)
    F = pd.DataFrame(out)
    F.to_csv(OUT / "composition_forecast.csv", index=False, encoding="utf-8-sig")

    ev = [dict(근거="대전 1호선 인허가 이중차분", 대상=s, 효과_퍼센트=eff.loc[s, "효과_%"], 하한=eff.loc[s, "하한_%"], 상한=eff.loc[s, "상한_%"], 판정=eff.loc[s, "판정"],
               비고="역 500m vs 1~3km, 2002~2014") for s in eff.index]
    tot = pd.read_csv(OUT / "line1_permits_effects.csv", encoding="utf-8-sig").iloc[0]
    ev.insert(0, dict(근거="대전 1호선 인허가 이중차분", 대상="전체 점포 수", 효과_퍼센트=tot["효과_%"], 하한=tot["하한_%"], 상한=tot["상한_%"], 판정="유의하지 않음", 비고=tot["분석"]))
    fs = OUT / "sector_evidence_share.csv"
    if fs.exists():
        for _, r in pd.read_csv(fs, encoding="utf-8-sig").iterrows():
            if "비중" in r.지표 or "전체" in r.지표:
                ev.append(dict(근거=f"대전 1호선 {r.단계} 인허가 이중차분 (근거 점검)", 대상=r.지표, 효과_퍼센트=r.효과, 하한=r.하한, 상한=r.상한,
                               판정=("확실" if r.p값 < 0.01 else "유의(5%)" if r.p값 < 0.05 else "유의하지 않음") + f" p={r.p값:.3f}", 비고=f"단위 {r.단위}"))
    ev += [dict(근거="마르세유 트램 (Credit 외)", 대상="신규 업체 중 숙박·음식 비중", 효과_퍼센트=np.nan, 하한=np.nan, 상한=np.nan, 판정="5% → 14%", 비고="트램 개통 후 노선 주변"),
           dict(근거="서울 9호선", 대상="음식점 생존율", 효과_퍼센트=12.7, 하한=np.nan, 상한=np.nan, 판정="보고값", 비고="개통 후 역세권"),
           dict(근거="피렌체 트램", 대상="업종 구성", 효과_퍼센트=np.nan, 하한=np.nan, 상한=np.nan, 판정="음식·관광 업종 비중 증가 보고", 비고="정성 근거")]
    pd.DataFrame(ev).to_csv(OUT / "composition_evidence.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 200)
    print("대전 전체:", N[N.level == "대전"][["n_stores", "n_카페", "n_빵·과자", "share_카페", "near500_카페", "near500_빵·과자"]].to_string(index=False))
    b = F[(F.scenario == "base") & (F.year == 2034)]
    for lvl in ("상권", "행정동"):
        x = b[b.level == lvl].sort_values("cafe_bakery_pp", ascending=False)
        print(f"\n[{lvl}] 2034 기본: 카페·빵집 비중 증가(%p) 상위\n", x.head(8)[["name", "cafe_bakery_share_now", "cafe_bakery_share", "cafe_bakery_pp", "cafe_bakery_add"]].to_string(index=False))
    t = F[(F.level == "대전") & (F.year == 2034)][["scenario", "cafe_bakery_add", "add_카페", "add_빵·과자", "cafe_bakery_pp"]]
    print("\n대전 전체 2034 트램 때문에 늘어나는 카페·빵집:\n", t.to_string(index=False))
    print(f"연차 모양({shp.src}, 개통 후 0~8년):", [round(shp(k), 2) for k in range(9)])


if __name__ == "__main__":
    main()
