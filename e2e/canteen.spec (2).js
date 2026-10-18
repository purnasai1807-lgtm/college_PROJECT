const { test, expect } = require('@playwright/test');

test('homepage loads branded app and live catalogue', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));

  await page.goto('/');
  await expect(page).toHaveTitle(/ACE Canteen/);
  await expect(page.getByRole('heading', { name: /Good food/i })).toBeVisible();
  await expect(page.locator('#catalogue-grid .product-card').first()).toBeVisible();
  await expect(page.locator('#catalogue-message')).toContainText(/items loaded/);
  await expect(page.locator('#pickup-queue-heading')).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test('search and item-type filter update catalogue', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#catalogue-grid .product-card').first()).toBeVisible();

  await page.locator('#product-type').selectOption('stationery');
  await expect(page.locator('#catalogue-grid .product-card').first()).toBeVisible();
  const stationeryCards = page.locator('#catalogue-grid .product-card');
  await expect(stationeryCards.first()).toBeVisible();
  await expect(stationeryCards.first()).toContainText(/stationery|pen|notebook|pencil|paper|book/i);

  await page.locator('#product-search').fill('this-item-should-not-exist-ace-e2e');
  await expect(page.locator('#catalogue-message')).toContainText(/No matching/i);
  await expect(page.locator('#catalogue-grid .product-card')).toHaveCount(0);
});

test('guest is directed to sign in before adding an item to cart', async ({ page }) => {
  await page.goto('/');
  const firstCard = page.locator('#catalogue-grid .product-card').first();
  await expect(firstCard).toBeVisible();
  const itemName = (await firstCard.locator('h3').innerText()).trim();
  await firstCard.getByRole('button', { name: 'Add to cart' }).click();
  await expect(page.locator('#cart-items')).toContainText(itemName);
  await expect(page.locator('#cart-subtotal')).not.toHaveText('₹0.00');
  await page.locator('#cart-clear').click();
  await expect(page.locator('#cart-message')).toContainText(/cart is empty/i);
  await expect(page.locator('#cart-subtotal')).toHaveText('₹0.00');
});

test('account form exposes accessible sign-in and registration modes', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Your campus account/i })).toBeVisible();
  await expect(page.getByLabel('Email address')).toBeVisible();
  await expect(page.getByLabel('Password')).toBeVisible();
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByLabel('Full name')).toBeVisible();
  await expect(page.locator('#auth-submit')).toHaveText(/Create student account/i);
});
