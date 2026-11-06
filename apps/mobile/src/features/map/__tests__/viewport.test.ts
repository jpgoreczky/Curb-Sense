import type { BBox } from "../../../api/types";
import { RAW_MIN_ZOOM } from "../layers";
import { boundsToBBox, toViewportRequest } from "../viewport";

// Roughly what a phone shows at zoom 13 over midtown Manhattan.
const VIEW_Z13: BBox = [-74.008, 40.735, -73.972, 40.765];

describe("toViewportRequest", () => {
  it("asks for clusters below street zoom and raw pins at or above it", () => {
    expect(toViewportRequest(VIEW_Z13, 13.7)).toMatchObject({ kind: "clusters", zoom: 13 });
    expect(toViewportRequest(VIEW_Z13, RAW_MIN_ZOOM)).toMatchObject({ kind: "pins" });
  });

  it("pads and rounds outward, so the request covers the view", () => {
    const { bbox } = toViewportRequest(VIEW_Z13, 13);
    expect(bbox[0]).toBeLessThan(VIEW_Z13[0]);
    expect(bbox[1]).toBeLessThan(VIEW_Z13[1]);
    expect(bbox[2]).toBeGreaterThan(VIEW_Z13[2]);
    expect(bbox[3]).toBeGreaterThan(VIEW_Z13[3]);
  });

  it("gives nearby cameras the same request (shared cache key)", () => {
    const nudged: BBox = [VIEW_Z13[0] + 0.0004, VIEW_Z13[1] + 0.0004, VIEW_Z13[2] + 0.0004, VIEW_Z13[3] + 0.0004];
    expect(toViewportRequest(nudged, 13.2)).toEqual(toViewportRequest(VIEW_Z13, 13.9));
  });

  it("stays inside the API's per-zoom size guard for clusters", () => {
    // A tablet in landscape at zoom 10 over a wide area.
    const { bbox, zoom } = toViewportRequest([-76, 39, -72, 42.5], 10) as { bbox: BBox; zoom: number };
    const maxSpan = (360 * 4) / 2 ** zoom;
    expect(bbox[2] - bbox[0]).toBeLessThanOrEqual(maxSpan);
    expect(bbox[3] - bbox[1]).toBeLessThanOrEqual(maxSpan);
  });

  it("clamps to valid coordinates", () => {
    const { bbox } = toViewportRequest([-180, -85, 180, 85], 0);
    expect(bbox[0]).toBeGreaterThanOrEqual(-180);
    expect(bbox[2]).toBeLessThanOrEqual(180);
    expect(bbox[1]).toBeGreaterThanOrEqual(-90);
    expect(bbox[3]).toBeLessThanOrEqual(90);
  });
});

it("boundsToBBox orders ne/sw into min/max", () => {
  expect(boundsToBBox([-73.9, 40.8], [-74.0, 40.7])).toEqual([-74.0, 40.7, -73.9, 40.8]);
});
