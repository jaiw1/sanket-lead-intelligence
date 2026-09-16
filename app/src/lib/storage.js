// localStorage, but it cannot take the page down.
//
// Private windows, embedded webviews and locked-down bank desktops all have a
// localStorage that is absent or throws on access. Nothing this app stores there is
// load-bearing — remembering that the tour was dismissed is not worth a white screen.

const backend = () => {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null
  } catch {
    return null
  }
}

export const storage = {
  get(key) {
    try { return backend()?.getItem(key) ?? null } catch { return null }
  },
  set(key, value) {
    try { backend()?.setItem(key, value) } catch { /* quota, or storage disabled */ }
  },
  remove(key) {
    try { backend()?.removeItem(key) } catch { /* ignore */ }
  },
}

export default storage
