#!/usr/bin/env node
import { copyFile, mkdir, rm, stat, writeFile, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const outDir = join(root, "dist");

const assets = [
  "index.html",
  "styles.css",
  "graph-data.js",
  "app.js",
  "sw.js",
  "manifest.webmanifest",
  "icon.svg",
  "src/draft-ui.js",
  "src/draft-tools.mjs",
  "src/search-tools.mjs",
  "src/word-card-tools.mjs",
  "src/local-data-tools.mjs",
  "src/review-tools.mjs",
];

const requiredSnippets = [
  ["index.html", "含非商业来源"],
  ["index.html", "没有账号、上传或同步"],
  ["index.html", "FLELex、Lexique、Démonette"],
  ["sw.js", "wordcloud-learning-"],
  ["sw.js", "./src/review-tools.mjs"],
];

async function assertFile(path) {
  const info = await stat(join(root, path));
  if (!info.isFile()) throw new Error(`${path} is not a file`);
}

async function copyAsset(path) {
  const from = join(root, path);
  const to = join(outDir, path);
  await mkdir(dirname(to), { recursive: true });
  await copyFile(from, to);
}

async function assertSnippet(path, snippet) {
  const text = await readFile(join(root, path), "utf8");
  if (!text.includes(snippet)) throw new Error(`${path} should include ${snippet}`);
}

await Promise.all(assets.map(assertFile));
for (const [path, snippet] of requiredSnippets) await assertSnippet(path, snippet);

await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });
for (const asset of assets) await copyAsset(asset);
await writeFile(join(outDir, ".nojekyll"), "");
await writeFile(
  join(outDir, "release-manifest.json"),
  `${JSON.stringify({ schema: "wordcloud.static-release.v1", assets, createdAt: new Date().toISOString() }, null, 2)}\n`,
);

console.log(`static release package ready: ${outDir}`);
