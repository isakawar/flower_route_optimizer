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
        bg: {
          base: "#0a0a12",
          deep: "#06060e",
          card: "#12121e",
          raised: "#191928",
        },
        border: {
          DEFAULT: "#252538",
          subtle: "#1c1c2e",
          accent: "#3a2a40",
        },
        rose: {
          50: "#fdf0f6",
          100: "#fce4f0",
          200: "#fac9e2",
          300: "#f5a0cc",
          400: "#ed6bae",
          500: "#e24191",
          600: "#cc2474",
          700: "#ab185c",
          800: "#8e174d",
          900: "#771843",
          950: "#470827",
          soft: "#d4a5bf",
          muted: "#8a6a7e",
          glow: "rgba(212, 165, 191, 0.12)",
        },
        gold: {
          soft: "#c9a96e",
          muted: "#8a7a5e",
          glow: "rgba(201, 169, 110, 0.12)",
        },
        text: {
          primary: "#f0ece8",
          secondary: "#9090a8",
          muted: "#5a5a70",
          accent: "#d4a5bf",
        },
      },
      fontFamily: {
        serif: ["Playfair Display", "Georgia", "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        "rose-glow": "0 0 40px rgba(212, 165, 191, 0.08)",
        "rose-sm": "0 0 16px rgba(212, 165, 191, 0.06)",
        card: "0 4px 24px rgba(0, 0, 0, 0.4), 0 1px 2px rgba(0, 0, 0, 0.2)",
        "card-hover":
          "0 8px 40px rgba(0, 0, 0, 0.5), 0 0 24px rgba(212, 165, 191, 0.06)",
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
      },
      animation: {
        "spin-slow": "spin 3s linear infinite",
        "pulse-subtle": "pulseSubtle 2s ease-in-out infinite",
        "fade-up": "fadeUp 0.5s ease-out forwards",
        shimmer: "shimmer 2s linear infinite",
        "float": "float 6s ease-in-out infinite",
      },
      keyframes: {
        pulseSubtle: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-8px)" },
        },
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        shimmer:
          "linear-gradient(90deg, transparent 0%, rgba(212,165,191,0.08) 50%, transparent 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
