import { useEffect, useRef } from "react";
import html from "../cover/cover.html";
import "../cover/cover.css";
import { mountCover } from "../cover/cover.js";
import { useData, go, pct } from "../lib.js";

const LOOP = Array.from({ length: 40 }, (_, i) => 201 + i), BRANCH = [241, 242, 243, 244], SPURS = [[233, [245]]];

function coverRoute(meta) {
  const pos = Object.fromEntries(meta.stations.map(s => [s.no, [s.lon, s.lat]]));
  const loop = LOOP.filter(n => pos[n]);
  let branch = [];
  if (meta.route.length > 1) {
    const b0 = meta.route[1][0];
    const start = loop.find(n => Math.abs(pos[n][0] - b0[0]) < 1e-6 && Math.abs(pos[n][1] - b0[1]) < 1e-6) || loop[0];
    branch = [start, ...BRANCH.filter(n => pos[n])];
  }
  const spurs = SPURS.filter(([a]) => pos[a]).map(([a, ns]) => [[...pos[a], a], ...ns.filter(n => pos[n]).map(n => [...pos[n], n])]);
  return { loop: loop.map(n => [...pos[n], n]), branch: branch.map(n => [...pos[n], n]), spurs };
}

export default function Cover() {
  const { data } = useData(["meta", "areas"]);
  const el = useRef(null);
  useEffect(() => {
    document.body.classList.add("on-cover");
    return () => document.body.classList.remove("on-cover");
  }, []);
  useEffect(() => {
    if (!data || !el.current || !window.gsap) return;
    const { meta, areas } = data;
    const reb = areas.filter(a => a.quadrant_after === "트램 반등 기회");
    const ca = meta.city.cafe_add || {};
    const stats = {
      rebound: reb.length, rb_rent: reb.filter(a => a.rent?.grade === "높음").length,
      base: pct(meta.scen.base.effect_pct), low: pct(meta.scen.low.effect_pct), high: pct(meta.scen.high.effect_pct),
      cafe_add: ca.base != null ? `+${Math.round(ca.base)}` : "-", cafe_rng: ca.low != null ? `${Math.round(ca.low)}~${Math.round(ca.high)}곳` : "-",
      n_scores: 120,
    };
    window.scrollTo(0, 0);
    const stop = mountCover(el.current, coverRoute(meta), stats, act => {
      if (act === "open") go("/map");
      else if (act === "about") go("/about");
    });
    return () => stop && stop();
  }, [data]);
  return <div ref={el} className="cover-root" dangerouslySetInnerHTML={{ __html: html }} />;
}
