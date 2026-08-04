/* Woher kommt der Strom? — Austrian grid mix.
   No dependencies. All numbers are precomputed by scripts/fetch_data.py;
   this file only draws them. */

'use strict';

// Stack order = colour order. Validated as a set against the CVD, normal-vision
// and lightness checks in both modes; reordering invalidates that.
const ORDER = ['hydro', 'fossil', 'wind', 'solar', 'pumped', 'biomass', 'other'];
const REPO = 'https://github.com/rfuzzo/woher-kommt-der-strom';
const COLOR = k => getComputedStyle(document.documentElement).getPropertyValue('--' + k).trim();

const I18N = {
  de: {
    title: 'Woher kommt der Strom?',
    sub: 'Österreichs Erzeugungsmix, Tagesverlauf und Grenzflüsse — aus offenen Daten.',
    mixTitle: 'Woher der Strom gerade kommt',
    dayTitle: 'Erzeugung nach Quelle · 24 Stunden',
    flowTitle: 'Grenzüberschreitende Flüsse · jetzt',
    tradeTitle: 'Import und Export · 24 Stunden',
    perCountry: 'Je Nachbarland',
    peakImport: 'Höchster Import',
    peakExport: 'Höchster Export',
    timeImporting: 'Zeit als Netto-Importeur',
    ofLoadThen: 'der Last in diesem Moment',
    ofDay: 'der letzten 24 Stunden',
    importing2: 'Import',
    exporting2: 'Export',
    tradeNote: 'Über null importiert Österreich netto, darunter exportiert es. Der Tagesverlauf folgt der Sonne: nachts und früh am Morgen hängt das Land am Import, mittags dreht die Photovoltaik die Bilanz um.',
    balanceCol: 'Saldo',
    tableToggle: 'Werte als Tabelle',
    importing: 'Import nach Österreich',
    exporting: 'Export aus Österreich',
    generation: 'Erzeugung',
    load: 'Last',
    renew: 'Erneuerbaren-Anteil',
    price: 'Day-Ahead-Preis',
    ofLoad: 'der Last',
    total: 'Gesamt',
    source: 'Quelle',
    share: 'Anteil',
    net: 'Saldo',
    netExport: 'Nettoexport',
    netImport: 'Nettoimport',
    balanced: 'ausgeglichen',
    asOf: 'Stand',
    lag: 'veröffentlicht mit rund {h} Verzögerung',
    mixNote: 'Die Anteile beziehen sich auf die inländische Erzeugung, nicht auf den Verbrauch. Pumpspeicher zählt hier als Erzeugung — die Energie zum Hochpumpen stammt aus einem früheren Zeitpunkt.',
    dayNote: 'Die Flächen sind die inländische Erzeugung, die kräftige Linie ist die Last. Liegt die Linie unter den Flächen, exportiert Österreich mehr, als es importiert.',
    flowNote: 'Physikalische Flüsse an den Kuppelstellen, nicht Handelsgeschäfte. Strom fließt auch durch Österreich hindurch, ohne hier verbraucht zu werden.',
    sources: 'Erzeugung, Last, Grenzflüsse und Preis: <a href="https://api.energy-charts.info/">Energy-Charts</a> (Fraunhofer ISE), gespeist aus <a href="https://transparency.entsoe.eu/">ENTSO-E</a> und <a href="https://www.apg.at/">APG</a>.',
    credit: 'Idee inspiriert von <a href="https://holadelej.hu/">holadelej.hu</a> (Ungarn) — eigenständig gebaut, ohne Übernahme von Gestaltung oder Text.',
    colophon: 'Quellcode auf <a href="' + REPO + '">GitHub</a> — offen und nachbaubar. Gebaut mit Unterstützung von <a href="https://claude.com/claude-code">Claude Code</a>.',
    err: 'Die Daten konnten nicht geladen werden.',
    hours: 'h', mins: 'min'
  },
  en: {
    title: 'Where does the power come from?',
    sub: "Austria's generation mix, daily shape and cross-border flows — from open data.",
    mixTitle: 'Where the power is coming from right now',
    dayTitle: 'Generation by source · 24 hours',
    flowTitle: 'Cross-border flows · right now',
    tradeTitle: 'Import and export · 24 hours',
    perCountry: 'By neighbour',
    peakImport: 'Peak import',
    peakExport: 'Peak export',
    timeImporting: 'Time as a net importer',
    ofLoadThen: 'of demand at that moment',
    ofDay: 'of the last 24 hours',
    importing2: 'Import',
    exporting2: 'Export',
    tradeNote: 'Above zero Austria is a net importer, below it a net exporter. The shape follows the sun: overnight and early morning the country leans on imports, and around midday solar flips the balance.',
    balanceCol: 'Balance',
    tableToggle: 'View values as a table',
    importing: 'Importing into Austria',
    exporting: 'Exporting from Austria',
    generation: 'Generation',
    load: 'Load',
    renew: 'Renewable share',
    price: 'Day-ahead price',
    ofLoad: 'of load',
    total: 'Total',
    source: 'Source',
    share: 'Share',
    net: 'Net',
    netExport: 'net export',
    netImport: 'net import',
    balanced: 'balanced',
    asOf: 'As of',
    lag: 'published about {h} later',
    mixNote: 'Shares are of domestic generation, not of consumption. Pumped storage counts as generation here — the energy used to pump the water uphill came from an earlier moment.',
    dayNote: 'The areas are domestic generation; the heavy line is load. Where the line sits below the areas, Austria is exporting more than it imports.',
    flowNote: 'Physical flows across the interconnectors, not commercial trades. Power also transits Austria without being consumed here.',
    sources: 'Generation, load, cross-border flows and price: <a href="https://api.energy-charts.info/">Energy-Charts</a> (Fraunhofer ISE), fed from <a href="https://transparency.entsoe.eu/">ENTSO-E</a> and <a href="https://www.apg.at/">APG</a>.',
    credit: 'Concept inspired by <a href="https://holadelej.hu/">holadelej.hu</a> (Hungary) — built independently, with no design or copy taken from it.',
    colophon: 'Source on <a href="' + REPO + '">GitHub</a> — open, and rebuildable. Built with the help of <a href="https://claude.com/claude-code">Claude Code</a>.',
    err: 'The data could not be loaded.',
    hours: 'h', mins: 'min'
  }
};

let LANG = (localStorage.getItem('lang') || (navigator.language || '').slice(0, 2)) === 'en' ? 'en' : 'de';
let DATA = null;
const t = k => I18N[LANG][k];
const label = g => LANG === 'de' ? g.de : g.en;

// The API returns English country names; Austria's six neighbours get German
// ones on the German page.
const COUNTRY_DE = {
  'Czech Republic': 'Tschechien',
  'Germany': 'Deutschland',
  'Hungary': 'Ungarn',
  'Italy': 'Italien',
  'Slovenia': 'Slowenien',
  'Switzerland': 'Schweiz',
  'Slovakia': 'Slowakei',
};
const country = name => LANG === 'de' ? (COUNTRY_DE[name] || name) : name;

const nf = (v, d = 0) => new Intl.NumberFormat(LANG === 'de' ? 'de-AT' : 'en-GB',
  { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);

const clockFmt = () => new Intl.DateTimeFormat(LANG === 'de' ? 'de-AT' : 'en-GB',
  { hour: '2-digit', minute: '2-digit', timeZone: DATA.timezone || 'Europe/Vienna' });

const dateFmt = () => new Intl.DateTimeFormat(LANG === 'de' ? 'de-AT' : 'en-GB',
  { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    timeZone: DATA.timezone || 'Europe/Vienna' });

const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};

const svgEl = (tag, attrs) => {
  const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  return n;
};

/* ── header ───────────────────────────────────────────────────────────── */

function renderStamp() {
  const at = new Date(DATA.dataAt * 1000);
  const bits = [`${t('asOf')} ${dateFmt().format(at)}`];
  if (DATA.publishedAt) {
    const mins = Math.round((DATA.publishedAt - DATA.dataAt) / 60);
    const s = mins >= 90 ? `${Math.round(mins / 60)} ${t('hours')}` : `${mins} ${t('mins')}`;
    bits.push(t('lag').replace('{h}', s));
  }
  const p = document.getElementById('stamp');
  p.textContent = '';
  p.append(el('span', 'dot'), document.createTextNode(bits.join(' · ')));
}

/* ── stat tiles ───────────────────────────────────────────────────────── */

function renderTiles() {
  const n = DATA.now;
  const box = document.getElementById('tiles');
  box.textContent = '';

  const netMw = DATA.flows ? DATA.flows.reduce((a, f) => a + f.mw, 0) : null;
  const tiles = [
    { k: t('generation'), v: nf(n.generation), u: 'MW' },
    { k: t('load'), v: nf(n.load), u: 'MW' },
  ];
  if (n.renewableShareLoad != null) {
    tiles.push({ k: t('renew'), v: nf(n.renewableShareLoad, 1), u: '%', d: t('ofLoad') });
  }
  if (netMw != null) {
    const dir = Math.abs(netMw) < 20 ? t('balanced') : netMw > 0 ? t('netImport') : t('netExport');
    tiles.push({ k: t('net'), v: nf(Math.abs(netMw)), u: 'MW', d: dir });
  }
  if (DATA.price) {
    tiles.push({ k: t('price'), v: nf(DATA.price.now, 1), u: '€/MWh' });
  }

  for (const x of tiles) {
    const c = el('div', 'tile');
    c.append(el('div', 'k', x.k), el('div', 'v', `${x.v}<small>${x.u}</small>`));
    if (x.d) c.append(el('div', 'd', x.d));
    box.append(c);
  }
}

/* ── the mix ──────────────────────────────────────────────────────────── */

function orderedGroups() {
  return ORDER.map(k => DATA.groups.find(g => g.key === k)).filter(Boolean);
}

function renderMix() {
  const groups = orderedGroups();
  const bar = document.getElementById('sharebar');
  const leg = document.getElementById('legend');
  bar.textContent = '';
  leg.textContent = '';

  for (const g of groups) {
    if (g.pct <= 0) continue;
    const s = el('span');
    s.style.flex = `${g.pct} 1 0`;
    s.style.background = `var(--${g.key})`;
    s.title = `${label(g)} · ${nf(g.pct, 1)} %`;
    bar.append(s);
  }

  // Legend follows the bar's order, not size rank, so the eye can track
  // left-to-right between the two. The percentage carries the ranking.
  for (const g of groups) {
    const r = el('div', 'row');
    const sw = el('span', 'sw');
    sw.style.background = `var(--${g.key})`;
    r.append(sw, el('span', 'nm', label(g)),
      el('span', 'mw', `${nf(g.mw)} MW`),
      el('span', 'pc', `${nf(g.pct, 1)} %`));
    leg.append(r);
  }

  const rows = [...groups].sort((a, b) => b.mw - a.mw)
    .map(g => `<tr><td>${label(g)}</td><td class="n">${nf(g.mw)}</td><td class="n">${nf(g.pct, 1)}</td></tr>`).join('');
  document.getElementById('mixTable').innerHTML =
    `<table><caption>${t('mixTitle')} — ${dateFmt().format(new Date(DATA.dataAt * 1000))}</caption>
     <thead><tr><th>${t('source')}</th><th class="n">MW</th><th class="n">${t('share')} %</th></tr></thead>
     <tbody>${rows}<tr><td><strong>${t('total')}</strong></td><td class="n"><strong>${nf(DATA.now.generation)}</strong></td><td class="n">100</td></tr></tbody></table>`;
}

/* ── 24 h stacked area + load line ────────────────────────────────────── */

const PAD = { t: 14, r: 14, b: 26, l: 46 };

function renderDay() {
  const svg = document.getElementById('dayChart');
  const groups = orderedGroups();
  const times = DATA.day.t;
  const N = times.length;
  if (!N) return;

  const W = Math.max(svg.clientWidth || svg.parentElement.clientWidth || 720, 320);
  const H = 300;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('height', H);
  svg.textContent = '';

  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
  const totals = times.map((_, i) => groups.reduce((a, g) => a + g.series[i], 0));
  const peak = Math.max(...totals, ...DATA.day.load);
  const STEP = 2000;
  // Round to a whole number of ticks so the top gridline is always a tick and
  // reliably carries the unit label.
  const top = Math.max(Math.ceil(peak / STEP) * STEP, STEP);

  const x = i => PAD.l + (N === 1 ? iw / 2 : (i / (N - 1)) * iw);
  const y = v => PAD.t + ih - (v / top) * ih;

  svg.setAttribute('aria-label',
    `${t('dayTitle')} — ${groups.map(g => label(g)).join(', ')}`);

  // gridlines
  for (let v = 0; v <= top; v += STEP) {
    svg.append(svgEl('line', { class: v === 0 ? 'axisline' : 'gridline', x1: PAD.l, x2: W - PAD.r, y1: y(v), y2: y(v) }));
    const lab = svgEl('text', { x: PAD.l - 8, y: y(v) + 4, 'text-anchor': 'end' });
    lab.textContent = v ? nf(v / 1000) + (v === top ? ' GW' : '') : '0';
    svg.append(lab);
  }

  // stacked bands, bottom up
  let base = new Array(N).fill(0);
  for (const g of groups) {
    const upper = base.map((b, i) => b + g.series[i]);
    if (upper.every((v, i) => v - base[i] < 0.05)) { base = upper; continue; }
    const d = upper.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('') +
      base.map((v, i) => `L${x(N - 1 - i)},${y(base[N - 1 - i])}`).join('') + 'Z';
    svg.append(svgEl('path', { d, fill: `var(--${g.key})`, stroke: 'var(--surface)', 'stroke-width': 2, 'stroke-linejoin': 'round' }));
    base = upper;
  }

  // load line
  svg.append(svgEl('path', {
    class: 'loadline',
    d: DATA.day.load.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('')
  }));

  // hour ticks
  const fmt = clockFmt();
  const every = Math.max(1, Math.round(N / 8));
  times.forEach((ts, i) => {
    if (i % every && i !== N - 1) return;
    const lab = svgEl('text', { x: x(i), y: H - 8, 'text-anchor': i === N - 1 ? 'end' : 'middle' });
    lab.textContent = fmt.format(new Date(ts * 1000));
    svg.append(lab);
  });

  const cursor = svgEl('line', { class: 'cursor', y1: PAD.t, y2: PAD.t + ih, opacity: 0 });
  svg.append(cursor);

  // legend under the chart, in stack order (top of stack first, so it reads
  // the same direction as the bands)
  const dl = document.getElementById('dayLegend');
  dl.textContent = '';
  for (const g of [...groups].reverse()) {
    const r = el('div', 'row');
    const sw = el('span', 'sw');
    sw.style.background = `var(--${g.key})`;
    r.append(sw, el('span', 'nm', label(g)));
    dl.append(r);
  }
  const lr = el('div', 'row');
  const ls = el('span', 'sw');
  ls.style.background = 'var(--ink)';
  lr.append(ls, el('span', 'nm', t('load')));
  dl.append(lr);

  // hover
  const tip = document.getElementById('dayTip');
  const wrap = svg.closest('.plotwrap');

  const show = ev => {
    const box = svg.getBoundingClientRect();
    const px = (ev.clientX - box.left) / box.width * W;
    let i = Math.round((px - PAD.l) / iw * (N - 1));
    i = Math.max(0, Math.min(N - 1, i));
    if (!Number.isFinite(i)) return;

    cursor.setAttribute('x1', x(i));
    cursor.setAttribute('x2', x(i));
    cursor.setAttribute('opacity', 1);

    const rows = [...groups].reverse().filter(g => g.series[i] > 0.05).map(g =>
      `<div class="r"><span class="sw" style="background:var(--${g.key})"></span>${label(g)}<span class="v">${nf(g.series[i])} MW</span></div>`).join('');
    tip.innerHTML = `<div class="t">${dateFmt().format(new Date(times[i] * 1000))}</div>${rows}
      <div class="r tot"><span class="sw" style="background:var(--ink)"></span>${t('load')}<span class="v">${nf(DATA.day.load[i])} MW</span></div>`;
    tip.classList.add('on');

    const wb = wrap.getBoundingClientRect();
    const rel = x(i) / W * box.width + (box.left - wb.left);
    tip.style.left = Math.min(Math.max(rel + 14, 0), wb.width - tip.offsetWidth) + 'px';
    tip.style.top = '10px';
  };

  const hide = () => { tip.classList.remove('on'); cursor.setAttribute('opacity', 0); };
  svg.addEventListener('pointermove', show);
  svg.addEventListener('pointerleave', hide);
  svg.addEventListener('pointerdown', show);
}

/* ── import / export over 24 h ────────────────────────────────────────── */

/* Signed series drawn as an area off a zero baseline: the same path is
   filled twice, clipped above and below zero, so the sign carries the
   colour without a second scale or a second chart. */
function divergingArea(svg, vals, x, y, zeroY, idPrefix) {
  const N = vals.length;
  const defs = svgEl('defs', {});
  const box = { x: x(0), w: x(N - 1) - x(0) };

  for (const side of ['pos', 'neg']) {
    const cp = svgEl('clipPath', { id: `${idPrefix}-${side}` });
    cp.append(svgEl('rect', {
      x: box.x, width: Math.max(box.w, 1),
      y: side === 'pos' ? y.top : zeroY,
      height: Math.max(side === 'pos' ? zeroY - y.top : y.bottom - zeroY, 0),
    }));
    defs.append(cp);
  }
  svg.append(defs);

  const d = vals.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y.of(v)}`).join('')
    + `L${x(N - 1)},${zeroY}L${x(0)},${zeroY}Z`;

  for (const [side, color] of [['pos', 'var(--import)'], ['neg', 'var(--export)']]) {
    svg.append(svgEl('path', {
      d, fill: color, 'clip-path': `url(#${idPrefix}-${side})`, 'fill-opacity': 0.85,
    }));
  }
}

function renderTrade() {
  const sec = document.getElementById('tradeSection');
  const tr = DATA.trade;
  if (!tr || !tr.t || tr.t.length < 2) { sec.hidden = true; return; }
  sec.hidden = false;

  // stats
  const pct = tr.steps ? Math.round(tr.importingSteps / tr.steps * 100) : 0;
  const stats = [
    { k: t('peakImport'), v: `+${nf(tr.peakImport)}`, u: 'MW',
      d: tr.peakImportShare != null ? `${nf(tr.peakImportShare, 1)} % ${t('ofLoadThen')}` : '' },
    { k: t('peakExport'), v: nf(tr.peakExport), u: 'MW' },
    { k: t('timeImporting'), v: `${pct}`, u: '%', d: t('ofDay') },
  ];
  const box = document.getElementById('tradeStats');
  box.textContent = '';
  for (const s of stats) {
    const c = el('div', 'tstat');
    c.append(el('div', 'k', s.k), el('div', 'v', `${s.v}<small>${s.u}</small>`));
    if (s.d) c.append(el('div', 'd', s.d));
    box.append(c);
  }

  // main chart
  const svg = document.getElementById('tradeChart');
  const N = tr.t.length;
  const W = Math.max(svg.clientWidth || svg.parentElement.clientWidth || 720, 320);
  const H = 240;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('height', H);
  svg.textContent = '';
  svg.setAttribute('aria-label', t('tradeTitle'));

  // Extra headroom over the shared padding: this chart carries a unit
  // caption above the top tick.
  const P = { t: 28, r: PAD.r, b: PAD.b, l: PAD.l };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const mag = Math.max(...tr.net.map(Math.abs), 500);
  const STEP = mag > 2500 ? 1000 : 500;
  const top = Math.ceil(mag / STEP) * STEP;

  const x = i => P.l + (i / (N - 1)) * iw;
  const yOf = v => P.t + ih / 2 - (v / top) * (ih / 2);
  const y = { of: yOf, top: P.t, bottom: P.t + ih };
  const zeroY = yOf(0);

  for (let v = -top; v <= top; v += STEP) {
    svg.append(svgEl('line', {
      class: v === 0 ? 'axisline' : 'gridline',
      x1: P.l, x2: W - P.r, y1: yOf(v), y2: yOf(v),
    }));
    const lab = svgEl('text', { x: P.l - 8, y: yOf(v) + 4, 'text-anchor': 'end' });
    lab.textContent = v === 0 ? '0' : nf(v / 1000, 1);
    svg.append(lab);
  }

  // Unit as a caption rather than a suffix on the top tick — "2,5 GW" is
  // wider than the left gutter and would clip.
  const unit = svgEl('text', { x: P.l - 8, y: P.t - 10, 'text-anchor': 'end' });
  unit.textContent = 'GW';
  svg.append(unit);

  divergingArea(svg, tr.net, x, y, zeroY, 'net');

  svg.append(svgEl('path', {
    class: 'loadline',
    d: tr.net.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${yOf(v)}`).join(''),
    'stroke-width': 1.5,
  }));

  const fmt = clockFmt();
  const every = Math.max(1, Math.round(N / 8));
  tr.t.forEach((ts, i) => {
    if (i % every && i !== N - 1) return;
    const lab = svgEl('text', { x: x(i), y: H - 8, 'text-anchor': i === N - 1 ? 'end' : i === 0 ? 'start' : 'middle' });
    lab.textContent = fmt.format(new Date(ts * 1000));
    svg.append(lab);
  });

  const cursor = svgEl('line', { class: 'cursor', y1: P.t, y2: P.t + ih, opacity: 0 });
  svg.append(cursor);

  const tip = document.getElementById('tradeTip');
  const wrap = svg.closest('.plotwrap');
  const show = ev => {
    const b = svg.getBoundingClientRect();
    const px = (ev.clientX - b.left) / b.width * W;
    let i = Math.round((px - P.l) / iw * (N - 1));
    i = Math.max(0, Math.min(N - 1, i));
    cursor.setAttribute('x1', x(i));
    cursor.setAttribute('x2', x(i));
    cursor.setAttribute('opacity', 1);

    const v = tr.net[i];
    const rows = tr.countries.map(c =>
      `<div class="r"><span class="sw" style="background:${c.series[i] >= 0 ? 'var(--import)' : 'var(--export)'}"></span>${country(c.name)}<span class="v">${c.series[i] > 0 ? '+' : ''}${nf(c.series[i])}</span></div>`).join('');
    tip.innerHTML = `<div class="t">${dateFmt().format(new Date(tr.t[i] * 1000))}</div>${rows}
      <div class="r tot"><span class="sw" style="background:${v >= 0 ? 'var(--import)' : 'var(--export)'}"></span>${v >= 0 ? t('importing2') : t('exporting2')}<span class="v">${v > 0 ? '+' : ''}${nf(v)} MW</span></div>`;
    tip.classList.add('on');

    const wb = wrap.getBoundingClientRect();
    const rel = x(i) / W * b.width + (b.left - wb.left);
    tip.style.left = Math.min(Math.max(rel + 14, 0), wb.width - tip.offsetWidth) + 'px';
    tip.style.top = '6px';
  };
  const hide = () => { tip.classList.remove('on'); cursor.setAttribute('opacity', 0); };
  svg.addEventListener('pointermove', show);
  svg.addEventListener('pointerleave', hide);
  svg.addEventListener('pointerdown', show);

  renderSparks(tr);

  const rows = tr.countries.map(c => {
    const last = c.series[c.series.length - 1];
    const hi = Math.max(...c.series), lo = Math.min(...c.series);
    return `<tr><td>${country(c.name)}</td><td class="n">${last > 0 ? '+' : ''}${nf(last)}</td><td class="n">${nf(hi)}</td><td class="n">${nf(lo)}</td></tr>`;
  }).join('');
  document.getElementById('tradeTable').innerHTML =
    `<table><caption>${t('tradeTitle')}</caption>
     <thead><tr><th>${t('perCountry')}</th><th class="n">${t('balanceCol')} MW</th><th class="n">max</th><th class="n">min</th></tr></thead>
     <tbody>${rows}</tbody></table>`;
}

function renderSparks(tr) {
  const box = document.getElementById('sparks');
  box.textContent = '';
  // One shared scale across the small multiples, so the panels are
  // comparable to each other rather than each self-normalised.
  const mag = Math.max(...tr.countries.flatMap(c => c.series.map(Math.abs)), 500);

  for (const c of tr.countries) {
    const card = el('div', 'spark');
    const last = c.series[c.series.length - 1];
    const head = el('div', 'sh');
    head.append(el('span', 'nm', country(c.name)),
      el('span', 'val', `${last > 0 ? '+' : ''}${nf(last)} MW`));
    card.append(head);

    const N = c.series.length;
    const W = 220, H = 54;
    const svg = svgEl('svg', {
      class: 'chart', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none',
      role: 'img', 'aria-label': `${country(c.name)} ${nf(last)} MW`,
    });
    svg.style.height = H + 'px';

    const x = i => (i / (N - 1)) * W;
    const yOf = v => H / 2 - (v / mag) * (H / 2 - 3);
    const y = { of: yOf, top: 0, bottom: H };
    const zeroY = yOf(0);

    divergingArea(svg, c.series, x, y, zeroY, 'sp-' + c.name.replace(/\W/g, ''));
    svg.append(svgEl('line', { class: 'axisline', x1: 0, x2: W, y1: zeroY, y2: zeroY }));
    card.append(svg);
    box.append(card);
  }
}

/* ── cross-border flows ───────────────────────────────────────────────── */

function renderFlows() {
  const sec = document.getElementById('flowSection');
  if (!DATA.flows || !DATA.flows.length) { sec.hidden = true; return; }
  sec.hidden = false;

  const box = document.getElementById('flows');
  box.textContent = '';
  const max = Math.max(...DATA.flows.map(f => Math.abs(f.mw)), 1);

  for (const f of DATA.flows) {
    const row = el('div', 'flowrow');
    const track = el('div', 'flowtrack');
    track.append(el('div', 'zero'));

    const bar = el('div', 'bar');
    const w = Math.abs(f.mw) / max * 50;
    bar.style.width = w + '%';
    bar.style.background = f.mw >= 0 ? 'var(--import)' : 'var(--export)';
    if (f.mw >= 0) bar.style.left = '50%'; else bar.style.right = '50%';
    track.append(bar);

    row.append(el('div', 'nm', country(f.name)), track,
      el('div', 'val', `${f.mw > 0 ? '+' : ''}${nf(f.mw)} MW`));
    box.append(row);
  }
}

/* ── footer ───────────────────────────────────────────────────────────── */

function renderFooter() {
  document.getElementById('srcLine').innerHTML = t('sources');
  document.getElementById('licLine').textContent =
    [DATA.license, DATA.price && DATA.price.license].filter(Boolean).join(' · ');
  document.querySelector('[data-i18n="credit"]').innerHTML = t('credit');
  document.getElementById('colophon').innerHTML = t('colophon');
}

/* ── wiring ───────────────────────────────────────────────────────────── */

function renderAll() {
  document.documentElement.lang = LANG;
  for (const n of document.querySelectorAll('[data-i18n]')) {
    const k = n.dataset.i18n;
    if (I18N[LANG][k] != null && k !== 'credit') n.textContent = t(k);
  }
  document.title = t('title') + ' — ' + (LANG === 'de' ? 'Österreichs Stromnetz' : "Austria's power grid");
  document.getElementById('lang').textContent = LANG === 'de' ? 'EN' : 'DE';
  renderStamp();
  renderTiles();
  renderMix();
  renderDay();
  renderTrade();
  renderFlows();
  renderFooter();
}

document.getElementById('lang').addEventListener('click', () => {
  LANG = LANG === 'de' ? 'en' : 'de';
  localStorage.setItem('lang', LANG);
  renderAll();
});

document.getElementById('theme').addEventListener('click', () => {
  const cur = document.documentElement.dataset.theme;
  const dark = cur ? cur === 'dark'
    : matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = dark ? 'light' : 'dark';
  localStorage.setItem('theme', document.documentElement.dataset.theme);
  renderDay();
  renderTrade();
});

if (localStorage.getItem('theme')) {
  document.documentElement.dataset.theme = localStorage.getItem('theme');
}

let resizeTimer;
addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (DATA) { renderDay(); renderTrade(); } }, 150);
});

fetch('data.json?' + Date.now())
  .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then(d => {
    DATA = d;
    document.getElementById('app').hidden = false;
    renderAll();
  })
  .catch(e => {
    const box = document.getElementById('error');
    box.hidden = false;
    box.textContent = `${t('err')} (${e.message})`;
  });
