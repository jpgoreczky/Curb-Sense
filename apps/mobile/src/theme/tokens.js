/**
 * SETUP-1.5 design tokens: the single source for Tailwind (NativeWind
 * classes) and for Mapbox layer styles (which take raw values, not classes).
 *
 * CommonJS on purpose: tailwind.config.js requires it at build time.
 * Types live in tokens.d.ts.
 *
 * Color rules (PRD 3.1):
 * - `status` colors mean availability ONLY. Never use them for tier, chrome,
 *   brand or decoration.
 * - Tier is shown by shape/style (solid, dashed, flag), never by color.
 */

const color = {
  // Chrome / UI. Never used for parking status.
  ink: "#1B1D1F",
  paper: "#FDFDFB",
  steel: "#6B7280",
  line: "#E7E5E0",

  // Brand accent: active states and the primary FAB.
  // NOTE: currently identical to status.conditional. See WP-2b notes;
  // a brand color must not read as "conditional/paid" on the map.
  brand: "#E8AA1F",

  // Status: RESERVED for availability.
  status: {
    available: "#2E7D46", // green: free / available
    conditional: "#E8AA1F", // yellow: conditional / paid
    restricted: "#C1443B", // red: restricted
  },

  // Map-only neutrals (lot fills, cluster text, halos).
  map: {
    lotFill: "#6B7280",
    halo: "#FFFFFF",
    clusterText: "#FFFFFF",
  },
};

const fontSize = {
  // Single family (system-ui / Inter); hierarchy via size and weight only.
  xs: 12,
  sm: 13,
  base: 14,
  md: 15,
  lg: 17,
  xl: 19,
  "2xl": 24,
};

// 4 px base grid.
const spacing = {
  1: 4,
  2: 8,
  2.5: 10,
  3: 12,
  3.5: 14,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
};

const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  full: 9999,
};

// Minimum touch targets (dp). Driving mode uses the larger one (UI-4.3.5).
const touchTarget = {
  min: 44,
  driving: 60,
};

module.exports = { color, fontSize, spacing, radius, touchTarget };
