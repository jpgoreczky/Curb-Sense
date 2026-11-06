import type { PinCluster, PinSummary } from "../../../api/types";
import { clustersToCollections, formatCount, passesFilter, pinsToCollections, recencyOpacity, TIER2_DECAY } from "../geojson";

const NOW = Date.parse("2026-11-06T12:00:00Z");
const daysAgo = (d: number) => new Date(NOW - d * 86_400_000).toISOString();

const LINE: GeoJSON.LineString = { type: "LineString", coordinates: [[-73.99, 40.75], [-73.989, 40.75]] };
const LOT: GeoJSON.Polygon = {
  type: "Polygon",
  coordinates: [[[-73.99, 40.75], [-73.989, 40.75], [-73.989, 40.751], [-73.99, 40.75]]],
};

function pin(overrides: Partial<PinSummary>): PinSummary {
  return {
    id: "p",
    kind: "point",
    anchor_lon: -73.99,
    anchor_lat: 40.75,
    geometry: { type: "Point", coordinates: [-73.99, 40.75] },
    curb_side: null,
    tier: 1,
    status: "available",
    restrictions: {},
    last_verified_at: daysAgo(0),
    display_priority: 1,
    street_name: null,
    from_street: null,
    to_street: null,
    ...overrides,
  };
}

describe("passesFilter", () => {
  it.each([
    [{ tier: 1, status: "restricted" }, "verified", true],
    [{ tier: 3, status: "available" }, "verified", false], // disputed is not verified
    [{ tier: 2, status: "available" }, "free", true],
    [{ tier: 1, status: "conditional" }, "free", false],
    [{ tier: 2, status: "restricted" }, "all", true],
  ] as const)("%o under %s -> %s", (p, filter, expected) => {
    expect(passesFilter(p, filter)).toBe(expected);
  });
});

describe("recencyOpacity", () => {
  it("only decays Tier 2", () => {
    expect(recencyOpacity(1, daysAgo(400), NOW)).toBe(1);
    expect(recencyOpacity(3, null, NOW)).toBe(1);
  });

  it("is full for a week, then fades to the floor", () => {
    expect(recencyOpacity(2, daysAgo(3), NOW)).toBe(1);
    const mid = recencyOpacity(2, daysAgo(48), NOW);
    expect(mid).toBeLessThan(1);
    expect(mid).toBeGreaterThan(TIER2_DECAY.floor);
    expect(recencyOpacity(2, daysAgo(200), NOW)).toBe(TIER2_DECAY.floor);
    expect(recencyOpacity(2, null, NOW)).toBe(TIER2_DECAY.floor);
  });
});

describe("pinsToCollections", () => {
  it("routes each kind to its collection and offsets segments toward the curb", () => {
    const out = pinsToCollections(
      [
        pin({ id: "left", kind: "segment", geometry: LINE, curb_side: "left" }),
        pin({ id: "right", kind: "segment", geometry: LINE, curb_side: "right" }),
        pin({ id: "lot", kind: "lot", geometry: LOT, status: "conditional" }),
        pin({ id: "pt" }),
      ],
      "all",
      NOW,
    );

    expect(out.segments.features.map((f) => [f.properties.id, f.properties.offsetSign])).toEqual([
      ["left", -1], // Mapbox line-offset: negative = left of digitized direction
      ["right", 1],
    ]);
    expect(out.lots.features.map((f) => f.properties.id)).toEqual(["lot"]);
    // Lot anchors get a status dot alongside point pins.
    expect(out.points.features.map((f) => f.properties.id).sort()).toEqual(["lot", "pt"]);
  });

  it("flags every Tier 3 pin at its anchor, whatever its geometry", () => {
    const out = pinsToCollections(
      [pin({ id: "seg", kind: "segment", geometry: LINE, curb_side: "left", tier: 3, anchor_lon: -73.9895 }), pin({ id: "t1" })],
      "all",
      NOW,
    );
    expect(out.flags.features).toHaveLength(1);
    expect(out.flags.features[0].geometry.coordinates).toEqual([-73.9895, 40.75]);
  });

  it("filters before building features", () => {
    const pins = [pin({ id: "t1" }), pin({ id: "t2", tier: 2 }), pin({ id: "t3", tier: 3 })];
    expect(pinsToCollections(pins, "verified", NOW).points.features.map((f) => f.properties.id)).toEqual(["t1"]);
  });

  it("emits no labels until the restrictions schema exists", () => {
    expect(pinsToCollections([pin({ restrictions: { max_hours: 2 } })], "all", NOW).labels.features).toEqual([]);
  });
});

describe("clustersToCollections", () => {
  const rep = (id: string, tier: 1 | 2 | 3, status: "available" | "restricted") => ({
    id,
    kind: "point" as const,
    tier,
    status,
    anchor_lon: -73.99,
    anchor_lat: 40.75,
    last_verified_at: daysAgo(1),
  });
  const cell: PinCluster = {
    cell: "10/1/2",
    lon: -73.991,
    lat: 40.751,
    counts: { all: 5, verified: 1, free: 0 },
    representatives: { all: rep("t3", 3, "restricted"), verified: rep("t1", 1, "available"), free: null },
  };

  it("uses the active filter's count and representative", () => {
    const all = clustersToCollections([cell], "all", NOW);
    expect(all.clusters.features[0].properties).toMatchObject({ count: 5, tier: 3, status: "restricted" });
    expect(all.flags.features.map((f) => f.id)).toEqual(["flag:10/1/2"]); // disputed rep keeps its flag

    const verified = clustersToCollections([cell], "verified", NOW);
    expect(verified.clusters.features).toEqual([]); // one member: drawn as the pin itself
    expect(verified.singles.features[0].properties).toMatchObject({ id: "t1", tier: 1 });

    const free = clustersToCollections([cell], "free", NOW);
    expect([free.clusters.features, free.singles.features]).toEqual([[], []]);
  });
});

it.each([
  [7, "7"],
  [1234, "1.2k"],
  [2000, "2k"],
  [15_400, "15k"],
])("formatCount(%i) = %s", (n, s) => expect(formatCount(n)).toBe(s));
