import type { BBox } from "../../api/types";
import { RAW_MIN_ZOOM } from "./layers";

/**
 * Turns the camera's visible bounds into what we ask the API for.
 * Pure request shaping: no spatial logic (that stays in PostGIS).
 *
 * - Pads the view so small pans are served from cache.
 * - Rounds outward to a zoom-dependent step so nearby cameras share a
 *   React Query key instead of refetching on every pixel of movement.
 * - Clamps to the API's per-zoom bbox size guard for /pins/clusters.
 */

const PAD_RATIO = 0.25;
/** Mirrors MAX_CLUSTER_SPAN_DEG_AT_Z0 in apps/api/routers/pins.py. */
const MAX_CLUSTER_SPAN_DEG_AT_Z0 = 360 * 4;

export type ViewportRequest =
  | { kind: "clusters"; zoom: number; bbox: BBox }
  | { kind: "pins"; bbox: BBox };

function roundingStep(zoom: number): number {
  // About 1/8 of a 512 px tile at this zoom, in degrees.
  return 360 / 2 ** zoom / 8;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function toViewportRequest(bbox: BBox, cameraZoom: number): ViewportRequest {
  const zoom = Math.max(0, Math.floor(cameraZoom));
  const [minLon, minLat, maxLon, maxLat] = bbox;
  let halfW = ((maxLon - minLon) / 2) * (1 + PAD_RATIO);
  let halfH = ((maxLat - minLat) / 2) * (1 + PAD_RATIO);
  const cx = (minLon + maxLon) / 2;
  const cy = (minLat + maxLat) / 2;

  const clusters = zoom < RAW_MIN_ZOOM;
  if (clusters) {
    // Stay inside the server guard even after padding and rounding.
    const maxHalf = (MAX_CLUSTER_SPAN_DEG_AT_Z0 / 2 ** zoom) * 0.45;
    halfW = Math.min(halfW, maxHalf);
    halfH = Math.min(halfH, maxHalf);
  }

  const step = roundingStep(zoom);
  const out: BBox = [
    clamp(Math.floor((cx - halfW) / step) * step, -180, 180),
    clamp(Math.floor((cy - halfH) / step) * step, -90, 90),
    clamp(Math.ceil((cx + halfW) / step) * step, -180, 180),
    clamp(Math.ceil((cy + halfH) / step) * step, -90, 90),
  ];
  // Kill float noise so equal requests produce equal query keys.
  const tidy = out.map((v) => Number(v.toFixed(6))) as BBox;

  return clusters ? { kind: "clusters", zoom, bbox: tidy } : { kind: "pins", bbox: tidy };
}

/** Camera bounds from Mapbox ({ne, sw} positions) as [minLon, minLat, maxLon, maxLat]. */
export function boundsToBBox(ne: GeoJSON.Position, sw: GeoJSON.Position): BBox {
  return [Math.min(sw[0], ne[0]), Math.min(sw[1], ne[1]), Math.max(sw[0], ne[0]), Math.max(sw[1], ne[1])];
}
