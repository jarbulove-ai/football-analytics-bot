/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#080b10",
        panel: "#11161e",
        panelSoft: "#171d27",
        line: "#252d38",
        accent: "#7187ff",
        lime: "#b9f44c",
        gold: "#f5c85b",
      },
      boxShadow: {
        card: "0 16px 40px rgba(0, 0, 0, 0.28)",
        nav: "0 -16px 40px rgba(0, 0, 0, 0.3)",
      },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "0.45" },
          "50%": { opacity: "0.85" },
        },
      },
      animation: {
        rise: "rise 300ms ease-out both",
        pulseSoft: "pulseSoft 1.5s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
