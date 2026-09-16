import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ScreenHelp from './ScreenHelp'
import { HELP } from '../help'
import { NAV } from './AppShell'

describe('ScreenHelp', () => {
  it('renders nothing for a screen with no help entry', () => {
    const { container } = render(<ScreenHelp screen="nope" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('opens a labelled dialog with the copy for that screen', async () => {
    const user = userEvent.setup()
    render(<ScreenHelp screen="queue" />)

    const trigger = screen.getByRole('button', { name: 'Help' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    await user.click(trigger)

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName(HELP.queue.title)
    expect(dialog).toHaveTextContent(HELP.queue.sections[0].heading)
    expect(dialog).toHaveTextContent(HELP.queue.caveat)
  })

  it('closes on Escape and gives focus back to the trigger', async () => {
    const user = userEvent.setup()
    render(<ScreenHelp screen="trust" />)
    const trigger = screen.getByRole('button', { name: 'Help' })

    await user.click(trigger)
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('has an entry for every screen the cockpit links to', () => {
    // Derived from the navigation rather than hard-coded, so a new screen without help
    // copy fails here instead of silently shipping a help button that renders nothing.
    const keys = [...NAV.map((item) => item.to.replace(/^\//, '')), 'login']
    for (const key of keys) {
      expect(HELP[key], `no help copy for the ${key} screen`).toBeTruthy()
      expect(HELP[key].summary.length).toBeGreaterThan(30)
      expect(HELP[key].sections.length).toBeGreaterThan(0)
      expect(HELP[key].caveat.length).toBeGreaterThan(20)
    }
  })

  it('never claims more than the product can do', () => {
    // The help copy is prose a jury will read. It must not promise approval, and it must
    // not resurrect the retired whole-book headline.
    const all = JSON.stringify(HELP)
    expect(all).not.toMatch(/pre-approved|guaranteed conversion|28×|28x/i)
    // "1% → 36%" ranked the whole liability book. It is retired everywhere.
    expect(all).not.toMatch(/1% *(→|->) *36%/)
  })
})
