const CACHE = "lampgrid-v20";
const ASSETS = [
  "./", "./index.html", "./manifest.webmanifest",
  "./icon-192.png", "./icon-512.png", "./icon-512-maskable.png", "./icon-180.png",
  "./analytics-config.js", "./analytics.js", "./demo.js", "./social-preview.png"
];
const ASSET_URLS = new Set(ASSETS.map(path => new URL(path, self.registration.scope).href));
const INDEX_URL = new URL("./index.html", self.registration.scope).href;

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => /^lampgrid-v\d+$/.test(k) && k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  const scope = new URL(self.registration.scope);
  if (url.origin !== scope.origin || !url.pathname.startsWith(scope.pathname)) return;
  url.search = "";
  url.hash = "";
  if (!ASSET_URLS.has(url.href)) return;
  const key = url.href;
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res.ok && res.type === "basic") {
          const copy = res.clone();
          e.waitUntil(caches.open(CACHE).then(c => c.put(key, copy)).catch(() => {
            console.warn("LAMP GRID: an offline asset could not be cached.");
          }));
        }
        return res;
      })
      .catch(async () => {
        const cached = await caches.match(key);
        if (cached) return cached;
        if (e.request.mode === "navigate") {
          const index = await caches.match(INDEX_URL);
          if (index) return index;
        }
        return Response.error();
      })
  );
});
