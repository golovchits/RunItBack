/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: {
          0: "#0b0d10",
          1: "#101317",
          2: "#161a1f",
          3: "#1c2128",
          4: "#232932",
        },
        line: {
          DEFAULT: "#262c35",
          strong: "#323a45",
        },
        text: {
          0: "#e8ecf1",
          1: "#b4bcc7",
          2: "#7c8593",
          3: "#545c68",
          mono: "#c9d1db",
        },
        agent: {
          paper: "#d98040",
          auditor: "#5a8cd9",
          validator: "#4fa579",
          reviewer: "#9a7fd1",
        },
        severity: {
          critical: "#e55353",
          high: "#e08340",
          medium: "#d6a54a",
          low: "#9ba34a",
          info: "#7c8593",
        },
        verdict: {
          reproducible: "#4fa579",
          likely: "#86a74a",
          questionable: "#d6a54a",
          not_reproducible: "#e55353",
          inconclusive: "#7c8593",
        },
        code: {
          bg: "#0f1216",
          gutter: "#7c8593",
          hl: "rgba(229,83,83,0.14)",
          hlEdge: "#e55353",
          addBg: "rgba(79,165,121,0.12)",
          delBg: "rgba(229,83,83,0.12)",
          addFg: "#6fbf95",
          delFg: "#f07a7a",
        },
      },
      fontFamily: {
        ui: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      borderRadius: {
        xs: "3px",
        sm: "4px",
        md: "6px",
        lg: "8px",
        xl: "12px",
      },
      boxShadow: {
        innerLine: "inset 0 0 0 1px #262c35",
        sm: "0 1px 0 rgba(0,0,0,0.2), 0 1px 2px rgba(0,0,0,0.15)",
        md: "0 1px 0 rgba(0,0,0,0.25), 0 4px 16px rgba(0,0,0,0.25)",
        lg: "0 1px 0 rgba(0,0,0,0.3), 0 12px 40px rgba(0,0,0,0.4)",
      },
      keyframes: {
        pulseDot: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "pulse-dot": "pulseDot 1.6s ease-in-out infinite",
        shimmer: "shimmer 2s linear infinite",
      },
    },
  },
  plugins: [],
};
