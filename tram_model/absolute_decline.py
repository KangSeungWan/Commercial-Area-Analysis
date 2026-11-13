"""B9: 절대 쇠퇴 신호 (보조 지표) — score_areas.py · score_dongs.py 가 같이 씀.

왜: 쇠퇴 위험 점수는 20개(82개) 안 백분위라 언제나 절반이 50점 이상 → '상대적으로 덜 좋다'일 뿐.
    그래서 대전 전체와 비교한 '절대' 기준을 따로 둠.
조건 (대전 전체 = 82개 행정동, 점포 수 가중 평균)
  ① 점포 비중 10년 감소   store_g < 0      (2016→2026, 대전 점포 가운데 이 곳 몫이 줄어듦 = 대전보다 느리게 늘거나 줄어듦)
  ② 점포 비중 최근 3년 감소 store_recent < 0 (2023→2026)
  ③ 폐업률이 대전 평균보다 높음 close_rate > 대전 평균 (2017~2025 연평균)
  ④ 문 닫는 곳이 여는 곳보다 많음 close_rate > open_rate
신호 = ②와 ③을 모두 만족 (계획 B9: '점포 비중 감소 + 폐업률 모두 대전 평균보다 나쁨'), 강함 = ①~④ 모두
"""
import numpy as np
import pandas as pd

COND = [("abs_share10_down", "점포 비중 10년 감소"), ("abs_share3_down", "점포 비중 최근 3년 감소"),
        ("abs_close_hi", "폐업률 대전 평균보다 높음"), ("abs_net_shrink", "폐업 > 개업")]


def city_close_rate(dong_types):
    d = dong_types.dropna(subset=["close_rate", "n_stores"])
    return float(np.average(d.close_rate, weights=d.n_stores))


def add(X, city_close):
    """X 에 store_g, store_recent, close_rate, open_rate 가 있어야 함. 값이 없으면(왜곡 제외 등) 신호 판단 안 함."""
    X = X.copy()
    ok = X[["store_recent", "close_rate"]].notna().all(axis=1)
    X["abs_share10_down"] = X.store_g < 0
    X["abs_share3_down"] = X.store_recent < 0
    X["abs_close_hi"] = X.close_rate > city_close
    X["abs_net_shrink"] = X.close_rate > X.open_rate
    X["abs_decline_n"] = X[[c for c, _ in COND]].sum(axis=1).where(ok)
    X["abs_decline"] = np.where(~ok, "판단 안 함", np.where(X.abs_share3_down & X.abs_close_hi,
                                np.where(X.abs_decline_n == 4, "강함", "있음"), "없음"))
    X["abs_decline_why"] = [", ".join(lab for c, lab in COND if r[c]) if k else "점포 지표 없음"
                            for (_, r), k in zip(X.iterrows(), ok)]
    X["city_close_rate"] = round(city_close, 4)
    return X
