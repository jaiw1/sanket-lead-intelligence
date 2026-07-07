/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 900: '#0B1026', 800: '#0F1530', 700: '#151C3B', 600: '#1D2549', 500: '#28315C' },
        line: '#26304F',
        signal: { amber: '#F5A623', teal: '#2DD4BF', rose: '#FB7185' },
        txt: { hi: '#EAEDFB', mid: '#A7AFD4', lo: '#6B7399' },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
