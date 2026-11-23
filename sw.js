// Работа без интернета. После первого открытия файлы сайта хранятся в телефоне.
// При изменении сайта увеличить номер версии — телефоны скачают новые файлы.
const PREFIX = 'pol-za-minutu:' + self.registration.scope + ':';
const VERSION = PREFIX + 'v83';
const FILES = ['./', 'index.html', 'style.css?v=83', 'calc.js?v=83', 'layout.js?v=83', 'layout-view.js?v=83', 'app.js?v=83', 'data/living/index.json', 'data/rooms.json',
  'lib/qrcode.js?v=83', 'manifest.json', 'icons/icon-192.png', 'icons/icon-512.png', 'data/catalog.json'];

self.addEventListener('install', e => {
  // cache: 'reload' — мимо кэша браузера (там могут лежать файлы прошлой версии до 10 минут)
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(FILES.map(f => new Request(f, { cache: 'reload' }))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith(PREFIX) && k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const request = e.request;
  if (request.method !== 'GET' || !request.url.startsWith(self.registration.scope)) return;
  e.respondWith(serve(request));
});

async function serve(request) {
  const cache = await caches.open(VERSION);
  const url = new URL(request.url);
  const page = request.mode === 'navigate';
  const fresh = page || /\/(catalog|rooms|index)\.json$/.test(url.pathname);
  if (page) url.search = '';
  const key = page ? url.href : request;
  const saved = await cache.match(key);
  if (saved && !fresh) return saved;
  try {
    const response = await fetch(request, fresh ? { cache: 'no-cache' } : {});
    if (!response.ok) return saved || response;
    try { await cache.put(key, response.clone()); } catch { /* При заполненной памяти сайт работает из сети. */ }
    return response;
  } catch {
    return saved || Response.error();
  }
}
