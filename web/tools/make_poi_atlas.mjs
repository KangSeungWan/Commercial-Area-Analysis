import { KINDS, iconSvg, BADGE } from "/home/claude/web/src/icons.js";
import fs from "fs";
const cols = Object.keys(KINDS), colors = Object.entries(BADGE); const S = 64;
let h = `<html><body style="margin:0;background:transparent"><div id=a style="position:relative;width:${cols.length*S}px;height:${colors.length*S}px">`;
const map = {};
colors.forEach(([cn, c], r) => cols.forEach((k, i) => { h += `<div style="position:absolute;left:${i*S}px;top:${r*S}px">${iconSvg(k, c, S)}</div>`; map[k + c] = { x: i*S, y: r*S, width: S, height: S, anchorY: S/2 }; }));
h += "</div></body></html>";
fs.writeFileSync("/tmp/claude-0/atlas.html", h); fs.writeFileSync("/tmp/claude-0/atlas_map.json", JSON.stringify(map));
console.log(cols.length*S, colors.length*S);
