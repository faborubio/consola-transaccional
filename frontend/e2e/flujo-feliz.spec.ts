import { expect, test } from '@playwright/test';

/**
 * Camino feliz de extremo a extremo (hito de Fase 7):
 *   login → listado → filtro en la URL → detalle → transición (aprobar).
 *
 * Corre contra el stack real (imagen edge, same-origin): el SPA en `/` y el API en
 * `/api`. Usa el supervisor demo, que es checker (puede aprobar lo de un maker sin
 * violar la segregación de funciones). El seed deja ~5% de transacciones EN_REVISION.
 */
test('login → listado → filtro EN_REVISION → detalle → aprobar', async ({ page }) => {
  // 1. Login
  await page.goto('/login');
  await page.locator('#username').fill('supervisor1');
  await page.locator('#password').fill('Demo1234!');
  await page.getByRole('button', { name: 'Ingresar' }).click();

  // 2. Listado: el login redirige a /transactions y la tabla carga
  await expect(page).toHaveURL(/\/transactions(\?|$)/);
  const filas = page.locator('table tbody tr');
  await expect(filas.first()).toBeVisible();

  // 3. Filtro en la URL: togglear EN_REVISION deja el estado en el query param y la
  //    lista se recarga; esperar a que la primera fila sea ya EN_REVISION antes de abrir.
  await page.locator('#st-EN_REVISION').check();
  await expect(page).toHaveURL(/status=EN_REVISION/);
  await expect(filas.first()).toContainText('EN_REVISION');

  // 4. Detalle: abrir la primera transacción EN_REVISION (badge principal = .badge.fs-6)
  await filas.first().click();
  await expect(page).toHaveURL(/\/transactions\/[^/]+$/);
  await expect(page.locator('.badge.fs-6')).toHaveText('EN_REVISION');

  // 5. Transición: el supervisor aprueba; el toast confirma y el estado pasa a APROBADA
  await page.getByRole('button', { name: 'Aprobar' }).click();
  await expect(page.getByText(/Transición aplicada: ahora está APROBADA/)).toBeVisible();
  await expect(page.locator('.badge.fs-6')).toHaveText('APROBADA');
});
