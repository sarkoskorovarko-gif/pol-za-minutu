// Точная раскладка ламината: ряды, куски, остатки, число досок. ТЗ — docs/layout-spec.md.
// Только формулы, без интерфейса (проверка: node tools/test_layout.js). Всё в миллиметрах.
//
// Ряд идёт вдоль доски (ось u). У доски заводские торцы: левый (L) и правый (R) с разными замками.
// Первый кусок ряда должен иметь заводской R (левый край — к стене, его можно резать),
// последний — заводской L, средние — целые. Новую доску режем на левую часть (с L, годится
// только в конец ряда — куча A) и правую (с R, только в начало ряда — куча B); пропил уходит в отход.
// Остатки продольной резки крайних рядов не используются.
// Диагональ: комната повёрнута на 45°, у каждого ряда свои начало и длина; длина куска — по длинной
// стороне, край у стены режется под 45° (остаток со скосом годится, если хватает длины).

const r1 = x => Math.round(x * 10) / 10;
const SQ2 = Math.SQRT2;

// Ширины рядов; узкий последний ряд (< 1/3 доски) делим поровну с первым
function rowWidths(across, bw) {
  const n = Math.ceil(across / bw - 1e-6);
  const ws = Array(n).fill(bw);
  const rem = across - (n - 1) * bw;
  ws[n - 1] = rem;
  if (n > 1 && rem < bw / 3) ws[0] = ws[n - 1] = (rem + bw) / 2;
  return ws.map(r1);
}

// Ряды комнаты: начало u0 и длина len каждого ряда (в осях доски), ширина w, положение v.
// Комната — прямоугольник; для «Г» сюда добавится разбиение на прямоугольники.
function roomRows(L, W, boardW, dir, gap) {
  const long = Math.max(L, W) - 2 * gap, short = Math.min(L, W) - 2 * gap;
  if (!(long > 0 && short > 0)) return null;
  if (dir !== 'diag') {
    const run = dir === 'cross' ? short : long, across = dir === 'cross' ? long : short;
    let v = gap;
    return { run, across, rows: rowWidths(across, boardW).map(w => { const r = { v: r1(v), w, u0: gap, len: run }; v += w; return r; }) };
  }
  // x — вдоль длинной стены (0..a), y — поперёк (0..b); u = (x + y)/√2, v = (y − x)/√2
  const a = long, b = short;
  const uMin = v => Math.max(v, -v), uMax = v => Math.min(v + a * SQ2, b * SQ2 - v);
  const vMin = -a / SQ2, vMax = b / SQ2;
  let v = vMin;
  const rows = rowWidths(vMax - vMin, boardW).map(w => {
    const v0 = v, v1 = v + w, vs = [v0, v1];
    if (v0 < 0 && v1 > 0) vs.push(0);
    const vStar = (b - a) / SQ2;                 // здесь сходятся две дальние стены
    if (v0 < vStar && v1 > vStar) vs.push(vStar);
    const u0 = Math.min(...vs.map(uMin)), u1 = Math.max(...vs.map(uMax));
    v += w;
    return { v: r1(v0), w, u0: r1(u0), len: r1(u1 - u0) };
  });
  return { run: r1(Math.max(...rows.map(r => r.len))), across: r1(vMax - vMin), rows, a, b };
}

/**
 * Одна раскладка с заданными параметрами.
 * dir: 'long' — вдоль длинной стены, 'cross' — поперёк, 'diag' — по диагонали 45°;
 * scheme: 'deck' — хаотично (обрезком), 'half' — смещение 1/2, 'third' — 1/3;
 * s0 — длина первого куска первого ряда; order — какие остатки брать первыми ('big'/'small').
 */
function layoutRoom(o) {
  const { L, W, boardLen: B, boardW, dir = 'long', scheme = 'deck', gap = 10, minShift = 300,
    minPiece = 300, kerf = 3, order = 'big' } = o;
  const s0 = o.s0 || B;
  if (!(B > 0 && boardW > 0)) return null;
  const geo = roomRows(L, W, boardW, dir, gap);
  if (!geo) return null;
  const diag = dir === 'diag';

  const poolA = [], poolB = [];   // A — с заводским L (в конец ряда), B — с заводским R (в начало)
  // остаток помнит, от какой доски он (id) — для проверки расчёта
  const keep = (pool, len, id) => { if (len >= minPiece) pool.push(Object.assign(new Number(r1(len)), { id })); };
  const take = (pool, i) => pool.splice(i, 1)[0];
  const mod = x => { const m = r1(((x % B) + B) % B); return m < 0.5 ? B : m; };

  let boards = 0, prev = null, minFound = Infinity;
  const rows = [], warnings = [];
  geo.rows.forEach((g, i) => {
    const run = g.len;
    // Ряд с началом s: хвост, стыки (в общих координатах u), годится ли
    const shape = s => {
      if (s >= run - 0.5) return { s: run, k: 0, t: 0, joints: [] };
      const k = Math.floor((run - s) / B + 1e-6);
      let t = r1(run - s - k * B);
      const joints = [];
      for (let j = 0; j < k; j++) joints.push(g.u0 + s + j * B);
      if (t > 0.5) joints.push(g.u0 + s + k * B); else t = 0;
      return { s, k, t, joints };
    };
    const ok = sh => sh.s >= Math.min(minPiece, run) && (sh.t === 0 || sh.t >= minPiece);
    const shiftTo = (sh, p) => {
      let m = Infinity;
      for (const a of sh.joints) for (const b of p) m = Math.min(m, Math.abs(a - b));
      return m;
    };
    let sh = null, src = null, from = -1, deviated = false;
    const good = s => { const c = shape(s); return ok(c) && (!prev || scheme !== 'deck' || shiftTo(c, prev) >= minShift) ? c : null; };

    if (run < minPiece) {   // угол на диагонали: короткий кусок неизбежен
      sh = shape(run);
      warnings.push(i);
    } else if (scheme === 'deck') {
      // хаотично: сперва остаток из кучи B (можно подрезать у стены), потом новая доска
      const idx = poolB.map((p, j) => j).sort((a, b) => order === 'big' ? poolB[b] - poolB[a] : poolB[a] - poolB[b]);
      for (const j of idx) {
        for (let s = Math.min(poolB[j], run); s >= minPiece && !sh; s -= 10) sh = good(r1(s));
        if (sh) { from = j; src = 'spare'; break; }
      }
      if (!sh) for (let s = i === 0 ? s0 : B; s >= minPiece && !sh; s -= 10) sh = good(r1(s));
      if (!sh) { // швы не разошлись — берём лучший по смещению и отмечаем
        let best = null, bm = -1;
        for (let s = B; s >= minPiece; s -= 10) { const c = shape(r1(s)); if (ok(c) && shiftTo(c, prev || []) > bm) { bm = shiftTo(c, prev || []); best = c; } }
        sh = best || shape(Math.min(B, run)); deviated = true;
      }
    } else {
      // 1/2 и 1/3: швы ряда i на общей сетке s0 − фаза·доска (по модулю длины доски)
      const ph = scheme === 'half' ? (i % 2) / 2 : (i % 3) / 3;
      const target = Math.min(mod(s0 - ph * B - g.u0), run);
      sh = good(target);
      // последний кусок вышел короче минимума — сдвигаем начало, ряд помечаем
      for (let d = 10; !sh && d < B; d += 10) {
        sh = (target - d >= minPiece && good(r1(target - d))) || (target + d <= Math.min(B, run) && good(r1(target + d))) || null;
        if (sh) deviated = true;
      }
      if (!sh) { sh = shape(Math.min(target, run)); deviated = true; }
    }
    if (src !== 'spare') {  // остаток нужной длины тоже годится в начало
      const j = poolB.reduce((bj, p, jj) => p >= sh.s && (bj < 0 || p < poolB[bj]) ? jj : bj, -1);
      if (j >= 0) { from = j; src = 'spare'; }
    }
    if (diag && sh.t > 0 && sh.t < minPiece) warnings.push(i);

    const pieces = [];
    let x = g.u0;
    const add = (len, s, end, board) => { pieces.push({ x: r1(x), len: r1(len), src: s, end, board, short: len < minPiece - 0.5 }); x += len; };
    const single = sh.k === 0 && sh.t === 0;

    // начало ряда
    if (src === 'spare') add(sh.s, 'spare', single ? 'only' : 'start', take(poolB, from).id);
    else {
      const id = ++boards;
      src = sh.s >= B - 0.5 ? 'full' : 'cut';
      if (src === 'cut') keep(poolA, B - sh.s - kerf, id);
      add(sh.s, src, single ? 'only' : 'start', id);
    }
    for (let j = 0; j < sh.k; j++) add(B, 'full', 'mid', ++boards);
    // конец ряда: остаток с заводским L или новая доска (её правая часть — в кучу B)
    if (sh.t > 0) {
      const j = poolA.reduce((bj, p, jj) => p >= sh.t && (bj < 0 || p < poolA[bj]) ? jj : bj, -1);
      if (j >= 0) add(sh.t, 'spare', 'end', take(poolA, j).id);
      else { const id = ++boards; add(sh.t, 'cut', 'end', id); keep(poolB, B - sh.t - kerf, id); }
    }
    if (diag && pieces.some(q => q.short)) warnings.push(i);   // у углов короткие куски неизбежны — предупреждаем
    if (prev && sh.joints.length && prev.length) minFound = Math.min(minFound, shiftTo(sh, prev));
    rows.push({ i, y: g.v, w: g.w, u0: g.u0, len: run, deviated, warn: warnings.includes(i), pieces });
    prev = sh.joints;
  });

  // площадь пола: для диагонали — сама комната
  const area = diag ? geo.a * geo.b : geo.run * geo.across;
  const waste = boards * B * boardW - area;
  return { dir, scheme, s0, order, run: geo.run, across: geo.across, gap, boardLen: B, boardW, rows, boards,
    room: diag ? { a: geo.a, b: geo.b } : null,
    minShiftFound: minFound === Infinity ? null : r1(minFound), waste,
    lower: Math.ceil(area / (B * boardW) - 1e-9), deviations: rows.filter(r => r.deviated).length,
    warnings: [...new Set(warnings)] };
}

// Лучше: схема соблюдена (отступлений не больше трети рядов) → меньше досок → меньше отход → шире смещение швов
const neat = p => p.deviations <= Math.ceil(p.rows.length / 3);
const better = (a, b) => !b || (neat(a) && !neat(b)) || (neat(a) === neat(b) && a.boards < b.boards) || (neat(a) === neat(b) && a.boards === b.boards &&
  (a.waste < b.waste - 1 || (Math.abs(a.waste - b.waste) <= 1 && (a.minShiftFound || 0) > (b.minShiftFound || 0))));

/** Перебор вариантов. dir/scheme заданы консультантом; если другой прямой вариант экономнее — hint */
function bestLayout(o) {
  const search = (dirs, schemes) => {
    let best = null;
    for (const dir of dirs) for (const scheme of schemes)
      for (const order of scheme === 'deck' ? ['big', 'small'] : ['big'])
        // у 1/2 и 1/3 s0 сдвигает весь цикл: швы соседних рядов всё равно смещены на 1/2 или 1/3 доски
        for (let s0 = o.boardLen; s0 >= (o.minPiece || 300); s0 -= 10) {
          const p = layoutRoom({ ...o, dir, scheme, order, s0 });
          if (p && better(p, best)) best = p;
        }
    return best;
  };
  const best = search(o.dir ? [o.dir] : ['long', 'cross'], o.scheme ? [o.scheme] : ['deck', 'half', 'third']);
  if (best && (o.dir || o.scheme) && o.dir !== 'diag') {
    const free = search(['long', 'cross'], ['deck', 'half', 'third']);
    if (free && free.boards < best.boards) best.hint = { dir: free.dir, scheme: free.scheme, boards: free.boards };
  }
  return best;
}

// Список резов для мастера, простыми словами
function cutList(plan) {
  const cm = v => Math.round(v / 10) + ' см';
  const bevel = plan.dir === 'diag' ? ' (край под 45°)' : '';
  return plan.rows.map(r => {
    const p = r.pieces, first = p[0], last = p[p.length - 1];
    const parts = [];
    if (first.end === 'only') parts.push((first.src === 'spare' ? `один кусок из остатка ${cm(first.len)}` : `один кусок ${cm(first.len)}`) + bevel);
    else {
      parts.push((first.src === 'full' ? 'начать с целой' : first.src === 'spare' ? `начать с остатка ${cm(first.len)}` : `начать с куска ${cm(first.len)}`) + (first.src !== 'full' ? bevel : ''));
      const full = p.filter(q => q.end === 'mid').length;
      if (full) parts.push(`дальше ${full} ${full === 1 ? 'целая' : 'целые'}`);
      if (last.end === 'end') parts.push(`последняя ${cm(last.len)}${last.src === 'spare' ? ' из остатка' : ''}${bevel}`);
    }
    const narrow = plan.dir !== 'diag' && r.w < plan.boardW - 0.5 ? ` · доски распилить вдоль до ${Math.round(r.w)} мм` : '';
    return `Ряд ${r.i + 1}: ${parts.join(', ')}${narrow}${r.warn ? ' · у угла короткий кусок' : ''}`;
  });
}

if (typeof module !== 'undefined') module.exports = { layoutRoom, bestLayout, cutList, rowWidths, roomRows };
