"""정거장 추정 좌표 민감도: 설계 도면이 아닌 정거장 32곳(정류장 추정 17 + 2026-11 공식 위치도 대조 보정 15)을 무작위로 옮겨 보며 500m 판정·진단이 얼마나 흔들리는지

입력: data/tram_stations.csv (coord_source '설계도면' 13곳은 고정, 나머지 32곳을 흔듦), 상가정보 2026-06 점포 좌표,
      outputs/sangkwon_polygons.geojson, outputs/8989/dong_code_map.csv,
      outputs/area_profile.csv · robust_radius.csv (상권 in500, 격자 기준), outputs/dong_map_profile.csv (동 tram500_share)
방법: 추정 정거장마다 방향 무작위, 거리 0~R m(면적 균등)로 옮김(R = 300m 기본, 150m 변형) × N회(300)
      → 상권·동마다 '점포 중 500m 안 비율' 다시 계산. 앱의 비율(상권 = 격자 기준)에 '점포 기준 변화량'을 더해 판정
      → 위험 50 이상인 곳은 비율이 0.5 를 넘나들면 '트램 반등 기회' ↔ '쇠퇴 우려'가 바뀜
출력: outputs/station_coord_sensitivity.csv
      level, key, name, quadrant, risk_score, in500(앱), in500_lo/hi(5~95%), in500_store_base, p_rebound(반등 기회로 판정된 비율, R300),
      p_rebound_150, eff_rel_lo/hi(트램 효과 상대 범위 = 비율 변화), sensitive(진단이 10% 넘게 바뀜), note
한계: 성장 점수 안의 트램 효과 항목은 다시 계산하지 않음(위험 50 미만 곳의 성장 지속↔정체 판정은 그대로 둠)
"""
import json
import numpy as np
import pandas as pd
import config as C
from build_composition import hav, pip

OUT = C.OUT_DIR
N, R_MAIN, R_ALT, SEED, IN500_MIN = 300, 300, 150, 7, 0.5


def load_stores():
    raw = next((C.ROOT / "data" / "raw").glob("*상가_상권_정보_대전_2026*.csv"))
    st = pd.read_csv(raw, dtype=str, usecols=["행정동코드", "경도", "위도"]).dropna(subset=["경도", "위도"])
    st["lon"], st["lat"] = st.경도.astype(float), st.위도.astype(float)
    cm = pd.read_csv(OUT / "8989" / "dong_code_map.csv", dtype=str)
    st = st.merge(cm[["adstrdCode", "adm_cd2"]], left_on="행정동코드", right_on="adstrdCode", how="left")
    st["area"] = None
    for f in json.load(open(OUT / "sangkwon_polygons.geojson", encoding="utf-8"))["features"]:
        g = f["geometry"]; polys = [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]
        m = np.zeros(len(st), bool)
        for p in polys: m |= pip(st.lon.values, st.lat.values, p)
        st.loc[m & st.area.isna(), "area"] = f["properties"]["code"]
    return st.reset_index(drop=True)


def simulate(st, TR, R, n, rng):
    lat0 = 36.35; ky, kx = 111_000.0, 111_000.0 * np.cos(np.radians(lat0))
    sx, sy = st.lon.values * kx, st.lat.values * ky
    fixed = TR[~TR.approx]; appr = TR[TR.approx]
    dfix = np.full(len(st), np.inf)
    for _, r in fixed.iterrows():
        dfix = np.minimum(dfix, np.hypot(sx - r.lon * kx, sy - r.lat * ky))
    ax, ay = appr.lon.values * kx, appr.lat.values * ky
    near = [np.where(np.hypot(sx - x, sy - y) <= 500 + R + 1)[0] for x, y in zip(ax, ay)]   # 옮겨도 닿을 수 있는 점포만
    cand = np.unique(np.concatenate(near)) if near else np.array([], int)
    base_in = dfix <= 500
    sims = []
    for i in range(n + 1):
        if i == 0:
            dx = dy = np.zeros(len(ax))
        else:
            th = rng.uniform(0, 2 * np.pi, len(ax)); rr = R * np.sqrt(rng.uniform(0, 1, len(ax)))
            dx, dy = rr * np.cos(th), rr * np.sin(th)
        d = dfix[cand].copy()
        for j, (x, y) in enumerate(zip(ax + dx, ay + dy)):
            d = np.minimum(d, np.hypot(sx[cand] - x, sy[cand] - y))
        inn = base_in.copy(); inn[cand] = d <= 500
        sims.append(inn)
    return np.vstack(sims)          # 0행 = 지금 좌표


def summarize(st, S, key):
    g = st[key].values; ok = pd.notna(g)
    keys = pd.Index(sorted(set(g[ok])))
    idx = pd.Series(range(len(keys)), index=keys).reindex(g[ok]).values
    cnt = np.bincount(idx, minlength=len(keys))
    sh = np.vstack([np.bincount(idx, weights=row[ok].astype(float), minlength=len(keys)) / np.maximum(cnt, 1) for row in S])
    return keys, sh                 # sh[draw, unit]


def main():
    TR = pd.read_csv(C.ROOT / "data" / "tram_stations.csv", encoding="utf-8-sig")
    TR["approx"] = ~TR.coord_source.astype(str).str.startswith("설계도면")      # 추정(기존) + 2026-11 공식 위치도 대조 보정(±200m) 모두 흔들어 봄
    print(f"정거장 {len(TR)}곳 중 추정 좌표 {int(TR.approx.sum())}곳을 0~{R_MAIN}m 무작위 이동 × {N}회")
    st = load_stores()
    rng = np.random.default_rng(SEED)
    S3 = simulate(st, TR, R_MAIN, N, rng); S1 = simulate(st, TR, R_ALT, N, rng)
    prof = pd.read_csv(OUT / "area_profile.csv", encoding="utf-8-sig").set_index("code")
    rr = pd.read_csv(OUT / "robust_radius.csv", encoding="utf-8-sig").set_index("zone")
    dp = pd.read_csv(OUT / "dong_map_profile.csv", encoding="utf-8-sig", dtype={"dong_id": str}).set_index("dong_id")
    cm = pd.read_csv(OUT / "8989" / "dong_code_map.csv", dtype=str)
    rows = []
    for level, key, app_in, risk, quad, name in [
            ("상권", "area", rr.in500, prof.risk_score, prof.get("quadrant"), prof.name),
            ("행정동", "adm_cd2", dp.tram500_share, dp.risk_score, dp.quadrant, dp.name)]:
        keys, sh3 = summarize(st, S3, key); _, sh1 = summarize(st, S1, key)
        for j, k in enumerate(keys):
            if k not in app_in.index or pd.isna(app_in.get(k)):
                continue
            base_store = sh3[0, j]; a = float(app_in[k])
            v3 = np.clip(a + (sh3[1:, j] - base_store), 0, 1); v1 = np.clip(a + (sh1[1:, j] - base_store), 0, 1)
            rk = float(risk.get(k, np.nan)); q = quad.get(k) if quad is not None else None
            hi = rk >= 50
            p3 = float(np.mean(v3 >= IN500_MIN)) if hi else np.nan
            p1 = float(np.mean(v1 >= IN500_MIN)) if hi else np.nan
            base_reb = (q == "트램 반등 기회")
            flip = (1 - p3 if base_reb else p3) if hi else 0.0
            rel = (v3 / a) if a > 0 else np.array([np.nan])
            rows.append(dict(level=level, key=k, name=name.get(k, k), quadrant=q, risk_score=round(rk, 1),
                             in500=round(a, 3), in500_lo=round(np.quantile(v3, .05), 3), in500_hi=round(np.quantile(v3, .95), 3),
                             in500_store_base=round(base_store, 3), p_rebound=round(p3, 3) if hi else np.nan,
                             p_rebound_150=round(p1, 3) if hi else np.nan,
                             eff_rel_lo=round(np.nanquantile(rel, .05), 2), eff_rel_hi=round(np.nanquantile(rel, .95), 2),
                             p_flip=round(flip, 3), sensitive=bool(flip > 0.10)))
    D = pd.DataFrame(rows)
    def note(r):
        if not r.sensitive:
            return ""
        to = "쇠퇴 우려" if r.quadrant == "트램 반등 기회" else "트램 반등 기회"
        return (f"정거장 추정 좌표가 0~300m 다르면 {r.p_flip * 100:.0f}% 확률로 '{to}'로 바뀜 "
                f"(500m 안 점포 비율 {r.in500_lo * 100:.0f}~{r.in500_hi * 100:.0f}%)")
    D["note"] = D.apply(note, axis=1)
    D.to_csv(OUT / "station_coord_sensitivity.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    show = D[(D.risk_score >= 50) | (D.in500_hi - D.in500_lo > 0.15)]
    print(show[["level", "name", "quadrant", "risk_score", "in500", "in500_lo", "in500_hi", "p_rebound", "p_rebound_150", "p_flip", "sensitive"]].to_string(index=False))
    print("\n민감(진단이 10% 넘게 바뀜):", ", ".join(D[D.sensitive].name))


if __name__ == "__main__":
    main()
