import Mapbox, { type MapState } from "@rnmapbox/maps";
import type { ReactNode } from "react";
import { StyleSheet } from "react-native";

import { env } from "../../../config/env";
import { useMapStore } from "../store";
import { boundsToBBox } from "../viewport";

/**
 * L0 Base Map: the Mapbox canvas. L1 (DataLayer) renders as its children,
 * because Mapbox sources and layers must live inside the MapView.
 * Reports the settled camera to the store; data fetching keys off that.
 */
export function BaseMapLayer({ children }: { children?: ReactNode }) {
  const setViewport = useMapStore((s) => s.setViewport);

  const onMapIdle = (state: MapState) => {
    const { bounds, zoom } = state.properties;
    setViewport({ bbox: boundsToBBox(bounds.ne, bounds.sw), zoom });
  };

  return (
    <Mapbox.MapView
      testID="base-map"
      style={StyleSheet.absoluteFill}
      styleURL={env.mapboxStyleUrl || Mapbox.StyleURL.Street}
      onMapIdle={onMapIdle}
      scaleBarEnabled={false}
      // Leave the bottom edge to L2 FABs and the L3 sheet.
      logoPosition={{ top: 8, left: 8 }}
      attributionPosition={{ top: 8, right: 8 }}
      pitchEnabled={false}
    >
      <Mapbox.Camera
        defaultSettings={{ centerCoordinate: env.initialCenter, zoomLevel: env.initialZoom }}
      />
      {children}
    </Mapbox.MapView>
  );
}
