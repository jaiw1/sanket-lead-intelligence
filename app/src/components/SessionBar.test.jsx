import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import SessionBar from './SessionBar'
import { renderScreen, session } from '../test/render'

describe('SessionBar — a name that does not fit', () => {
  const longName = 'Bhuvaneshwari Venkataraghavan-Chandrasekaran'

  it('truncates the signed-in name with an ellipsis instead of letting the header clip it', () => {
    renderScreen(<SessionBar />, { user: session('manager', { full_name: longName }) })

    const name = screen.getByText(longName)
    // AppShell's header row is `overflow-hidden`, so without these the name is cut off
    // mid-character and reads as a shorter, different name.
    expect(name.className).toMatch(/\btruncate\b/)
    expect(name.className).toMatch(/max-w-\[140px\]/)
    // Tailwind's `truncate` does nothing inside a flex item that refuses to shrink.
    expect(name.parentElement.className).toMatch(/\bmin-w-0\b/)
    // The whole name is still reachable, not lost with the pixels.
    expect(name).toHaveAttribute('title', longName)
  })

  it('falls back to the username, truncated the same way', () => {
    renderScreen(<SessionBar />, { user: session('manager', { full_name: null }) })
    const name = screen.getByText('demo.manager')
    expect(name.className).toMatch(/\btruncate\b/)
  })
})
