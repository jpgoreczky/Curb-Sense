// Mirrors apps/api/schemas.py. Keep in sync when the API changes.

import type { ParkingStatus } from "../theme/tokens";

export type Status = ParkingStatus;
export type Tier = 1 | 2 | 3;
export type PinKind = "point" | "segment" | "lot";
export type CurbSide = "left" | "right";

/** GET /pins (zoom >= RAW_MIN_ZOOM). */
export interface PinSummary {
  id: string;
  kind: PinKind;
  anchor_lon: number;
  anchor_lat: number;
  /** Full GeoJSON geometry. Segments are street centerlines; offset toward curb_side. */
  geometry: GeoJSON.Point | GeoJSON.LineString | GeoJSON.Polygon;
  curb_side: CurbSide | null;
  tier: Tier;
  status: Status;
  restrictions: Record<string, unknown>;
  last_verified_at: string | null;
  display_priority: number;
  street_name: string | null;
  from_street: string | null;
  to_street: string | null;
}

export interface ClusterRepresentative {
  id: string;
  kind: PinKind;
  tier: Tier;
  status: Status;
  anchor_lon: number;
  anchor_lat: number;
  last_verified_at: string | null;
}

export interface PinCluster {
  /** "zoom/x/y": stable per grid cell; used as the feature id. */
  cell: string;
  lon: number;
  lat: number;
  counts: { all: number; verified: number; free: number };
  representatives: {
    all: ClusterRepresentative;
    verified: ClusterRepresentative | null;
    free: ClusterRepresentative | null;
  };
}

/** GET /pins/clusters (zoom < RAW_MIN_ZOOM). */
export interface PinClusterResponse {
  zoom: number;
  raw_min_zoom: number;
  clusters: PinCluster[];
}

export type BBox = [minLon: number, minLat: number, maxLon: number, maxLat: number];
