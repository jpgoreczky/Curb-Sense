import Mapbox, { type CircleLayerStyle, type LineLayerStyle, type SymbolLayerStyle } from "@rnmapbox/maps";

import { color } from "../../../theme/tokens";
import type { PinCollections, ClusterCollections } from "../geojson";
import { LABEL_MIN_ZOOM, RAW_MIN_ZOOM } from "../layers";
import type { MapMode } from "../store";

/**
 * L1 Data Layer: everything drawn inside the Mapbox canvas. Must render as
 * a child of MapView (BaseMapLayer).
 *
 * Layers are declared bottom-to-top in the order of MAP_LAYER_ORDER, so
 * Tier 3 > Tier 1 > Tier 2 regardless of data order.
 *
 * Morphology for SEGMENTS is final (solid / dashed + decay / solid + flag).
 * Point and cluster morphology is interim until UI-4.2.4 adds icon images
 * (city-seal glyph, dashed ring, flag badge): tier is shown by stroke here.
 */

const EMPTY = { type: "FeatureCollection", features: [] } as const satisfies GeoJSON.FeatureCollection;

// Color = status only.
const statusColor = [
  "match",
  ["get", "status"],
  "available",
  color.status.available,
  "conditional",
  color.status.conditional,
  "restricted",
  color.status.restricted,
  color.steel,
] as const;

const isTier = (tier: 1 | 2 | 3) => ["==", ["get", "tier"], tier] as const;

// Curb segments: the geometry is the street centerline; push it to the
// curb side. Mapbox line-offset is positive to the right of the line's
// direction, so offsetSign is +1 (right curb) or -1 (left curb).
const segmentBase: LineLayerStyle = {
  lineColor: statusColor as never,
  lineCap: "round",
  lineJoin: "round",
  lineWidth: ["interpolate", ["exponential", 1.5], ["zoom"], RAW_MIN_ZOOM, 3, 18, 7, 20, 14] as never,
  lineOffset: [
    "interpolate",
    ["exponential", 1.5],
    ["zoom"],
    RAW_MIN_ZOOM,
    ["*", ["get", "offsetSign"], 3],
    18,
    ["*", ["get", "offsetSign"], 9],
    20,
    ["*", ["get", "offsetSign"], 22],
  ] as never,
};

const pointRadius = ["interpolate", ["linear"], ["zoom"], 10, 4, RAW_MIN_ZOOM, 6, 18, 9] as never;

const pointStyles: Record<1 | 2 | 3, CircleLayerStyle> = {
  1: { circleColor: statusColor as never, circleRadius: pointRadius, circleStrokeColor: color.map.halo, circleStrokeWidth: 2 },
  2: {
    circleColor: statusColor as never,
    circleRadius: pointRadius,
    circleOpacity: ["*", ["get", "opacity"], 0.35] as never,
    circleStrokeColor: statusColor as never,
    circleStrokeWidth: 2,
    circleStrokeOpacity: ["get", "opacity"] as never,
  },
  3: { circleColor: statusColor as never, circleRadius: pointRadius, circleStrokeColor: color.ink, circleStrokeWidth: 3 },
};

// Interim flag badge: a small ink dot up-right of the anchor.
const flagStyle: CircleLayerStyle = {
  circleColor: color.ink,
  circleRadius: 4,
  circleStrokeColor: color.map.halo,
  circleStrokeWidth: 1.5,
  circleTranslate: [9, -9],
  circlePitchAlignment: "viewport",
};

const clusterStyle: CircleLayerStyle = {
  circleColor: statusColor as never,
  circleRadius: ["step", ["get", "count"], 14, 10, 17, 100, 21, 1000, 26] as never,
  circleStrokeColor: ["case", isTier(3), color.ink, color.map.halo] as never,
  circleStrokeWidth: ["case", isTier(3), 3, 2] as never,
  circleOpacity: ["case", isTier(2), 0.8, 1] as never,
};

const TEXT_FONT = ["DIN Pro Medium", "Arial Unicode MS Regular"];

const clusterCountStyle: SymbolLayerStyle = {
  textField: ["get", "countLabel"] as never,
  textFont: TEXT_FONT,
  textSize: 12,
  textColor: color.map.clusterText,
  textAllowOverlap: true,
  textIgnorePlacement: true,
};

/** Labels collide by tier priority: Tier 3, then Tier 1, then Tier 2 keep their label. */
export function labelStyle(mode: MapMode): SymbolLayerStyle {
  return {
    visibility: mode === "driving" ? "none" : "visible",
    textField: ["get", "label"] as never,
    textFont: TEXT_FONT,
    textSize: 12,
    textColor: color.ink,
    textHaloColor: color.map.halo,
    textHaloWidth: 1.5,
    textOffset: [0, 1.4],
    textAllowOverlap: false,
    symbolSortKey: ["match", ["get", "tier"], 3, 0, 1, 1, 2] as never,
  };
}

export type DataLayerInput =
  | ({ mode: "pins" } & PinCollections)
  | ({ mode: "clusters" } & ClusterCollections);

export function DataLayer({ data, mapMode }: { data: DataLayerInput | null; mapMode: MapMode }) {
  const pins = data?.mode === "pins" ? data : null;
  const clusters = data?.mode === "clusters" ? data : null;
  const points = pins?.points ?? clusters?.singles ?? EMPTY;
  const flags = data?.flags ?? EMPTY;

  // Every source/layer stays mounted; switching modes swaps data, not layers,
  // so stacking order never changes.
  return (
    <>
      <Mapbox.ShapeSource id="lots" shape={pins?.lots ?? EMPTY}>
        <Mapbox.FillLayer id="lots-fill" style={{ fillColor: color.map.lotFill, fillOpacity: 0.12 }} />
        <Mapbox.LineLayer
          id="lots-outline"
          style={{
            lineColor: color.steel,
            lineWidth: 1.5,
            lineOpacity: ["get", "opacity"] as never,
            lineDasharray: ["case", isTier(2), ["literal", [2, 1.5]], ["literal", [1, 0]]] as never,
          }}
        />
      </Mapbox.ShapeSource>

      <Mapbox.ShapeSource id="segments" shape={pins?.segments ?? EMPTY}>
        <Mapbox.LineLayer
          id="segments-tier2"
          filter={isTier(2) as never}
          style={{ ...segmentBase, lineDasharray: [1.5, 1], lineOpacity: ["get", "opacity"] as never }}
        />
        <Mapbox.LineLayer id="segments-tier1" filter={isTier(1) as never} style={segmentBase} />
        <Mapbox.LineLayer id="segments-tier3" filter={isTier(3) as never} style={segmentBase} />
      </Mapbox.ShapeSource>

      <Mapbox.ShapeSource id="points" shape={points}>
        <Mapbox.CircleLayer id="points-tier2" filter={isTier(2) as never} style={pointStyles[2]} />
        <Mapbox.CircleLayer id="points-tier1" filter={isTier(1) as never} style={pointStyles[1]} />
        <Mapbox.CircleLayer id="points-tier3" filter={isTier(3) as never} style={pointStyles[3]} />
      </Mapbox.ShapeSource>

      <Mapbox.ShapeSource id="flags" shape={flags}>
        <Mapbox.CircleLayer id="tier3-flags" style={flagStyle} />
      </Mapbox.ShapeSource>

      <Mapbox.ShapeSource id="clusters" shape={clusters?.clusters ?? EMPTY}>
        <Mapbox.CircleLayer id="clusters" maxZoomLevel={RAW_MIN_ZOOM} style={clusterStyle} />
        <Mapbox.SymbolLayer id="cluster-counts" maxZoomLevel={RAW_MIN_ZOOM} style={clusterCountStyle} />
      </Mapbox.ShapeSource>

      <Mapbox.ShapeSource id="labels" shape={pins?.labels ?? EMPTY}>
        <Mapbox.SymbolLayer id="labels" minZoomLevel={LABEL_MIN_ZOOM} style={labelStyle(mapMode)} />
      </Mapbox.ShapeSource>
    </>
  );
}
