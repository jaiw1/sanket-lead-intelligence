// Indian-currency + misc formatters used across the cockpit.

export function inr(n) {
  if (n == null) return '—'
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)} L`
  return `₹${Math.round(n).toLocaleString('en-IN')}`
}

export const pct = (x, d = 0) => `${(x * 100).toFixed(d)}%`

export const RAG = {
  red:   { label: 'Red',   text: 'text-rag-red',   bg: 'bg-rag-red',   soft: 'bg-red-50 text-rag-red border-red-200',   dot: 'bg-rag-red' },
  amber: { label: 'Amber', text: 'text-rag-amber', bg: 'bg-rag-amber', soft: 'bg-amber-50 text-rag-amber border-amber-200', dot: 'bg-rag-amber' },
  green: { label: 'Green', text: 'text-rag-green', bg: 'bg-rag-green', soft: 'bg-green-50 text-rag-green border-green-200', dot: 'bg-rag-green' },
}
