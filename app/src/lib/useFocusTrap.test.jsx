import { useRef, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import useFocusTrap from './useFocusTrap'

/**
 * A dialog with a controlled field and an INLINE onClose — the shape every dialog in this
 * product actually has. The regression this file exists for: an unstable `onClose` used to
 * be an effect dependency, so each keystroke tore the trap down, restored focus to the
 * opener, and lost a character on the way back.
 */
function Dialog({ onClose }) {
  const panel = useRef(null)
  const first = useRef(null)
  const [value, setValue] = useState('')
  useFocusTrap(panel, { active: true, onClose: () => onClose(), initialFocusRef: first })
  return (
    <div ref={panel} role="dialog" aria-modal="true" aria-label="Test dialog" tabIndex={-1}>
      <label htmlFor="field">Field</label>
      <input ref={first} id="field" value={value} onChange={(e) => setValue(e.target.value)} />
      <button type="button">Save</button>
    </div>
  )
}

function Harness({ onClose }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open</button>
      {open && <Dialog onClose={() => { setOpen(false); onClose?.() }} />}
    </>
  )
}

describe('useFocusTrap', () => {
  it('keeps every keystroke of a controlled field, with an inline onClose', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Open' }))

    const field = screen.getByLabelText('Field')
    expect(field).toHaveFocus()
    await user.type(field, 'LB-2000002')
    // Before the fix this dropped characters non-deterministically: 'LB-200002', 'LB2000002'.
    expect(field).toHaveValue('LB-2000002')
    expect(field).toHaveFocus()
  })

  it('closes on Escape', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<Harness onClose={onClose} />)
    await user.click(screen.getByRole('button', { name: 'Open' }))
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('returns focus to whatever opened it', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'Open' })
    await user.click(opener)
    expect(screen.getByLabelText('Field')).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(opener).toHaveFocus()
  })

  it('keeps Tab inside the dialog', async () => {
    // What jsdom can actually check. `focusableWithin` filters on `offsetParent` and
    // `getClientRects()`, neither of which jsdom implements, so in this environment the
    // trap sees only the focused element and Tab has nowhere to go but back to it.
    // That is the right OUTCOME to assert here — focus never escapes to the page behind —
    // and the real cycle across several controls is covered by the Playwright suite, which
    // runs in a browser with a layout engine.
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Open' }))
    const dialog = screen.getByRole('dialog')

    await user.tab()
    expect(dialog).toContainElement(document.activeElement)
    await user.tab()
    expect(dialog).toContainElement(document.activeElement)
  })
})
