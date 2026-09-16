import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AppShell, { NAV, homeFor } from './AppShell'
import { renderScreen, session } from '../test/render'

const navFor = (role) => NAV.filter((i) => i.roles.includes(role)).map((i) => i.to)

describe('AppShell — the navigation mirrors x-roles', () => {
  it('gives a manager the dashboard and the model scorecard', () => {
    expect(navFor('M')).toContain('/dashboard')
    expect(navFor('M')).toContain('/trust')
  })

  it('gives a relationship manager the queue but neither manager screen', () => {
    const rm = navFor('RM')
    expect(rm).toContain('/queue')
    expect(rm).toContain('/consent')
    // sanketFunnel is x-roles M, A — and it is the only source for both of these.
    expect(rm).not.toContain('/dashboard')
    expect(rm).not.toContain('/trust')
    expect(rm).not.toContain('/admin')
  })

  it('gives a credit officer only the two meta screens the contract allows them', () => {
    // A credit officer has no sanket/* operation at all; meta/sync and meta/provenance
    // are A, M, CO, RM.
    expect(navFor('CO').sort()).toEqual(['/radar', '/sources'])
  })

  it('gives an administrator everything', () => {
    expect(navFor('A')).toHaveLength(NAV.length)
  })
})

describe('homeFor — nobody lands on a screen they cannot see', () => {
  it('sends each role somewhere its own role permits', () => {
    expect(homeFor('manager')).toBe('/dashboard')
    expect(homeFor('admin')).toBe('/dashboard')
    expect(homeFor('relationship_manager')).toBe('/queue')
    expect(homeFor('credit_officer')).toBe('/sources')
  })

  it('checks every landing route against that role’s own navigation', () => {
    for (const role of ['A', 'M', 'CO', 'RM']) {
      const long = { A: 'admin', M: 'manager', CO: 'credit_officer', RM: 'relationship_manager' }[role]
      expect(navFor(role), `${role} lands on a screen it cannot see`).toContain(homeFor(long))
    }
  })
})

describe('AppShell — the primary navigation is one tab stop', () => {
  it('is a toolbar with a roving tabindex', async () => {
    renderScreen(<AppShell title="Test"><p>body</p></AppShell>, { path: '/queue', user: session('manager') })
    const toolbar = screen.getByRole('toolbar', { name: 'Screens' })
    const links = within(toolbar).getAllByRole('link')
    // Exactly one tab stop: eight links would otherwise be eight presses before the screen.
    expect(links.filter((l) => l.getAttribute('tabindex') === '0')).toHaveLength(1)
    expect(links.filter((l) => l.getAttribute('tabindex') === '-1')).toHaveLength(links.length - 1)
  })

  it('moves focus with the arrow keys, and wraps', async () => {
    const user = userEvent.setup()
    renderScreen(<AppShell title="Test"><p>body</p></AppShell>, { path: '/queue', user: session('manager') })
    const toolbar = screen.getByRole('toolbar', { name: 'Screens' })
    const links = within(toolbar).getAllByRole('link')

    links[0].focus()
    await user.keyboard('{ArrowRight}')
    expect(links[1]).toHaveFocus()
    await user.keyboard('{End}')
    expect(links[links.length - 1]).toHaveFocus()
    await user.keyboard('{ArrowRight}')
    expect(links[0]).toHaveFocus()
  })

  it('renders a skip-link target', () => {
    renderScreen(<AppShell title="Test"><p>body</p></AppShell>, { path: '/queue', user: session('manager') })
    expect(document.getElementById('main-content')).toBeInTheDocument()
  })
})
