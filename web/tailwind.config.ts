import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/**
 * "Stripe Slate": flat surfaces, hairline borders, one accent.
 *
 * Severity colours are deliberately NOT the accent. The accent says "you can
 * act here"; severity says "how bad is this". Mixing them makes every button
 * look like an alarm.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F8FAFC",
        surface: "#FFFFFF",
        recessed: "#F1F5F9",
        hairline: "#E2E8F0",
        ink: {
          DEFAULT: "#0F172A",
          secondary: "#475569",
          muted: "#64748B",
        },
        accent: {
          DEFAULT: "#4F46E5",
          hover: "#4338CA",
          soft: "#EEF2FF",
        },
        trace: "#0EA5E9",
      },
      fontFamily: {
        display: ["var(--font-display)", "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        // The only elevation in the product. Borders do the rest.
        hairline: "0 1px 2px rgba(15, 23, 42, 0.03)",
        // A one pixel inner highlight along the top of the primary button.
        lift: "inset 0 1px 0 rgba(255, 255, 255, 0.14), 0 1px 2px rgba(15, 23, 42, 0.08)",
        overlay: "0 12px 32px -8px rgba(15, 23, 42, 0.18), 0 2px 6px rgba(15, 23, 42, 0.06)",
      },
      borderRadius: {
        lg: "0.5rem",
        md: "0.375rem",
        sm: "0.25rem",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [animate],
};

export default config;
