/**
 * API rows -> GeoJSON for the Mapbox layers in DataLayer.
 *
 * Filtering happens here, on data already loaded, so filter chips re-render
 * instantly with no request (UI-4.2.3). Clusters carry per-filter counts and
 * representatives from the API for the same reason.
 *
 * Feature properties used by layer styles:
 *   tier, status       morphology (tier) and color (status), never mixed
 *   offsetSign         segments: +1 right curb, -1 left curb (Mapbox line-offset sign)
 *   opacity            Tier 2 recency decay; 1 for Tier 1/3
 *   label              short label ("2h"); null until the restrictions schema exists
 */

import type { ClusterRepresentative, PinCluster, PinSummary, Status, Tier } from "../../api/types";
import type { PinFilter } from "./store";

type Props = { id: string; tier: Tier; status: Status; opacity: number; label: string | null };
export type SegmentProps = Props & { offsetSign: 1 | -1 };
export type ClusterProps = { id: string; tier: Tier; status: Status; count: number; countLabel: string };

export interface PinCollections {
  segments: GeoJSON.FeatureCollection<GeoJSON.LineString, SegmentProps>;
  lots: GeoJSON.FeatureCollection<GeoJSON.Polygon, Props>;
  /** Point pins plus lot anchors (a lot's status dot sits on its callout point). */
  points: GeoJSON.FeatureCollection<GeoJSON.Point, Props>;
  /** Tier 3 anchors: where the conflict flag badge goes, for every geometry kind. */
  flags: GeoJSON.FeatureCollection<GeoJSON.Point, Props>;
  /** Anchors that have a label. */
  labels: GeoJSON.FeatureCollection<GeoJSON.Point, Props>;
}

const DAY_MS = 24 * 60 * 60 * 1000;
/** Tier 2 recency decay: full opacity for a week, fading to a floor by 90 days. */
export const TIER2_DECAY = { fullForDays: 7, floorAtDays: 90, floor: 0.35 } as const;

export function recencyOpacity(tier: Tier, lastVerifiedAt: string | null, now: number): number {
  if (tier !== 2) return 1;
  if (!lastVerifiedAt) return TIER2_DECAY.floor;
  const ageDays = (now - Date.parse(lastVerifiedAt)) / DAY_MS;
  if (!Number.isFinite(ageDays) || ageDays <= TIER2_DECAY.fullForDays) return 1;
  if (ageDays >= TIER2_DECAY.floorAtDays) return TIER2_DECAY.floor;
  const t = (ageDays - TIER2_DECAY.fullForDays) / (TIER2_DECAY.floorAtDays - TIER2_DECAY.fullForDays);
  return Number((1 - t * (1 - TIER2_DECAY.floor)).toFixed(3));
}

export function passesFilter(pin: { tier: Tier; status: Status }, filter: PinFilter): boolean {
  switch (filter) {
    case "all":
      return true;
    case "verified":
      return pin.tier === 1;
    case "free":
      return pin.status === "available";
  }
}

/**
 * Short map label from structured restrictions. Returns null until the
 * restrictions JSON has a schema (pairs with AI-3.3); the label layer is
 * wired and zoom/mode-gated already.
 */
export function shortLabel(_restrictions: Record<string, unknown>): string | null {
  return null;
}

const emptyCollection = <G extends GeoJSON.Geometry, P>(): GeoJSON.FeatureCollection<G, P> => ({
  type: "FeatureCollection",
  features: [],
});

const point = (lon: number, lat: number): GeoJSON.Point => ({ type: "Point", coordinates: [lon, lat] });

export function pinsToCollections(pins: PinSummary[], filter: PinFilter, now: number = Date.now()): PinCollections {
  const out: PinCollections = {
    segments: emptyCollection(),
    lots: emptyCollection(),
    points: emptyCollection(),
    flags: emptyCollection(),
    labels: emptyCollection(),
  };

  for (const pin of pins) {
    if (!passesFilter(pin, filter)) continue;
    const props: Props = {
      id: pin.id,
      tier: pin.tier,
      status: pin.status,
      opacity: recencyOpacity(pin.tier, pin.last_verified_at, now),
      label: shortLabel(pin.restrictions),
    };
    const anchor = point(pin.anchor_lon, pin.anchor_lat);

    if (pin.kind === "segment" && pin.geometry.type === "LineString") {
      out.segments.features.push({
        type: "Feature",
        id: pin.id,
        geometry: pin.geometry,
        properties: { ...props, offsetSign: pin.curb_side === "left" ? -1 : 1 },
      });
    } else if (pin.kind === "lot" && pin.geometry.type === "Polygon") {
      out.lots.features.push({ type: "Feature", id: pin.id, geometry: pin.geometry, properties: props });
      out.points.features.push({ type: "Feature", id: pin.id, geometry: anchor, properties: props });
    } else {
      out.points.features.push({ type: "Feature", id: pin.id, geometry: anchor, properties: props });
    }

    if (pin.tier === 3) {
      out.flags.features.push({ type: "Feature", id: `flag:${pin.id}`, geometry: anchor, properties: props });
    }
    if (props.label) {
      out.labels.features.push({ type: "Feature", id: `label:${pin.id}`, geometry: anchor, properties: props });
    }
  }
  return out;
}

export function formatCount(n: number): string {
  if (n < 1000) return String(n);
  if (n < 10_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return `${Math.round(n / 1000)}k`;
}

export interface ClusterCollections {
  /** Cells with 2+ members under the active filter: count bubbles. */
  clusters: GeoJSON.FeatureCollection<GeoJSON.Point, ClusterProps>;
  /** Cells with exactly one member: drawn as that pin at its own anchor. */
  singles: GeoJSON.FeatureCollection<GeoJSON.Point, Props>;
  flags: GeoJSON.FeatureCollection<GeoJSON.Point, Props>;
}

export function clustersToCollections(
  cells: PinCluster[],
  filter: PinFilter,
  now: number = Date.now(),
): ClusterCollections {
  const out: ClusterCollections = { clusters: emptyCollection(), singles: emptyCollection(), flags: emptyCollection() };

  for (const cell of cells) {
    const count = cell.counts[filter];
    const rep: ClusterRepresentative | null = cell.representatives[filter];
    if (count === 0 || rep === null) continue;

    if (count === 1) {
      const props: Props = {
        id: rep.id,
        tier: rep.tier,
        status: rep.status,
        opacity: recencyOpacity(rep.tier, rep.last_verified_at, now),
        label: null, // labels only exist at street zoom, never in cluster mode
      };
      const anchor = point(rep.anchor_lon, rep.anchor_lat);
      out.singles.features.push({ type: "Feature", id: rep.id, geometry: anchor, properties: props });
      if (rep.tier === 3) {
        out.flags.features.push({ type: "Feature", id: `flag:${rep.id}`, geometry: anchor, properties: props });
      }
      continue;
    }

    const bubble = point(cell.lon, cell.lat);
    out.clusters.features.push({
      type: "Feature",
      id: cell.cell,
      geometry: bubble,
      properties: { id: cell.cell, tier: rep.tier, status: rep.status, count, countLabel: formatCount(count) },
    });
    if (rep.tier === 3) {
      // A disputed representative keeps its flag on the bubble, so conflicts stay visible.
      out.flags.features.push({
        type: "Feature",
        id: `flag:${cell.cell}`,
        geometry: bubble,
        properties: { id: rep.id, tier: 3, status: rep.status, opacity: 1, label: null },
      });
    }
  }
  return out;
}
