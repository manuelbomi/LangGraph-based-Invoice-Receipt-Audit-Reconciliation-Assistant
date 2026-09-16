/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          200: "#b3ccff",
          300: "#80a8ff",
          400: "#4d7fff",
          500: "#265ef2",
          600: "#1a48d1",
          700: "#1638a8",
          800: "#152f83",
          900: "#152a68",
        },
      },
    },
  },
  plugins: [],
};
