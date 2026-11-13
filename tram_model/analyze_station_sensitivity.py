"""정거장 추정 좌표 민감도: 설계 도면이 아닌 정거장 32곳(정류장 추정 17 + 2026-11 공식 위치도 대조 보정 15)을 무작위로 옮겨 보며 500m 판정·진단이 얼마나 흔들리는지

입력: data/tram_stations.csv (coord_source '설계도면' 13곳은 고정, 나머지 32곳을 흔듦), 상가정보 2026-06 점포 좌표·업종,
      outputs/sangkwon_polygons.geojson, outputs/8989/dong_code_map.csv, outputs/robust_radius.csv (상권 in500, 격자 기준),
      outputs/dong_map_profile.csv (동 tram500_share), outputs/area_scores.csv · dong_scores.csv (정책 진단 4칸)
방법: 추정 정거장마다 방향 무작위, 거리 0~R m(면적 균등)로 옮김(R = 300m 기본, 150m 변형) × N회(300)
      → 정책 진단 4칸(policy_quadrant.py, 2026-11-12 규칙)을 매번 다시 판정
        · 대상: 동 = 점포 500m 안 비율(앱 비율 + 점포 기준 변화량) ≥ 0.1, 상권 = 500m 안 점포가 하나라도 있으면(기본 판정 유지, 0이 되면 빠짐)
        · 업종 변화: 카페 중 500m 안 비율이 바뀐 만큼 기본 %p 를 비례 조정(카페 500m 안이 원래 0이던 곳은 0 유지)
        · 지금 위험(위험 점수·절대 쇠퇴 신호)은 좌표와 무관 → 그대로
출력: outputs/station_coord_sensitivity.csv
      level, key, name, quadrant, risk_score, in500(앱), in500_lo/hi(5~95%), in500_store_base, p_first(먼저 지원 비율, R300),
      p_first_150, p_flip(진단이 바뀌는 비율, R300), quad_alt(가장 흔한 다른 칸), sensitive(10% 넘게 바뀜), note
한계: 상권 대상 판정은 원래 상권 경계·앵커 기준(build_areas.py)이라 점포 기준으로 근사함
"""
import json
import numpy as np
import pandas as pd
import config as C
from build_composition import hav, pip
import policy_quadrant as PQ

OUT = C.OUT_DIR
N, R_MAIN, R_ALT, SEED, IN500_MIN = 300, 300, 150, 7, 0.5


def load_stores():
    raw = next((C.ROOT / "data" / "raw").glob("*상가_상권_정보_대전_2026*.csv"))
    st = pd.read_csv(raw, dtype=str, usecols=["상권업종대분류명", "상권업종중분류명", "상권업종소분류명", "행정동코드", "경도", "위도"]).dropna(subset=["경도", "위도"])
    from build_composition import group_of
    st["is_cafe"] = (group_of(st) == "카페").values
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


def summarize(st, S, key, mask=None):
    g = st[key].values; ok = pd.notna(g) & (np.ones(len(st), bool) if mask is None else mask)
    keys = pd.Index(sorted(set(st[key].values[pd.notna(st[key].values)])))
    idx = pd.Series(range(len(keys)), index=keys).reindex(g[ok]).values
    cnt = np.bincount(idx, minlength=len(keys))
    sh = np.vstack([np.bincount(idx, weights=row[ok].astype(float), minlength=len(keys)) / np.maximum(cnt, 1) for row in S])
    return keys, sh, cnt            # sh[draw, unit]


def judge(level, keys, sh, csh, app_in, sc):
    """draw 마다 정책 진단 다시. 반환: DataFrame(draw × unit) 칸 이름"""
    K = [k for k in keys if k in sc.index and k in app_in.index]
    pos = [list(keys).index(k) for k in K]
    sh, csh = sh[:, pos], csh[:, pos]
    a = app_in.reindex(K).fillna(0).values
    v = np.clip(a + (sh - sh[0]), 0, 1)                         # 앱 비율 + 점포 기준 변화량
    base_t = sc.policy_target.reindex(K).fillna(False).astype(bool).values
    if level == "행정동":
        T = v >= PQ.DONG_TARGET_MIN
    else:
        T = base_t[None, :] & (sh > 0)                          # 기본 대상만, 500m 안 점포가 0이 되면 빠짐
        T[0] = base_t
    pp0 = sc.change_pp.reindex(K).fillna(0).values
    ratio = np.where(csh[0] > 0, csh / np.where(csh[0] > 0, csh[0], 1), 0)
    PP = pp0 * np.where(csh[0] > 0, ratio, 1)
    risk = sc.risk_score.reindex(K); absd = sc.abs_decline.reindex(K)
    rows = []
    for d in range(len(sh)):
        q = PQ.classify(risk, absd, pd.Series(PP[d], index=K), pd.Series(T[d], index=K))
        rows.append(q.values)
    return pd.DataFrame(rows, columns=K), v


def main():
    TR = pd.read_csv(C.ROOT / "data" / "tram_stations.csv", encoding="utf-8-sig")
    TR["approx"] = ~TR.coord_source.astype(str).str.startswith("설계도면")      # 추정(기존) + 2026-11 공식 위치도 대조 보정(±200m) 모두 흔들어 봄
    print(f"정거장 {len(TR)}곳 중 추정 좌표 {int(TR.approx.sum())}곳을 0~{R_MAIN}m 무작위 이동 × {N}회")
    st = load_stores()
    rng = np.random.default_rng(SEED)
    S3 = simulate(st, TR, R_MAIN, N, rng); S1 = simulate(st, TR, R_ALT, N, rng)
    rr = pd.read_csv(OUT / "robust_radius.csv", encoding="utf-8-sig").set_index("zone")
    dp = pd.read_csv(OUT / "dong_map_profile.csv", encoding="utf-8-sig", dtype={"dong_id": str}).set_index("dong_id")
    sa = pd.read_csv(OUT / "area_scores.csv", encoding="utf-8-sig").set_index("code")
    sd = pd.read_csv(OUT / "dong_scores.csv", encoding="utf-8-sig", dtype={"dong_id": str}).set_index("dong_id")
    cafe = st.is_cafe.values
    rows = []
    for level, key, app_in, sc in [("상권", "area", rr.in500, sa), ("행정동", "adm_cd2", dp.tram500_share, sd)]:
        keys, sh3, _ = summarize(st, S3, key); _, sh1, _ = summarize(st, S1, key)
        _, c3, _ = summarize(st, S3, key, cafe); _, c1, _ = summarize(st, S1, key, cafe)
        Q3, v3 = judge(level, keys, sh3, c3, app_in, sc); Q1, _ = judge(level, keys, sh1, c1, app_in, sc)
        for j, k in enumerate(Q3.columns):
            q0 = Q3[k].iloc[0]; d3 = Q3[k].iloc[1:]; d1 = Q1[k].iloc[1:]
            flip = float((d3 != q0).mean())
            other = d3[d3 != q0]
            rows.append(dict(level=level, key=k, name=sc.name.get(k, k), quadrant=q0, risk_score=round(float(sc.risk_score.get(k, np.nan)), 1),
                             in500=round(float(v3[0, j]), 3), in500_lo=round(np.quantile(v3[1:, j], .05), 3),
                             in500_hi=round(np.quantile(v3[1:, j], .95), 3),
                             p_first=round(float((d3 == PQ.FIRST).mean()), 3), p_first_150=round(float((d1 == PQ.FIRST).mean()), 3),
                             p_flip=round(flip, 3), quad_alt=(other.mode().iloc[0] if len(other) else ""), sensitive=bool(flip > 0.10)))
    D = pd.DataFrame(rows)
    def note(r):
        if not r.sensitive:
            return ""
        return (f"정거장 추정 좌표가 0~300m 다르면 {r.p_flip * 100:.0f}% 확률로 '{r.quad_alt}'로 바뀜 "
                f"(500m 안 점포 비율 {r.in500_lo * 100:.0f}~{r.in500_hi * 100:.0f}%)")
    D["note"] = D.apply(note, axis=1)
    D.to_csv(OUT / "station_coord_sensitivity.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    show = D[D.sensitive | (D.p_flip > 0)]
    print(show[["level", "name", "quadrant", "risk_score", "in500", "in500_lo", "in500_hi", "p_first", "p_flip", "quad_alt"]].to_string(index=False))
    for lv, g in D.groupby("level"):
        print(f"[{lv}] 민감(진단이 10% 넘게 바뀜) {int(g.sensitive.sum())}/{len(g)}곳:", ", ".join(g[g.sensitive].name))


if __name__ == "__main__":
    main()
