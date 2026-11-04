// Картинка раскладки на canvas: «Как будет выглядеть» (текстура декора) и «Чертёж».
// План — из layout.js (миллиметры). Комната рисуется длинной стороной по горизонтали.

// Доски на фото декора: полосы (ряды) и куски между торцевыми швами — чтобы фрагмент
// для доски брался с одной доски на фото, без лишнего шва внутри
function textureSegments(img, d) {
  const W = 400, H = Math.round(img.height * W / img.width);
  const c = Object.assign(document.createElement('canvas'), { width: W, height: H });
  const g = c.getContext('2d', { willReadFrequently: true });
  g.drawImage(img, 0, 0, W, H);
  const px = g.getImageData(0, 0, W, H).data;
  const lum = (x, y) => { const i = (y * W + x) * 4; return px[i] * .3 + px[i + 1] * .59 + px[i + 2] * .11; };
  const pxPerM = W / (d.texture_scale_m || 2);
  const bwPx = d.board_w_mm / 1000 * pxPerM;
  // провалы яркости (тёмные швы) в профиле
  const dips = (prof, gap) => {
    const out = [];
    for (let i = 3; i < prof.length - 3; i++) {
      const s = prof[i] - (prof[i - 3] + prof[i + 3]) / 2;
      if (s < -2.5 && prof[i] <= prof[i - 1] && prof[i] <= prof[i + 1] && (!out.length || i - out[out.length - 1] > gap)) out.push(i);
    }
    return out;
  };
  const rowsProf = Array.from({ length: H }, (_, y) => { let s = 0; for (let x = 0; x < W; x += 2) s += lum(x, y); return s / (W / 2); });
  let ys = dips(rowsProf, bwPx * 0.6);
  if (ys.length < 2) ys = Array.from({ length: Math.floor(H / bwPx) + 1 }, (_, i) => Math.round(i * bwPx)).filter(y => y < H);
  const edges = [0, ...ys, H];
  const bands = [];
  for (let i = 0; i < edges.length - 1; i++) {
    const y0 = edges[i], y1 = edges[i + 1];
    if (y1 - y0 < bwPx * 0.6) continue;
    const a = Math.round(y0 + (y1 - y0) * .2), b = Math.round(y1 - (y1 - y0) * .2);
    const prof = Array.from({ length: W }, (_, x) => { let s = 0; for (let y = a; y < b; y++) s += lum(x, y); return s / (b - a); });
    const xs = [0, ...dips(prof, pxPerM * 0.3), W];
    const segs = [];
    for (let j = 0; j < xs.length - 1; j++) if (xs[j + 1] - xs[j] > pxPerM * 0.25) segs.push([xs[j] + 2, xs[j + 1] - 2]);
    if (segs.length) bands.push({ y0: y0 + 2, y1: y1 - 2, segs });
  }
  if (!bands.length) bands.push({ y0: 0, y1: Math.min(H, bwPx), segs: [[0, W]] });   // швов не нашли — берём верх фото
  const k = img.width / W;   // обратно в пиксели исходного фото
  return { pxPerM: pxPerM * k, bands: bands.map(b => ({ y0: b.y0 * k, y1: b.y1 * k, segs: b.segs.map(s => s.map(v => v * k)) })) };
}

// Детерминированный «случай»: одна и та же раскладка выглядит одинаково у консультанта и клиента
function rnd(a, b) { let h = (a * 73856093) ^ (b * 19349663); h = (h ^ (h >>> 13)) * 1274126177; return ((h ^ (h >>> 16)) >>> 0) / 4294967296; }

const LAY_COLORS = { full: '#c9a27e', spare: '#f2a65a', cut: '#f6dd8b', wall: '#e9e2d6', seam: '#5b4636' };

/** Рисует план на новом canvas. mode: 'look' | 'plan'. tex — { img, seg } или null */
function drawLayout(plan, mode, tex) {
  const diag = plan.dir === 'diag', G = plan.gap;
  const long = diag ? plan.room.a + 2 * G : plan.dir === 'cross' ? plan.across + 2 * G : plan.run + 2 * G;
  const short = diag ? plan.room.b + 2 * G : plan.dir === 'cross' ? plan.run + 2 * G : plan.across + 2 * G;
  const left = mode === 'plan' && plan.dir === 'long' ? 44 : 0;           // поле под номера рядов
  const top = mode === 'plan' && plan.dir === 'cross' ? 34 : 0;
  const k = (1000 - left) / long;
  const c = Object.assign(document.createElement('canvas'), { width: 1000, height: Math.round(short * k) + 2 + top });
  const g = c.getContext('2d');
  g.fillStyle = mode === 'plan' ? '#fff' : LAY_COLORS.wall;
  g.fillRect(0, 0, c.width, c.height);
  // переход из координат плана (x — вдоль доски, y — поперёк) в экран
  // диагональ: рисуем в повёрнутых осях доски (u, v), комнату обрезаем по стенам
  const at = (x, y, w, h) => diag ? [x * k, y * k, w * k, h * k] : plan.dir === 'cross'
    ? [left + y * k, top + x * k, h * k, w * k] : [left + x * k, top + y * k, w * k, h * k];
  const toScreen = (X, Y) => diag ? [G * k + (X - Y) / Math.SQRT2, G * k + (X + Y) / Math.SQRT2] : [X, Y];
  const labels = [];
  if (diag) {
    g.save();
    g.beginPath(); g.rect(G * k, G * k, plan.room.a * k, plan.room.b * k); g.clip();
    g.translate(G * k, G * k); g.rotate(Math.PI / 4);
  }

  plan.rows.forEach(r => r.pieces.forEach((p, j) => {
    const [X, Y, Wd, Ht] = at(p.x, r.y, p.len, r.w);
    if (mode === 'look' && tex) {
      const { img, seg } = tex;
      const band = seg.bands[Math.floor(rnd(r.i + 1, j + 7) * seg.bands.length)];
      const s = band.segs[Math.floor(rnd(r.i + 3, j + 11) * band.segs.length)];
      const need = p.len / 1000 * seg.pxPerM, have = s[1] - s[0];
      const sw = Math.min(need, have), sx = s[0] + rnd(r.i + 5, j + 13) * Math.max(0, have - sw);
      const sh = Math.min(band.y1 - band.y0, r.w / 1000 * seg.pxPerM);
      g.save();
      g.beginPath(); g.rect(X, Y, Wd, Ht); g.clip();
      if (plan.dir === 'cross') {  // доска вертикально — поворачиваем фрагмент
        g.translate(X + Wd, Y); g.rotate(Math.PI / 2);
        g.drawImage(img, sx, band.y0, sw, sh, 0, 0, Ht, Wd);
      } else g.drawImage(img, sx, band.y0, sw, sh, X, Y, Wd, Ht);
      g.restore();
    } else {
      g.fillStyle = LAY_COLORS[p.src];
      g.fillRect(X, Y, Wd, Ht);
    }
    g.strokeStyle = 'rgba(40,28,18,.55)'; g.lineWidth = 1;
    g.strokeRect(X + .5, Y + .5, Wd - 1, Ht - 1);

    if (mode === 'look' && p.src === 'spare') {   // кусок из остатка: штриховка и оранжевая рамка
      g.save(); g.beginPath(); g.rect(X, Y, Wd, Ht); g.clip();
      g.strokeStyle = 'rgba(242,140,40,.55)'; g.lineWidth = 1.5;
      for (let t = -Ht; t < Wd; t += 9) { g.beginPath(); g.moveTo(X + t, Y + Ht); g.lineTo(X + t + Ht, Y); g.stroke(); }
      g.restore();
      g.strokeStyle = '#f08c28'; g.lineWidth = 2.5; g.strokeRect(X + 1.5, Y + 1.5, Wd - 3, Ht - 3);
    }
    if (mode === 'look' && !diag) {                // край, который режут у стены: жёлтый пунктир
      g.save(); g.strokeStyle = '#ffd400'; g.lineWidth = 3; g.setLineDash([7, 5]);
      const line = (x1, y1, x2, y2) => { g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke(); };
      const cutStart = p.src !== 'full' && (p.end === 'start' || p.end === 'only');
      const cutEnd = p.src !== 'full' && (p.end === 'end' || p.end === 'only');
      const narrow = r.w < plan.boardW - 0.5;
      const firstRow = r.i === 0, lastRow = r.i === plan.rows.length - 1;
      if (plan.dir === 'cross') {
        if (cutStart) line(X, Y + 2, X + Wd, Y + 2);
        if (cutEnd) line(X, Y + Ht - 2, X + Wd, Y + Ht - 2);
        if (narrow && firstRow) line(X + 2, Y, X + 2, Y + Ht);
        if (narrow && lastRow) line(X + Wd - 2, Y, X + Wd - 2, Y + Ht);
      } else {
        if (cutStart) line(X + 2, Y, X + 2, Y + Ht);
        if (cutEnd) line(X + Wd - 2, Y, X + Wd - 2, Y + Ht);
        if (narrow && firstRow) line(X, Y + 2, X + Wd, Y + 2);
        if (narrow && lastRow) line(X, Y + Ht - 2, X + Wd, Y + Ht - 2);
      }
      g.restore();
    }
    if (p.src !== 'full') labels.push([...toScreen(X + Wd / 2, Y + Ht / 2), Math.round(p.len / 10) + '', Math.max(Wd, Ht) * (diag ? .6 : 1), Math.min(Wd, Ht)]);
  }));
  if (diag) {
    g.restore();
    if (mode === 'look') {   // у диагонали подрезаются все края у стен
      g.save(); g.strokeStyle = '#ffd400'; g.lineWidth = 3; g.setLineDash([7, 5]);
      g.strokeRect(G * k + 2, G * k + 2, plan.room.a * k - 4, plan.room.b * k - 4); g.restore();
    }
  }

  // длины неполных кусков, см — на белой плашке, если помещается
  g.font = '600 22px system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  for (const [x, y, t, big, small] of labels) {
    const w = g.measureText(t).width + 10;
    if (big < w + 4 || small < 24) continue;
    g.fillStyle = 'rgba(255,255,255,.92)'; g.fillRect(x - w / 2, y - 13, w, 26);
    g.fillStyle = '#2a2622'; g.fillText(t, x, y + .5);
  }
  if (mode === 'plan' && !diag) {                  // номера рядов
    g.fillStyle = '#8a8178'; g.font = '20px system-ui, sans-serif';
    plan.rows.forEach(r => {
      const [X, Y, Wd, Ht] = at(0, r.y, plan.gap, r.w);
      if (plan.dir === 'cross') g.fillText(r.i + 1, X + Wd / 2, top / 2);
      else g.fillText(r.i + 1, left / 2, Y + Ht / 2);
    });
  }
  return c;
}

// Легенда под картинкой — обычными словами
const LAY_LEGEND = {
  look: 'Так пол будет выглядеть сверху. Оранжевой штриховкой отмечены куски, отрезанные от других досок, жёлтым пунктиром — края, которые подрезают у стены. Цифры — длина куска в сантиметрах.',
  plan: 'Коричневые — целые доски, оранжевые — куски из остатков других досок, жёлтые — доски, подрезанные у стены. Цифры — длина куска в сантиметрах, слева — номер ряда.',
};
