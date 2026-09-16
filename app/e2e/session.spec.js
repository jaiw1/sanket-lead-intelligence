// A session that ends server-side must not leave the SPA showing a broken screen — the
// next navigation has to land back on /login, with the page the user was trying to reach
// preserved so sign-in-again does not also cost them their place.

import { test, expect } from '@playwright/test'
import { statePath } from './roles.js'

test.use({ storageState: statePath('manager') })

test('a session killed server-side sends the next navigation to /login with the deep link preserved', async ({ page }) => {
  // Through page.request so the logout POST rides the same cookies the browser holds.
  const logoutResponse = await page.request.post('/api/v1/auth/logout')
  expect(logoutResponse.ok()).toBeTruthy()

  const stillHasSessionCookie = (await page.context().cookies()).some((c) => c.name === 'rrsq_session')
  if (stillHasSessionCookie) {
    // The server said the session is over but the browser is still holding the cookie —
    // force it, because what this test is about is the app's behaviour once the session is
    // truly gone, not whether this particular backend clears its own Set-Cookie promptly.
    await page.context().clearCookies({ name: 'rrsq_session' })
  }

  await page.goto('/queue')

  await expect(page).toHaveURL(/\/login(?:[?#]|$)/)
  await expect(page.locator('#login-username')).toBeVisible()
  // A dead session is not a credentials failure — there must be no error banner.
  await expect(page.getByTestId('login-error')).toHaveCount(0)

  const next = new URL(page.url()).searchParams.get('next')
  expect(next).toBe('/queue')
})
