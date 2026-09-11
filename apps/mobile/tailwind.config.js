/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./App.{js,jsx,ts,tsx}", "./src/**/*.{js,jsx,ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        // Chrome / UI (never used for parking status)
        ink: "#1B1D1F",
        paper: "#FDFDFB",
        steel: "#6B7280",
        line: "#E7E5E0",
        // Brand accent — used sparingly (active states, primary FAB)
        "curb-yellow": "#E8AA1F",
        // Status colors — RESERVED strictly for availability (green/yellow/red).
        // Never use these for tier distinction — tier is shape/morphology only.
        "status-green": "#2E7D46",
        "status-yellow": "#E8AA1F",
        "status-red": "#C1443B",
      },
      fontSize: {
        // Type scale — single family (system-ui/Inter), hierarchy via size/weight only
        xs: "12px",
        sm: "13px",
        base: "14px",
        md: "15px",
        lg: "17px",
        xl: "19px",
        "2xl": "24px",
      },
      spacing: {
        // Spacing units, 4px base grid
        1: "4px",
        2: "8px",
        2.5: "10px",
        3: "12px",
        3.5: "14px",
        4: "16px",
        5: "20px",
        6: "24px",
        8: "32px",
      },
      borderRadius: {
        sm: "8px",
        md: "12px",
        lg: "16px",
        xl: "24px",
        full: "9999px",
      },
    },
  },
  plugins: [],
};