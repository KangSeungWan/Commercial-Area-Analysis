import { useEffect, useRef, useState } from "react";
import { ROUTE_C } from "./lib.js";

const TIP = { backgroundColor: "#fff", color: "#0a1d08", fontSize: "12.5px", lineHeight: "1.5", borderRadius: "8px", border: "1px solid #e1e6df",
  boxShadow: "0 4px 14px rgba(0,0,0,.14)", padding: "8px 11px", fontFamily: "Pretendard Variable, Pretendard, sans-serif", maxWidth: "260px" };
const BASEMAP = "https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png";
const NGII_BOUNDS = [127.239536, 36.177161, 127.594721, 36.506619];
const BASEMAP_LABELS = "https://basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}@2x.png";

function bbox(fcs, pts) {
  let x0 = 180, x1 = -180, y0 = 90, y1 = -90;
  const walk = c => { if (typeof c[0] === "number") { x0 = Math.min(x0, c[0]); x1 = Math.max(x1, c[0]); y0 = Math.min(y0, c[1]); y1 = Math.max(y1, c[1]); } else c.forEach(walk); };
  fcs.forEach(fc => fc && fc.features.forEach(f => walk(f.geometry.coordinates)));
  pts.forEach(p => walk([p.lon, p.lat]));
  return [[x0, y0], [x1, y1]];
}
export function centroid(f) {
  const g = f.geometry;
  const ring = g.type === "Polygon" ? g.coordinates[0] : g.coordinates.reduce((a, p) => (p[0].length > a.length ? p[0] : a), []);
  let x = 0, y = 0; ring.forEach(p => { x += p[0]; y += p[1]; });
  return [x / ring.length, y / ring.length];
}

/**
 * props: base (행정동 경계, 바탕), regions, core (상권) 또는 dongs, fill: {key: [r,g,b]}, keyProp ("code"|"dong_id"),
 * sel, onPick(key), stations, route, line1, tramAfter, station, onStation(no), tooltip(key) → html, labels [{key,text,pos,pri}],
 * stationTip(st) → html, showRegion, buffers
 */
export default function MapView(p) {
  const el = useRef(null), dk = useRef(null), vs = useRef(null);
  const [err, setErr] = useState(null);
  const [labelKeys, setLabelKeys] = useState(null);
  const latest = useRef(p); latest.current = p;

  // 라벨 겹침 정리: 우선순위 높은 것부터, 겹치면 생략
  // 축척 막대: 화면 폭 1/5 안에서 1·2·5km 중 맞는 길이
  function scaleBar(viewState) {
    const sb = el.current && el.current.querySelector(".map-scale");
    if (!sb || !viewState) return;
    const mpp = 40075016.686 * Math.cos(viewState.latitude * Math.PI / 180) / (512 * Math.pow(2, viewState.zoom));
    const maxPx = Math.max(60, Math.min(140, el.current.clientWidth / 5));
    const km = [0.5, 1, 2, 5, 10].filter(k => k * 1000 / mpp <= maxPx).pop() || 0.5;
    sb.querySelector("i").style.width = Math.round(km * 1000 / mpp) + "px";
    sb.querySelector("span").textContent = (km < 1 ? km * 1000 + " m" : km + " km");
  }
  function dedupe(viewState) {
    scaleBar(viewState);
    const D = window.deck, P = latest.current;
    if (!D || !P.labels || !el.current) return;
    const vp = new D.WebMercatorViewport({ ...viewState, width: el.current.clientWidth, height: el.current.clientHeight });
    const boxes = [], keep = [];
    for (const l of [...P.labels].sort((a, b) => b.pri - a.pri)) {
      const [x, y] = vp.project(l.pos);
      const w = l.text.length * 13 + 14, h = 22;
      const b = [x - w / 2, y - h / 2, x + w / 2, y + h / 2];
      if (b[2] < 0 || b[0] > vp.width || b[3] < 0 || b[1] > vp.height) continue;
      if (boxes.some(o => !(b[2] < o[0] || b[0] > o[2] || b[3] < o[1] || b[1] > o[3]))) continue;
      boxes.push(b); keep.push(l.key);
    }
    setLabelKeys(keep.join("|"));
  }

  // 상권(또는 동)과 정거장 전체가 지도 상자에 꽉 차는 중심·줌
  function fitView() {
    const D = window.deck, P = latest.current;
    const [[x0, y0], [x1, y1]] = bbox([P.fitTo || P.polys], P.stations || []);
    const w = el.current.clientWidth || 800, h = el.current.clientHeight || 600;
    const fit = new D.WebMercatorViewport({ width: w, height: h }).fitBounds([[x0, y0], [x1, y1]], { padding: Math.max(16, Math.min(36, w / 14)) });
    return { longitude: fit.longitude, latitude: fit.latitude, zoom: fit.zoom, minZoom: 9.5, maxZoom: 16.5, pitch: 0, bearing: 0 };
  }

  function layers() {
    const D = window.deck, P = latest.current;
    const L = [];
    const rc = P.tramAfter ? [...ROUTE_C, 255] : [140, 146, 154, 210], rw = P.tramAfter ? 3 : 2;
    // 바탕 지도 타일(CARTO 래스터)은 2026-09-25부터 API 키가 필요해 기본으로 끔. 켜려면 basemap={true} + 키 붙은 주소
    if (P.basemap === true) {
      for (const [id, url, op] of [["tiles", BASEMAP, 0.75]]) {
        L.push(new D.TileLayer({ id, data: url, minZoom: 0, maxZoom: 19, tileSize: 256, opacity: op,
          renderSubLayers: pr => { const { boundingBox: [[w, s], [e, n]] } = pr.tile; return new D.BitmapLayer(pr, { data: null, image: pr.data, bounds: [w, s, e, n] }); } }));
      }
    }
    // 자체 바탕: 대전 땅(밝게) — 시 경계 안쪽을 칠해 바깥(시 밖)과 구분
    if (P.gu?.city?.length) L.push(new D.PolygonLayer({ id: "land", data: P.gu.city, getPolygon: d => d, filled: true, stroked: false,
      getFillColor: [252, 252, 249, 255], pickable: false }));
    if (P.base) L.push(new D.GeoJsonLayer({ id: "base", data: P.base, stroked: true, filled: true, getFillColor: [248, 249, 245, 60],
      getLineColor: [165, 172, 159, 130], lineWidthMinPixels: 0.6, pickable: false }));
    const key = P.keyProp;
    const fillOf = (f, a) => [...(P.fill[f.properties[key]] || [210, 210, 210]), a];
    if (P.regions && P.showRegion) L.push(new D.GeoJsonLayer({ id: "regions", data: P.regions, pickable: true, stroked: true, filled: true,
      getFillColor: f => fillOf(f, 95), getLineColor: [255, 255, 255, 255], lineWidthMinPixels: 1.1, autoHighlight: true, highlightColor: [255, 255, 255, 90],
      updateTriggers: { getFillColor: P.fillKey } }));
    if (P.polys) L.push(new D.GeoJsonLayer({ id: "polys", data: P.polys, pickable: true, stroked: true, filled: true,
      getFillColor: f => fillOf(f, P.polyAlpha ?? 225), getLineColor: [255, 255, 255, 255], lineWidthMinPixels: 1, autoHighlight: true, highlightColor: [255, 255, 255, 90],
      updateTriggers: { getFillColor: P.fillKey } }));
    // 구 경계(얇게) · 시 경계(조금 굵게) — 통계청 행정동 경계에서 만든 자체 선
    if (P.gu?.gu?.length) L.push(new D.PathLayer({ id: "gu-lines", data: P.gu.gu, getPath: d => d, getColor: [42, 51, 42, 150],
      widthUnits: "pixels", getWidth: 1.6, capRounded: true, jointRounded: true, pickable: false }));
    if (P.gu?.city?.length) L.push(new D.PathLayer({ id: "city-line", data: P.gu.city, getPath: d => d, getColor: [42, 51, 42, 210],
      widthUnits: "pixels", getWidth: 2.2, capRounded: true, jointRounded: true, pickable: false }));
    // 꺼 둠(10-28): 국토지리정보원 어린이지도여행 백지도에는 공공누리 표시가 없어 저작권정책상 담당부서 사전 협의 필요. 허락 받으면 backdrop={true}
    // 국토지리정보원(국토정보플랫폼) 대전광역시 지도 1:200,000 — 시 경계·갑천·금강·대청호 (공공누리 출처표시).
    // 상권·행정동 색 위에 옅게 얹어 강·호수 위치를 보여 줌. 위치는 행정동 경계에 맞춰 보정(평균 오차 약 1px ≈ 80m)
    if (P.backdrop === true) L.push(new D.BitmapLayer({ id: "ngii", image: "./img/daejeon_ngii.png", bounds: NGII_BOUNDS, opacity: 0.75 }));
    if (P.sel) {
      const src = (P.regions && P.showRegion) ? P.regions : P.polys;
      const sf = { type: "FeatureCollection", features: (src?.features || []).filter(f => f.properties[key] === P.sel) };
      L.push(new D.GeoJsonLayer({ id: "halo", data: sf, stroked: true, filled: false, getLineColor: [255, 255, 255, 255], lineWidthMinPixels: 8, updateTriggers: { data: P.sel } }));
      L.push(new D.GeoJsonLayer({ id: "selline", data: sf, stroked: true, filled: false, getLineColor: [...ROUTE_C, 255], lineWidthMinPixels: 3.5 }));
    }
    if (P.line1?.length) L.push(new D.PathLayer({ id: "line1", data: [{ path: P.line1.map(s => [s.lon, s.lat]) }], getPath: d => d.path,
      getColor: [79, 134, 198, 170], widthMinPixels: 2, capRounded: true, jointRounded: true }));
    const route = (P.route || []).map(path => ({ path }));
    L.push(new D.PathLayer({ id: "route_case", data: route, getPath: d => d.path, getColor: [255, 255, 255, 235], widthMinPixels: rw + 3, capRounded: true, jointRounded: true }));
    L.push(new D.PathLayer({ id: "route", data: route, getPath: d => d.path, getColor: rc, widthMinPixels: rw, capRounded: true, jointRounded: true,
      getDashArray: P.tramAfter ? [0, 0] : [4, 3], updateTriggers: { getColor: P.tramAfter } }));
    const st = P.stations || [];
    const sel = st.find(s => s.no === P.station);
    if (sel) L.push(new D.ScatterplotLayer({ id: "buffer", data: [sel], getPosition: d => [d.lon, d.lat], getRadius: 500, filled: true,
      getFillColor: [...ROUTE_C, 28], stroked: true, getLineColor: [...ROUTE_C, 240], lineWidthMinPixels: 2.5 }));
    L.push(new D.ScatterplotLayer({ id: "stations", data: st, getPosition: d => [d.lon, d.lat], getRadius: 55, radiusMinPixels: 4.5, radiusMaxPixels: 9,
      getFillColor: [255, 255, 255, 255], getLineColor: rc, stroked: true, lineWidthMinPixels: P.tramAfter ? 1.8 : 1.2, pickable: true,
      autoHighlight: true, highlightColor: [35, 39, 46, 255], updateTriggers: { getLineColor: P.tramAfter } }));
    if (sel) L.push(new D.ScatterplotLayer({ id: "selstop", data: [sel], getPosition: d => [d.lon, d.lat], getRadius: 90, radiusMinPixels: 7,
      getFillColor: [...ROUTE_C, 255], getLineColor: [255, 255, 255, 255], stroked: true, lineWidthMinPixels: 2 }));
    if (P.pois?.length) L.push(new D.ScatterplotLayer({ id: "pois", data: P.pois, getPosition: d => [d.lon, d.lat], getRadius: 40, radiusMinPixels: 3.5,
      getFillColor: d => d.gateway ? [35, 39, 46, 255] : [127, 79, 36, 220], getLineColor: [255, 255, 255, 255], stroked: true, lineWidthMinPixels: 1, pickable: true }));
    if (P.gu?.labels?.length && P.showGu !== false) L.push(new D.TextLayer({ id: "gu-names", data: P.gu.labels, getPosition: d => d.pos,
      getText: d => d.name.split("").join(" "), characterSet: "auto", fontFamily: "Pretendard Variable, Pretendard, Apple SD Gothic Neo, sans-serif",
      fontWeight: 700, getSize: 15, getColor: [91, 103, 81, 235], fontSettings: { sdf: true }, outlineWidth: 5, outlineColor: [252, 252, 249, 240], pickable: false }));
    if (P.labels && P.showLabels !== false) {
      const keep = new Set((labelKeys || "").split("|"));
      const data = P.labels.filter(l => keep.has(l.key));
      L.push(new D.TextLayer({ id: "labels", data, getPosition: d => d.pos, getText: d => d.text, characterSet: "auto",
        fontFamily: "Pretendard Variable, Pretendard, Apple SD Gothic Neo, sans-serif", fontWeight: 600, getSize: 12.5,
        getColor: d => d.key === P.sel ? [255, 255, 255, 255] : [25, 28, 32, 255], background: true, backgroundPadding: [5, 2],
        getBackgroundColor: d => d.key === P.sel ? [35, 39, 46, 235] : [255, 255, 255, 225], getBorderColor: [225, 230, 223, 255], getBorderWidth: 1,
        updateTriggers: { getColor: P.sel, getBackgroundColor: P.sel } }));
    }
    return L;
  }

  useEffect(() => {
    let tries = 0, timer;
    function init() {
      const D = window.deck;
      if (!D) {
        if (tries++ < 60) { timer = setTimeout(init, 150); return; }
        setErr("지도 라이브러리(deck.gl)를 불러오지 못했습니다. 인터넷 연결을 확인하고 새로 고쳐 주세요."); return;
      }
      vs.current = fitView();
      dk.current = new D.Deck({
        parent: el.current, viewState: vs.current, controller: { dragRotate: false, touchRotate: false, doubleClickZoom: true },
        layers: layers(), getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
        onViewStateChange: ({ viewState, interactionState }) => { if (interactionState && (interactionState.isDragging || interactionState.isZooming || interactionState.isPanning)) dk.touched = true; vs.current = viewState; dk.current.setProps({ viewState }); cancelAnimationFrame(dk.raf); dk.raf = requestAnimationFrame(() => dedupe(viewState)); },
        getTooltip: ({ object, layer }) => {
          if (!object || !layer) return null;
          const Q = latest.current;
          let html = null;
          if (layer.id === "stations") html = Q.stationTip?.(object);
          else if (layer.id === "pois") html = `<b>${object.name}</b><br/><span style="color:#5b6751">${object.gateway ? "관문(교통)" : object.type} · 대략적 위치</span>`;
          else if (object.properties) html = Q.tooltip?.(object.properties[Q.keyProp]);
          return html ? { html, style: TIP } : null;
        },
        onClick: ({ object, layer }) => {
          const Q = latest.current;
          if (!object || !layer) return;
          if (layer.id === "stations") Q.onStation?.(object.no);
          else if (object.properties && Q.onPick) Q.onPick(object.properties[Q.keyProp]);
        },
      });
      dedupe(vs.current);
    }
    init();
    // 상자 크기가 정해지면(처음 그릴 때·창 크기 변경) 사용자가 아직 지도를 움직이지 않았으면 다시 맞춤
    const ro = new ResizeObserver(() => {
      if (!dk.current || !el.current.clientHeight) return;
      if (!dk.touched) { vs.current = fitView(); dk.current.setProps({ viewState: vs.current }); }
      dedupe(vs.current);
    });
    if (el.current) ro.observe(el.current);
    return () => { clearTimeout(timer); ro.disconnect(); if (dk.current) { dk.current.finalize(); dk.current = null; } };
  }, []);

  useEffect(() => { if (dk.current) dk.current.setProps({ layers: layers() }); });
  useEffect(() => { if (dk.current && vs.current) dedupe(vs.current); }, [p.labels]);

  return (
    <div className="map" ref={el} role="application" aria-label={p.ariaLabel || "대전 트램 상권 지도"}>
      {err && <div className="map-msg">{err}</div>}
      <div className="map-scale" aria-hidden="true"><i /><span /></div>
      {p.backdrop === true && p.basemap !== true && <div className="map-attr">바탕 지도: 국토지리정보원</div>}
      {p.basemap === true && <div className="map-attr">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> 기여자 © <a href="https://carto.com/attributions" target="_blank" rel="noopener noreferrer">CARTO</a></div>}
    </div>
  );
}
