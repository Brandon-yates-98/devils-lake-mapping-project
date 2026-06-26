// campflare-availability, live per-site availability for the public map, via Campflare.
//
// Replaces the WAF-blocked direct GoingToCamp path (see gtc-availability): GoingToCamp
// sits behind a Cloudflare WAF that 403s server IPs, so we source availability from
// Campflare's v2 API instead. The API key is held server-side (Deno.env) and never
// reaches the browser.
//
// Availability is keyed by Campflare's campsite_id. Each of our campsite features
// stores its campflare_id (precomputed by enrich_campsites_campflare.py), so the
// frontend joins on that id, robust against Campflare's site-name quirks (e.g. it
// labels electric sites "109E" while our ref is "109").
//
// Request (POST JSON):
//   { campgroundIds: string[], start_date: "YYYY-MM-DD", end_date: "YYYY-MM-DD" }
// Response:
//   { availability: { [campgroundId]: { [campsiteId]: Roll } }, start_date, end_date, fetchedAt }
//   Roll = "available" | "partial" | "unavailable" | "unknown"
//     available  , open every night in the range
//     partial    , open some nights, not all
//     unavailable, open no nights (reserved/closed/first-come every night)
//     unknown    , only unknown / not-yet-released nights

const API_BASE = "https://api.campflare.com/v2";
const AVAIL_TTL_MS = 90_000; // availability changes constantly; brief cache only
const MAX_RANGE_DAYS = 60; // Campflare returns at most 60 days per availability call

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, content-type, apikey, x-client-info",
};

// `${campgroundId}|${start}|${end}` -> { ts, rolled: Record<campsiteId, Roll> }
const availCache = new Map<string, { ts: number; rolled: Record<string, string> }>();

// Prefer the canonical CAMPFLARE_API_KEY, but tolerate any secret whose name
// contains "campflare" (e.g. it was set as "campflare-availability").
function cfKey(): string {
  const direct = Deno.env.get("CAMPFLARE_API_KEY");
  if (direct) return direct;
  for (const [k, v] of Object.entries(Deno.env.toObject())) {
    if (v && /campflare/i.test(k)) return v;
  }
  return "";
}

function cfHeaders() {
  return { "Authorization": cfKey(), "Accept": "application/json" };
}

// One fetch with a single 429 retry honoring Retry-After (capped).
async function cfFetch(url: string): Promise<Response> {
  let res = await fetch(url, { headers: cfHeaders() });
  if (res.status === 429) {
    const wait = Math.min(5, Number(res.headers.get("retry-after")) || 1);
    await new Promise((r) => setTimeout(r, wait * 1000));
    res = await fetch(url, { headers: cfHeaders() });
  }
  return res;
}

// "YYYY-MM-DD" nights occupied by a stay [start, end): a stay checks out on
// end_date, so the nights are start .. end-1. A zero/!-length range collapses to
// the single start night.
function nightsInRange(start: string, end: string): string[] {
  const toUTC = (s: string) => { const [y, m, d] = s.split("-").map(Number); return Date.UTC(y, m - 1, d); };
  const dayMs = 86_400_000;
  const s = toUTC(start);
  const e = Math.max(toUTC(end), s + dayMs); // at least one night
  const out: string[] = [];
  for (let t = s; t < e && out.length < MAX_RANGE_DAYS; t += dayMs) {
    out.push(new Date(t).toISOString().slice(0, 10));
  }
  return out;
}

function roll(statuses: string[]): string {
  if (!statuses.length) return "unknown";
  const openCount = statuses.filter((s) => s === "available" || s === "first-come-first-serve").length;
  const known = statuses.filter((s) => s !== "unknown" && s !== "not-yet-released").length;
  if (openCount === statuses.length) return "available";
  if (openCount > 0) return "partial";
  if (known > 0) return "unavailable"; // some night is reserved/closed and none are open
  return "unknown";
}

async function campgroundAvailability(
  campgroundId: string,
  start: string,
  end: string,
): Promise<Record<string, string>> {
  const cacheKey = `${campgroundId}|${start}|${end}`;
  const hit = availCache.get(cacheKey);
  if (hit && Date.now() - hit.ts < AVAIL_TTL_MS) return hit.rolled;

  const nights = nightsInRange(start, end);
  const lastNight = nights[nights.length - 1];
  const qs = new URLSearchParams({ start_date: start, end_date: lastNight });
  const res = await cfFetch(`${API_BASE}/campground/${encodeURIComponent(campgroundId)}/availability?${qs}`);
  if (!res.ok) throw new Error(`availability ${campgroundId} -> HTTP ${res.status}`);
  const data = await res.json();

  const rolled: Record<string, string> = {};
  for (const site of data?.campsite_availability ?? []) {
    const id = String(site?.campsite_id ?? "");
    if (!id) continue;
    const avail = site?.availability ?? {};
    rolled[id] = roll(nights.map((d) => String(avail[d] ?? "unknown")));
  }
  availCache.set(cacheKey, { ts: Date.now(), rolled });
  return rolled;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  if (!cfKey()) return json({ error: "CAMPFLARE_API_KEY not configured" }, 500);

  let body: { campgroundIds?: string[]; start_date?: string; end_date?: string };
  try {
    body = await req.json();
  } catch {
    return json({ error: "invalid JSON body" }, 400);
  }
  const { campgroundIds, start_date, end_date } = body;
  const dateOk = (s?: string) => typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s);
  if (!Array.isArray(campgroundIds) || !campgroundIds.length || !dateOk(start_date) || !dateOk(end_date)) {
    return json({ error: "need campgroundIds[], start_date, end_date (YYYY-MM-DD)" }, 400);
  }

  try {
    const availability: Record<string, Record<string, string>> = {};
    for (const id of campgroundIds) {
      availability[id] = await campgroundAvailability(id, start_date!, end_date!);
    }
    return json({ availability, start_date, end_date, fetchedAt: new Date().toISOString() });
  } catch (e) {
    // Never block the map, frontend renders "unknown" on error.
    return json({ error: String((e as Error)?.message ?? e) }, 502);
  }
});
