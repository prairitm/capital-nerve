import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx,css}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0B0F17",
          deep: "#070A11",
          soft: "#0E1320",
        },
        surface: {
          DEFAULT: "#141A26",
          2: "#1B2330",
          3: "#222B3D",
        },
        line: {
          DEFAULT: "#222B3D",
          soft: "#1B2330",
          strong: "#2E3A52",
        },
        ink: {
          DEFAULT: "#E6EAF2",
        mute: "#AAB3C5",
          soft: "#7D879B",
          fade: "#4B5469",
        },
        brand: {
          DEFAULT: "#3B82F6",
          soft: "#60A5FA",
          dim: "#1D4ED8",
        },
        positive: {
          DEFAULT: "#22C55E",
          soft: "#16A34A",
          bg: "rgba(34, 197, 94, 0.12)",
        },
        negative: {
          DEFAULT: "#EF4444",
          soft: "#DC2626",
          bg: "rgba(239, 68, 68, 0.12)",
        },
        mixed: {
          DEFAULT: "#F59E0B",
          soft: "#D97706",
          bg: "rgba(245, 158, 11, 0.14)",
        },
        neutral: {
          DEFAULT: "#3B82F6",
          soft: "#2563EB",
          bg: "rgba(59, 130, 246, 0.12)",
        },
        low: {
          DEFAULT: "#64748B",
          bg: "rgba(100, 116, 139, 0.14)",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(255,255,255,0.035) inset, 0 14px 35px rgba(0,0,0,0.18)",
        glow: "0 0 0 1px rgba(59, 130, 246, 0.4), 0 0 32px rgba(96, 165, 250, 0.25)",
      },
      backgroundImage: {
        "radial-fade":
          "radial-gradient(circle at 20% 0%, rgba(59,130,246,0.15), transparent 50%), radial-gradient(circle at 80% 100%, rgba(96,165,250,0.08), transparent 50%)",
      },
    },
  },
  plugins: [],
} satisfies Config;
