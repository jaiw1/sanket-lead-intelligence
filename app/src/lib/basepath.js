// Vite's BASE_URL is `./` in dev and for the host-agnostic static bundle, and `/drishti/`
// (or `/sanket/`) for the nginx deploy. react-router wants a leading-slash basename or
// nothing, so normalise here rather than in three call sites.
//
// A *relative* base cannot be a router basename — it resolves to '/', which is right for
// the dev server and wrong for a bundle mounted at a sub-path. Any deployment that mounts
// this app below the domain root must build with an absolute `--base` (the nginx deploy
// uses `--base /drishti/`), or set `VITE_ROUTER_BASE` if the two must differ.

export function routerBasename(base = import.meta.env?.VITE_ROUTER_BASE || import.meta.env?.BASE_URL) {
  const raw = String(base ?? '/').trim()
  if (!raw || raw === './' || raw === '.' || raw === '/') return '/'
  if (raw.startsWith('.')) return '/' // a relative base cannot be a router basename
  return `/${raw.replace(/^\/+/, '').replace(/\/+$/, '')}`
}

/** Absolute URL for a file in `public/`, honouring the deployed base. */
export function publicPath(file) {
  const base = String(import.meta.env?.BASE_URL ?? '/')
  return `${base}${base.endsWith('/') ? '' : '/'}${String(file).replace(/^\/+/, '')}`
}
