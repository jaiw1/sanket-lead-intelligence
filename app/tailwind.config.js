/** @type {import('tailwindcss').Config} */
//
// SANKET is a dark cockpit. The shared frontend kit (lib/, auth/, components/, the two
// auth screens) was authored in DRISHTi, which is a LIGHT product, so its class names are
// `bg-white`, `bg-slate-50`, `text-slate-900`, `bg-idbi-green`, `text-rag-red`.
//
// Rather than hand-edit ~25 kit files — which would fork the kit and make the next copy
// from DRISHTi a merge — the kit's palette is REMAPPED here: `slate` becomes SANKET's ink
// ramp INVERTED (so `bg-slate-50` is the darkest surface and `text-slate-900` the
// lightest text), `white` becomes the panel surface, and the DRISHTi brand tokens point at
// SANKET's signal colours. The kit then renders correctly dark with zero edits, and one
// commented block documents the whole translation.
//
// Two rules follow from that and are not negotiable:
//   * SANKET's own components use ink/txt/signal and never slate/white.
//   * `text-white` in a kit file means "text on a filled brand button" — which here is
//     dark ink on amber, and is exactly right. Do not "fix" it to a light colour.
//
// Contrast (audited with a WCAG relative-luminance script, see the L11 report):
//   txt.lo was #6B7399 and failed 4.5:1 on EVERY ink surface (3.60 on ink-700, the one
//   the plan named; 4.06 on ink-900 was the best case). It is now #868DAC: 5.75 / 5.49 /
//   5.09 / 4.54 on ink-900/800/700/600. It is still below 4.5 on ink-500 (3.81), which
//   carries no body text — ink-500 is the scrollbar thumb and the cold tier bar.
//   `line` (#26304F) is 1.28:1 on ink-700 — fine for a decorative divider, a 1.4.11
//   failure for a form-control boundary, so controls use `border-line-strong` (#6B7399,
//   3.60:1 on ink-700). The old txt.lo makes a good border; it never made body text.
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 900: '#0B1026', 800: '#0F1530', 700: '#151C3B', 600: '#1D2549', 500: '#28315C' },
        line: { DEFAULT: '#26304F', strong: '#6B7399' },
        signal: { amber: '#F5A623', teal: '#2DD4BF', rose: '#FB7185' },
        txt: { hi: '#EAEDFB', mid: '#A7AFD4', lo: '#868DAC' },

        // ---- kit compatibility layer (see the note above) -------------------------
        white: '#151C3B',           // kit panels  -> ink-700
        slate: {
          50: '#0B1026',            // kit page background -> ink-900
          100: '#0F1530',           // kit inset background -> ink-800
          200: '#26304F',           // kit borders -> line
          300: '#39456F',
          400: '#868DAC',           // kit hint text -> txt-lo (contrast-fixed)
          500: '#A7AFD4',           // kit body text -> txt-mid
          600: '#C0C6E2',
          700: '#D5D9F0',
          800: '#EAEDFB',           // kit headings -> txt-hi
          900: '#F3F5FF',
        },
        'idbi-green': '#F5A623',    // kit primary action -> signal amber
        'idbi-greenlt': '#FFBF4D',
        'rag-red': '#FB7185',
        'rag-amber': '#F5A623',
        'rag-green': '#2DD4BF',
        // The kit's tinted panels (`bg-amber-50`, `bg-red-50`, `bg-violet-50`) would be
        // near-white here, so they are re-pointed at dark tints of the same hue.
        amber: { 50: '#2A2010', 200: '#7A5A1A', 900: '#F5D9A3' },
        red: { 50: '#2A1219', 200: '#7A2F3C' },
        green: { 50: '#0E2622', 200: '#1E6B5E' },
        violet: { 50: '#1C1733', 200: '#4C3F8A', 700: '#C6B8FF' },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
