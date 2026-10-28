// 빌드: dist/ = index.html + public/ + ../web_data(→ data/) + 묶은 app.js·app.css
import { cpSync, rmSync, mkdirSync, existsSync } from "node:fs";
let esbuild;
try { esbuild = await import("esbuild"); } catch { esbuild = await import("/opt/npm-tools/node_modules/esbuild/lib/main.js"); }
const prod = process.argv.includes("--prod");
rmSync("dist", { recursive: true, force: true }); mkdirSync("dist");
cpSync("public", "dist", { recursive: true });
cpSync("index.html", "dist/index.html");
const data = existsSync("../web_data") ? "../web_data" : "public/data";
if (data !== "public/data") { cpSync(data, "dist/data", { recursive: true }); cpSync(`${data}/map3d.html`, "dist/map3d.html"); }
await esbuild.build({
  entryPoints: ["src/main.jsx"], bundle: true, outfile: "dist/app.js", format: "iife", target: ["es2020"],
  jsx: "automatic", loader: { ".html": "text" }, minify: prod, sourcemap: !prod, legalComments: "none",
  nodePaths: ["node_modules", "/opt/npm-tools/node_modules"], define: { "process.env.NODE_ENV": prod ? '"production"' : '"development"' },
  logLevel: "info",
});
