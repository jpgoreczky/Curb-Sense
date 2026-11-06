import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { fetchPinClusters, fetchPins } from "../../api/client";
import { clustersToCollections, pinsToCollections } from "./geojson";
import { useMapStore } from "./store";
import { toViewportRequest } from "./viewport";

const STALE_MS = 30_000;

/**
 * Server state for the visible map. Below RAW_MIN_ZOOM it loads clusters,
 * at or above it raw features. Only one query is enabled at a time; the
 * previous result stays on screen while the next loads (no flash, no spinner).
 * Filter changes only re-run the GeoJSON conversion, never a request.
 */
export function useMapData() {
  const viewport = useMapStore((s) => s.viewport);
  const filter = useMapStore((s) => s.filter);

  const request = useMemo(() => (viewport ? toViewportRequest(viewport.bbox, viewport.zoom) : null), [viewport]);

  const clustersQuery = useQuery({
    queryKey: ["pin-clusters", request?.kind === "clusters" ? request.zoom : null, request?.bbox],
    queryFn: ({ signal }) => {
      if (request?.kind !== "clusters") throw new Error("unreachable: query disabled");
      return fetchPinClusters(request.bbox, request.zoom, signal);
    },
    enabled: request?.kind === "clusters",
    placeholderData: keepPreviousData,
    staleTime: STALE_MS,
  });

  const pinsQuery = useQuery({
    queryKey: ["pins", request?.bbox],
    queryFn: ({ signal }) => {
      if (request?.kind !== "pins") throw new Error("unreachable: query disabled");
      return fetchPins(request.bbox, signal);
    },
    enabled: request?.kind === "pins",
    placeholderData: keepPreviousData,
    staleTime: STALE_MS,
  });

  const mode = request?.kind ?? null;

  const collections = useMemo(() => {
    if (mode === "clusters" && clustersQuery.data) {
      return { mode, ...clustersToCollections(clustersQuery.data.clusters, filter) } as const;
    }
    if (mode === "pins" && pinsQuery.data) {
      return { mode, ...pinsToCollections(pinsQuery.data, filter) } as const;
    }
    return null;
  }, [mode, clustersQuery.data, pinsQuery.data, filter]);

  const active = mode === "clusters" ? clustersQuery : pinsQuery;
  return { collections, error: active.error, isFetching: active.isFetching };
}
