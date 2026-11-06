/**
 * Map screen layer architecture (handoff §4). One place for stacking order
 * so no component picks its own zIndex.
 *
 *   L0 Base Map       Mapbox canvas + style
 *   L1 Data Layer     curb segments, pins, lots, clusters, (later) event overlays
 *                     -- lives INSIDE the Mapbox canvas; ordered by MAP_LAYER_ORDER
 *   L2 Navigation     search bar, filter chips, ETA strip
 *   L2 Floating       recenter / add-parking FABs (driving: one voice FAB)
 *   L3 Sheets/Modals  pin detail sheet, review composer, legend, confirm card
 */
export const Z_INDEX = {
  baseMap: 0,
  navigation: 20,
  floatingActions: 21,
  sheets: 30,
} as const;

/** Below this zoom the API returns clusters; at or above it, raw features. Mirrors the API. */
export const RAW_MIN_ZOOM = 14;
/** Short map labels ("2h", "$2") appear at and above this zoom (PRD 3.1). */
export const LABEL_MIN_ZOOM = 16;

/**
 * Mapbox layer ids, bottom to top. Rendered in this order inside L1, so
 * higher-priority data always draws over lower: Tier 3 > Tier 1 > Tier 2.
 */
export const MAP_LAYER_ORDER = [
  "lots-fill",
  "lots-outline",
  "segments-tier2",
  "segments-tier1",
  "segments-tier3",
  "points-tier2",
  "points-tier1",
  "points-tier3",
  "tier3-flags",
  "clusters",
  "cluster-counts",
  "labels",
] as const;

export type MapLayerId = (typeof MAP_LAYER_ORDER)[number];
