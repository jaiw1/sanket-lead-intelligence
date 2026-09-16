/** Keyboard-first: the first tab stop on every page jumps past the navigation. */
export default function SkipLink({ target = '#main-content', children = 'Skip to main content' }) {
  return (
    <a
      href={target}
      className="sr-only rounded-br-lg bg-idbi-green px-4 py-2 text-sm font-semibold text-white focus:not-sr-only focus:absolute focus:left-0 focus:top-0 focus:z-[200] focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
    >
      {children}
    </a>
  )
}
