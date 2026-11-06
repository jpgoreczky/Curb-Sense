/**
 * Runtime config. EXPO_PUBLIC_* values are inlined into the JS bundle at
 * build time, so only put public values here (never secrets).
 * Set them per EAS environment (development / preview / production) with
 * `eas env:create`, or locally in apps/mobile/.env.local (see .env.example).
 */

function parseCenter(raw: string | undefined): [number, number] {
  const parts = (raw ?? "").split(",").map(Number);
  if (parts.length === 2 && parts.every(Number.isFinite)) {
    return [parts[0], parts[1]];
  }
  // No pilot city chosen yet: midtown Manhattan as a neutral default.
  return [-73.99, 40.75];
}

export const env = {
  // Public (pk.*) Mapbox token, scoped per environment (SETUP-1.4).
  mapboxToken: process.env.EXPO_PUBLIC_MAPBOX_TOKEN ?? "",
  // Mapbox Studio style (UI-4.1.2). Empty = Mapbox Streets until it exists.
  mapboxStyleUrl: process.env.EXPO_PUBLIC_MAPBOX_STYLE_URL ?? "",
  apiUrl: (process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, ""),
  initialCenter: parseCenter(process.env.EXPO_PUBLIC_INITIAL_CENTER),
  initialZoom: Number(process.env.EXPO_PUBLIC_INITIAL_ZOOM ?? 13),
};
