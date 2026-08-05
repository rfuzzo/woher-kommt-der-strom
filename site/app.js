/* Woher kommt der Strom? — Austrian grid mix.
   No dependencies. All numbers are precomputed by scripts/fetch_data.py;
   this file only draws them. */

'use strict';

// Stack order = colour order. Validated as a set against the CVD, normal-vision
// and lightness checks in both modes; reordering invalidates that.
const ORDER = ['hydro', 'fossil', 'wind', 'solar', 'pumped', 'biomass', 'other'];
const REPO = 'https://github.com/rfuzzo/woher-kommt-der-strom';

/* Rivers are fetched straight from the browser, not baked into data.json:
   ehyd serves `access-control-allow-origin: *` and refreshes every ~15 min,
   so this panel is roughly two hours fresher than the electricity data.
   One representative gauge per river, each the most downstream one inside
   Austria. `hzbnr` is ehyd's station id. */
const EHYD = 'https://ehyd.gv.at/services/Diagram/pegelBgis?hzbnr=';
const RIVERS = [
  { river: 'Donau', en: 'Danube', hzbnr: 207373 },
  { river: 'Inn', en: 'Inn', hzbnr: 201889 },
  { river: 'Salzach', en: 'Salzach', hzbnr: 203539 },
  { river: 'Enns', en: 'Enns', hzbnr: 205922 },
  { river: 'Drau', en: 'Drava', hzbnr: 213595 },
  { river: 'Mur', en: 'Mur', hzbnr: 211490 },
];
const COLOR = k => getComputedStyle(document.documentElement).getPropertyValue('--' + k).trim();

const I18N = {
  de: {
    title: 'Woher kommt der Strom?',
    sub: 'Österreichs Erzeugungsmix, Tagesverlauf und Grenzflüsse — aus offenen Daten.',
    mixTitle: 'Woher der Strom gerade kommt',
    dayTitle: 'Versorgung nach Quelle',
    cleanScoreTitle: 'Saubere Versorgung · 24 Stunden',
    compareTitle: 'Heute im Vergleich',
    compareNote: 'Verglichen wird das gleitende letzte 24-Stunden-Fenster mit dem Mittel der sechs davorliegenden 24-Stunden-Fenster.',
    dependencyTitle: 'Importabhängigkeit · 7 Tage',
    dependencyNote: 'Positive Nettoimporte als Anteil der Last. Bei Nettoexport liegt die Importabhängigkeit bei null.',
    avgLoad: 'Mittlere Last',
    renewableDomestic: 'Erneuerbar · Inland',
    importDependency: 'Importanteil',
    vsAverage: 'gegenüber dem 6-Tage-Mittel',
    seasonTitle: 'Im Jahresverlauf',
    seasonLatest: 'Letzter Tag',
    seasonBetter: 'Grüner als',
    ofYear: 'der letzten 365 Tage',
    seasonMedian: 'Median im Jahr',
    seasonBest: 'Bester Tag',
    seasonDaily: 'Tageswert',
    seasonTrend: '30-Tage-Mittel',
    seasonNote: 'Täglicher Erneuerbaren-Anteil an der Last über die letzten 365 Tage, direkt von Energy-Charts. Die helle Fläche sind die Tageswerte, die kräftige Linie das gleitende 30-Tage-Mittel — einzelne Tage schwanken zu stark, um die Jahreszeit zu zeigen. Der jüngste Tag kann noch unvollständig sein. Anders als der Vergleich darüber misst diese Reihe gegen ein ganzes Jahr statt gegen eine Woche Wetter.',
    balanceTitle: 'Energiebilanz · 24 Stunden',
    balanceGap: 'Nicht aufgelöste Differenz',
    balanceMean: 'Ø absolute Differenz',
    balanceNote: 'Rechnung: inländische Erzeugung + kommerzieller Nettoimport − Last − Pumpleistung. Das erklärt den großen Mittagsüberschuss weitgehend. Die verbleibende Differenz ist kein eigener Energiefluss: Erzeugung, Handel und Last haben unterschiedliche Abgrenzungen und Veröffentlichungsstände; auch Netzverluste spielen hinein. Deshalb wird sie gezeigt, nicht künstlich auf null gerechnet.',
    storageTitle: 'Pumpspeicher und Strompreis · 24 Stunden',
    storageOperation: 'Speicherbetrieb',
    price24: 'Day-Ahead-Preis',
    storageGenerating: 'erzeugt',
    storagePumping: 'pumpt',
    storageIdle: 'nahezu still',
    currentMode: 'Aktueller Betrieb',
    peakGeneration: 'Höchste Erzeugung',
    peakPumping: 'Höchste Pumpleistung',
    storageNote: 'Oben: Erzeugung aus dem Speicher über null, Pumpleistung darunter. Unten: der Preis auf einer eigenen Skala. Die zeitliche Nähe ist aufschlussreich, beweist aber allein noch keine Arbitrage oder Kausalität.',
    tradeTitle: 'Import und Export',
    tradeShape: 'Saldo · 24 Stunden',
    perCountry: 'Je Nachbarland',
    peakImport: 'Höchster Import',
    peakExport: 'Höchster Export',
    timeImporting: 'Zeit als Netto-Importeur',
    ofLoadThen: 'der Last in diesem Moment',
    ofDay: 'der letzten 24 Stunden',
    importing2: 'Import',
    exporting2: 'Export',
    tradeNote: 'Über null importiert Österreich netto, darunter exportiert es. Der Tagesverlauf folgt der Sonne: nachts und früh am Morgen hängt das Land am Import, mittags dreht die Photovoltaik die Bilanz um. Gezeigt sind physikalische Flüsse an den Kuppelstellen, keine Handelsgeschäfte: Strom fließt auch durch Österreich hindurch, ohne hier verbraucht zu werden.',
    balanceCol: 'Saldo',
    netBalance: 'Netto-Saldo',
    sourceAge: 'Datenquelle rund {h} alt',
    impMixTitle: 'Woraus der importierte Strom besteht',
    impMix24: 'Importmix · 24 Stunden',
    fossilNuclear: 'Fossil und Kernkraft',
    ofImports: 'des Imports über 24 Stunden',
    renDomestic: 'Erneuerbare · nur Inland',
    renSupply: 'Erneuerbare · mit Importen',
    ofSupply: 'der gesamten Versorgung',
    imported: 'Importiert',
    impMixNote: 'Gezeigt ist der Bruttoimport — die Summe aller Zuflüsse, also mehr als der Nettosaldo weiter oben. Geschätzt, nicht gemessen: Jeder Grenzfluss wird dem Erzeugungsmix des Herkunftslands zum selben Zeitpunkt zugerechnet. Das ist eine Zurechnung, keine Verfolgung — Transit bleibt unberücksichtigt. Strom aus Tschechien kann ursprünglich aus Polen stammen, deutscher Strom aus Frankreich. Gegengeprüft: Eine echte Flussverfolgung über 16 Länder ergibt für Fossil und Kernkraft zusammen 53,3 % statt 54,2 % — die Abweichung liegt bei rund einem Prozentpunkt. Das Skript dafür liegt im Repository.',
    moneyTitle: 'Was der Stromhandel gekostet hat · 24 Stunden',
    importCost: 'Kosten für Import',
    exportRevenue: 'Erlös aus Export',
    netCost: 'Netto',
    paidOut: 'geflossen',
    avgPaid: 'Ø bezahlt',
    avgEarned: 'Ø erlöst',
    runningTotal: 'Laufende Summe',
    moneyNote: 'Bewertet zum Day-Ahead-Börsenpreis, gerechnet auf die kommerziellen Handelsmengen — eine Größenordnung, keine Abrechnung: reale Verträge laufen nicht alle über die Börse. Import ist nicht automatisch schlecht: eingekaufter Strom ist oft billiger, als ein Gaskraftwerk hochzufahren. An diesem Tag lag der Ø-Importpreis allerdings über dem Ø-Exportpreis.',
    riverTitle: 'Flüsse · live',
    riverNote: 'Abfluss an je einem Pegel pro Fluss, dem jeweils untersten in Österreich. NW und MW sind die Referenzwerte der Hydrographie für Niedrig- und Mittelwasser an dieser Messstelle. Diese Werte kommen direkt aus eHYD und sind rund zwei Stunden aktueller als die Stromdaten oben.',
    belowNW: 'unter Niedrigwasser',
    nearNW: 'um Niedrigwasser',
    belowMW: 'unter Mittelwasser',
    aboveMW: 'über Mittelwasser',
    ofMean: 'des Mittelwassers',
    riverLive: 'Direkt von eHYD geladen',
    days7: '7 Tage',
    days: 'Tage',
    range7: '7 Tage',
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
    mixNote: 'Der äußere Ring zeigt die Quelle, der innere die Herkunft: inländische Erzeugung plus positive Nettoimporte ergeben 100 % des Stroms, der in diesem Moment zur Verfügung steht. Bei Nettoexport gibt es keinen Importanteil. Die schraffierten Segmente sind importiert und geschätzt — der Importmix ist eine Zurechnung (siehe unten) und wird hier anteilig auf den Nettoimport umgelegt. Pumpspeicher zählt als Erzeugung: die Energie zum Hochpumpen stammt aus einem früheren Zeitpunkt.',
    dayNote: 'Die Flächen sind die inländische Erzeugung, die kräftige Linie ist die Last. Liegt die Linie unter den Flächen, exportiert Österreich mehr, als es importiert.',
    domesticLabel: 'Inländische Erzeugung',
    importedLabel: 'Importiert · geschätzt',
    supplyTotal: 'Versorgung',
    sources: 'Erzeugung, Last, Grenzflüsse und Preis: <a href="https://api.energy-charts.info/">Energy-Charts</a> (Fraunhofer ISE), gespeist aus <a href="https://transparency.entsoe.eu/">ENTSO-E</a> und <a href="https://www.apg.at/">APG</a>. Abflussdaten: <a href="https://ehyd.gv.at">ehyd.gv.at</a>, Hydrographie Österreich, CC BY 4.0.',
    credit: 'Idee inspiriert von <a href="https://holadelej.hu/">holadelej.hu</a> (Ungarn) — eigenständig gebaut, ohne Übernahme von Gestaltung oder Text.',
    colophon: 'Quellcode auf <a href="' + REPO + '">GitHub</a> — offen und nachbaubar. Gebaut mit Unterstützung von <a href="https://claude.com/claude-code">Claude Code</a>.',
    err: 'Die Daten konnten nicht geladen werden.',
    hours: 'h', mins: 'min'
  },
  en: {
    title: 'Where does the power come from?',
    sub: "Austria's generation mix, daily shape and cross-border flows — from open data.",
    mixTitle: 'Where the power is coming from right now',
    dayTitle: 'Supply by source',
    cleanScoreTitle: 'Clean supply · 24 hours',
    compareTitle: 'Today in context',
    compareNote: 'The rolling latest 24-hour window is compared with the average of the six preceding 24-hour windows.',
    dependencyTitle: 'Import dependency · 7 days',
    dependencyNote: 'Positive net imports as a share of demand. During net export, import dependency is zero.',
    avgLoad: 'Average load',
    renewableDomestic: 'Renewable · domestic',
    importDependency: 'Import share',
    vsAverage: 'versus the 6-day average',
    seasonTitle: 'Across the year',
    seasonLatest: 'Latest day',
    seasonBetter: 'Greener than',
    ofYear: 'of the last 365 days',
    seasonMedian: 'Median for the year',
    seasonBest: 'Best day',
    seasonDaily: 'Daily value',
    seasonTrend: '30-day mean',
    seasonNote: 'Daily renewable share of load over the last 365 days, straight from Energy-Charts. The pale area is the daily value, the heavy line a trailing 30-day mean — single days swing too much to show a season. The most recent day may still be incomplete. Unlike the comparison above, this measures against a whole year rather than a week of weather.',
    balanceTitle: 'Energy balance · 24 hours',
    balanceGap: 'Unreconciled difference',
    balanceMean: 'Average absolute difference',
    balanceNote: 'Equation: domestic generation + commercial net imports − load − pumping demand. That accounts for most of the apparent midday surplus. The remaining difference is not a separate energy flow: generation, trading and load use different scopes and publication schedules, and grid losses also contribute. It is shown rather than artificially forced to zero.',
    storageTitle: 'Pumped storage and electricity price · 24 hours',
    storageOperation: 'Storage operation',
    price24: 'Day-ahead price',
    storageGenerating: 'generating',
    storagePumping: 'pumping',
    storageIdle: 'nearly idle',
    currentMode: 'Current operation',
    peakGeneration: 'Peak generation',
    peakPumping: 'Peak pumping',
    storageNote: 'Top: storage generation above zero, pumping demand below. Bottom: price on its own scale. Timing is informative, but by itself does not prove arbitrage or causation.',
    tradeTitle: 'Import and export',
    tradeShape: 'Balance · 24 hours',
    perCountry: 'By neighbour',
    peakImport: 'Peak import',
    peakExport: 'Peak export',
    timeImporting: 'Time as a net importer',
    ofLoadThen: 'of demand at that moment',
    ofDay: 'of the last 24 hours',
    importing2: 'Import',
    exporting2: 'Export',
    tradeNote: 'Above zero Austria is a net importer, below it a net exporter. The shape follows the sun: overnight and early morning the country leans on imports, and around midday solar flips the balance. These are physical flows across the interconnectors, not commercial trades: power also transits Austria without being consumed here.',
    balanceCol: 'Balance',
    netBalance: 'Net balance',
    sourceAge: 'source data about {h} old',
    impMixTitle: 'What the imported power is made of',
    impMix24: 'Import mix · 24 hours',
    fossilNuclear: 'Fossil and nuclear',
    ofImports: 'of imports over 24 hours',
    renDomestic: 'Renewable · domestic only',
    renSupply: 'Renewable · including imports',
    ofSupply: 'of total supply',
    imported: 'Imported',
    impMixNote: 'This shows gross imports — the sum of all inflows, so more than the net balance above. Estimated, not measured: each border flow is attributed to the exporting country\'s generation mix at the same moment. That is attribution, not tracing — transit is not accounted for. Power imported from Czechia may have originated in Poland, and German power in France. Cross-checked: proper flow-tracing across 16 countries puts fossil and nuclear together at 53.3 % rather than 54.2 % — a gap of about one percentage point. The script for that is in the repository.',
    moneyTitle: 'What the power trade cost · 24 hours',
    importCost: 'Paid for imports',
    exportRevenue: 'Earned from exports',
    netCost: 'Net',
    paidOut: 'out',
    avgPaid: 'avg paid',
    avgEarned: 'avg earned',
    runningTotal: 'Running total',
    moneyNote: 'Valued at the day-ahead exchange price against commercial trade volumes — an order of magnitude, not a settlement: real contracts do not all go through the exchange. Importing is not automatically bad, since bought power is often cheaper than firing up a gas plant. On this day, though, the average import price was above the average export price.',
    riverTitle: 'Rivers · live',
    riverNote: 'Discharge at one gauge per river, the most downstream one inside Austria. NW and MW are the hydrographic service\'s own reference values for low water and mean water at that gauge. These readings come straight from eHYD and are about two hours fresher than the electricity data above.',
    belowNW: 'below low water',
    nearNW: 'around low water',
    belowMW: 'below mean water',
    aboveMW: 'above mean water',
    ofMean: 'of mean water',
    riverLive: 'Loaded directly from eHYD',
    days7: '7 days',
    days: 'days',
    range7: '7 days',
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
    mixNote: 'The outer ring is the source, the inner ring the origin: domestic generation plus positive net imports make up 100% of the electricity available at that moment. During net export, the import share is zero. Hatched segments are imported and estimated — the import mix is an attribution (see below), scaled here onto the net import figure. Pumped storage counts as generation: the energy used to pump the water uphill came from an earlier moment.',
    dayNote: 'The areas are domestic generation; the heavy line is load. Where the line sits below the areas, Austria is exporting more than it imports.',
    domesticLabel: 'Domestic generation',
    importedLabel: 'Imported · estimated',
    supplyTotal: 'Supply',
    sources: 'Generation, load, cross-border flows and price: <a href="https://api.energy-charts.info/">Energy-Charts</a> (Fraunhofer ISE), fed from <a href="https://transparency.entsoe.eu/">ENTSO-E</a> and <a href="https://www.apg.at/">APG</a>.',
    credit: 'Concept inspired by <a href="https://holadelej.hu/">holadelej.hu</a> (Hungary) — built independently, with no design or copy taken from it.',
    colophon: 'Source on <a href="' + REPO + '">GitHub</a> — open, and rebuildable. Built with the help of <a href="https://claude.com/claude-code">Claude Code</a>.',
    err: 'The data could not be loaded.',
    hours: 'h', mins: 'min'
  }
};

let LANG = (localStorage.getItem('lang') || (navigator.language || '').slice(0, 2)) === 'en' ? 'en' : 'de';
let DATA = null;
let DAY_RANGE = 'day';
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

// Native tooltip on a shape, and the accessible name a screen reader reads.
const svgTitle = (node, text) => {
  const title = svgEl('title', {});
  title.textContent = text;
  node.append(title);
  return node;
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

function renderPanelStamp(id, timestamp) {
  const node = document.getElementById(id);
  if (!node || !timestamp) return;
  const generated = Date.parse(DATA.generatedAt) / 1000;
  const ageMinutes = Number.isFinite(generated) ? Math.max(0, Math.round((generated - timestamp) / 60)) : 0;
  const age = ageMinutes >= 90
    ? `${Math.floor(ageMinutes / 60)} ${t('hours')} ${ageMinutes % 60} ${t('mins')}`
    : `${ageMinutes} ${t('mins')}`;
  node.textContent = '';
  node.append(el('span', 'dot'), document.createTextNode(
    `${t('asOf')} ${dateFmt().format(new Date(timestamp * 1000))} · ${t('sourceAge').replace('{h}', age)}`));
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

/* The donut. Two rings on one total: the outer one is the source, the inner
   one is whether that source stood in Austria. Imported segments are hatched
   rather than given their own hues — they reuse the source colours, and the
   texture is what says "this came over a border, and it is an estimate". */

// Angles run clockwise from twelve o'clock, so the ring reads like a clock.
const polar = (cx, cy, r, a) => [cx + r * Math.sin(a), cy - r * Math.cos(a)];

function ringPath(cx, cy, rOuter, rInner, a0, a1) {
  const [x0, y0] = polar(cx, cy, rOuter, a0);
  const [x1, y1] = polar(cx, cy, rOuter, a1);
  const [x2, y2] = polar(cx, cy, rInner, a1);
  const [x3, y3] = polar(cx, cy, rInner, a0);
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${x0},${y0}A${rOuter},${rOuter} 0 ${large} 1 ${x1},${y1}`
    + `L${x2},${y2}A${rInner},${rInner} 0 ${large} 0 ${x3},${y3}Z`;
}

// A segment covering the whole circle has no arc endpoints to draw between,
// so it becomes a stroked circle instead. Happens on the inner ring whenever
// Austria is a net exporter and the whole supply is domestic.
function ringSegment(cx, cy, rOuter, rInner, a0, a1, fill) {
  if (a1 - a0 >= Math.PI * 2 - 1e-6) {
    return svgEl('circle', {
      cx, cy, r: (rOuter + rInner) / 2, fill: 'none',
      stroke: fill, 'stroke-width': rOuter - rInner,
    });
  }
  return svgEl('path', {
    d: ringPath(cx, cy, rOuter, rInner, a0, a1), fill,
    stroke: 'var(--surface)', 'stroke-width': 2, 'stroke-linejoin': 'round',
  });
}

function hatchPattern(key) {
  const p = svgEl('pattern', {
    id: `hatch-${key}`, width: 8, height: 8,
    patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)',
  });
  p.append(svgEl('rect', { width: 8, height: 8, fill: `var(--${key})` }));
  p.append(svgEl('rect', { width: 3, height: 8, fill: 'var(--surface)', 'fill-opacity': 0.75 }));
  return p;
}

function renderMix() {
  const mix = DATA.supplyMix;
  if (!mix) return;

  const domestic = ORDER.map(k => mix.domestic.find(g => g.key === k)).filter(Boolean);
  const imported = IMP_ORDER.map(k => mix.imported.find(g => g.key === k))
    .filter(Boolean)
    .concat(mix.imported.filter(g => !IMP_ORDER.includes(g.key)));
  const segments = [
    ...domestic.map(g => ({ ...g, imported: false })),
    ...imported.map(g => ({ ...g, imported: true })),
  ];

  drawMixDonut(mix, segments);

  const leg = document.getElementById('legend');
  const impLeg = document.getElementById('importedLegend');
  leg.textContent = '';
  impLeg.textContent = '';

  // Legends follow ring order, not size rank, so the eye can travel between
  // the two. The percentage carries the ranking.
  for (const s of segments) {
    const r = el('div', 'row');
    const sw = el('span', s.imported ? 'sw imported' : 'sw');
    sw.style.backgroundColor = `var(--${s.key})`;
    r.append(sw, el('span', 'nm', label(s)),
      el('span', 'mw', `${nf(s.mw)} MW`),
      el('span', 'pc', `${nf(s.pct, 1)} %`));
    (s.imported ? impLeg : leg).append(r);
  }

  const hasImports = imported.length > 0;
  document.getElementById('importedHead').hidden = !hasImports;
  impLeg.hidden = !hasImports;

  const row = s => `<tr><td>${label(s)}${s.imported ? ` · ${t('imported')}` : ''}</td>` +
    `<td class="n">${nf(s.mw)}</td><td class="n">${nf(s.pct, 1)}</td></tr>`;
  document.getElementById('mixTable').innerHTML =
    `<table><caption>${t('mixTitle')} — ${dateFmt().format(new Date(DATA.dataAt * 1000))}</caption>
     <thead><tr><th>${t('source')}</th><th class="n">MW</th><th class="n">${t('share')} %</th></tr></thead>
     <tbody>${[...segments].sort((a, b) => b.mw - a.mw).map(row).join('')}
     <tr><td><strong>${t('total')}</strong></td><td class="n"><strong>${nf(mix.supplyMw)}</strong></td><td class="n">100</td></tr></tbody></table>`;
}

function drawMixDonut(mix, segments) {
  const svg = document.getElementById('mixDonut');
  const S = 320, c = S / 2;
  svg.setAttribute('viewBox', `0 0 ${S} ${S}`);
  svg.textContent = '';
  svg.setAttribute('aria-label',
    `${t('mixTitle')} — ${segments.map(s => `${label(s)} ${nf(s.pct, 1)} %`).join(', ')}`);

  const defs = svgEl('defs', {});
  for (const s of segments) if (s.imported) defs.append(hatchPattern(s.key));
  svg.append(defs);

  // Each share is rounded on its own, so they sum to 100 only to within a
  // rounding error. Normalising here keeps the ring from overshooting itself.
  const sum = segments.reduce((a, s) => a + s.pct, 0) || 100;
  const TAU = Math.PI * 2;
  let a = 0;
  for (const s of segments) {
    const span = s.pct / sum * TAU;
    if (span <= 0) continue;
    const fill = s.imported ? `url(#hatch-${s.key})` : `var(--${s.key})`;
    const seg = ringSegment(c, c, 150, 108, a, a + span, fill);
    svgTitle(seg, `${label(s)}${s.imported ? ` · ${t('imported')}` : ''} — ${nf(s.mw)} MW · ${nf(s.pct, 1)} %`);
    svg.append(seg);
    a += span;
  }

  // Inner ring: the same total, split only by which side of the border it
  // was generated on.
  a = 0;
  const inner = (mix.domesticPct + mix.importedPct) || 100;
  for (const [pct, color, name] of [
    [mix.domesticPct, 'var(--ink-2)', t('domesticLabel')],
    [mix.importedPct, 'var(--import)', t('importing2')],
  ]) {
    const span = pct / inner * TAU;
    if (span <= 0) continue;
    const seg = ringSegment(c, c, 96, 84, a, a + span, color);
    svgTitle(seg, `${name} — ${nf(pct, 1)} %`);
    svg.append(seg);
    a += span;
  }

  const total = svgEl('text', { class: 'donutv', x: c, y: c + 4, 'text-anchor': 'middle' });
  total.textContent = nf(mix.supplyMw);
  const unit = svgEl('text', { class: 'donutk', x: c, y: c + 26, 'text-anchor': 'middle' });
  unit.textContent = `MW · ${t('supplyTotal')}`;
  svg.append(total, unit);

  const split = document.getElementById('donutSplit');
  split.textContent = '';
  for (const [pct, color, name] of [
    [mix.domesticPct, 'var(--ink-2)', t('domesticLabel')],
    [mix.importedPct, 'var(--import)', t('importing2')],
  ]) {
    if (pct <= 0) continue;
    const item = el('span', 'splititem');
    const sw = el('i');
    sw.style.background = color;
    item.append(sw, document.createTextNode(`${name} ${nf(pct, 1)} %`));
    split.append(item);
  }
}

function renderCleanScore() {
  const box = document.getElementById('cleanScore');
  box.textContent = '';
  const im = DATA.importMix;
  if (!im) return;
  const stats = [
    { k: t('renDomestic'), v: im.renewableShareDomestic },
    { k: t('renSupply'), v: im.renewableShareSupply },
    { k: t('fossilNuclear'), v: im.fossilNuclearPct, d: t('ofImports') },
  ];
  for (const s of stats) {
    if (s.v == null) continue;
    const card = el('div', 'tstat');
    card.append(el('div', 'k', s.k), el('div', 'v', `${nf(s.v, 1)}<small>%</small>`));
    if (s.d) card.append(el('div', 'd', s.d));
    box.append(card);
  }
}

/* ── 24 h stacked area + load line ────────────────────────────────────── */

const PAD = { t: 14, r: 14, b: 26, l: 46 };

function renderDay() {
  const svg = document.getElementById('dayChart');
  const source = DAY_RANGE === 'week' && DATA.history ? DATA.history : DATA.day;
  const groups = DAY_RANGE === 'week' && DATA.history
    ? ORDER.map(k => DATA.history.groups.find(g => g.key === k)).filter(Boolean)
    : orderedGroups();
  const times = source.t;
  const N = times.length;
  if (!N) return;

  const W = Math.max(svg.clientWidth || svg.parentElement.clientWidth || 720, 320);
  const H = 300;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('height', H);
  svg.textContent = '';

  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;

  // Net imports ride on top of the domestic stack, so the bands add up to
  // total supply. Only the positive side: when Austria is exporting there is
  // nothing coming in, and the load line already sits below the stack there.
  const imports = source.netImport.map(v => Math.max(v, 0));
  const bands = [...groups.map(g => ({
    key: g.key, name: label(g), series: g.series,
  })), { key: 'import', name: t('importing2'), series: imports }];

  const totals = times.map((_, i) => bands.reduce((a, b) => a + b.series[i], 0));
  const peak = Math.max(...totals, ...source.load);
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
  for (const b of bands) {
    const upper = base.map((v, i) => v + b.series[i]);
    if (upper.every((v, i) => v - base[i] < 0.05)) { base = upper; continue; }
    const d = upper.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('') +
      base.map((v, i) => `L${x(N - 1 - i)},${y(base[N - 1 - i])}`).join('') + 'Z';
    svg.append(svgEl('path', { d, fill: `var(--${b.key})`, stroke: 'var(--surface)', 'stroke-width': 2, 'stroke-linejoin': 'round' }));
    base = upper;
  }

  // load line
  svg.append(svgEl('path', {
    class: 'loadline',
    d: source.load.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('')
  }));

  // hour ticks
  const fmt = DAY_RANGE === 'week'
    ? new Intl.DateTimeFormat(LANG === 'de' ? 'de-AT' : 'en-GB',
      { weekday: 'short', day: 'numeric', timeZone: DATA.timezone || 'Europe/Vienna' })
    : clockFmt();
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
  for (const b of [...bands].reverse()) {
    const r = el('div', 'row');
    const sw = el('span', 'sw');
    sw.style.background = `var(--${b.key})`;
    r.append(sw, el('span', 'nm', b.name));
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

    const tot = totals[i] || 1;
    const rows = [...bands].reverse().filter(b => b.series[i] > 0.05).map(b =>
      `<div class="r"><span class="sw" style="background:var(--${b.key})"></span>${b.name}<span class="v">${nf(b.series[i])} MW<em>${nf(b.series[i] / tot * 100, 1)} %</em></span></div>`).join('');
    tip.innerHTML = `<div class="t">${dateFmt().format(new Date(times[i] * 1000))}</div>${rows}
      <div class="r tot"><span class="sw" style="background:var(--ink)"></span>${t('load')}<span class="v">${nf(source.load[i])} MW</span></div>`;
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

function renderRangeButtons() {
  for (const button of document.querySelectorAll('#rangeButtons button')) {
    button.classList.toggle('active', button.dataset.range === DAY_RANGE);
  }
}

function renderComparison() {
  const c = DATA.comparison;
  const section = document.getElementById('compareSection');
  if (!c) { section.hidden = true; return; }
  section.hidden = false;
  const metrics = [
    { key: 'avgLoad', label: t('avgLoad'), unit: 'MW', digits: 0, goodDirection: 0 },
    { key: 'renewablePct', label: t('renewableDomestic'), unit: '%', digits: 1, goodDirection: 1 },
    { key: 'importShare', label: t('importDependency'), unit: '%', digits: 1, goodDirection: -1 },
  ];
  const box = document.getElementById('compareGrid');
  box.textContent = '';
  for (const m of metrics) {
    const now = c.current[m.key], base = c.baseline[m.key];
    const delta = now - base;
    const sentiment = m.goodDirection === 0 || delta === 0 ? ''
      : delta * m.goodDirection > 0 ? 'good' : 'bad';
    const card = el('div', 'comparecard');
    card.append(el('div', 'k', m.label),
      el('div', 'v', `${nf(now, m.digits)}<small>${m.unit}</small>`),
      el('div', `delta ${sentiment}`,
        `${delta > 0 ? '↑' : delta < 0 ? '↓' : '→'} ${nf(Math.abs(delta), m.digits)} ${m.unit}`),
      el('div', 'base', `${nf(base, m.digits)} ${m.unit} · ${t('vsAverage')}`));
    box.append(card);
  }
}

function renderDependency() {
  const h = DATA.history;
  const section = document.getElementById('dependencySection');
  if (!h || h.t.length < 2) { section.hidden = true; return; }
  section.hidden = false;
  const values = h.importShare;
  const svg = document.getElementById('dependencyChart');
  const W = Math.max(svg.clientWidth || svg.parentElement.clientWidth || 720, 320), H = 220;
  const P = { t: 20, r: 14, b: 26, l: 42 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const top = Math.max(10, Math.ceil(Math.max(...values) / 10) * 10);
  const x = i => P.l + i / (values.length - 1) * iw;
  const y = v => P.t + ih - v / top * ih;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('height', H); svg.textContent = '';
  for (let v = 0; v <= top; v += 10) {
    svg.append(svgEl('line', { class: v ? 'gridline' : 'axisline', x1: P.l, x2: W - P.r, y1: y(v), y2: y(v) }));
    const lab = svgEl('text', { x: P.l - 7, y: y(v) + 4, 'text-anchor': 'end' });
    lab.textContent = `${v}${v === top ? ' %' : ''}`; svg.append(lab);
  }
  const line = values.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
  svg.append(svgEl('path', { d: `${line}L${x(values.length - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: 'var(--import)', 'fill-opacity': .14 }));
  svg.append(svgEl('path', { d: line, fill: 'none', stroke: 'var(--import)', 'stroke-width': 2 }));
  const dayFmt = new Intl.DateTimeFormat(LANG === 'de' ? 'de-AT' : 'en-GB', { weekday: 'short', day: 'numeric', timeZone: DATA.timezone });
  const every = Math.max(1, Math.round(values.length / 7));
  h.t.forEach((ts, i) => { if (i % every && i !== values.length - 1) return; const lab = svgEl('text', { x: x(i), y: H - 8, 'text-anchor': i === values.length - 1 ? 'end' : 'middle' }); lab.textContent = dayFmt.format(new Date(ts * 1000)); svg.append(lab); });
  const cursor = svgEl('line', { class: 'cursor', y1: P.t, y2: P.t + ih, opacity: 0 }); svg.append(cursor);
  const tip = document.getElementById('dependencyTip'), wrap = svg.closest('.plotwrap');
  const show = ev => { const b = svg.getBoundingClientRect(); let i = Math.round((((ev.clientX - b.left) / b.width * W) - P.l) / iw * (values.length - 1)); i = Math.max(0, Math.min(values.length - 1, i)); cursor.setAttribute('x1', x(i)); cursor.setAttribute('x2', x(i)); cursor.setAttribute('opacity', 1); tip.innerHTML = `<div class="t">${dateFmt().format(new Date(h.t[i] * 1000))}</div><div class="r tot"><span class="sw" style="background:var(--import)"></span>${t('importDependency')}<span class="v">${nf(values[i], 1)} %</span></div>`; tip.classList.add('on'); const wb = wrap.getBoundingClientRect(); tip.style.left = Math.min(Math.max(x(i) / W * b.width + b.left - wb.left + 12, 0), wb.width - tip.offsetWidth) + 'px'; tip.style.top = '5px'; };
  svg.addEventListener('pointermove', show); svg.addEventListener('pointerdown', show); svg.addEventListener('pointerleave', () => { tip.classList.remove('on'); cursor.setAttribute('opacity', 0); });
}

function drawLineChart(svg, times, values, color, unit) {
  if (!times.length || times.length !== values.length) return;
  const W = Math.max(svg.clientWidth || svg.parentElement.clientWidth || 420, 300), H = 170;
  const P = { t: 12, r: 12, b: 24, l: 42 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const rawLo = Math.min(0, ...values), rawHi = Math.max(1, ...values);
  const step = niceStep(rawHi - rawLo || 1, 4);
  const lo = Math.floor(rawLo / step) * step, hi = Math.ceil(rawHi / step) * step;
  const x = i => P.l + i / Math.max(1, values.length - 1) * iw;
  const y = v => P.t + ih - (v - lo) / Math.max(step, hi - lo) * ih;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('height', H); svg.textContent = '';
  for (let v = lo; v <= hi + step / 2; v += step) {
    svg.append(svgEl('line', { class: Math.abs(v) < step / 1000 ? 'axisline' : 'gridline', x1: P.l, x2: W - P.r, y1: y(v), y2: y(v) }));
    const lab = svgEl('text', { x: P.l - 7, y: y(v) + 4, 'text-anchor': 'end' }); lab.textContent = nf(v); svg.append(lab);
  }
  const u = svgEl('text', { x: P.l - 7, y: P.t - 2, 'text-anchor': 'end' }); u.textContent = unit; svg.append(u);
  const line = values.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
  svg.append(svgEl('path', { d: `${line}L${x(values.length - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: color, 'fill-opacity': .13 }));
  svg.append(svgEl('path', { d: line, fill: 'none', stroke: color, 'stroke-width': 2 }));
  const fmt = clockFmt(), every = Math.max(1, Math.round(values.length / 4));
  times.forEach((ts, i) => { if (i % every && i !== values.length - 1) return; const lab = svgEl('text', { x: x(i), y: H - 7, 'text-anchor': i === values.length - 1 ? 'end' : i === 0 ? 'start' : 'middle' }); lab.textContent = fmt.format(new Date(ts * 1000)); svg.append(lab); });
}

/* ── a year of daily renewable share ──────────────────────────────────── */

function renderSeason() {
  const s = DATA.season, section = document.getElementById('seasonSection');
  if (!s || !s.values || s.values.length < 60) { section.hidden = true; return; }
  section.hidden = false;

  const dayFmt = new Intl.DateTimeFormat(LANG === 'de' ? 'de-AT' : 'en-GB',
    { day: 'numeric', month: 'short', year: 'numeric', timeZone: DATA.timezone || 'Europe/Vienna' });

  const stats = [
    { k: t('seasonLatest'), v: `${nf(s.latest, 1)}<small>%</small>`,
      d: dayFmt.format(new Date(s.latestAt * 1000)) },
    { k: t('seasonMedian'), v: `${nf(s.median, 1)}<small>%</small>` },
    { k: t('seasonBest'), v: `${nf(s.best.value, 1)}<small>%</small>`,
      d: dayFmt.format(new Date(s.best.at * 1000)) },
  ];
  if (s.percentile != null) {
    stats.splice(1, 0, { k: t('seasonBetter'), v: `${nf(s.percentile, 0)}<small>%</small>`,
      d: t('ofYear') });
  }
  const box = document.getElementById('seasonStats');
  box.textContent = '';
  for (const item of stats) {
    const card = el('div', 'tstat');
    card.append(el('div', 'k', item.k), el('div', 'v', item.v));
    if (item.d) card.append(el('div', 'd', item.d));
    box.append(card);
  }

  drawSeason(s);
}

function drawSeason(s) {
  const svg = document.getElementById('seasonChart');
  const N = s.values.length;
  const W = Math.max(svg.clientWidth || svg.parentElement.clientWidth || 720, 320), H = 240;
  const P = { t: 22, r: 14, b: 26, l: 42 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const top = Math.min(100, Math.max(20, Math.ceil(Math.max(...s.values) / 20) * 20));
  const x = i => P.l + i / (N - 1) * iw;
  const y = v => P.t + ih - v / top * ih;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('height', H);
  svg.textContent = '';
  svg.setAttribute('aria-label', `${t('seasonTitle')} — ${t('renew')}, ${s.days} ${t('days')}`);

  for (let v = 0; v <= top; v += 20) {
    svg.append(svgEl('line', { class: v ? 'gridline' : 'axisline', x1: P.l, x2: W - P.r, y1: y(v), y2: y(v) }));
    const lab = svgEl('text', { x: P.l - 7, y: y(v) + 4, 'text-anchor': 'end' });
    lab.textContent = `${v}${v === top ? ' %' : ''}`;
    svg.append(lab);
  }

  // Daily values sit behind as texture; the trailing mean is the line the
  // eye should follow.
  const daily = s.values.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
  svg.append(svgEl('path', {
    d: `${daily}L${x(N - 1)},${y(0)}L${x(0)},${y(0)}Z`,
    fill: 'var(--wind)', 'fill-opacity': 0.16,
  }));
  svg.append(svgEl('path', {
    d: daily, fill: 'none', stroke: 'var(--wind)', 'stroke-width': 1,
    'stroke-opacity': 0.45,
  }));

  const at = new Map(s.t.map((ts, i) => [ts, i]));
  const trend = s.trend.t.map((ts, i) =>
    `${i ? 'L' : 'M'}${x(at.get(ts))},${y(s.trend.v[i])}`).join('');
  svg.append(svgEl('path', {
    d: trend, fill: 'none', stroke: 'var(--wind)', 'stroke-width': 2.5,
    'stroke-linejoin': 'round',
  }));

  // Where today sits in that year.
  svg.append(svgEl('circle', { cx: x(N - 1), cy: y(s.latest), r: 4.5, fill: 'var(--ink)' }));

  const monthFmt = new Intl.DateTimeFormat(LANG === 'de' ? 'de-AT' : 'en-GB',
    { month: 'short', timeZone: DATA.timezone || 'Europe/Vienna' });
  let lastMonth = null;
  s.t.forEach((ts, i) => {
    const d = new Date(ts * 1000);
    const month = d.getUTCMonth();
    if (month === lastMonth) return;
    lastMonth = month;
    if (i < N * 0.02 || i > N * 0.97) return;
    svg.append(svgEl('line', { class: 'gridline', x1: x(i), x2: x(i), y1: P.t, y2: P.t + ih, 'stroke-dasharray': '2 4' }));
    const lab = svgEl('text', { x: x(i), y: H - 8, 'text-anchor': 'middle' });
    lab.textContent = monthFmt.format(d);
    svg.append(lab);
  });

  const cursor = svgEl('line', { class: 'cursor', y1: P.t, y2: P.t + ih, opacity: 0 });
  svg.append(cursor);
  const tip = document.getElementById('seasonTip'), wrap = svg.closest('.plotwrap');
  const dayFmt = new Intl.DateTimeFormat(LANG === 'de' ? 'de-AT' : 'en-GB',
    { day: 'numeric', month: 'short', year: 'numeric', timeZone: DATA.timezone || 'Europe/Vienna' });
  const byTrend = new Map(s.trend.t.map((ts, i) => [ts, s.trend.v[i]]));
  const show = ev => {
    const b = svg.getBoundingClientRect();
    let i = Math.round((((ev.clientX - b.left) / b.width * W) - P.l) / iw * (N - 1));
    i = Math.max(0, Math.min(N - 1, i));
    cursor.setAttribute('x1', x(i));
    cursor.setAttribute('x2', x(i));
    cursor.setAttribute('opacity', 1);
    const mean = byTrend.get(s.t[i]);
    tip.innerHTML = `<div class="t">${dayFmt.format(new Date(s.t[i] * 1000))}</div>
      <div class="r"><span class="sw" style="background:var(--wind)"></span>${t('seasonDaily')}<span class="v">${nf(s.values[i], 1)} %</span></div>` +
      (mean == null ? '' : `<div class="r tot"><span class="sw" style="background:var(--wind)"></span>${t('seasonTrend')}<span class="v">${nf(mean, 1)} %</span></div>`);
    tip.classList.add('on');
    const wb = wrap.getBoundingClientRect();
    tip.style.left = Math.min(Math.max(x(i) / W * b.width + b.left - wb.left + 12, 0), wb.width - tip.offsetWidth) + 'px';
    tip.style.top = '5px';
  };
  svg.addEventListener('pointermove', show);
  svg.addEventListener('pointerdown', show);
  svg.addEventListener('pointerleave', () => { tip.classList.remove('on'); cursor.setAttribute('opacity', 0); });
}

function renderBalance() {
  const b = DATA.balance, section = document.getElementById('balanceSection');
  if (!b || !b.series || b.series.length < 2) { section.hidden = true; return; }
  section.hidden = false;
  const equation = document.getElementById('balanceEquation');
  equation.textContent = '';
  const terms = [
    { label: t('generation'), value: b.generation },
    { op: b.netImport >= 0 ? '+' : '−', label: b.netImport >= 0 ? t('netImport') : t('netExport'), value: Math.abs(b.netImport) },
    { op: '−', label: t('load'), value: b.load },
    { op: '−', label: t('storagePumping'), value: b.pumping },
    { op: '=', label: t('balanceGap'), value: b.gap, gap: true },
  ];
  for (const term of terms) {
    if (term.op) equation.append(el('div', 'eqop', term.op));
    const card = el('div', `eqterm${term.gap ? ' gap' : ''}`);
    card.append(el('div', 'k', term.label), el('div', 'v', `${term.value > 0 && term.gap ? '+' : ''}${nf(term.value)}<small>MW</small>`));
    equation.append(card);
  }
  const mean = el('div', 'balanceMean', `${t('balanceMean')}: ${nf(b.meanAbsGap)} MW`);
  equation.append(mean);

  const svg = document.getElementById('balanceChart'), N = b.series.length;
  const W = Math.max(svg.clientWidth || svg.parentElement.clientWidth || 720, 320), H = 210;
  const P = { t: 24, r: 14, b: 26, l: 48 }, iw = W - P.l - P.r, ih = H - P.t - P.b;
  const mag = Math.max(...b.series.map(Math.abs), 100);
  const step = niceStep(mag, 4), top = Math.ceil(mag / step) * step;
  const x = i => P.l + i / (N - 1) * iw, y = v => P.t + ih / 2 - v / top * ih / 2;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('height', H); svg.textContent = '';
  for (let v = -top; v <= top; v += step) {
    svg.append(svgEl('line', { class: v === 0 ? 'axisline' : 'gridline', x1: P.l, x2: W - P.r, y1: y(v), y2: y(v) }));
    const lab = svgEl('text', { x: P.l - 7, y: y(v) + 4, 'text-anchor': 'end' }); lab.textContent = nf(v); svg.append(lab);
  }
  const u = svgEl('text', { x: P.l - 7, y: P.t - 9, 'text-anchor': 'end' }); u.textContent = 'MW'; svg.append(u);
  const line = b.series.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
  svg.append(svgEl('path', { d: `${line}L${x(N - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: 'var(--pumped)', 'fill-opacity': .16 }));
  svg.append(svgEl('path', { d: line, fill: 'none', stroke: 'var(--pumped)', 'stroke-width': 2 }));
  const fmt = clockFmt(), every = Math.max(1, Math.round(N / 8));
  b.t.forEach((ts, i) => { if (i % every && i !== N - 1) return; const lab = svgEl('text', { x: x(i), y: H - 7, 'text-anchor': i === N - 1 ? 'end' : i === 0 ? 'start' : 'middle' }); lab.textContent = fmt.format(new Date(ts * 1000)); svg.append(lab); });
  const cursor = svgEl('line', { class: 'cursor', y1: P.t, y2: P.t + ih, opacity: 0 }); svg.append(cursor);
  const tip = document.getElementById('balanceTip'), wrap = svg.closest('.plotwrap');
  const show = ev => { const rect = svg.getBoundingClientRect(); let i = Math.round((((ev.clientX - rect.left) / rect.width * W) - P.l) / iw * (N - 1)); i = Math.max(0, Math.min(N - 1, i)); cursor.setAttribute('x1', x(i)); cursor.setAttribute('x2', x(i)); cursor.setAttribute('opacity', 1); const v = b.series[i]; tip.innerHTML = `<div class="t">${dateFmt().format(new Date(b.t[i] * 1000))}</div><div class="r tot"><span class="sw" style="background:var(--pumped)"></span>${t('balanceGap')}<span class="v">${v > 0 ? '+' : ''}${nf(v)} MW</span></div>`; tip.classList.add('on'); const wb = wrap.getBoundingClientRect(); tip.style.left = Math.min(Math.max(x(i) / W * rect.width + rect.left - wb.left + 12, 0), wb.width - tip.offsetWidth) + 'px'; tip.style.top = '5px'; };
  svg.addEventListener('pointermove', show); svg.addEventListener('pointerdown', show); svg.addEventListener('pointerleave', () => { tip.classList.remove('on'); cursor.setAttribute('opacity', 0); });
}

function renderStorage() {
  const s = DATA.storage, section = document.getElementById('storageSection');
  if (!s || !s.t || s.t.length < 2) { section.hidden = true; return; }
  section.hidden = false;
  const mode = s.nowPumping > 10 ? `${t('storagePumping')} · ${nf(s.nowPumping)} MW`
    : s.nowGeneration > 10 ? `${t('storageGenerating')} · ${nf(s.nowGeneration)} MW` : t('storageIdle');
  const stats = [
    { k: t('currentMode'), v: mode },
    { k: t('peakGeneration'), v: `${nf(s.peakGeneration)}<small>MW</small>` },
    { k: t('peakPumping'), v: `${nf(s.peakPumping)}<small>MW</small>` },
  ];
  const box = document.getElementById('storageStats'); box.textContent = '';
  for (const item of stats) { const card = el('div', 'tstat'); card.append(el('div', 'k', item.k), el('div', 'v', item.v)); box.append(card); }

  const svg = document.getElementById('storageChart'), N = s.t.length;
  const W = Math.max(svg.clientWidth || svg.parentElement.clientWidth || 720, 320), H = 230;
  const P = { t: 24, r: 14, b: 26, l: 48 }, iw = W - P.l - P.r, ih = H - P.t - P.b;
  const mag = Math.max(...s.generation, ...s.pumping, 100), step = niceStep(mag, 4), top = Math.ceil(mag / step) * step;
  const x = i => P.l + i / (N - 1) * iw, y = v => P.t + ih / 2 - v / top * ih / 2;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('height', H); svg.textContent = '';
  for (let v = -top; v <= top; v += step) { svg.append(svgEl('line', { class: v === 0 ? 'axisline' : 'gridline', x1: P.l, x2: W - P.r, y1: y(v), y2: y(v) })); const lab = svgEl('text', { x: P.l - 7, y: y(v) + 4, 'text-anchor': 'end' }); lab.textContent = nf(v); svg.append(lab); }
  const u = svgEl('text', { x: P.l - 7, y: P.t - 9, 'text-anchor': 'end' }); u.textContent = 'MW'; svg.append(u);
  const genLine = s.generation.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
  const pumpLine = s.pumping.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(-v)}`).join('');
  svg.append(svgEl('path', { d: `${genLine}L${x(N - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: 'var(--export)', 'fill-opacity': .75 }));
  svg.append(svgEl('path', { d: `${pumpLine}L${x(N - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: 'var(--import)', 'fill-opacity': .75 }));
  const fmt = clockFmt(), every = Math.max(1, Math.round(N / 8));
  s.t.forEach((ts, i) => { if (i % every && i !== N - 1) return; const lab = svgEl('text', { x: x(i), y: H - 7, 'text-anchor': i === N - 1 ? 'end' : i === 0 ? 'start' : 'middle' }); lab.textContent = fmt.format(new Date(ts * 1000)); svg.append(lab); });
  const cursor = svgEl('line', { class: 'cursor', y1: P.t, y2: P.t + ih, opacity: 0 }); svg.append(cursor);
  const tip = document.getElementById('storageTip'), wrap = svg.closest('.plotwrap');
  const show = ev => { const rect = svg.getBoundingClientRect(); let i = Math.round((((ev.clientX - rect.left) / rect.width * W) - P.l) / iw * (N - 1)); i = Math.max(0, Math.min(N - 1, i)); cursor.setAttribute('x1', x(i)); cursor.setAttribute('x2', x(i)); cursor.setAttribute('opacity', 1); tip.innerHTML = `<div class="t">${dateFmt().format(new Date(s.t[i] * 1000))}</div><div class="r"><span class="sw" style="background:var(--export)"></span>${t('storageGenerating')}<span class="v">${nf(s.generation[i])} MW</span></div><div class="r"><span class="sw" style="background:var(--import)"></span>${t('storagePumping')}<span class="v">${nf(s.pumping[i])} MW</span></div><div class="r tot"><span class="sw" style="background:var(--hydro)"></span>${t('price')}<span class="v">${nf(s.price[i], 1)} €/MWh</span></div>`; tip.classList.add('on'); const wb = wrap.getBoundingClientRect(); tip.style.left = Math.min(Math.max(x(i) / W * rect.width + rect.left - wb.left + 12, 0), wb.width - tip.offsetWidth) + 'px'; tip.style.top = '5px'; };
  svg.addEventListener('pointermove', show); svg.addEventListener('pointerdown', show); svg.addEventListener('pointerleave', () => { tip.classList.remove('on'); cursor.setAttribute('opacity', 0); });
  drawLineChart(document.getElementById('storagePriceChart'), s.t, s.price, 'var(--hydro)', '€/MWh');
}

/* ── what the imports are made of ─────────────────────────────────────── */

// Stack order for the import mix, colour-validated as this sequence.
// Nuclear only ever appears here — Austria has none of its own.
const IMP_ORDER = ['hydro', 'fossil', 'wind', 'solar', 'nuclear', 'other'];

function renderImportMix() {
  const sec = document.getElementById('impMixSection');
  const im = DATA.importMix;
  if (!im || !im.groups || !im.groups.length) { sec.hidden = true; return; }
  sec.hidden = false;

  const groups = IMP_ORDER.map(k => im.groups.find(g => g.key === k)).filter(Boolean);

  const bar = document.getElementById('impMixBar');
  const leg = document.getElementById('impMixLegend');
  bar.textContent = '';
  leg.textContent = '';
  for (const g of groups) {
    if (g.pct <= 0) continue;
    const sp = el('span');
    sp.style.flex = `${g.pct} 1 0`;
    sp.style.background = `var(--${g.key})`;
    sp.title = `${label(g)} · ${nf(g.pct, 1)} %`;
    bar.append(sp);
  }
  for (const g of groups) {
    const r = el('div', 'row');
    const sw = el('span', 'sw');
    sw.style.background = `var(--${g.key})`;
    r.append(sw, el('span', 'nm', label(g)),
      el('span', 'mw', `${nf(g.mw)} MW`),
      el('span', 'pc', `${nf(g.pct, 1)} %`));
    leg.append(r);
  }

  const rows = groups.map(g =>
    `<tr><td>${label(g)}</td><td class="n">${nf(g.mw)}</td><td class="n">${nf(g.pct, 1)}</td></tr>`).join('');
  document.getElementById('impMixTable').innerHTML =
    `<table><caption>${t('impMixTitle')}</caption>
     <thead><tr><th>${t('source')}</th><th class="n">MW</th><th class="n">${t('share')} %</th></tr></thead>
     <tbody>${rows}</tbody></table>`;

  drawImportMixChart(groups, im);
}

function drawImportMixChart(groups, im) {
  const svg = document.getElementById('impMixChart');
  const N = im.t.length;
  if (N < 2) return;

  const W = Math.max(svg.clientWidth || svg.parentElement.clientWidth || 720, 320);
  const H = 250;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('height', H);
  svg.textContent = '';
  svg.setAttribute('aria-label', `${t('impMix24')} — ${groups.map(g => label(g)).join(', ')}`);

  const P = { t: 26, r: PAD.r, b: PAD.b, l: PAD.l };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const totals = im.t.map((_, i) => groups.reduce((a, g) => a + g.series[i], 0));
  const step = niceStep(Math.max(...totals, 1), 4);
  const top = Math.max(Math.ceil(Math.max(...totals) / step) * step, step);

  const x = i => P.l + (i / (N - 1)) * iw;
  const y = v => P.t + ih - (v / top) * ih;

  for (let v = 0; v <= top + step / 2; v += step) {
    svg.append(svgEl('line', {
      class: v === 0 ? 'axisline' : 'gridline',
      x1: P.l, x2: W - P.r, y1: y(v), y2: y(v),
    }));
    const lab = svgEl('text', { x: P.l - 8, y: y(v) + 4, 'text-anchor': 'end' });
    lab.textContent = v === 0 ? '0' : nf(v);
    svg.append(lab);
  }
  const unit = svgEl('text', { x: P.l - 8, y: P.t - 10, 'text-anchor': 'end' });
  unit.textContent = 'MW';
  svg.append(unit);

  let base = new Array(N).fill(0);
  for (const g of groups) {
    const upper = base.map((b, i) => b + g.series[i]);
    if (upper.every((v, i) => v - base[i] < 0.05)) { base = upper; continue; }
    const d = upper.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('')
      + base.map((_, i) => `L${x(N - 1 - i)},${y(base[N - 1 - i])}`).join('') + 'Z';
    svg.append(svgEl('path', {
      d, fill: `var(--${g.key})`, stroke: 'var(--surface)',
      'stroke-width': 2, 'stroke-linejoin': 'round',
    }));
    base = upper;
  }

  const fmt = clockFmt();
  const every = Math.max(1, Math.round(N / 8));
  im.t.forEach((ts, i) => {
    if (i % every && i !== N - 1) return;
    const lab = svgEl('text', {
      x: x(i), y: H - 8,
      'text-anchor': i === N - 1 ? 'end' : i === 0 ? 'start' : 'middle',
    });
    lab.textContent = fmt.format(new Date(ts * 1000));
    svg.append(lab);
  });

  const cursor = svgEl('line', { class: 'cursor', y1: P.t, y2: P.t + ih, opacity: 0 });
  svg.append(cursor);

  const tip = document.getElementById('impMixTip');
  const wrap = svg.closest('.plotwrap');
  const show = ev => {
    const b = svg.getBoundingClientRect();
    const px = (ev.clientX - b.left) / b.width * W;
    let i = Math.round((px - P.l) / iw * (N - 1));
    i = Math.max(0, Math.min(N - 1, i));
    cursor.setAttribute('x1', x(i));
    cursor.setAttribute('x2', x(i));
    cursor.setAttribute('opacity', 1);
    const tot = totals[i] || 1;
    const rows = [...groups].reverse().filter(g => g.series[i] > 0.05).map(g =>
      `<div class="r"><span class="sw" style="background:var(--${g.key})"></span>${label(g)}<span class="v">${nf(g.series[i])} MW<em>${nf(g.series[i] / tot * 100, 1)} %</em></span></div>`).join('');
    tip.innerHTML = `<div class="t">${dateFmt().format(new Date(im.t[i] * 1000))}</div>${rows}
      <div class="r tot"><span class="sw" style="background:var(--import)"></span>${t('imported')}<span class="v">${nf(totals[i])} MW</span></div>`;
    tip.classList.add('on');
    const wb = wrap.getBoundingClientRect();
    const rel = x(i) / W * b.width + (b.left - wb.left);
    tip.style.left = Math.min(Math.max(rel + 14, 0), wb.width - tip.offsetWidth) + 'px';
    tip.style.top = '6px';
  };
  svg.addEventListener('pointermove', show);
  svg.addEventListener('pointerdown', show);
  svg.addEventListener('pointerleave', () => {
    tip.classList.remove('on'); cursor.setAttribute('opacity', 0);
  });
}

/* ── what the trade cost ──────────────────────────────────────────────── */

// Largest of 1/2/5 × 10^k that still leaves at most `count` ticks.
function niceStep(range, count) {
  const rough = range / count;
  const mag = 10 ** Math.floor(Math.log10(rough));
  for (const m of [1, 2, 5, 10]) {
    if (rough <= m * mag) return m * mag;
  }
  return 10 * mag;
}

const eur = (v, frac = 0) => new Intl.NumberFormat(LANG === 'de' ? 'de-AT' : 'en-GB',
  { style: 'currency', currency: 'EUR', maximumFractionDigits: frac,
    minimumFractionDigits: frac }).format(v);

// Millions read better than nine digits on a headline figure.
const eurShort = v => {
  const a = Math.abs(v);
  if (a >= 1e6) return (v < 0 ? '−' : '') + eur(a / 1e6, 2).replace(/([\d.,]+)/, '$1') + ' M';
  if (a >= 1e4) return (v < 0 ? '−' : '') + eur(Math.round(a / 1e3) * 1e3);
  return eur(v);
};

function renderMoney() {
  const sec = document.getElementById('moneySection');
  const m = DATA.money;
  if (!m || !m.cumulative || m.cumulative.length < 2) { sec.hidden = true; return; }
  sec.hidden = false;

  const box = document.getElementById('moneyStats');
  box.textContent = '';
  const stats = [
    { k: t('importCost'), v: eurShort(m.importCost), cls: 'imp',
      d: m.avgImportPrice != null ? `${t('avgPaid')} ${nf(m.avgImportPrice, 1)} €/MWh` : '' },
    { k: t('exportRevenue'), v: eurShort(m.exportRevenue), cls: 'exp',
      d: m.avgExportPrice != null ? `${t('avgEarned')} ${nf(m.avgExportPrice, 1)} €/MWh` : '' },
    { k: t('netCost'), v: eurShort(m.net), d: t('paidOut') },
  ];
  for (const s of stats) {
    const c = el('div', 'tstat');
    const val = el('div', 'v', s.v);
    if (s.cls) val.classList.add(s.cls);
    c.append(el('div', 'k', s.k), val);
    if (s.d) c.append(el('div', 'd', s.d));
    box.append(c);
  }

  const svg = document.getElementById('moneyChart');
  const N = m.cumulative.length;
  const W = Math.max(svg.clientWidth || svg.parentElement.clientWidth || 720, 320);
  const H = 210;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('height', H);
  svg.textContent = '';
  svg.setAttribute('aria-label', `${t('moneyTitle')} — ${t('runningTotal')} ${eur(m.net)}`);

  const P = { t: 26, r: PAD.r, b: PAD.b, l: 58 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;

  // Round tick step, so the axis reads 0 / 1 / 2 / 3 M rather than whatever
  // quarters of the data range happen to be.
  const rawHi = Math.max(...m.cumulative, 0), rawLo = Math.min(...m.cumulative, 0);
  const step = niceStep((rawHi - rawLo) || 1, 5);
  const hi = Math.ceil(rawHi / step) * step;
  const lo = Math.floor(rawLo / step) * step;
  const span = (hi - lo) || step;

  const x = i => P.l + (i / (N - 1)) * iw;
  const y = v => P.t + ih - ((v - lo) / span) * ih;

  const millions = Math.max(Math.abs(hi), Math.abs(lo)) >= 1e6;
  for (let v = lo; v <= hi + step / 2; v += step) {
    svg.append(svgEl('line', {
      class: Math.abs(v) < step / 1000 ? 'axisline' : 'gridline',
      x1: P.l, x2: W - P.r, y1: y(v), y2: y(v),
    }));
    const lab = svgEl('text', { x: P.l - 8, y: y(v) + 4, 'text-anchor': 'end' });
    lab.textContent = v === 0 ? '0'
      : millions ? nf(v / 1e6, step < 1e6 ? 1 : 0) : nf(Math.round(v / 1e3));
    svg.append(lab);
  }
  const unit = svgEl('text', { x: P.l - 8, y: P.t - 10, 'text-anchor': 'end' });
  unit.textContent = millions ? 'Mio €' : '1000 €';
  svg.append(unit);

  const line = m.cumulative.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
  svg.append(svgEl('path', {
    d: `${line}L${x(N - 1)},${y(0)}L${x(0)},${y(0)}Z`,
    fill: 'var(--import)', 'fill-opacity': 0.16,
  }));
  svg.append(svgEl('path', {
    d: line, fill: 'none', stroke: 'var(--import)', 'stroke-width': 2,
    'stroke-linejoin': 'round',
  }));

  const fmt = clockFmt();
  const every = Math.max(1, Math.round(N / 8));
  m.t.forEach((ts, i) => {
    if (i % every && i !== N - 1) return;
    const lab = svgEl('text', {
      x: x(i), y: H - 8,
      'text-anchor': i === N - 1 ? 'end' : i === 0 ? 'start' : 'middle',
    });
    lab.textContent = fmt.format(new Date(ts * 1000));
    svg.append(lab);
  });

  const cursor = svgEl('line', { class: 'cursor', y1: P.t, y2: P.t + ih, opacity: 0 });
  svg.append(cursor);

  const tip = document.getElementById('moneyTip');
  const wrap = svg.closest('.plotwrap');
  const show = ev => {
    const b = svg.getBoundingClientRect();
    const px = (ev.clientX - b.left) / b.width * W;
    let i = Math.round((px - P.l) / iw * (N - 1));
    i = Math.max(0, Math.min(N - 1, i));
    cursor.setAttribute('x1', x(i));
    cursor.setAttribute('x2', x(i));
    cursor.setAttribute('opacity', 1);
    tip.innerHTML = `<div class="t">${dateFmt().format(new Date(m.t[i] * 1000))}</div>
      <div class="r tot"><span class="sw" style="background:var(--import)"></span>${t('runningTotal')}<span class="v">${eur(m.cumulative[i])}</span></div>`;
    tip.classList.add('on');
    const wb = wrap.getBoundingClientRect();
    const rel = x(i) / W * b.width + (b.left - wb.left);
    tip.style.left = Math.min(Math.max(rel + 14, 0), wb.width - tip.offsetWidth) + 'px';
    tip.style.top = '6px';
  };
  svg.addEventListener('pointermove', show);
  svg.addEventListener('pointerdown', show);
  svg.addEventListener('pointerleave', () => {
    tip.classList.remove('on'); cursor.setAttribute('opacity', 0);
  });
}

/* ── rivers (fetched live, client-side) ───────────────────────────────── */

let RIVER_DATA = null;

const num = v => {
  const x = parseFloat(String(v).replace(',', '.'));
  return Number.isFinite(x) ? x : null;
};

// "04.08.26 18:30" — ehyd's own display format, not ISO.
function ehydTime(s) {
  const m = /^(\d{2})\.(\d{2})\.(\d{2}) (\d{2}):(\d{2})/.exec(String(s || ''));
  if (!m) return null;
  return new Date(2000 + +m[3], +m[2] - 1, +m[1], +m[4], +m[5]);
}

async function loadRivers() {
  const results = await Promise.allSettled(
    RIVERS.map(r => fetch(EHYD + r.hzbnr, { cache: 'no-store' })
      .then(res => { if (!res.ok) throw new Error(res.status); return res.json(); })
      .then(d => ({ ...r, d }))));

  const ok = results.filter(r => r.status === 'fulfilled').map(r => r.value);
  if (!ok.length) return;           // panel simply stays hidden

  RIVER_DATA = ok.map(({ river, en, d }) => {
    const series = (d.data || []).map(num).filter(v => v !== null);
    return {
      river, en,
      gauge: d.messstelle,
      unit: d.einheit || 'm³/s',
      now: num(d.wert),
      at: ehydTime(d.zp),
      nw: num(d.niedrigwasser),
      mw: num(d.mittelwasser),
      link: d.internet || null,
      series,
    };
  }).filter(r => r.now !== null);

  if (RIVER_DATA.length) renderRivers();
}

function riverStatus(r) {
  if (r.nw == null || r.mw == null) return '';
  if (r.now < r.nw * 0.95) return t('belowNW');
  if (r.now < r.nw * 1.1) return t('nearNW');
  if (r.now < r.mw) return t('belowMW');
  return t('aboveMW');
}

function renderRivers() {
  if (!RIVER_DATA) return;
  const sec = document.getElementById('riverSection');
  sec.hidden = false;

  const at = RIVER_DATA.map(r => r.at).filter(Boolean).sort((a, b) => b - a)[0];
  const st = document.getElementById('riverStamp');
  st.textContent = '';
  st.append(el('span', 'dot'), document.createTextNode(
    (at ? `${t('asOf')} ${dateFmt().format(at)} · ` : '') + t('riverLive')));

  const box = document.getElementById('rivers');
  box.textContent = '';

  for (const r of RIVER_DATA) {
    const card = el('div', 'river');

    const head = el('div', 'rh');
    head.append(el('span', 'nm', LANG === 'de' ? r.river : r.en),
      el('span', 'gauge', r.gauge));
    card.append(head);

    const v = el('div', 'rv');
    v.innerHTML = `${nf(r.now, r.now < 100 ? 1 : 0)}<small>${r.unit}</small>`;
    card.append(v);

    if (r.mw != null) {
      card.append(el('div', 'rpct',
        `${nf(r.now / r.mw * 100, 0)} % ${t('ofMean')} · ${riverStatus(r)}`));
    }

    // Scale runs 0 → mean water, so the bars are comparable as a fraction of
    // normal; it stretches only if a river runs above its mean.
    const scale = Math.max(r.mw || r.now, r.now * 1.08);
    const track = el('div', 'rtrack');
    const bar = el('div', 'rbar');
    bar.style.width = Math.max(r.now / scale * 100, 1) + '%';
    track.append(bar);

    for (const [val, lab] of [[r.nw, 'NW'], [r.mw, 'MW']]) {
      if (val == null || val > scale) continue;
      const tick = el('div', 'rtick');
      tick.style.left = (val / scale * 100) + '%';
      tick.append(el('span', 'lab', lab));
      track.append(tick);
    }
    card.append(track);

    if (r.series.length > 2) card.append(riverSpark(r));
    box.append(card);
  }
}

function riverSpark(r) {
  const N = r.series.length, W = 240, H = 34;
  const svg = svgEl('svg', {
    class: 'chart', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none',
    role: 'img', 'aria-label': `${r.gauge} ${t('days7')}`,
  });
  svg.style.height = H + 'px';

  const hi = Math.max(...r.series), lo = Math.min(...r.series);
  const span = hi - lo || 1;
  const x = i => (i / (N - 1)) * W;
  const y = v => H - 3 - ((v - lo) / span) * (H - 6);

  const line = r.series.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
  svg.append(svgEl('path', {
    d: `${line}L${W},${H}L0,${H}Z`, fill: 'var(--hydro)', 'fill-opacity': 0.18,
  }));
  svg.append(svgEl('path', {
    d: line, fill: 'none', stroke: 'var(--hydro)', 'stroke-width': 1.5,
    'stroke-linejoin': 'round', 'vector-effect': 'non-scaling-stroke',
  }));
  return svg;
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
  renderPanelStamp('tradeStamp', tr.at);

  // stats — the current balance first, then the shape of the day around it
  const pct = tr.steps ? Math.round(tr.importingSteps / tr.steps * 100) : 0;
  const net = DATA.flows ? DATA.flows.reduce((sum, f) => sum + f.mw, 0) : null;
  const stats = [];
  if (net != null) {
    stats.push({
      k: t('netBalance'), v: nf(Math.abs(net)), u: 'MW',
      d: Math.abs(net) < 20 ? t('balanced') : net > 0 ? t('netImport') : t('netExport'),
      cls: Math.abs(net) < 20 ? '' : net > 0 ? 'imp' : 'exp',
    });
  }
  stats.push(
    { k: t('peakImport'), v: `+${nf(tr.peakImport)}`, u: 'MW',
      d: tr.peakImportShare != null ? `${nf(tr.peakImportShare, 1)} % ${t('ofLoadThen')}` : '' },
    { k: t('peakExport'), v: nf(tr.peakExport), u: 'MW' },
    { k: t('timeImporting'), v: `${pct}`, u: '%', d: t('ofDay') });

  const box = document.getElementById('tradeStats');
  box.textContent = '';
  for (const s of stats) {
    const c = el('div', 'tstat');
    const value = el('div', 'v', `${s.v}<small>${s.u}</small>`);
    if (s.cls) value.classList.add(s.cls);
    c.append(el('div', 'k', s.k), value);
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
    // Percentages here are of gross flow across all borders, so an inflow and
    // an outflow of equal size each read as half the traffic rather than
    // cancelling to nothing.
    const gross = tr.countries.reduce((a, c) => a + Math.abs(c.series[i]), 0) || 1;
    const rows = tr.countries.map(c =>
      `<div class="r"><span class="sw" style="background:${c.series[i] >= 0 ? 'var(--import)' : 'var(--export)'}"></span>${country(c.name)}<span class="v">${c.series[i] > 0 ? '+' : ''}${nf(c.series[i])}<em>${nf(Math.abs(c.series[i]) / gross * 100, 0)} %</em></span></div>`).join('');
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

/* One card per border: the current value and the shape of the day behind it.
   The headline number comes from `flows`, which walks back to each border's
   newest published reading; the series is padded with zeros where the API has
   not settled a step yet, so its last point is not always the live one. */
function renderSparks(tr) {
  const box = document.getElementById('sparks');
  box.textContent = '';
  // One shared scale across the small multiples, so the panels are
  // comparable to each other rather than each self-normalised.
  const mag = Math.max(...tr.countries.flatMap(c => c.series.map(Math.abs)), 500);
  const now = new Map((DATA.flows || []).map(f => [f.name, f.mw]));
  const countries = [...tr.countries].sort((a, b) =>
    Math.abs(now.get(b.name) ?? b.series[b.series.length - 1]) -
    Math.abs(now.get(a.name) ?? a.series[a.series.length - 1]));

  for (const c of countries) {
    const card = el('div', 'spark');
    const last = now.get(c.name) ?? c.series[c.series.length - 1];
    const head = el('div', 'sh');
    const val = el('span', 'val', `${last > 0 ? '+' : ''}${nf(last)} MW`);
    if (Math.abs(last) >= 20) val.classList.add(last > 0 ? 'imp' : 'exp');
    head.append(el('span', 'nm', country(c.name)), val);
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
  renderCleanScore();
  renderRangeButtons();
  renderDay();
  renderComparison();
  renderSeason();
  renderBalance();
  renderDependency();
  renderStorage();
  renderTrade();
  renderImportMix();
  renderMoney();
  renderRivers();
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
  renderMix();
  renderSeason();
  renderBalance();
  renderDependency();
  renderStorage();
  renderTrade();
  renderImportMix();
  renderMoney();
});

document.getElementById('rangeButtons').addEventListener('click', event => {
  const button = event.target.closest('button[data-range]');
  if (!button) return;
  DAY_RANGE = button.dataset.range;
  renderRangeButtons();
  renderDay();
});

if (localStorage.getItem('theme')) {
  document.documentElement.dataset.theme = localStorage.getItem('theme');
}

let resizeTimer;
addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (DATA) { renderDay(); renderSeason(); renderBalance(); renderDependency(); renderStorage(); renderTrade(); } }, 150);
});

fetch('data.json?' + Date.now())
  .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then(d => {
    DATA = d;
    document.getElementById('app').hidden = false;
    renderAll();
    // Independent of the main payload: if ehyd is unreachable the rest of
    // the page is unaffected and the panel stays hidden.
    loadRivers().catch(e => console.warn('rivers unavailable:', e));
  })
  .catch(e => {
    const box = document.getElementById('error');
    box.hidden = false;
    box.textContent = `${t('err')} (${e.message})`;
  });
