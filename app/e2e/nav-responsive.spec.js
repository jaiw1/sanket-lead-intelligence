// The primary navigation, at the widths it is actually used at.
//
// This cannot be a component test. jsdom does no layout: `hidden sm:block` hides nothing,
// `scrollWidth` and `clientWidth` are both 0, and a label clipped by its container is
// indistinguishable from one that fits. Which of the two bars a viewport shows, and whether
// every screen on it can be reached, are questions only a real browser at a real width can
// answer — so they are asked here.
//
// What was wrong: the toolbar shared one header row with the logo block and the session
// chip, which left it ~170px to render seven administrator screens in at phone width. It
// scrolled, so nothing was technically unreachable, but the only affordance was an 8px
// scrollbar and five of the seven sat past the visible edge. At 1316px it had 774px for
// 882px of content — the same problem, one row up.
//
// `AppShell.test.jsx` covers the half this cannot: that both bars are built from ONE
// role-filtered list, so a phone can never be shown a screen the role may not open.

import { test, expect } from '@playwright/test'
import { statePath } from './roles.js'

/** Every screen the signed-in role can reach, as rendered in whichever bar is showing. */
async function visibleNavLinks(page) {
  const toolbar = page.getByRole('toolbar', { name: 'Screens' })
  const bottom = page.getByRole('navigation', { name: 'Screens' })
  const bar = (await toolbar.isVisible()) ? toolbar : bottom
  return { bar, links: bar.getByRole('link') }
}

/** No page-level sideways scroll. A nav strip may scroll; the document may not. */
async function expectNoHorizontalPageScroll(page) {
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(
    overflow.scrollWidth,
    `the page itself scrolls sideways (${overflow.scrollWidth} > ${overflow.clientWidth})`,
  ).toBeLessThanOrEqual(overflow.clientWidth + 1)
}

test.describe('primary navigation — an administrator’s seven screens', () => {
  test.use({ storageState: statePath('admin') })

  test('a phone reaches every screen from the bottom bar', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/queue')

    const bottom = page.getByRole('navigation', { name: 'Screens' })
    await expect(bottom).toBeVisible()
    // The header toolbar gives up its row rather than competing for it.
    await expect(page.getByRole('toolbar', { name: 'Screens' })).toBeHidden()

    const links = bottom.getByRole('link')
    await expect(links).toHaveCount(7)

    // Reachable, not merely present: each one is scrolled to and clicked, and the app
    // navigates. A link sitting past the edge of a scroller fails this.
    for (const href of await links.evaluateAll((els) => els.map((el) => el.getAttribute('href')))) {
      const link = bottom.locator(`a[href="${href}"]`)
      await link.scrollIntoViewIfNeeded()
      await expect(link).toBeVisible()
      const box = await link.boundingBox()
      expect(box.width, `${href} is too narrow to tap`).toBeGreaterThanOrEqual(44)
      await link.click()
      await expect(page).toHaveURL(new RegExp(`${href}(?:[/?#]|$)`))
    }

    await expectNoHorizontalPageScroll(page)
  })

  test('the bottom bar sits clear of the page content it floats over', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/queue')
    const bar = await page.getByRole('navigation', { name: 'Screens' }).boundingBox()
    const main = await page.locator('#main-content').boundingBox()
    // `main` has pb-20 for exactly this: its padding, not its content, is what the bar
    // covers, so the last row of a queue is never hidden under the bar.
    expect(main.y + main.height).toBeGreaterThan(bar.y)
  })

  for (const [width, height] of [[1024, 768], [1316, 900], [1440, 900]]) {
    test(`every screen is visible and unclipped at ${width}×${height}`, async ({ page }) => {
      await page.setViewportSize({ width, height })
      await page.goto('/queue')

      const toolbar = page.getByRole('toolbar', { name: 'Screens' })
      await expect(toolbar).toBeVisible()
      await expect(page.getByRole('navigation', { name: 'Screens' })).toBeHidden()

      const links = toolbar.getByRole('link')
      await expect(links).toHaveCount(7)

      const boxes = await links.evaluateAll((els) => els.map((el) => {
        const rect = el.getBoundingClientRect()
        return {
          href: el.getAttribute('href'),
          text: el.textContent.trim(),
          left: rect.left,
          right: rect.right,
          // A label clipped by its own box: the text is wider than the element showing it.
          clipped: el.scrollWidth > el.clientWidth + 1,
        }
      }))

      for (const box of boxes) {
        await expect(toolbar.locator(`a[href="${box.href}"]`)).toBeVisible()
        expect(box.right, `${box.text} runs past the right edge`).toBeLessThanOrEqual(width)
        expect(box.left, `${box.text} starts left of the viewport`).toBeGreaterThanOrEqual(0)
        expect(box.clipped, `${box.text} is clipped mid-word`).toBe(false)
      }

      // The toolbar itself no longer hides anything behind a scroll edge: it wraps.
      const scrolls = await toolbar.evaluate((el) => el.scrollWidth > el.clientWidth + 1)
      expect(scrolls, 'the toolbar is a hidden scroller again').toBe(false)

      await expectNoHorizontalPageScroll(page)
    })
  }
})

test.describe('primary navigation — the shorter menus', () => {
  for (const [role, count] of [['manager', 5], ['rm', 2]]) {
    test.describe(`${role}`, () => {
      test.use({ storageState: statePath(role) })

      test(`sees its own ${count} screens in both bars`, async ({ page }) => {
        await page.setViewportSize({ width: 390, height: 844 })
        await page.goto(role === 'rm' ? '/queue' : '/dashboard')
        const phone = await visibleNavLinks(page)
        const onPhone = await phone.links.evaluateAll((els) => els.map((el) => el.getAttribute('href')))
        expect(onPhone).toHaveLength(count)
        await expectNoHorizontalPageScroll(page)

        await page.setViewportSize({ width: 1316, height: 900 })
        const desktop = await visibleNavLinks(page)
        const onDesktop = await desktop.links.evaluateAll((els) => els.map((el) => el.getAttribute('href')))
        // One filtered list, two renderings of it. A second filter would drift.
        expect(onDesktop).toEqual(onPhone)
        await expectNoHorizontalPageScroll(page)
      })
    })
  }
})
