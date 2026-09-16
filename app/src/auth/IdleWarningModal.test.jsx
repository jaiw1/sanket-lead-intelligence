import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import IdleWarningModal from './IdleWarningModal'

const open = (props = {}) => render(
  <IdleWarningModal
    open
    secondsLeft={95}
    pinging={false}
    onStayAlive={() => {}}
    onSignOut={() => {}}
    {...props}
  />,
)

describe('IdleWarningModal', () => {
  it('renders nothing when closed', () => {
    render(<IdleWarningModal open={false} secondsLeft={120} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('is a labelled modal dialog with the time remaining', () => {
    open()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName('Still there?')
    expect(dialog).toHaveTextContent('1:35')
  })

  it('puts focus on "Stay signed in" and traps Tab inside the dialog', async () => {
    const user = userEvent.setup()
    render(
      <>
        <button type="button">outside</button>
        <IdleWarningModal open secondsLeft={60} onStayAlive={() => {}} onSignOut={() => {}} />
      </>,
    )

    const stay = await screen.findByRole('button', { name: 'Stay signed in' })
    await vi.waitFor(() => expect(stay).toHaveFocus())

    const signOut = screen.getByRole('button', { name: /sign out now/i })
    await user.tab()
    expect(document.activeElement === signOut || document.activeElement === stay).toBe(true)
    expect(screen.getByRole('button', { name: 'outside' })).not.toHaveFocus()
  })

  it('offers both ways out', async () => {
    const user = userEvent.setup()
    const onStayAlive = vi.fn()
    const onSignOut = vi.fn()
    open({ onStayAlive, onSignOut })

    await user.click(screen.getByRole('button', { name: 'Stay signed in' }))
    expect(onStayAlive).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: /sign out now/i }))
    expect(onSignOut).toHaveBeenCalledOnce()
  })

  it('disables the ping button while the ping is in flight', () => {
    open({ pinging: true })
    expect(screen.getByRole('button', { name: /keeping you signed in/i })).toBeDisabled()
  })
})
