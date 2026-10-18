"""3D 지도 시제품 (B안) — 본 앱(app.py)과 따로 실행.

    streamlit run app_3d.py

분석 결과 파일(tram_model/outputs)을 그대로 읽으므로 run_all.py 를 다시 돌릴 필요 없음.
지도·조작은 HTML 한 장(tram_model/map3d_template.html) 안에서 돌아가서 재생·회전이 끊기지 않음.
"""
import os, sys
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tram_model"))
import map3d                                                          # noqa: E402

st.set_page_config(page_title="대전 트램 3D 지도 (시제품)", layout="wide")
st.markdown("<style>.block-container{padding-top:1.2rem;padding-left:1.2rem;padding-right:1.2rem}</style>",
            unsafe_allow_html=True)


@st.cache_data
def html(mtimes):                                                     # 결과 파일이 바뀌면 다시 만듦
    return map3d.make_html()


_files = ["outputs/area_profile.csv", "outputs/forecast_land.csv", "outputs/sangkwon_polygons.geojson",
          "outputs/station_summary.csv", "outputs/buildings_3d.geojson", "map3d_template.html"]
_mt = tuple(os.path.getmtime(p) if os.path.exists(p) else 0 for p in (os.path.join(map3d.HERE, f) for f in _files))
try:
    components.html(html(_mt), height=780)
except Exception as e:                                                # 파일이 없을 때 파이썬 오류 대신 안내
    st.error(f"3D 지도를 만들지 못했습니다: {e}")
    st.markdown("프로젝트 폴더에서 `python tram_model/run_all.py` 를 실행해 결과 파일을 만든 뒤 새로 고치세요.")
