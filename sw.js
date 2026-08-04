const CACHE_NAME = "wordcloud-learning-978028a803ec";
const APP_SHELL = [
  "./index.html",
  "./styles.css",
  "./graph-data.js?v=978028a803ec",
  "./app.js?v=978028a803ec",
  "./src/draft-ui.js",
  "./src/draft-tools.mjs",
  "./src/search-tools.mjs",
  "./src/word-card-tools.mjs",
  "./src/local-data-tools.mjs",
  "./src/review-tools.mjs",
  "./manifest.webmanifest",
  "./icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match("./index.html")));
    return;
  }
  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
});
