import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AppShell, { NAV, STATIC_HIDDEN, homeFor } from './AppShell'
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

  it('gives a relationship manager neither the radar nor data sources', () => {
    // Business radar is an appendix on public company filings, kept for an administrator's
    // reference; Data sources is the platform's own plumbing, and metaSync/metaProvenance
    // narrowed to A and M with it.
    expect(navFor('RM')).not.toContain('/radar')
    expect(navFor('RM')).not.toContain('/sources')
  })

  it('gives a credit officer nothing at all — SANKET is not their product', () => {
    // A credit officer has no sanket/* operation, and the two screens that used to be
    // theirs here read metaSync/metaProvenance, which are now A and M.
    expect(navFor('CO')).toEqual([])
  })

  it('gives a manager data sources but not the radar', () => {
    expect(navFor('M')).toContain('/sources')
    expect(navFor('M')).not.toContain('/radar')
  })

  it('gives an administrator everything', () => {
    expect(navFor('A')).toHaveLength(NAV.length)
    expect(navFor('A')).toContain('/radar')
  })
})

describe('homeFor — nobody lands on a screen they cannot see', () => {
  it('sends each role somewhere its own role permits', () => {
    expect(homeFor('manager')).toBe('/dashboard')
    expect(homeFor('admin')).toBe('/dashboard')
    expect(homeFor('relationship_manager')).toBe('/queue')
  })

  it('checks every landing route against that role’s own navigation', () => {
    for (const role of ['A', 'M', 'RM']) {
      const long = { A: 'admin', M: 'manager', RM: 'relationship_manager' }[role]
      expect(navFor(role), `${role} lands on a screen it cannot see`).toContain(homeFor(long))
    }
  })

  // There is no honest answer for a credit officer any more: SANKET has no screen for
  // them. They land on the queue and are told so, inside the shell, rather than being
  // pointed at somebody else's plumbing.
  it('lands a credit officer on the queue, which then refuses them by name', () => {
    expect(homeFor('credit_officer')).toBe('/queue')
    expect(navFor('CO')).toEqual([])
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

  // The frozen bundle has no session and no backend, so Administration would open a user
  // table and an audit log with nothing behind them. DRISHTi's shell already drops it.
  it('hides Administration in the frozen bundle', () => {
    renderScreen(<AppShell title="Test"><p>body</p></AppShell>, { path: '/queue', mode: 'static', user: null })
    const toolbar = screen.getByRole('toolbar', { name: 'Screens' })
    expect(within(toolbar).queryByRole('link', { name: /Administration|Admin/i })).not.toBeInTheDocument()
    expect(within(toolbar).getByRole('link', { name: /Lead queue|Queue/i })).toBeInTheDocument()
  })

  // Static mode has no role, so it needs a rule of its own: what a manager sees, minus the
  // screens that are an administrator's alone. Data sources is a manager's, so it stays;
  // the radar is not, so it goes.
  it('shows the frozen bundle a manager’s screens, minus the admin-only ones', () => {
    renderScreen(<AppShell title="Test"><p>body</p></AppShell>, { path: '/queue', mode: 'static', user: null })
    const toolbar = screen.getByRole('toolbar', { name: 'Screens' })
    expect(within(toolbar).getByRole('link', { name: /Data sources|Sources/i })).toBeInTheDocument()
    expect(within(toolbar).queryByRole('link', { name: /Business radar|Radar/i })).not.toBeInTheDocument()
    expect(STATIC_HIDDEN).toEqual(new Set(['/admin', '/radar']))
  })
})

/**
 * The phone bar carries the same screens as the toolbar, for every role.
 *
 * jsdom does no layout: `hidden sm:block` hides nothing here, `scrollWidth` is 0, and a
 * clipped label is invisible to it. Which of the two bars a viewport shows is therefore an
 * e2e question (`e2e/nav-responsive.spec.js`, at real widths in a real browser), and what
 * is checked here is the thing that would silently break role scoping and no browser test
 * would notice quickly: that the two bars are built from ONE filtered list. Rebuilding the
 * mobile bar from `NAV` would put Administration on an RM's phone.
 */
describe('AppShell — the phone bar and the toolbar show one set of screens', () => {
  const bars = () => {
    const toolbar = screen.getByRole('toolbar', { name: 'Screens' })
    const bottom = screen.getByRole('navigation', { name: 'Screens' })
    const names = (el) => within(el).getAllByRole('link').map((l) => l.getAttribute('href'))
    return { toolbar, bottom, toolbarHrefs: names(toolbar), bottomHrefs: names(bottom) }
  }

  for (const role of ['manager', 'admin', 'relationship_manager']) {
    it(`gives a ${role} the same screens in both bars`, () => {
      renderScreen(<AppShell title="Test"><p>body</p></AppShell>, { path: '/queue', user: session(role) })
      const { toolbarHrefs, bottomHrefs } = bars()
      expect(bottomHrefs).toEqual(toolbarHrefs)
      expect(bottomHrefs).toEqual(navFor({ manager: 'M', admin: 'A', relationship_manager: 'RM' }[role]))
    })
  }

  it('gives the frozen bundle the same screens in both bars', () => {
    renderScreen(<AppShell title="Test"><p>body</p></AppShell>, { path: '/queue', mode: 'static', user: null })
    const { toolbarHrefs, bottomHrefs } = bars()
    expect(bottomHrefs).toEqual(toolbarHrefs)
    expect(bottomHrefs).not.toContain('/admin')
    expect(bottomHrefs).not.toContain('/radar')
  })

  it('renders no phone bar at all for a role with no screen of its own', () => {
    renderScreen(<AppShell title="Test"><p>body</p></AppShell>, { path: '/queue', user: session('credit_officer') })
    expect(screen.queryByRole('navigation', { name: 'Screens' })).not.toBeInTheDocument()
  })

  // The toolbar's roving tabindex is sized for the toolbar. The phone bar is an ordinary
  // set of tab stops; wiring it into the same refs array would have the two fighting over
  // one active index, and arrow keys on a desktop would move a link nobody can see.
  it('leaves the phone bar out of the toolbar’s roving tabindex', () => {
    renderScreen(<AppShell title="Test"><p>body</p></AppShell>, { path: '/queue', user: session('manager') })
    const bottom = screen.getByRole('navigation', { name: 'Screens' })
    for (const link of within(bottom).getAllByRole('link')) {
      expect(link).not.toHaveAttribute('tabindex')
    }
  })

  it('leaves room under the page for the bar to sit over', () => {
    renderScreen(<AppShell title="Test"><p>body</p></AppShell>, { path: '/queue', user: session('manager') })
    expect(document.getElementById('main-content').className).toContain('pb-20')
    expect(document.getElementById('main-content').className).toContain('sm:pb-5')
  })
})
