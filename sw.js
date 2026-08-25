const CACHE_NAME = "wordcloud-learning-5bdca13f8377";
const APP_SHELL = [
  "./index.html",
  "./styles.css",
  "./graph-data.js?v=5bdca13f8377",
  "./app.js?v=5bdca13f8377",
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
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => Promise.all(
      APP_SHELL.map((url) => fetch(url, { cache: "reload" }).then((response) => {
        if (!response.ok) throw new Error(`app shell fetch failed: ${url} (${response.status})`);
        return cache.put(url, response);
      }))
    )).catch((error) => caches.delete(CACHE_NAME).then(() => { throw error; })).then(() => self.skipWaiting())
  );
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
