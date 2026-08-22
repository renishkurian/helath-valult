/* Family Vault PWA — cache shell assets; network-first for admin pages. */
const CACHE = "vault-shell-v3";
const OFFLINE = "/static/offline.html";
const PRECACHE = [
  OFFLINE,
  "/static/icon.svg",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/apple-touch-icon.png",
  "/static/vendor/bootstrap.min.css",
  "/static/vendor/bootstrap-icons.min.css",
  "/static/vendor/bootstrap.bundle.min.js",
  "/static/vault.css",
  "/static/pwa.js",
];

function isOAuthNavigation(pathname) {
  return /\/google\/(connect|callback)(\/|$)/.test(pathname);
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    // OAuth starts with a 302 to Google — never intercept; SW "ok" checks break it.
    if (isOAuthNavigation(url.pathname)) return;
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(OFFLINE).then(
          (page) => page || new Response("Offline", { status: 503, headers: { "Content-Type": "text/plain" } })
        )
      )
    );
    return;
  }

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((response) => {
            if (response && response.ok) {
              const clone = response.clone();
              caches.open(CACHE).then((cache) => cache.put(request, clone));
            }
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});
