const APG_HOST = "https://transparency.apg.at";
const SWAGGER = `${APG_HOST}/api/swagger/v1/swagger.json`;
const TZ = "Europe/Vienna";
const TIMEOUT_MS = 8000;

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data, null, 2) + "\n", {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
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

function todayAndTomorrow(): [string, string] {
  const { y, m, d } = localDateParts();
  const today = ymd(y, m, d);
  const tomorrowUtc = new Date(Date.UTC(y, m - 1, d + 1));
  const tomorrow = ymd(tomorrowUtc.getUTCFullYear(), tomorrowUtc.getUTCMonth() + 1, tomorrowUtc.getUTCDate());
  return [today, tomorrow];
}

async function timedFetch(url: string): Promise<{ response: Response; elapsedMs: number }> {
  const started = performance.now();
  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "woher-kommt-der-strom-deno-probe/1.0",
    },
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  return { response, elapsedMs: Math.round(performance.now() - started) };
}

async function probeSwagger(): Promise<Response> {
  try {
    const { response, elapsedMs } = await timedFetch(SWAGGER);
    return json({
      ok: response.ok,
      target: SWAGGER,
      status: response.status,
      elapsedMs,
      region: Deno.env.get("DENO_REGION") ?? null,
    }, response.ok ? 200 : 502);
  } catch (error) {
    return json({
      ok: false,
      target: SWAGGER,
      error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
      region: Deno.env.get("DENO_REGION") ?? null,
    }, 502);
  }
}

async function probeTodayGeneration(): Promise<Response> {
  const [today, tomorrow] = todayAndTomorrow();
  const target = `${APG_HOST}/api/v1/AGPT/Data/English/PT15M/${today}T000000/${tomorrow}T000000`;
  try {
    const { response, elapsedMs } = await timedFetch(target);
    const payload = await response.json();
    const data = payload?.ResponseData ?? payload;
    const rows = Array.isArray(data?.ValueRows) ? data.ValueRows : [];
    const columns = Array.isArray(data?.ValueColumns) ? data.ValueColumns : [];
    return json({
      ok: response.ok,
      target,
      status: response.status,
      elapsedMs,
      region: Deno.env.get("DENO_REGION") ?? null,
      columns: columns.map((c: Record<string, unknown>) => c?.InternalName ?? null),
      rowCount: rows.length,
      firstRow: rows[0] ?? null,
      lastRow: rows.at(-1) ?? null,
      apiMessage: payload?.Message ?? null,
    }, response.ok ? 200 : 502);
  } catch (error) {
    return json({
      ok: false,
      target,
      error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
      region: Deno.env.get("DENO_REGION") ?? null,
    }, 502);
  }
}

Deno.serve(async (request) => {
  const url = new URL(request.url);
  if (url.pathname === "/") {
    return json({
      service: "woher-kommt-der-strom APG connectivity probe",
      endpoints: ["/probe", "/apg/today"],
      region: Deno.env.get("DENO_REGION") ?? null,
    });
  }
  if (url.pathname === "/probe") return await probeSwagger();
  if (url.pathname === "/apg/today") return await probeTodayGeneration();
  return json({ error: "not found" }, 404);
});
