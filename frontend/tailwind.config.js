/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#00DC82',
        secondary: '#7C3AED',
        dark: '#0F172A',
        darker: '#020617',
      },
    },
  },
  plugins: [],
}
