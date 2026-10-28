"""공개 웹사이트(web/)용 데이터 내보내기: outputs 결과 → web_data/*.json (2026-10-28)

사용: python tram_model/export_web.py            (프로젝트 폴더에서, run_all.py 다음)
출력: web_data/  (React 사이트가 그대로 읽음. 사이트 빌드 때 public/data 로 복사)

공개 원칙 (8989 재배포 금지 · API 키)
- 8989 원자료·월별 매출·금액·행정동별 카드매출 증감(%)은 넣지 않음 (10-28 결정: 공개 사이트에서 누구나 내려받을 수 있어
  재단 '재배포 금지' 조건과 겹칠 수 있음 → 재단 확인 전까지 제외. Streamlit 앱·발표에는 그대로). 분석 결과 요약(공사 −1.4% 등)만 출처와 함께
- AI 해설은 미리 만든 기본 해설만. Gemini 키·실시간 호출 없음
- 개인정보 없음. 모든 값은 분석 결과(통계)이며 원자료 행이 아님
"""
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
OUT, DATA = HERE / "outputs", HERE / "data"
DST = ROOT / "web_data"


def csv(p, **kw):
    p = Path(p)
    return pd.read_csv(p, encoding="utf-8-sig", **kw) if p.exists() else None


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 5)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if o is pd.NaT:
        return None
    return o


def save(name, obj):
    DST.mkdir(exist_ok=True)
    (DST / name).write_text(json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  {name:<28} {(DST / name).stat().st_size / 1024:8.1f} KB")


def records(df, cols=None):
    if df is None:
        return []
    d = df[[c for c in (cols or df.columns) if c in df.columns]]
    return d.replace({np.nan: None}).to_dict("records")


def quad_before(df):
    reb = df.quadrant == "트램 반등 기회"
    return df.quadrant.where(~reb, np.select([df.risk_score >= 50, df.growth_score >= 50], ["쇠퇴 우려", "성장 지속"], "정체·안정"))


def main():
    import ai_comment as ac
    from tram_route import route_paths

    stations = csv(DATA / "tram_stations.csv")
    if stations is None:
        stations = csv(DATA / "tram_stations_approx.csv")
    stations = stations.sort_values("station_no")
    prof = csv(OUT / "area_profile.csv")
    ts = csv(OUT / "tram_scenarios.csv")
    fc = csv(OUT / "forecast_land.csv")
    comp = csv(OUT / "composition_forecast.csv", dtype={"key": str})
    cnow = csv(OUT / "composition_now.csv", dtype={"key": str})
    rentp = csv(OUT / "rent_pressure.csv", dtype={"key": str})
    money = csv(OUT / "tram_impact_money.csv")
    sens = csv(OUT / "station_coord_sensitivity.csv", dtype={"key": str})
    dev = csv(OUT / "development_trend_dong.csv", dtype={"dong_id": str})
    rsurv = csv(OUT / "rent_survey_area.csv")
    ssp = csv(OUT / "station_sales_premium.csv")
    st_sum = csv(OUT / "station_summary.csv")
    st_areas = csv(OUT / "station_areas.csv")
    dss = csv(OUT / "dong_station_summary.csv", dtype={"dong_id": str})
    events = csv(DATA / "area_events.csv")
    dprof = csv(OUT / "dong_map_profile.csv", dtype={"dong_id": str})
    print("→", DST)

    # ── 시나리오·노선·정거장 ──
    TS = {r.scenario: dict(label=r.label, effect_pct=r.effect_pct, source=r.source,
                           ci95=r.ci95 if isinstance(r.ci95, str) else None) for r in ts.itertuples()}
    paths = route_paths(stations)
    l1 = csv(DATA / "line1_stations.csv")
    st_rec = stations[["station_no", "station_name", "lat", "lon"]].copy()
    if st_sum is not None:
        st_rec = st_rec.merge(st_sum, on="station_no", how="left", suffixes=("", "_s"))
    stn = []
    for r in st_rec.itertuples():
        a = st_areas[st_areas.station_no == r.station_no] if st_areas is not None else pd.DataFrame()
        d = dss[dss.station_no == r.station_no] if dss is not None else pd.DataFrame()
        stn.append(dict(no=int(r.station_no), name=r.station_name, lat=r.lat, lon=r.lon,
                        n_stores=getattr(r, "n_stores", None),
                        top=getattr(r, "top3", None) if hasattr(r, "top3") else None,
                        areas=[dict(code=x.code, n=int(x.stores_in_500m), share=x.share_of_area_pct) for x in a.itertuples()],
                        dongs=[dict(id=x.dong_id, name=getattr(x, "name", None) or getattr(x, "dong", None), share=getattr(x, "share", None),
                                    n=getattr(x, "n_stores_500", None) or getattr(x, "stores_in_500m", None)) for x in d.itertuples()]))
    sales_ratio = None
    if ssp is not None and "전체: 기본" in set(ssp.model):
        sales_ratio = float(ssp.set_index("model").loc["전체: 기본", "ratio_to_land"])

    # ── 상권 20 ──
    P = prof.copy()
    P["quadrant_after"] = P.quadrant
    P["quadrant_before"] = quad_before(P)
    y = int(fc.year.max())
    f = fc[fc.year == y].set_index("code")
    areas = []
    for r in P.itertuples():
        c = r.code
        a = {k: getattr(r, k) for k in ["code", "name", "gu", "type", "n_stores", "top3_mid", "nearest_tram", "nearest_tram_m",
                                       "tram_group", "land_chg_5y_pct", "land_chg_10y_pct", "land_rel_idx", "store_share_chg_5y_pct",
                                       "close_rate_q_pct", "type_name", "risk_score", "growth_score", "risk_drivers", "growth_drivers",
                                       "quadrant_stability", "quadrant_alt", "quadrant_uncertain", "in500", "abs_decline", "abs_decline_n",
                                       "abs_decline_why", "survey_dong", "decline_pct", "closing_pct", "bad_pct",
                                       "tram_effect", "tram_effect_low", "tram_effect_high", "quadrant_after", "quadrant_before"]
             if hasattr(r, k)}
        if c in f.index:
            a["land_fc"] = {"none": f.loc[c, "base_path"] - 100, "base": f.loc[c, "tram_base"] - 100,
                            "low": f.loc[c, "tram_low"] - 100, "high": f.loc[c, "tram_high"] - 100}
        if comp is not None:
            cc = comp[(comp.level == "상권") & (comp.key == c) & (comp.year == comp.year.max())].set_index("scenario")
            a["comp"] = {s: dict(pp=cc.loc[s, "cafe_bakery_pp"], add=cc.loc[s, "cafe_bakery_add"], now=cc.loc[s, "cafe_bakery_share_now"],
                                 y34=cc.loc[s, "cafe_bakery_share"], add_cafe=cc.loc[s, "add_카페"]) for s in cc.index}
        if rentp is not None:
            rr = rentp[(rentp.level == "상권") & (rentp.key == c)]
            if len(rr):
                x = rr.iloc[0]
                a["rent"] = dict(grade=x.rent_pressure, score=x.rent_pressure_score,
                                 drivers=x.rent_drivers if isinstance(x.rent_drivers, str) else None,
                                 stab=x.get("rent_pressure_stability"))
        if money is not None and c in set(money.code):
            m = money.set_index("code").loc[c]
            a["money"] = {s: m.get(f"gain_{s}_eok") for s in ("low", "base", "high")}
        if sens is not None:
            s_ = sens[(sens.level == "상권") & (sens.key == c) & sens.sensitive.astype(bool)]
            a["sens"] = s_.note.iloc[0] if len(s_) else None
        if rsurv is not None and c in set(rsurv.code):
            x = rsurv.set_index("code").loc[c]
            mid = pd.notna(x.get("vac_mid_4q"))
            a["rent_market"] = dict(region=x.region, kind="중대형" if mid else "집합",
                                    vac=x.get("vac_mid_4q") if mid else x.get("vac_coll_4q"),
                                    idx=x.get("idx_chg_mid_22_26") if mid else x.get("idx_chg_coll_22_26"),
                                    rent=(x.get("rent_mid_2026q2") if mid else x.get("rent_coll_2026q2")))
        if events is not None:
            ev = events[events.area_codes.fillna("").str.contains(c)]
            a["events"] = [dict(date=e.date, text=e.description) for e in ev.itertuples()]
        if st_areas is not None:
            a["stations"] = [dict(no=int(x.station_no), n=int(x.stores_in_500m), share=x.share_of_area_pct)
                             for x in st_areas[st_areas.code == c].itertuples()]
        areas.append(a)
    if money is not None and "ALL" in set(money.code):
        m = money.set_index("code").loc["ALL"]
        money_all = {s: m.get(f"gain_{s}_eok") for s in ("low", "base", "high")}
    else:
        money_all = None

    # ── 행정동 82 ──
    dongs = []
    if dprof is not None:
        D = dprof.copy()
        D["quadrant_after"] = D.quadrant
        D["quadrant_before"] = quad_before(D)
        devm = {r.dong_id: (r.dev_kind, r.dev_reason) for r in dev.itertuples() if bool(r.dev_flag)} if dev is not None else {}
        keep = ["dong_id", "name", "si", "dong", "n_stores", "top3", "nearest_tram", "nearest_tram_m", "tram500_share", "tram_group",
                "land_chg_5y_pct", "land_chg_10y_pct", "land_rel_idx", "store_share_chg_5y_pct", "type_name", "risk_score", "growth_score",
                "risk_drivers", "growth_drivers", "quadrant_stability", "quadrant_alt", "quadrant_uncertain", "abs_decline", "abs_decline_n",
                "abs_decline_why", "small", "areas", "score_note", "survey_bad_pct", "tram_effect", "tram_effect_low", "tram_effect_high",
                "quadrant_after", "quadrant_before"]  # s89_sales_yoy_pct·s89_market_caveat 는 공개 제외(위 공개 원칙)
        for r in D.to_dict("records"):
            k = r["dong_id"]
            d = {c: r.get(c) for c in keep if c in r}
            d["land_fc"] = {"none": r.get("land_2034_base", np.nan) - 100, "base": r.get("land_2034_tram", np.nan) - 100,
                            "low": r.get("land_2034_tram_low", np.nan) - 100, "high": r.get("land_2034_tram_high", np.nan) - 100}
            d["money"] = {s: r.get(f"money_gain_{s}_eok") for s in ("low", "base", "high")}
            if comp is not None:
                cc = comp[(comp.level == "행정동") & (comp.key == k) & (comp.year == comp.year.max())].set_index("scenario")
                d["comp"] = {s: dict(pp=cc.loc[s, "cafe_bakery_pp"], add=cc.loc[s, "cafe_bakery_add"], now=cc.loc[s, "cafe_bakery_share_now"],
                                     y34=cc.loc[s, "cafe_bakery_share"], add_cafe=cc.loc[s, "add_카페"]) for s in cc.index}
            if rentp is not None:
                rr = rentp[(rentp.level == "행정동") & (rentp.key == k)]
                if len(rr):
                    x = rr.iloc[0]
                    d["rent"] = dict(grade=x.rent_pressure, score=x.rent_pressure_score,
                                     drivers=x.rent_drivers if isinstance(x.rent_drivers, str) else None,
                                     stab=x.get("rent_pressure_stability"))
            if sens is not None:
                s_ = sens[(sens.level == "행정동") & (sens.key == k) & sens.sensitive.astype(bool)]
                d["sens"] = s_.note.iloc[0] if len(s_) else None
            d["dev"] = list(devm[k]) if k in devm else None
            dongs.append(d)

    # ── 대전 전체 수치 ──
    city = {}
    if comp is not None:
        cd = comp[(comp.level == "대전") & (comp.year == comp.year.max())].set_index("scenario")
        city["cafe_add"] = {s: cd.loc[s, "add_카페"] for s in cd.index}
    devc = csv(OUT / "development_trend_checks.csv")
    if devc is not None:
        v = devc.variant.astype(str)
        city["dev_l1"] = devc[v.str.startswith("개발지 법정동")].effect_pct.iloc[0] if v.str.startswith("개발지 법정동").any() else None
        city["dev_money"] = devc[v == "개발지 동의 몫"].effect_pct.iloc[0] if (v == "개발지 동의 몫").any() else None
    lp = csv(OUT / "landprice_area_panel.csv")
    if lp is not None:
        a_ = lp[lp.code == "ALL"].set_index("year").idx
        city["land_5y_pct"] = float((a_.iloc[-1] / a_.loc[a_.index.max() - 5] - 1) * 100)

    save("meta.json", dict(open_year=2030, scen=TS, route=paths, stations=stn, sales_ratio=sales_ratio, money_all=money_all, city=city,
                           line1=records(l1, ["station_no", "name", "lat", "lon", "phase"]) if l1 is not None else [],
                           sources=dict(area="outputs/area_profile.csv", tram="outputs/tram_scenarios.csv",
                                        s8989="대전신용보증재단 '대전 소상공인 상권분석 서비스'(8989.daejeon.go.kr) 상권 정보 — 신한카드 결제를 카드사 점유 비율로 보정한 추정매출 (2026-10 재단 활용 허가, 재배포 금지)")))
    save("areas.json", areas)
    save("dongs.json", dongs)

    # ── 지도 경계 (속성은 코드만) ──
    def geo(name, key, step=1):
        g = json.loads((OUT / name).read_text(encoding="utf-8"))
        out = []
        for ft in g["features"]:
            gm = ft["geometry"]
            def rnd(c):
                return [rnd(x) for x in c] if isinstance(c[0], list) else [round(c[0], 5), round(c[1], 5)]
            out.append({"type": "Feature", "properties": {key: str(ft["properties"][key])},
                        "geometry": {"type": gm["type"], "coordinates": rnd(gm["coordinates"])}})
        return {"type": "FeatureCollection", "features": out}
    save("geo_core.json", geo("sangkwon_polygons.geojson", "code"))
    if (OUT / "sangkwon_regions.geojson").exists():
        save("geo_regions.json", geo("sangkwon_regions.geojson", "code"))
    save("geo_dongs.json", geo("dong_map.geojson", "dong_id"))

    # ── 그래프용 시계열 ──
    sp = csv(OUT / "store_panel.csv", dtype={"period": str})
    dyp = csv(OUT / "dong_year_panel.csv", dtype={"dong_id": str})
    dfl = csv(OUT / "dong_forecast_land.csv", dtype={"code": str})
    dps = csv(OUT / "dong_panel_store.csv", dtype={"period": str, "dong_id": str})
    ser = dict(
        land={c: g[["year", "idx"]].values.tolist() for c, g in lp.groupby("code")} if lp is not None else {},
        fc={c: g[["year", "base_path", "lo80", "hi80", "tram_low", "tram_base", "tram_high"]].values.tolist() for c, g in fc.groupby("code")},
        store={c: g[["period", "n_stores"]].values.tolist() for c, g in sp.groupby("code")} if sp is not None else {},
        breaks=["2023-03", "2024-12", "2026-06"])
    save("series_area.json", ser)
    dser = dict(
        land={k: g[["year", "land_idx"]].dropna().values.tolist() for k, g in dyp.groupby("dong_id")} if dyp is not None else {},
        fc={k: g[["year", "base_path", "lo80", "hi80", "tram_low", "tram_base", "tram_high"]].values.tolist() for k, g in dfl.groupby("code")} if dfl is not None else {},
        store={k: g[["period", "n_stores"]].values.tolist() for k, g in dps.groupby("dong_id")} if dps is not None else {})
    save("series_dong.json", dser)

    # ── 업종 구성 ──
    groups = ["카페", "빵·과자", "식사·주점", "소매", "생활서비스", "교육", "보건의료", "기타"]
    compo = {}
    if cnow is not None and comp is not None:
        for r in cnow.itertuples():
            key = f"{r.level}|{r.key}"
            fx = comp[(comp.level == r.level) & (comp.key == str(r.key)) & (comp.year == comp.year.max())].set_index("scenario")
            compo[key] = dict(n_stores=r.n_stores, n={g: getattr(r, f"n_{g}".replace("·", "_"), None) for g in groups},
                              near500_cafe=getattr(r, "near500_카페", None),
                              add={s: dict(cafe=fx.loc[s, "add_카페"], bakery=fx.loc[s].get("add_빵·과자", 0.0)) for s in fx.index})
        # 열 이름에 · 가 들어 있어 itertuples 가 못 읽는 경우 대비
        cn = cnow.set_index(cnow.level + "|" + cnow.key.astype(str))
        for key in compo:
            compo[key]["n"] = {g: cn.loc[key, f"n_{g}"] for g in groups if f"n_{g}" in cn.columns}
            compo[key]["near500_cafe"] = cn.loc[key, "near500_카페"] if "near500_카페" in cn.columns else None
    save("composition.json", dict(groups=groups, data=compo))

    # ── 업종 점수 ──
    IS = csv(OUT / "industry_scores.csv")
    ISW = csv(OUT / "industry_score_weights.csv")
    if IS is not None:
        keep = ["code", "name", "industry", "score_before", "n_stores"] + [c for c in IS.columns if c.startswith("s_")]
        save("industry.json", dict(rows=records(IS, keep), weights=records(ISW), order=ac.ind_list(IS)))

    # ── AI 해설 (기본 해설 + 보낸 정보) ──
    d = ac.load_inputs()
    info = d["prof"].set_index("code")
    scen, scen_help, _ = ac.scenarios(d["ts"], d["prof"].columns)
    scen_text = next(iter(scen))
    w = ac.default_weights(d["ISW"])
    saved = ac.load_saved() or {"areas": {}}
    ai = {}
    for c in info.index:
        ctx = ac.area_context(c, info, d["fc"], d["IS"], w, d["ind_area"], d["events"], d["st_areas"], "base",
                              d.get("rentp"), d.get("comp"), d.get("tour"))
        e = ac.saved_entry(saved, c)
        ai[c] = dict(text=e["text"] if e else None, generated_at=e["generated_at"] if e else None, kind=e.get("kind") if e else None,
                     context=ctx, prompt=ac.build_prompt(ac.context_text(ctx), scen_text, scen_help))
    save("ai.json", dict(scenario=scen_text, areas=ai))

    # ── 관광 ──
    tour = dict(layer=records(csv(OUT / "tourism_layer.csv", dtype={"id": str}),
                              ["kind", "id", "name", "tourism_type", "tour_level", "tour_score", "n_poi", "top_poi", "visitors_yr",
                               "visit_low_pct", "visit_base_pct", "visit_high_pct", "dlnA_traffic", "dlnA_busslow"]),
                station=records(csv(OUT / "tourism_station.csv")))
    poi = csv(DATA / "tourism_poi.csv", dtype=str, keep_default_na=False)
    if poi is not None:
        pz = poi[(poi.use_in_tourism == "1") | (poi.get("gateway", "0") == "1")]
        # 좌표는 공개하지 않음: 관광지 좌표가 카카오 로컬 API 결과라 저장·재제공 금지(카카오 데브톡 답변 2026-09·10) → 이름·종류만
        tour["poi"] = [dict(id=r.poi_id, name=r["name"], type=r.tour_type, gu=r.gu,
                            gateway=r.get("gateway", "0") == "1") for _, r in pz.iterrows() if r.lat and r.lon]
    lit = csv(DATA / "literature_tram_tourism.csv")
    tour["literature"] = records(lit, ["id", "group", "source", "city_system", "year", "finding", "reliability", "use_in_project", "url"])
    tour["params"] = records(csv(DATA / "tourism_params.csv"), ["param_id", "paper", "value", "unit", "note"])
    gt = csv(DATA / "tourism_gateway_traffic.csv")
    tour["gateways"] = records(gt)
    import tourism_page as tp
    tour["domestic"] = [dict(zip(["line", "section", "size", "open", "status", "tourism", "url"], r)) for r in tp.DOMESTIC]
    tour["good"] = [dict(zip(["city", "what", "num", "read", "grade", "url"], r)) for r in tp.GOOD]
    tour["caution"] = [dict(zip(["city", "text", "grade", "url"], r)) for r in tp.CAUTION]
    tour["checked"] = tp.CHECKED
    save("tourism.json", tour)

    # ── 분석 방법 (팝업 내용: 결과 파일에서 수치를 채운 문장) ──
    import about_page as ap
    import tram_evidence_page as te
    n = ap._numbers()
    fmt = lambda s: s.format(**n) if isinstance(s, str) else s
    about = dict(
        numbers={k: v for k, v in n.items() if isinstance(v, (str, int, float))},
        story=[dict(zip(["what", "verdict", "how", "result", "limit"], [fmt(x) for x in row])) for row in ap._story(n)],
        data=[dict(zip(["name", "source", "period", "size", "use"], r)) for r in ap.DATA],
        models=[dict(zip(["goal", "method", "result", "check"], [r[0], r[1], fmt(r[2]), r[3]])) for r in ap.MODELS],
        papers=[dict(zip(["tag", "paper", "use"], [r[0], r[1], fmt(r[2])])) for r in ap.PAPERS],
        frameworks=[dict(zip(["use", "fw", "where"], r)) for r in ap.FRAMEWORKS],
        why=ap.WHY, limits=[fmt(x) for x in ap.LIMITS], other_sectors=ap.other_sectors_line(),
        overseas=[dict(zip(["kind", "case", "what", "result", "control", "source", "url"], r)) for r in te.OVERSEAS])
    ms = csv(OUT / "tram_meta_summary.csv")
    if ms is not None:
        g = ms[ms.group == "전체 (트램·경전철)"]
        if len(g):
            about["meta"] = dict(k=int(g.k.iloc[0]), mu=g.mu_pct.iloc[0], lo=g.ci_low_pct.iloc[0], hi=g.ci_high_pct.iloc[0])
    cdn = csv(OUT / "construction_8989_density.csv")
    about["construction"] = records(cdn)
    save("about.json", about)

    # ── 그림 (분석 결과 그림, 공개 가능) ──
    (DST / "img").mkdir(exist_ok=True)
    for name in ["tram_meta_forest.png", "landprice_line1_es.png", "line1_permits_sector.png", "tram_with_without.png",
                 "forecast_backtest.png", "tram_distance_bands.png", "line1_trend_adjusted.png"]:
        if (OUT / name).exists():
            shutil.copy(OUT / name, DST / "img" / name)
    # 3D 지도 단독 페이지 (map3d.make_html, deck.gl CDN)
    try:
        import map3d
        html = map3d.make_html(map3d.make_data(), standalone=True)
        (DST / "map3d.html").write_text(html, encoding="utf-8")
        print("  map3d.html                   ", round(len(html) / 1024, 1), "KB")
    except Exception as e:
        print("  3D 지도 생략:", type(e).__name__, e)
    print("완료")


if __name__ == "__main__":
    main()
