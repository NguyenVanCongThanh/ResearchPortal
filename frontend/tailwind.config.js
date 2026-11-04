/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        portal: {
          void: '#070b14',      // Base deep canvas (slate-950)
          surface: '#0d1527',   // Elevated card container (slate-900 equivalent)
          overlay: '#151f32',   // Active dropdown, terminal and modal surface
          border: '#1e293b',    // Subtle separator (slate-800)
          borderBright: '#334155', // Hover and prominent outline (slate-700)
        },
      },
    },
  },
  plugins: [],
}

