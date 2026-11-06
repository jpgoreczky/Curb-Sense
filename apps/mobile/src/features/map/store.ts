import { create } from "zustand";

import type { BBox } from "../../api/types";

/** Filter chips (UI-4.2.3). "verified" = Tier 1 only; "free" = status available. */
export type PinFilter = "all" | "verified" | "free";
/** Discovery (planning) vs. driving (UI-4.3). Driving hides labels and prunes pins. */
export type MapMode = "discovery" | "driving";

export interface Viewport {
  bbox: BBox;
  zoom: number;
}

interface MapState {
  viewport: Viewport | null;
  filter: PinFilter;
  mode: MapMode;
  setViewport: (viewport: Viewport) => void;
  setFilter: (filter: PinFilter) => void;
  setMode: (mode: MapMode) => void;
}

export const useMapStore = create<MapState>()((set) => ({
  viewport: null,
  filter: "all",
  mode: "discovery",
  setViewport: (viewport) => set({ viewport }),
  setFilter: (filter) => set({ filter }),
  setMode: (mode) => set({ mode }),
}));
