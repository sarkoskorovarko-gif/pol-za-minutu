// Работа без интернета. После первого открытия файлы сайта хранятся в телефоне.
// При изменении сайта увеличить номер версии — телефоны скачают новые файлы.
const VERSION = 'v9';
const FILES = ['./', 'index.html', 'style.css?v=9', 'calc.js?v=9', 'app.js?v=9', 'interior.js?v=9', 'photo.js?v=9', 'data/photos.json', 'data/demo/laminate_floor_02.jpg',
  'lib/three.module.min.js', 'lib/RoomEnvironment.js', 'lib/qrcode.js?v=9', 'manifest.json', 'icons/icon-192.png', 'data/catalog.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  // Каталог и страница — сначала из сети (свежие цены), без сети — из памяти
  const fresh = url.pathname.endsWith('catalog.json') || url.pathname.endsWith('/') || url.pathname.endsWith('index.html');
  if (fresh) {
    e.respondWith(fetch(e.request).then(r => {
      const copy = r.clone();
      caches.open(VERSION).then(c => c.put(e.request, copy));
      return r;
    }).catch(() => caches.match(e.request, { ignoreSearch: true })));
    return;
  }
  // Остальное (код, текстуры) — из памяти, если есть; новое докладываем в память
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => {
    if (r.ok) { const copy = r.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); }
    return r;
  })));
});
