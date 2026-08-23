#!/usr/bin/env node
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const ROOT = process.env.WORDCLOUD_STATIC_ROOT
  ? resolve(process.env.WORDCLOUD_STATIC_ROOT)
  : resolve(new URL("..", import.meta.url).pathname);

async function getText(path) {
  return readFile(resolve(ROOT, path.replace(/\?.*$/, "").replace(/^\//, "")), "utf-8");
}

function includesAll(label, text, patterns) {
  for (const pattern of patterns) {
    assert.ok(text.includes(pattern), `${label} should include ${pattern}`);
  }
}

const index = await getText("/index.html");
includesAll("index.html", index, [
  'id="search"',
  'id="review-dialog"',
  'id="draft-dialog"',
  'id="local-data-dialog"',
  'id="local-data-export"',
  'id="learning-progress-open"',
  'id="learning-progress-dialog"',
  'id="learning-progress-summary"',
  'id="learning-recent"',
  'id="learning-paths"',
  "含非商业来源",
  "没有账号、上传或同步",
  "FLELex、Lexique、Démonette",
  'src="graph-data.js?v=',
  'src="app.js?v=',
]);

const appPath = index.match(/src="(app\.js\?v=[^"]+)"/)?.[1];
const graphPath = index.match(/src="(graph-data\.js\?v=[^"]+)"/)?.[1];
assert.ok(appPath, "index.html should reference app.js with a cache version");
assert.ok(graphPath, "index.html should reference graph-data.js with a cache version");
const [app, graph, styles, worker] = await Promise.all([
  getText(`/${appPath}`),
  getText(`/${graphPath}`),
  getText("/styles.css"),
  getText("/sw.js"),
]);

includesAll("app.js", app, [
  "openReviewDialog",
  "toggleRelationSaved",
  "savedRelations",
  "review-answer",
  "openFromWordCard",
  "openLocalDataDialog",
  "exportLocalData",
  "openLearningProgressDialog",
  "renderLearningProgress",
  "summarizeLearningProgress",
  "wordcloud.learning.v1",
  "searchLexemes",
]);
includesAll("graph-data.js", graph, ["GRAPH_NODES", "GRAPH_ALIASES", "GRAPH_SEARCH_LEXEMES"]);
includesAll("styles.css", styles, [
  "@media (max-width: 720px)",
  ".review-card",
  ".relation-review-answer",
  ".draft-dialog-card",
  ".local-data-card",
  ".local-data-output",
  ".source-note",
  ".release-boundary-list",
  ".learning-progress-card",
  ".learning-progress-summary",
  ".learning-progress-item",
]);
includesAll("sw.js", worker, [
  "./src/draft-tools.mjs",
  "./src/search-tools.mjs",
  "./src/word-card-tools.mjs",
  "./src/local-data-tools.mjs",
  "./src/review-tools.mjs",
  'cache: "reload"',
]);
assert.ok(
  !worker.includes("cache.addAll(APP_SHELL)"),
  "sw.js install handler must not repopulate the app shell with cache.addAll(APP_SHELL) alone " +
    "(it lets stale HTTP-cached responses leak into a freshly named cache bucket); " +
    "each app shell request must force revalidation, e.g. via cache: \"reload\"",
);

console.log("browser acceptance smoke passed: static shell and acceptance hooks are present");
