import { expect, test } from '@playwright/test'

const username = process.env.SIMB_DEV_PLAYER_USERNAME ?? 'player'
const password = process.env.SIMB_DEV_PLAYER_PASSWORD ?? ''

test('a player signs in, starts a bureau and plays its first days', async ({ page }) => {
  test.skip(!password, 'Set SIMB_DEV_PLAYER_PASSWORD (see .env) to run end-to-end tests')

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Your games' })).toBeVisible()

  // A new bureau (no history) on the first world: quick to prepare.
  const worlds = await page.getByLabel('World').locator('option').count()
  await page.getByLabel('World').selectOption({ index: worlds - 1 }) // the newest world
  await page.getByLabel('Bureau history').selectOption({ label: 'None: a new bureau' })
  await page.getByRole('button', { name: 'Start game' }).click()
  await expect(page.getByRole('heading', { name: 'Morning briefing' })).toBeVisible()
  await expect(page.getByTestId('game-clock')).toContainText('4 Jan 2027')

  // Play to the end of the first few days.
  for (let i = 0; i < 3; i++) {
    await page.getByRole('button', { name: 'End of day' }).click()
    await expect(page.getByRole('button', { name: 'End of day' })).toBeEnabled({ timeout: 120_000 })
  }
  await expect(page.getByTestId('game-clock')).toContainText('17:00')

  // The dashboard's figures drill down to their records.
  await page.getByRole('link', { name: 'Dashboard' }).click()
  await expect(page.getByTestId('metric-customers')).not.toHaveText('—')
  await page.getByRole('link', { name: /Why\? Show the records behind Files received/ }).click()
  await expect(page.getByRole('heading', { name: 'Submissions register' })).toBeVisible()

  // A submission reconciles, and the books balance.
  await page.getByRole('link', { name: /^SUB-/ }).first().click()
  await expect(page.getByText('reconciles', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Finance' }).click()
  await expect(page.getByText('Balances', { exact: true })).toBeVisible()
})
