import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import type { PinSummary } from "../../../api/types";
import { labelStyle } from "../layers/DataLayer";
import { MapScreen } from "../MapScreen";
import { useMapStore } from "../store";

const SEGMENT: PinSummary = {
  id: "seg-1",
  kind: "segment",
  anchor_lon: -73.9895,
  anchor_lat: 40.75,
  geometry: { type: "LineString", coordinates: [[-73.99, 40.75], [-73.989, 40.75]] },
  curb_side: "left",
  tier: 1,
  status: "available",
  restrictions: {},
  last_verified_at: "2026-11-06T00:00:00Z",
  display_priority: 1,
  street_name: "Test St",
  from_street: null,
  to_street: null,
};

let client: QueryClient;

async function renderScreen() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return await render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 47, left: 0, right: 0, bottom: 34 } }}>
      <QueryClientProvider client={client}>
        <MapScreen />
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
}

const fetchMock = jest.fn();

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  useMapStore.setState({ viewport: null, filter: "all", mode: "discovery" });
});

afterEach(() => client?.clear());

it("renders the L0-L3 stack", async () => {
  await renderScreen();
  for (const id of ["base-map", "navigation-layer", "floating-actions-layer", "sheets-layer"]) {
    expect(screen.getByTestId(id)).toBeTruthy();
  }
});

it("fetches clusters below zoom 14 and raw pins at zoom 14+", async () => {
  fetchMock.mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => (url.includes("/pins/clusters") ? { zoom: 12, raw_min_zoom: 14, clusters: [] } : [SEGMENT]),
  }));
  await renderScreen();

  await act(() => useMapStore.getState().setViewport({ bbox: [-74.01, 40.73, -73.97, 40.77], zoom: 12.4 }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(fetchMock.mock.calls[0][0]).toMatch(/\/pins\/clusters\?.*zoom=12/);

  await act(() => useMapStore.getState().setViewport({ bbox: [-73.995, 40.745, -73.985, 40.755], zoom: 15 }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(fetchMock.mock.calls[1][0]).toMatch(/\/pins\?min_lon=/);
});

it("re-filters without a request", async () => {
  fetchMock.mockResolvedValue({ ok: true, json: async () => [SEGMENT] });
  await renderScreen();
  await act(() => useMapStore.getState().setViewport({ bbox: [-73.995, 40.745, -73.985, 40.755], zoom: 15 }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

  await act(() => useMapStore.getState().setFilter("free"));
  await act(() => useMapStore.getState().setFilter("verified"));

  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("hides labels in driving mode", () => {
  expect(labelStyle("discovery").visibility).toBe("visible");
  expect(labelStyle("driving").visibility).toBe("none");
});
