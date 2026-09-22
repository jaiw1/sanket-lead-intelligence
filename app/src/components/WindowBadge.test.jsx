import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import WindowBadge from './WindowBadge'

// The badge is the one place an RM reads a number of days, so it is the one place an
// undated answer does the most damage: "Closed 372 days ago" beside a book scored three
// weeks ago is a fact about the calendar, not about the lead.

const SCORED = '2026-09-01T00:00:00+00:00'

describe('WindowBadge — the phrase is counted from the run’s anchor', () => {
  it('counts the days from the anchor, not from today', () => {
    render(<WindowBadge lead={{ product: 'education', windowDays: 7, contactBy: '2026-09-07T00:00:00Z' }} asOf={SCORED} />)
    const badge = screen.getByTestId('window-badge')
    expect(badge).toHaveTextContent('6 days left')
    expect(badge).toHaveAttribute('data-window-state', 'open')
    expect(badge).toHaveAttribute('data-window-as-of', SCORED)
  })

  it('names the anchor, and says it is frozen, in the title and for a screen reader', () => {
    render(<WindowBadge lead={{ product: 'education', windowDays: 7, contactBy: '2026-09-07T00:00:00Z' }} asOf={SCORED} />)
    const badge = screen.getByTestId('window-badge')
    expect(badge).toHaveAttribute('title', expect.stringContaining('as of 1 Sep 2026 (frozen snapshot)'))
    expect(badge).toHaveTextContent(/as of 1 Sep 2026 \(frozen snapshot\)/)
  })

  it('omits the anchor entirely when the payload declares none', () => {
    // A lead with no `as_of` is answered against the wall clock, exactly as before, and
    // the badge must not invent a date it was not given.
    render(<WindowBadge lead={{ product: 'home', windowDays: 14, abandonTs: '2026-09-01T00:00:00Z' }} />)
    const badge = screen.getByTestId('window-badge')
    expect(badge).not.toHaveAttribute('data-window-as-of')
    expect(badge.getAttribute('title')).not.toMatch(/as of/)
  })

  it('does not call a same-day anchor a frozen snapshot', () => {
    // A nightly run scoring last night's book declares last night. Calling that frozen
    // would be noise on every real run the platform will ever serve.
    const today = new Date().toISOString()
    render(<WindowBadge lead={{ product: 'home', windowDays: 14, abandonTs: today }} asOf={today} />)
    const badge = screen.getByTestId('window-badge')
    expect(badge.getAttribute('title')).toMatch(/as of/)
    expect(badge.getAttribute('title')).not.toMatch(/frozen snapshot/)
  })

  it('still says UNKNOWN — never closed — for a lead it cannot place', () => {
    render(<WindowBadge lead={{ product: 'home' }} asOf={SCORED} />)
    expect(screen.getByTestId('window-badge')).toHaveAttribute('data-window-state', 'unknown')
    expect(screen.getByTestId('window-badge')).toHaveTextContent('Window unknown')
  })
})
