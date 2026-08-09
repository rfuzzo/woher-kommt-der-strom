const APG_HOST = "https://transparency.apg.at";
const SWAGGER = `${APG_HOST}/api/swagger/v1/swagger.json`;
const TZ = "Europe/Vienna";
const TIMEOUT_MS = 10_000;
const CACHE_KEY: Deno.KvKey = ["apg", "latest"];
const KINDS = ["AGPT", "AL", "CBPF"] as const;
type Kind = typeof KINDS[number];

type ApgDataset = {
  ValueColumns: unknown[];
  ValueRows: unknown[];
  VersionInformation?: unknown;
};

type CachedPayload = {
  schemaVersion: 1;
  fetchedAt: string;
  fetchedAtEpoch: number;
  region: string | null;
  window: { from: string; to: string };
  generation: ApgDataset;
  load: ApgDataset;
  borders: ApgDataset;
};

function json(data: unknown, status = 200, cacheControl = "no-store"): Response {
  return new Response(JSON.stringify(data, null, 2) + "\n", {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": cacheControl,
      "access-control-allow-origin": "*",
    },
  });
}

function localDateParts(now = new Date()): { y: number; m: number; d: number } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const pick = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  return { y: pick("year"), m: pick("month"), d: pick("day") };
}

function ymd(y: number, m: number, d: number): string {
  return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function addDays(y: number, m: number, d: number, delta: number): string {
  const value = new Date(Date.UTC(y, m - 1, d + delta));
  return ymd(value.getUTCFullYear(), value.getUTCMonth() + 1, value.getUTCDate());
}

function cacheWindow(now = new Date()): { yesterday: string; today: string; tomorrow: string } {
  const { y, m, d } = localDateParts(now);
  return {
    yesterday: addDays(y, m, d, -1),
    today: ymd(y, m, d),
    tomorrow: addDays(y, m, d, 1),
  };
}

async function fetchJson(url: string): Promise<unknown> {
  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "woher-kommt-der-strom-deno-cache/1.0",
    },
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`APG HTTP ${response.status}: ${body.slice(0, 300)}`);
  }
  return await response.json();
}

function unwrap(payload: unknown): ApgDataset {
  const root = payload as Record<string, unknown>;
  const data = ((root?.ResponseData as Record<string, unknown>) ?? root) as Record<string, unknown>;
  const columns = Array.isArray(data?.ValueColumns) ? data.ValueColumns : [];
  const rows = Array.isArray(data?.ValueRows) ? data.ValueRows : [];
  if (columns.length === 0) throw new Error("APG response has no ValueColumns");
  return {
    ValueColumns: columns,
    ValueRows: rows,
    VersionInformation: data?.VersionInformation,
  };
}

function mergeDays(first: ApgDataset, second: ApgDataset): ApgDataset {
  const firstNames = first.ValueColumns.map((c) => (c as Record<string, unknown>)?.InternalName ?? null);
  const secondNames = second.ValueColumns.map((c) => (c as Record<string, unknown>)?.InternalName ?? null);
  if (JSON.stringify(firstNames) !== JSON.stringify(secondNames)) {
    throw new Error("APG ValueColumns changed between adjacent days");
  }
  return {
    ValueColumns: second.ValueColumns,
    ValueRows: [...first.ValueRows, ...second.ValueRows],
    VersionInformation: second.VersionInformation ?? first.VersionInformation,
  };
}

async function fetchKind(kind: Kind, yesterday: string, today: string, tomorrow: string): Promise<ApgDataset> {
  const base = `${APG_HOST}/api/v1/${kind}/Data/English/PT15M`;
  const previous = unwrap(await fetchJson(`${base}/${yesterday}T000000/${today}T000000`));
  const current = unwrap(await fetchJson(`${base}/${today}T000000/${tomorrow}T000000`));
  return mergeDays(previous, current);
}

async function buildCache(): Promise<CachedPayload> {
  const { yesterday, today, tomorrow } = cacheWindow();
  const [generation, load, borders] = await Promise.all([
    fetchKind("AGPT", yesterday, today, tomorrow),
    fetchKind("AL", yesterday, today, tomorrow),
    fetchKind("CBPF", yesterday, today, tomorrow),
  ]);
  const fetchedAtEpoch = Math.floor(Date.now() / 1000);
  return {
    schemaVersion: 1,
    fetchedAt: new Date(fetchedAtEpoch * 1000).toISOString(),
    fetchedAtEpoch,
    region: Deno.env.get("DENO_REGION") ?? null,
    window: { from: yesterday, to: tomorrow },
    generation,
    load,
    borders,
  };
}

async function refreshCache(): Promise<CachedPayload> {
  const payload = await buildCache();
  const kv = await Deno.openKv();
  try {
    await kv.set(CACHE_KEY, payload);
  } finally {
    kv.close();
  }
  console.log(`APG cache refreshed at ${payload.fetchedAt} from ${payload.region ?? "unknown region"}`);
  return payload;
}

async function readCache(): Promise<CachedPayload | null> {
  const kv = await Deno.openKv();
  try {
    const entry = await kv.get<CachedPayload>(CACHE_KEY);
    return entry.value;
  } finally {
    kv.close();
  }
}

Deno.cron(
  "Refresh APG cache",
  "*/15 * * * *",
  { backoffSchedule: [5_000, 30_000] },
  async () => {
    await refreshCache();
  },
);

Deno.serve(async (request) => {
  const url = new URL(request.url);

  if (url.pathname === "/") {
    return json({
      service: "woher-kommt-der-strom APG cache",
      endpoints: ["/probe", "/apg/latest.json", "/apg/refresh"],
      region: Deno.env.get("DENO_REGION") ?? null,
    });
  }

  if (url.pathname === "/probe") {
    const started = performance.now();
    try {
      const response = await fetch(SWAGGER, { signal: AbortSignal.timeout(TIMEOUT_MS) });
      return json({
        ok: response.ok,
        target: SWAGGER,
        status: response.status,
        elapsedMs: Math.round(performance.now() - started),
        region: Deno.env.get("DENO_REGION") ?? null,
      }, response.ok ? 200 : 502);
    } catch (error) {
      return json({ ok: false, error: String(error) }, 502);
    }
  }

  if (url.pathname === "/apg/latest.json") {
    try {
      const cached = await readCache();
      if (!cached) {
        return json({ ok: false, error: "cache is empty; call /apg/refresh once or wait for cron" }, 503);
      }
      const ageSeconds = Math.max(0, Math.floor(Date.now() / 1000) - cached.fetchedAtEpoch);
      return json({ ...cached, ageSeconds }, 200, "public, max-age=60");
    } catch (error) {
      return json({ ok: false, error: `KV unavailable: ${error}` }, 503);
    }
  }

  if (url.pathname === "/apg/refresh") {
    try {
      const payload = await refreshCache();
      return json({
        ok: true,
        fetchedAt: payload.fetchedAt,
        region: payload.region,
        rows: {
          generation: payload.generation.ValueRows.length,
          load: payload.load.ValueRows.length,
          borders: payload.borders.ValueRows.length,
        },
      });
    } catch (error) {
      console.error(error);
      return json({ ok: false, error: error instanceof Error ? error.message : String(error) }, 502);
    }
  }

  return json({ error: "not found" }, 404);
});
