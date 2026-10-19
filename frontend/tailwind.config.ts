import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        f1: {
          red: "#E10600",
          dark: "#0B0E14",
          surface: "#151922",
          card: "#1D2330",
          border: "#2A3245",
          muted: "#8E9AA8",
          text: "#F3F4F6",
        },
        tyre: {
          soft: "#FF1801",
          medium: "#FFD800",
          hard: "#FFFFFF",
          inter: "#39B54A",
          wet: "#00A0DE",
        },
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "Courier New",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
export default config;
