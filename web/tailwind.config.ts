import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef5ff",
          100: "#d9e8ff",
          200: "#bcd7ff",
          300: "#8ebdff",
          400: "#5898ff",
          500: "#2f72f5",
          600: "#1b55db",
          700: "#1743b1",
          800: "#193b8c",
          900: "#19356f",
        },
      },
    },
  },
  plugins: [],
};

export default config;
