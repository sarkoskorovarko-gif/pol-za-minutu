// Сборщик данных EGGER с diy.by. Запускается в браузере на странице diy.by
// (F12 → Консоль → вставить весь текст → Enter). Ходит по страницам строго
// по одной, с паузой 1,5 с. В конце скачивает файл egger_raw.json.
// Если сайт снова попросит проверку — обновите страницу (F5) и запустите ещё раз:
// сбор продолжится с того же места (прогресс хранится в браузере).
(async () => {
  const PAUSE = 1500;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const getDoc = async url => {
    const r = await fetch(url);
    if (!r.ok) throw new Error('Ошибка ' + r.status + ' на ' + url);
    const html = await r.text();
    if (html.includes('<title>Verification</title>')) throw new Error('Сайт просит проверку — обновите страницу и запустите снова');
    return new DOMParser().parseFromString(html, 'text/html');
  };

  // Прогресс прошлого запуска
  let st = {};
  try { st = JSON.parse(localStorage.getItem('egger_collect') || '{}'); } catch (e) {}
  const save = () => { try { localStorage.setItem('egger_collect', JSON.stringify(st)); } catch (e) {} };

  // 1. Список товаров со всех страниц каталога
  const urls = st.urls || [];
  for (let page = (st.page || 0) + 1; !st.listDone && page < 20; page++) {
    const listUrl = '/laminat/brend-egger/' + (page > 1 ? 'page' + page + '/' : '');
    // Страницы после последней нет (ошибка 404) — список закончился
    if (page > 1 && (await fetch(listUrl, { method: 'HEAD' })).status === 404) { st.listDone = true; break; }
    const d = await getDoc(listUrl);
    const found = [...d.querySelectorAll('a[href*="/laminat/laminat-"]')]
      .map(a => a.href).filter(h => /egger/i.test(h) && !urls.includes(h));
    console.log('Страница', page, '— товаров:', found.length);
    if (!found.length) { st.listDone = true; break; }
    urls.push(...new Set(found));
    st.urls = urls; st.page = page; save();
    await sleep(PAUSE);
  }
  if (!urls.length) throw new Error('Не найдено ни одного товара — возможно, сайт изменился');

  // 2. Карточки товаров
  st.listDone = true; save();
  const items = st.items || [];
  for (const [i, url] of urls.entries()) {
    if (items.some(x => x.url === url)) continue;
    try {
      const d = await getDoc(url);
      const props = {};
      d.querySelectorAll('.product-features__row').forEach(r => {
        const k = r.querySelector('.product-features__prop')?.textContent.trim();
        if (k) props[k] = r.querySelector('.product-features__val')?.textContent.trim() || '';
      });
      const ldTxt = [...d.querySelectorAll('script[type="application/ld+json"]')]
        .map(s => s.textContent).find(t => t.includes('"Product"'));
      const ld = ldTxt ? JSON.parse(ldTxt) : {};
      items.push({ url, name: ld.name, image: (ld.image || [])[0],
        price: ld.offers?.price, availability: ld.offers?.availability, props });
      st.items = items; save();
      console.log(i + 1, '/', urls.length, ld.name);
    } catch (e) {
      if (e.message.includes('проверку')) throw e;
      console.warn('Пропущен', url, e.message);
    }
    await sleep(PAUSE);
  }

  // 3. Отдаём результат
  const json = JSON.stringify({ collected: new Date().toISOString(), items }, null, 1);
  if (window.SEND_TO) {
    await fetch(window.SEND_TO, { method: 'POST', body: json });
  } else {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
    a.download = 'egger_raw.json';
    a.click();
  }
  localStorage.removeItem('egger_collect');
  console.log('Готово, товаров:', items.length);
  window.COLLECT_DONE = items.length;
})().catch(e => { console.error(e.message, '— обновите страницу (F5) и запустите снова, сбор продолжится.'); window.COLLECT_DONE = 'ОШИБКА: ' + e.message; });
