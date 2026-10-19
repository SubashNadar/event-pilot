/** @type {import('tailwindcss').Config} */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        surface: v("surface"),
        "surface-2": v("surface-2"),
        border: v("border"),
        ink: v("ink"),
        muted: v("muted"),
        accent: v("accent"),
        "accent-ink": v("accent-ink"),
        "accent-soft": v("accent-soft"),
        success: v("success"),
        danger: v("danger"),
        warn: v("warn"),
        info: v("info"),
      },
      fontFamily: {
        sans: ['Inter', "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        serif: ['"Source Serif 4"', "Georgia", "serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: { xl: "12px", "2xl": "16px", "3xl": "22px" },
      boxShadow: {
        soft: "0 1px 2px rgb(0 0 0 / 0.04), 0 2px 8px rgb(0 0 0 / 0.04)",
        lift: "0 4px 24px rgb(0 0 0 / 0.08), 0 1px 3px rgb(0 0 0 / 0.06)",
      },
      transitionDuration: { 150: "150ms", 200: "200ms", 250: "250ms" },
      keyframes: {
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        "fade-in": { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
        "slide-in-right": { from: { transform: "translateX(100%)" }, to: { transform: "none" } },
        "slide-in-left": { from: { transform: "translateX(-100%)" }, to: { transform: "none" } },
        "slide-in-up": { from: { transform: "translateY(100%)" }, to: { transform: "none" } },
        blink: { "0%,50%": { opacity: "1" }, "50.01%,100%": { opacity: "0" } },
      },
      animation: {
        shimmer: "shimmer 2.2s linear infinite",
        "fade-in": "fade-in 220ms ease-out both",
        "slide-in-right": "slide-in-right 240ms cubic-bezier(.2,.8,.2,1) both",
        "slide-in-left": "slide-in-left 220ms cubic-bezier(.2,.8,.2,1) both",
        "slide-in-up": "slide-in-up 240ms cubic-bezier(.2,.8,.2,1) both",
        blink: "blink 1s step-end infinite",
      },
    },
  },
  plugins: [],
};
