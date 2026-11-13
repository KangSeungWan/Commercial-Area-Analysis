"""B11 (2차 점검): 분석 전체에서 한 검정 목록 + 다중 검정 보정(Benjamini-Hochberg, FDR).

입력: outputs/*.csv 중 p값 열이 있는 결과 파일 (임대료 백분위·좌표 확률 열은 검정이 아니라 제외)
출력: outputs/tests_registry.csv (파일, 행 이름, p, BH q, 5%·1% 통과 여부), outputs/tests_registry_summary.csv
읽는 법: q < 0.05 = 수십 개 검정을 함께 봐도 우연이 아닐 가능성이 높은 결과. p < 0.05 이지만 q ≥ 0.05 = '경계' (확신 등급 '방향만')
"""
import glob

import numpy as np
import pandas as pd

import config as C

PCOLS = {"p", "p값", "perm_p", "placebo_p", "p_value", "p_approx"}
SKIP = {"rent_pressure.csv", "station_coord_sensitivity.csv", "tests_registry.csv", "tests_registry_summary.csv"}


def label(row, cols):
    parts = [str(row[c]) for c in cols if isinstance(row[c], str)][:3]
    return " | ".join(parts)[:120]


def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def main():
    rows = []
    for f in sorted(glob.glob(str(C.OUT_DIR / "*.csv"))):
        name = f.split("/")[-1]
        if name in SKIP:
            continue
        try:
            d = pd.read_csv(f)
        except Exception:
            continue
        pc = [c for c in d.columns if c in PCOLS]
        if not pc:
            continue
        tc = [c for c in d.columns if d[c].dtype == object]
        for _, r in d.iterrows():
            for c in pc:
                v = pd.to_numeric(r[c], errors="coerce")
                if pd.notna(v):
                    rows.append(dict(file=name, test=label(r, tc), p_col=c, p=float(v)))
    R = pd.DataFrame(rows)
    R["q_bh"] = bh(R.p.values).round(4)
    R["p_lt_05"] = R.p < 0.05; R["p_lt_01"] = R.p < 0.01; R["q_lt_05"] = R.q_bh < 0.05
    R.sort_values("p").to_csv(C.OUT_DIR / "tests_registry.csv", index=False, encoding="utf-8-sig")
    S = pd.DataFrame([dict(n_tests=len(R), p_lt_05=int(R.p_lt_05.sum()), p_lt_01=int(R.p_lt_01.sum()),
                           q_lt_05=int(R.q_lt_05.sum()), expected_false_at_05=round(len(R) * 0.05, 1))])
    S.to_csv(C.OUT_DIR / "tests_registry_summary.csv", index=False, encoding="utf-8-sig")
    print(S.to_string(index=False))
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 90)
    print(R.sort_values("p").head(40)[["file", "test", "p", "q_bh"]].to_string(index=False))


if __name__ == "__main__":
    main()
