// UI-UX-Pro-Max 체크리스트 자동 점검 (접근성·터치·반응형·글자)
const { chromium } = require("playwright");
const http = require("http"), fs = require("fs"), path = require("path");
const ROOT = process.argv[2], OUT = process.argv[3];
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png" };
const srv = http.createServer((q, r) => {
  let p = decodeURIComponent(q.url.split("?")[0]); if (p.endsWith("/")) p += "index.html";
  const f = path.join(ROOT, p);
  fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { "content-type": MIME[path.extname(f)] || "application/octet-stream" }); r.end(d); });
}).listen(8765);

const PAGES = [["cover", "/"], ["map", "/map"], ["map-dong", "/map", { unit: "dong" }], ["industry", "/industry"], ["compare", "/compare"], ["ai", "/ai"], ["tourism", "/tourism"], ["about", "/about"], ["3d", "/3d"]];

function check() {
  const res = { overflow: null, small: [], contrast: [], targets: [], names: [], headings: [], imgs: [] };
  const W = innerWidth;
  res.overflow = document.documentElement.scrollWidth > W + 1 ? document.documentElement.scrollWidth : null;
  // 넘치는 요소
  const wide = [];
  document.querySelectorAll("body *").forEach(e => { const b = e.getBoundingClientRect(); if (b.width && b.right > W + 1 && !e.closest(".tablewrap,.map,iframe,svg,canvas")) wide.push((e.className || e.tagName) + "@" + Math.round(b.right)); });
  res.wide = [...new Set(wide)].slice(0, 6);
  const parse = c => { const m = c.match(/[\d.]+/g); return m ? m.map(Number) : [0, 0, 0, 0]; };
  const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bgOf = e => { let blend = null; for (let n = e; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); const a = c.length > 3 ? c[3] : 1; if (a > 0.5) return c.slice(0, 3); } return [248, 249, 245]; };
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode; const s = t.textContent.trim(); if (!s) continue;
    const e = t.parentElement; if (!e || e.closest(".map,svg,iframe,[aria-hidden=true],.cover-root canvas")) continue;
    const cs = getComputedStyle(e); if (cs.visibility === "hidden" || cs.display === "none" || +cs.opacity === 0) continue;
    const b = e.getBoundingClientRect(); if (!b.width || !b.height) continue;
    const fs = parseFloat(cs.fontSize);
    const key = e.tagName + "." + e.className + "|" + fs;
    if (fs < 12 && !seen.has("s" + key)) { seen.add("s" + key); res.small.push(`${fs}px ${e.tagName}.${e.className} "${s.slice(0, 24)}"`); }
    const fg = parse(cs.color); const bg = bgOf(e);
    const L1 = lum(fg.slice(0, 3)), L2 = lum(bg); const cr = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const large = fs >= 24 || (fs >= 18.66 && +cs.fontWeight >= 700);
    if (cr < (large ? 3 : 4.5) && !seen.has("c" + key + cs.color)) { seen.add("c" + key + cs.color); res.contrast.push(`${cr.toFixed(2)} ${cs.color}/${bg} ${e.tagName}.${e.className} "${s.slice(0, 24)}"`); }
  }
  document.querySelectorAll("a[href],button,input,select,summary,[role=button],[tabindex='0']").forEach(e => {
    const b = e.getBoundingClientRect(); if (!b.width) return;
    const inline = e.tagName === "A" && e.closest("p,li,td") && getComputedStyle(e).display === "inline";
    if (!inline && (b.width < 24 || b.height < 24)) res.targets.push(`${Math.round(b.width)}x${Math.round(b.height)} ${e.tagName}.${e.className} "${(e.textContent || e.getAttribute("aria-label") || "").trim().slice(0, 18)}"`);
    const name = (e.getAttribute("aria-label") || e.textContent || e.title || (e.labels && e.labels[0] && e.labels[0].textContent) || "").trim();
    if (!name && e.tagName !== "SUMMARY") res.names.push(`${e.tagName}.${e.className} type=${e.type || ""}`);
  });
  res.headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")].filter(h => h.getBoundingClientRect().width).map(h => h.tagName[1]).join("");
  document.querySelectorAll("img").forEach(i => { if (!i.hasAttribute("alt")) res.imgs.push(i.src.split("/").pop()); });
  res.targets = [...new Set(res.targets)].slice(0, 25);
  return res;
}

(async () => {
  const b = await chromium.launch();
  const report = {};
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const pg = await ctx.newPage();
    await pg.route(/fonts\.(googleapis|gstatic)|jsdelivr/, r => r.abort());
    const errs = []; pg.on("pageerror", e => errs.push(e.message));
    for (const [name, route, state] of PAGES) {
      await pg.goto("http://localhost:8765/index.html");
      await pg.evaluate(s => { try { sessionStorage.clear(); if (s) sessionStorage.setItem("tram-state", JSON.stringify(s)); } catch (e) {} }, state || null);
      await pg.goto("http://localhost:8765/index.html#" + route);
      await pg.waitForTimeout(name === "cover" ? 2500 : 1500);
      const r = await pg.evaluate(check);
      r.errors = errs.splice(0);
      report[`${name}@${w}`] = r;
      await pg.screenshot({ path: `${OUT}/${name}_${w}.png`, fullPage: name !== "cover" });
    }
    await ctx.close();
  }
  fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 1));
  await b.close(); srv.close();
})();
