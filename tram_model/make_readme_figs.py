"""README 그림 4장을 결과 파일에서 다시 그린다.
실행: python tram_model/make_readme_figs.py  → docs/img/fig_*.png
쓰는 결과: robust_cafe_cluster, robust_construction_cohort, construction_8989_did, seoul_newline_*_did,
tram_scenarios, sector_evidence_es, area_scores, forecast_backtest (모두 공개 결과 파일, 8989 값 열 없음)
"""
import sys, glob, pathlib, pandas as pd, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
ROOT = pathlib.Path(__file__).resolve().parent.parent
O = str(ROOT / "tram_model" / "outputs") + "/"
IMG = str(ROOT / "docs" / "img")
FAM = None
for pat in ["/usr/share/fonts/**/NotoSansCJK-Regular.ttc", "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/Library/Fonts/*Noto*Sans*KR*", "C:/Windows/Fonts/malgun.ttf"]:
    for f in glob.glob(pat, recursive=True):
        fm.fontManager.addfont(f); FAM = fm.FontProperties(fname=f).get_name(); break
    if FAM: break
for f in glob.glob("/usr/share/fonts/**/NotoSansCJK-Bold.ttc", recursive=True): fm.fontManager.addfont(f)
plt.rcParams.update({"font.family":FAM or "sans-serif","axes.unicode_minus":False,"font.size":11,
  "axes.spines.top":False,"axes.spines.right":False,"axes.edgecolor":"#888","axes.labelcolor":"#333",
  "xtick.color":"#444","ytick.color":"#444","savefig.dpi":160,"savefig.bbox":"tight","figure.facecolor":"white"})
INK="#0a1d08"; G={"확실":"#1f6f4a","방향만":"#d9822b","확인 안 됨":"#8a8f98"}
# 1 forest
rc=pd.read_csv(O+"robust_cafe_cluster.csv"); cc=pd.read_csv(O+"robust_construction_cohort.csv")
c8=pd.read_csv(O+"construction_8989_did.csv"); sl=pd.read_csv(O+"seoul_newline_land_did.csv"); ss=pd.read_csv(O+"seoul_newline_sales_did.csv")
ts=pd.read_csv(O+"tram_scenarios.csv").set_index("scenario")
lo,hi=[float(x) for x in ts.loc["base","ci95"].replace(" ","").split("~")]
rows=[("② 카페 수 (1호선 역 500m)",rc.iloc[0]["효과_퍼센트"],rc.iloc[0]["하한"],rc.iloc[0]["상한"],"확실"),
 ("   └ 역 단위 묶음 (CR1)",rc.iloc[1]["효과_퍼센트"],rc.iloc[1]["하한"],rc.iloc[1]["상한"],"확실"),
 ("   └ 포아송 (PPML)",rc.iloc[3]["효과_퍼센트"],rc.iloc[3]["하한"],rc.iloc[3]["상한"],"확실"),
 ("① 땅값 (1호선 합산, 기본)",ts.loc["base","effect_pct"],lo,hi,"방향만"),
 ("   └ 신림선 경전철 땅값",sl.iloc[0]["효과"],sl.iloc[0]["하한"],sl.iloc[0]["상한"],"방향만"),
 ("③ 점포당 매출 (신림선)",ss.iloc[0]["효과"],ss.iloc[0]["하한"],ss.iloc[0]["상한"],"방향만"),
 ("⑤ 공사 구간 카드매출",c8.iloc[0]["효과_퍼센트"],c8.iloc[0]["하한"],c8.iloc[0]["상한"],"확인 안 됨"),
 ("   └ 공사 코호트별",cc.iloc[0]["효과_퍼센트"],cc.iloc[0]["하한"],cc.iloc[0]["상한"],"확인 안 됨")]
fig,ax=plt.subplots(figsize=(9,4.6)); y=np.arange(len(rows))[::-1]
for yi,(n,e,l,h,g) in zip(y,rows):
    ax.plot([l,h],[yi,yi],color=G[g],lw=2.4,solid_capstyle="round")
    ax.plot(e,yi,"o",color=G[g],ms=8 if not n.startswith(" ") else 6,mec="white",mew=1.2)
    ax.text(h+2,yi,f"{e:+.1f}%",va="center",fontsize=9.5,color=G[g])
ax.axvline(0,color="#444",lw=1)
ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows]); ax.set_xlabel("효과 (%) · 막대 = 95% 구간")
ax.set_xlim(-20,112)
from matplotlib.lines import Line2D
ax.legend([Line2D([0],[0],color=G[k],lw=3) for k in G],list(G),loc="lower right",frameon=False,title="확신 등급")
ax.set_title("트램(철도)은 매출이 아니라 거리(업종)를 바꿨다 — 단계별 효과와 확신 등급",loc="left",fontsize=12.5,color=INK,fontweight="bold")
fig.savefig(IMG+"/fig_evidence.png"); plt.close()
# 2 cafe ES
e=pd.read_csv(O+"sector_evidence_es.csv"); e=e[(e["업종"]=="카페")&(e["정의"]=="기존")].copy()
e=pd.concat([e,pd.DataFrame({"year":[2005],"b":[0.0],"se":[0.0]})]).sort_values("year")
e["pct"]=(np.exp(e.b)-1)*100; e["lo"]=(np.exp(e.b-1.96*e.se)-1)*100; e["hi"]=(np.exp(e.b+1.96*e.se)-1)*100
fig,ax=plt.subplots(figsize=(9,3.8))
ax.fill_between(e.year,e.lo,e.hi,color="#1f6f4a",alpha=.15,lw=0)
ax.plot(e.year,e.pct,"-o",color="#1f6f4a",ms=5); ax.axhline(0,color="#444",lw=1)
ax.axvline(2005.5,color="#c83232",ls="--",lw=1.2); ax.text(2005.6,e.hi.max()*0.92,"1호선 1단계 개통 (2006-03)",color="#c83232",fontsize=10)
ax.text(2002.1,e.hi.max()*0.92,"개통 전: 차이 없음",fontsize=10,color="#555")
ax.set_xticks(range(2002,2015)); ax.set_ylabel("역 500m vs 1~3km 카페 수 차이 (%)")
ax.set_title("카페 수 차이는 개통 뒤부터 해마다 벌어졌다 (기준 2005년, 음영 = 95% 구간)",loc="left",fontsize=12.5,color=INK,fontweight="bold")
fig.savefig(IMG+"/fig_cafe_years.png"); plt.close()
# 3 quadrant
QC={"먼저 지원":"#c83232","기존 지원 연계":"#eb8214","변화 관찰":"#2a6f97","정기 점검":"#6ea078"}
a=pd.read_csv(O+"area_scores.csv"); a=a[a.tram_group=="트램 근접"]; med=a.change_median.iloc[0]
fig,ax=plt.subplots(figsize=(9,5.4))
for q,c in QC.items():
    s=a[a.quadrant==q]; ax.scatter(s.risk_score,s.change_pp,s=120,color=c,label=f"{q} ({len(s)})",edgecolor="white",lw=1.2,zorder=3)
for _,r in a.iterrows():
    nm=r["name"].split("(")[0]; off={"도안신도시":(9,-15),"대전역·중앙시장":(8,6),"서대전네거리":(6,6)}.get(nm,(7,4))
    ax.annotate(nm+(" ⚠" if r.quadrant_uncertain else ""),(r.risk_score,r.change_pp),xytext=off,textcoords="offset points",fontsize=9,color="#333",ha="right" if off[0]<0 else "left")
ax.axvline(50,color="#666",ls=":",lw=1); ax.axhline(med,color="#666",ls=":",lw=1)
ax.text(50.8,0.18,"위험 50점",fontsize=9,color="#666")
ax.text(51,2.2,"50점을 넘어도 절대 쇠퇴 신호가 없으면\n'위험 낮음' (대전복합터미널·대전역·중앙시장)",fontsize=8.5,color="#2a6f97"); ax.text(27,med+0.05,f"업종 변화 가운데값 {med:.2f}%p",fontsize=9,color="#666")
ax.set_xlabel("지금 위험 점수 (상대 순위 0~100) · 50점 이상 + 절대 쇠퇴 신호가 있어야 '위험 높음'")
ax.set_ylabel("2034 카페·빵 비중 증가 (%p, 추정)"); ax.set_xlim(25,102)
ax.legend(frameon=False,loc="upper right",title="정책 진단 4칸 (상권 수)")
ax.set_title("트램 근처 상권 12곳의 정책 진단 4칸 (⚠ = 10가지 변형 중 같은 칸 비율 0.8 미만)",loc="left",fontsize=12.5,color=INK,fontweight="bold")
fig.savefig(IMG+"/fig_quadrant.png"); plt.close()
# 4 backtest
b=pd.read_csv(O+"forecast_backtest.csv"); b=b[(b.target=="지가")&(b.h==1)].sort_values("rmse_log_pct")
lab={"ARIMA(p,1,0)":"ARIMA (채택)","drift(최근 추세)":"최근 추세","naive(작년값)":"작년값 그대로","GBM(sklearn)":"기계학습 GBM","GBM(sklearn) · 상권 분할":"GBM · 상권 분할"}
fig,ax=plt.subplots(figsize=(8,3.2)); yy=np.arange(len(b))[::-1]
cols=["#1f6f4a" if m.startswith("ARIMA") else "#b8bec6" for m in b.model]
ax.barh(yy,b.rmse_log_pct,color=cols)
for yi,v in zip(yy,b.rmse_log_pct): ax.text(v+0.08,yi,f"{v:.1f}%",va="center",fontsize=10)
ax.set_yticks(yy); ax.set_yticklabels([lab.get(m,m) for m in b.model]); ax.set_xlabel("1년 앞 땅값 예측 오차 (RMSE, %) · 작을수록 정확")
ax.set_title("복잡한 모델이 늘 낫지는 않다 — 백테스트로 ARIMA를 골랐다",loc="left",fontsize=12.5,color=INK,fontweight="bold")
fig.savefig(IMG+"/fig_backtest.png"); plt.close()
print("ok")
