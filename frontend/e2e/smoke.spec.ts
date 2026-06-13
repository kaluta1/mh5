import { test, expect } from '@playwright/test'

test.describe('public pages', () => {
  test('homepage loads without console errors', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (err) => errors.push(err.message))
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
    })

    await page.goto('/')
    await expect(page).toHaveTitle(/MyHigh5/i)
    expect(errors).toHaveLength(0)
  })

  test('contests page loads', async ({ page }) => {
    await page.goto('/contests')
    await expect(page.locator('body')).toContainText(/concours|contests/i)
  })

  test('login page loads', async ({ page }) => {
    await page.goto('/login')
    await expect(page.locator('body')).toContainText(/login|connexion/i)
  })
})
