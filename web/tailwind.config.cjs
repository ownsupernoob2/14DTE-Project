/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        mirror: {
          black: "#000000",
          white: "#FFFFFF",
          gray: "#111111",
          border: "#2A2A2A"
        }
      },
      boxShadow: {
        glow: "0 0 40px rgba(255,255,255,0.08)",
        soft: "0 12px 40px rgba(0,0,0,0.5)"
      }
    }
  },
  plugins: []
}
