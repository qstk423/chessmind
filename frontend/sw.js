/* ChessCouncil PWA：缓存静态壳，API 仍走网络 */
const CACHE = 'cc-shell-mapp2';
const PRECACHE = [
  '/',
  '/index.html',
  '/learn.html',
  '/online.html',
  '/tools.html',
  '/style.css?v=mapp2',
  '/app.js?v=mapp2',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/vendor/jquery-3.7.1.min.js',
  '/vendor/chessboard-1.0.0.min.js',
  '/vendor/chessboard-1.0.0.min.css',
  '/vendor/chess-0.10.3.min.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/')) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      const networked = fetch(event.request)
        .then((res) => {
          if (res && res.ok && url.origin === self.location.origin) {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || networked;
    })
  );
});
