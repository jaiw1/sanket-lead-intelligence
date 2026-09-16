import { ResponsiveContainer } from 'recharts'

/**
 * A chart, plus the same numbers in a form a screen reader can read.
 *
 * Recharts renders an SVG of `<path>` elements: to assistive technology that is a picture
 * with no content. Rather than annotate every series, every chart on this product is
 * wrapped here — the SVG is marked `role="img"` with a summary, and the underlying rows
 * are emitted as a visually hidden table. A sighted user sees the chart; a screen-reader
 * user gets the figures; both get the same data, which is the actual requirement.
 */
export default function ChartFrame({
  title, summary, height = 230, rows, columns, children, className = '', tableCaption,
}) {
  const hasTable = Array.isArray(rows) && rows.length > 0 && Array.isArray(columns) && columns.length > 0

  return (
    <div className={className}>
      <div role="img" aria-label={summary || title} className="w-full">
        <ResponsiveContainer width="100%" height={height}>
          {children}
        </ResponsiveContainer>
      </div>
      {/* The data table is wrapped, not classed, because `sr-only` cannot contain a table:
          it works by clamping the box to 1x1 with overflow hidden, and a `display: table`
          box sizes to its content regardless. Left bare, these tables were laid out at
          their full content width — and since `sr-only` is `position: absolute` with no
          positioned ancestor, they widened the DOCUMENT, so every chart page scrolled
          sideways on a phone. A plain div takes the clamp properly and clips the table. */}
      {hasTable && (
        <div className="sr-only">
        <table>
          <caption>{tableCaption || `${title} — the same figures as a table`}</caption>
          <thead>
            <tr>{columns.map((c) => <th key={c.key} scope="col">{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={row.key ?? row.name ?? i}>
                {columns.map((c, j) => (
                  j === 0
                    ? <th key={c.key} scope="row">{c.format ? c.format(row[c.key], row) : row[c.key]}</th>
                    : <td key={c.key}>{c.format ? c.format(row[c.key], row) : row[c.key]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  )
}

/** Shared recharts styling, so twelve charts do not each invent their own grid colour. */
export const AXIS = { fontSize: 10, fill: '#868DAC' }
export const GRID = '#232B4D'
export const TOOLTIP = {
  background: '#0B1026',
  border: '1px solid #6B7399',
  borderRadius: 8,
  fontSize: 12,
  color: '#EAEDFB',
}
export const COLOR = { teal: '#2DD4BF', amber: '#F5A623', rose: '#FB7185', mid: '#A7AFD4', lo: '#868DAC' }
