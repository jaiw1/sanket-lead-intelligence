// shared formatters for the SANKET cockpit

export const inr = (n) => {
  if (n == null) return '—'
  if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`
  if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(1)} L`
  return `₹${Math.round(n).toLocaleString('en-IN')}`
}

export const pct = (x, d = 0) => `${(x * 100).toFixed(d)}%`

export const TIER = {
  hot:  { label: 'Hot',  text: 'text-signal-teal',  chip: 'bg-signal-teal/15 text-signal-teal border-signal-teal/40' },
  warm: { label: 'Warm', text: 'text-signal-amber', chip: 'bg-signal-amber/15 text-signal-amber border-signal-amber/40' },
  cold: { label: 'Cold', text: 'text-txt-lo',       chip: 'bg-ink-600 text-txt-mid border-line' },
}

export const PRODUCT = {
  home: { label: 'Home Loan', short: 'HL' },
  auto: { label: 'Auto Loan', short: 'AL' },
  pl:   { label: 'Personal Loan', short: 'PL' },
}
