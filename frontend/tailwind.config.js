/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fef2f2",
          500: "#ef4444",
          600: "#dc2626",
          700: "#b91c1c",
        },
      },
      fontFamily: {
        // Iowan Old Style and Charter are the faces iOS Safari Reader itself
        // uses; both ship on Apple platforms, with graceful fallbacks elsewhere.
        serif: [
          "Iowan Old Style",
          "Charter",
          "Palatino",
          "Georgia",
          "Times New Roman",
          "serif",
        ],
      },
    },
  },
  plugins: [],
};
