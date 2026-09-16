import { ShieldAlert } from 'lucide-react'

/** Hosts where plain HTTP is legitimate (the dev server, and only the dev server). */
const LOCAL = new Set(['localhost', '127.0.0.1', '::1', '[::1]', '0.0.0.0'])

export function isInsecureContext(location = typeof window === 'undefined' ? null : window.location) {
  if (!location) return false
  const protocol = location.protocol
  if (protocol === 'https:' || protocol === 'file:') return false
  const host = String(location.hostname || '').toLowerCase()
  if (LOCAL.has(host) || host.endsWith('.localhost')) return false
  return true
}

/**
 * Plan section A: "Never a login form over plain HTTP." Over HTTP on a non-local host the
 * login screen refuses to render at all rather than collecting a bank password in clear.
 * The self-signed-certificate deploy is the expected case behind this: the fix is to accept
 * the published fingerprint, not to fall back to HTTP.
 */
export default function InsecureContextNotice({ href }) {
  const secure = href || (typeof window === 'undefined' ? '' : window.location.href.replace(/^http:/, 'https:'))
  return (
    <main
      id="main-content"
      className="grid min-h-screen place-items-center bg-slate-100 px-6"
      data-testid="insecure-notice"
    >
      <div className="w-full max-w-md space-y-4 rounded-xl border border-rag-red/30 bg-white p-6 text-center shadow-sm">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-rag-red/10 text-rag-red">
          <ShieldAlert size={24} aria-hidden="true" />
        </div>
        <h1 className="text-lg font-extrabold text-slate-900">This connection is not secure</h1>
        <p className="text-sm leading-relaxed text-slate-600" role="alert">
          The sign-in form will not be shown over plain HTTP. A password typed here would cross the
          network in clear text.
        </p>
        <a
          href={secure}
          className="inline-block rounded-lg bg-idbi-green px-4 py-2 text-sm font-semibold text-white transition hover:bg-idbi-greenlt focus:outline-none focus-visible:ring-2 focus-visible:ring-idbi-green focus-visible:ring-offset-2"
        >
          Reload over HTTPS
        </a>
        <p className="text-xs leading-relaxed text-slate-400">
          If the certificate is self-signed, compare its SHA-256 fingerprint with the one published in
          the project README before accepting it.
        </p>
      </div>
    </main>
  )
}
