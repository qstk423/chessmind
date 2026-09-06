/* ChessCouncil PWA：静态壳可离线；HTML / JS 优先走网络，避免卡在旧版本 */
const CACHE = 'cc-shell-mapp14';
const PRECACHE = [
  '/chess/',
  '/chess/index.html',
  '/chess/learn.html',
  '/chess/online.html',
  '/chess/tools.html',
  '/chess/style.css?v=mapp8',
  '/chess/app.js?v=mapp13',
  '/chess/manifest.webmanifest',
  '/chess/icons/icon-192.png',
  '/chess/icons/icon-512.png',
  '/chess/vendor/jquery-3.7.1.min.js',
  '/chess/vendor/chessboard-1.0.0.min.js',
  '/chess/vendor/chessboard-1.0.0.min.css',
  '/chess/vendor/chess-0.10.3.min.js',
  '/shared/variant-switch.css',
  '/shared/variant-switch.js',
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

function isFreshAsset(url) {
  const p = url.pathname;
  return (
    p.endsWith('.html') ||
    p === '/' ||
    p.endsWith('/chess/') ||
    p.endsWith('/xiangqi/') ||
    p.endsWith('.js') ||
    p.endsWith('.css') ||
    p.endsWith('.webmanifest')
  );
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;

  if (isFreshAsset(url)) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req))
  );
});
