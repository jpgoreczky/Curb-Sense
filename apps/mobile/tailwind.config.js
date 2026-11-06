/** @type {import('tailwindcss').Config} */
const { color, fontSize, spacing, radius } = require("./src/theme/tokens");

const px = (scale) => Object.fromEntries(Object.entries(scale).map(([k, v]) => [k, `${v}px`]));

module.exports = {
  content: ["./App.{js,jsx,ts,tsx}", "./src/**/*.{js,jsx,ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        // Chrome / UI (never used for parking status)
        ink: color.ink,
        paper: color.paper,
        steel: color.steel,
        line: color.line,
        // Brand accent: used sparingly (active states, primary FAB)
        "curb-yellow": color.brand,
        // Status colors: RESERVED strictly for availability (green/yellow/red).
        // Never use these for tier distinction; tier is shape/morphology only.
        "status-green": color.status.available,
        "status-yellow": color.status.conditional,
        "status-red": color.status.restricted,
      },
      fontSize: px(fontSize),
      spacing: px(spacing),
      borderRadius: px(radius),
    },
  },
  plugins: [],
};
