import { expect, Page, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

async function completeProjectWizard(page: Page, projectName: string, horizon = '2', includeInitialSource = false): Promise<void> {
  await page.getByLabel('¿Cómo se llama la iniciativa?').fill(projectName);
  await page.getByLabel('Organización o área responsable').fill('Organización E2E');
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByLabel('¿Qué problema u oportunidad quieres abordar?').fill('El proceso manual genera demoras y costos evitables');
  await page.getByLabel('¿Qué solución estás proponiendo?').fill('Automatizar el proceso con trazabilidad de extremo a extremo');
  await page.getByLabel('¿Qué decisión necesitas obtener?').fill('Aprobar la inversión y comenzar la fase 1');
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByLabel('Responsable o sponsor').fill('Dirección General');
  await page.getByText('Ajustes financieros avanzados').click();
  await page.getByLabel('Moneda').selectOption('USD');
  await page.getByLabel('Horizonte').selectOption(horizon);
  await page.getByLabel('Tasa de descuento').fill('9.5');
  if (includeInitialSource) await page.locator('.creation-dialog input[type="file"]').setInputFiles({ name: 'fuente-inicial.txt', mimeType: 'text/plain', buffer: Buffer.from('La oportunidad inicial tiene respaldo documental.') });
  await page.getByRole('button', { name: 'Crear y continuar' }).click();
  await expect(page).toHaveURL(/\/generate\/[0-9a-f-]+\?step=sources$/);
}

test('creates, navigates and deletes a persisted business case', async ({ page }) => {
  const projectName = `Caso E2E ${Date.now()}`;
  let postCount = 0;
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/v1/projects')) postCount += 1;
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Crear mi business case' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await expect(page.getByText('Escribe un nombre para continuar.')).toBeVisible();
  expect(postCount).toBe(0);
  await completeProjectWizard(page, projectName, '2', true);
  await expect(page.getByText('fuente-inicial.txt', { exact: true }).last()).toBeVisible();
  await page.goto('/');
  await expect(page.getByRole('heading', { name: projectName })).toBeVisible();
  expect(postCount).toBe(1);

  const projectCard = page.getByRole('heading', { name: projectName }).locator('xpath=ancestor::article');
  await projectCard.getByRole('link', { name: 'Continuar construyendo' }).click();
  await expect(page).toHaveURL(/\/generate\/[0-9a-f-]+$/);
  await expect(page.getByRole('heading', { name: projectName, exact: true }).first()).toBeVisible();
  const projectId = page.url().split('/').pop();

  await page.goto(`/review/${projectId}`);
  await expect(page.getByRole('heading', { name: 'Revisa tu business case' })).toBeVisible();
  await page.goto('/');

  const reloadedCard = page.getByRole('heading', { name: projectName }).locator('xpath=ancestor::article');
  await reloadedCard.getByRole('button', { name: 'Eliminar' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Cancelar' }).click();
  await expect(page.getByRole('heading', { name: projectName })).toBeVisible();

  await reloadedCard.getByRole('button', { name: 'Eliminar' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Eliminar' }).click();
  await expect(page.getByRole('heading', { name: projectName })).toHaveCount(0);
});

test('captures a free-form idea and safely returns to edit it', async ({ page }) => {
  const projectName = `Idea libre E2E ${Date.now()}`;
  const initialIdea = 'Quiero reducir las demoras de compras, dar trazabilidad al gasto y comenzar con un piloto para dos áreas.';
  await page.goto('/');
  await page.getByRole('button', { name: 'Crear mi business case' }).click();
  await page.getByLabel('¿Cómo se llama la iniciativa?').fill(projectName);
  await page.getByLabel('Organización o área responsable').fill('Operaciones E2E');
  await page.getByRole('button', { name: /Escribir todo mi contexto/ }).click();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByLabel('Cuéntanos todo sobre tu proyecto o iniciativa').fill(initialIdea);
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByLabel('Responsable o sponsor').fill('Dirección de Operaciones');
  await page.getByRole('button', { name: 'Crear y continuar' }).click();
  await expect(page).toHaveURL(/\?step=sources$/);

  await page.locator('.step-workspace input[type="file"]').setInputFiles({ name: 'pendiente.txt', mimeType: 'text/plain', buffer: Buffer.from('Cambios todavía no guardados') });
  page.once('dialog', async (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: /Definición de idea/ }).click();
  await expect(page).toHaveURL(/\?step=sources$/);
  page.once('dialog', async (dialog) => dialog.accept());
  await page.getByRole('button', { name: /Definición de idea/ }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await expect(page.getByLabel('Cuéntanos todo sobre tu proyecto o iniciativa')).toHaveValue(initialIdea);
  await page.getByLabel('Cuéntanos todo sobre tu proyecto o iniciativa').fill(`${initialIdea} El sponsor confirmó una duración objetivo de ocho semanas.`);
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Guardar y volver al borrador' }).click();
  await expect(page).toHaveURL(/\?step=sources$/);
  await page.getByRole('link', { name: 'Mis business cases' }).first().click();
  const cleanup = page.getByRole('heading', { name: projectName }).locator('xpath=ancestor::article');
  await cleanup.getByRole('button', { name: 'Eliminar' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Eliminar' }).click();
});

for (const width of [360, 768, 1440]) {
  test(`keeps the dashboard usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Convierte una idea en un business case sólido.' })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow).toBe(false);
    await page.getByRole('button', { name: 'Crear mi business case' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByLabel('¿Cómo se llama la iniciativa?')).toBeFocused();
  });
}

test('reaches the creation form using only the keyboard', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Saltar al contenido' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Casecraft, inicio' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Mis business cases' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Nuevo business case' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('¿Cómo se llama la iniciativa?')).toBeFocused();
});

test('filters and paginates the project portfolio', async ({ page, request }) => {
  const prefix = `Portafolio ${Date.now()}`;
  const ids: string[] = [];
  for (let index = 1; index <= 7; index += 1) {
    const response = await request.post('/api/v1/projects', { data: { name: `${prefix} ${index}`, organization: index === 6 ? 'Organización especial' : 'Organización común', currency: 'MXN', horizon_years: 2, discount_rate: 10 } });
    ids.push((await response.json()).id);
  }
  await page.goto('/');
  await page.getByLabel('Buscar business cases').fill(prefix);
  await expect(page.locator('.project-card')).toHaveCount(6);
  await expect(page.getByText('Página 1 de 2')).toBeVisible();
  await page.getByRole('button', { name: 'Siguiente' }).click();
  await expect(page.locator('.project-card')).toHaveCount(1);
  await page.getByLabel('Buscar business cases').fill('Organización especial');
  await expect(page.getByRole('heading', { name: `${prefix} 6` })).toBeVisible();
  await page.getByRole('button', { name: /Lista/ }).click();
  await page.getByLabel('Buscar business cases').fill(prefix);
  await expect(page.locator('.portfolio-table tbody tr')).toHaveCount(7);
  await expect(page.getByText('15 por página')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: /Lista/ })).toHaveAttribute('aria-pressed', 'true');
  for (const id of ids) await request.delete(`/api/v1/projects/${id}`);
});

test('uploads a partial document batch and persists evidence selection', async ({ page }) => {
  const projectName = `Ingesta E2E ${Date.now()}`;
  await page.goto('/');
  await page.getByRole('button', { name: 'Crear mi business case' }).click();
  await completeProjectWizard(page, projectName);
  await expect(page.getByRole('heading', { name: projectName, exact: true }).first()).toBeVisible();
  await expect(page).toHaveURL(/\/generate\/[0-9a-f-]+\?step=sources$/);
  await expect(page.getByRole('heading', { name: 'Selecciona la evidencia que leerá el agente' })).toBeVisible();

  const dataTransfer = await page.evaluateHandle(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(['Fuente arrastrada'], 'arrastrado.txt', { type: 'text/plain' }));
    return transfer;
  });
  await page.locator('.step-workspace .dropzone').dispatchEvent('drop', { dataTransfer });
  await expect(page.getByText('arrastrado.txt')).toBeVisible();
  await page.getByRole('button', { name: 'Remover arrastrado.txt' }).click();

  await page.locator('.step-workspace input[type="file"]').setInputFiles([
    { name: 'evidencia-e2e.txt', mimeType: 'text/plain', buffer: Buffer.from('Ahorro trazable con acento: inversión') },
    { name: 'proxy-mayor-a-1mb.txt', mimeType: 'text/plain', buffer: Buffer.alloc(1_200_000, 65) },
    { name: 'plantilla-mayor-a-1mb.pdf', mimeType: 'application/pdf', buffer: Buffer.concat([readFileSync('/fixtures/Plantilla_Business_Case_Profesional.pdf'), Buffer.alloc(1_200_000)]) },
    { name: 'disfrazado.pdf', mimeType: 'application/pdf', buffer: Buffer.from('MZ executable') }
  ]);
  await expect(page.getByText('evidencia-e2e.txt')).toBeVisible();
  await expect(page.getByText('disfrazado.pdf')).toBeVisible();
  await page.getByRole('button', { name: 'Subir y procesar' }).click();
  await expect(page.getByText('3 archivos procesados; 1 rechazados.')).toBeVisible();
  await expect(page.getByText('proxy-mayor-a-1mb.txt', { exact: true }).last()).toBeVisible();
  await expect(page.getByText('plantilla-mayor-a-1mb.pdf', { exact: true }).last()).toBeVisible();
  await expect(page.getByText('The file signature does not match PDF.')).toBeVisible();

  await page.locator('.step-workspace input[type="file"]').setInputFiles(Array.from({ length: 4 }, (_, index) => ({ name: `adicional-${index + 1}.txt`, mimeType: 'text/plain', buffer: Buffer.from(`Fuente adicional ${index + 1}`) })));
  await page.getByRole('button', { name: 'Subir y procesar' }).click();
  await expect(page.getByText('4 archivos procesados correctamente.')).toBeVisible();
  await expect(page.getByText('Página 1 de 2')).toBeVisible();
  await page.getByRole('button', { name: 'Siguiente' }).click();
  await expect(page.getByText('Página 2 de 2')).toBeVisible();
  await page.getByLabel('Buscar documentos').fill('evidencia-e2e');

  await page.getByRole('button', { name: 'Abrir fuente evidencia-e2e.txt' }).click();
  await expect(page.getByRole('dialog', { name: 'evidencia-e2e.txt' })).toBeVisible();
  await expect(page.getByText('Ahorro trazable con acento: inversión')).toBeVisible();
  await page.getByRole('button', { name: 'Cerrar fuente' }).click();
  await expect(page.getByRole('dialog', { name: 'evidencia-e2e.txt' })).not.toBeVisible();
  const documentToggle = page.getByRole('checkbox', { name: 'Incluir evidencia-e2e.txt' });
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/v1/documents/') && response.request().method() === 'PATCH'),
    documentToggle.uncheck()
  ]);
  await page.reload();
  await page.getByLabel('Buscar documentos').fill('evidencia-e2e');
  await expect(page.getByRole('checkbox', { name: 'Incluir evidencia-e2e.txt' })).not.toBeChecked();

  await page.getByRole('button', { name: 'Abrir fuente evidencia-e2e.txt' }).click();
  const chunkToggle = page.getByRole('checkbox', { name: 'Incluir fragmento 1' });
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/v1/chunks/') && response.request().method() === 'PATCH'),
    chunkToggle.uncheck()
  ]);
  await page.reload();
  await page.getByLabel('Buscar documentos').fill('evidencia-e2e');
  await page.getByRole('button', { name: 'Abrir fuente evidencia-e2e.txt' }).click();
  await expect(page.getByRole('checkbox', { name: 'Incluir fragmento 1' })).not.toBeChecked();
  await page.getByRole('button', { name: 'Cerrar fuente' }).click();

  await page.getByRole('button', { name: 'Eliminar' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Eliminar fuente' }).click();
  await expect(page.getByRole('button', { name: 'Abrir fuente evidencia-e2e.txt' })).toHaveCount(0);

  await page.getByRole('link', { name: 'Mis business cases' }).first().click();
  const cleanupCard = page.getByRole('heading', { name: projectName }).locator('xpath=ancestor::article');
  await cleanupCard.getByRole('button', { name: 'Eliminar' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Eliminar' }).click();
});

test('generates, revises, validates and finalizes a professional business case', async ({ page }) => {
  const projectName = `Generación E2E ${Date.now()}`;
  await page.goto('/');
  await page.getByRole('button', { name: 'Crear mi business case' }).click();
  await completeProjectWizard(page, projectName, '5');
  await expect(page.getByRole('heading', { name: 'Selecciona la evidencia que leerá el agente' })).toBeVisible();
  await page.locator('.step-workspace input[type="file"]').setInputFiles({ name: 'fuente-generación.txt', mimeType: 'text/plain', buffer: Buffer.from('El proceso manual cuesta 100 MXN y tarda cinco días.') });
  await page.getByRole('button', { name: 'Subir y procesar' }).click();
  await expect(page.getByText('1 archivos procesados correctamente.')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await expect(page).toHaveURL(/\/generate\/[0-9a-f-]+\?step=interview$/);
  await expect(page.getByRole('heading', { name: 'Fortalece el caso con el agente' })).toBeFocused();
  await page.getByRole('button', { name: /Reanalizar con las fuentes actuales/ }).click();
  await expect(page.getByText('Existe evidencia documental')).toBeVisible();
  await page.getByLabel('Tu respuesta').fill('Reducir el ciclo operativo y mejorar la trazabilidad del gasto.');
  await page.getByRole('button', { name: 'Enviar al agente' }).click();
  await expect(page.getByText('Respuestas aportadas (1)')).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\?step=interview$/);
  await expect(page.getByRole('heading', { name: 'Fortalece el caso con el agente' })).toBeVisible();
  await expect(page.getByText('Respuestas aportadas (1)')).toBeVisible();
  const agentAnswers = [
    'No hacer nada, automatizar parcialmente o automatizar de extremo a extremo.',
    'Adopción y calidad de datos; capacitación, limpieza y seguimiento semanal.',
    'Piloto de ocho semanas y despliegue controlado en dos fases.'
  ];
  for (const [index, answer] of agentAnswers.entries()) {
    await expect(page.getByText(`Respuestas aportadas (${index + 1})`)).toBeVisible();
    await page.getByLabel('Tu respuesta').fill(answer);
    await expect(page.getByRole('button', { name: 'Enviar al agente' })).toBeEnabled();
    await page.getByRole('button', { name: 'Enviar al agente' }).click();
  }
  await expect(page.getByText('El agente tiene contexto suficiente')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await expect(page).toHaveURL(/\/generate\/[0-9a-f-]+\?step=financial$/);
  await expect(page.getByRole('heading', { name: 'Completa las cifras y genera' })).toBeFocused();
  await page.reload();
  await expect(page).toHaveURL(/\?step=financial$/);
  await expect(page.getByRole('heading', { name: 'Completa las cifras y genera' })).toBeVisible();
  await page.getByLabel('Aún no tengo cifras confiables').uncheck();
  await page.getByLabel('Inversión inicial estimada').fill('100');
  await page.getByLabel('Costo anual estimado').fill('10');
  await page.getByLabel('Beneficio anual estimado').fill('80');
  await page.getByRole('button', { name: 'Construir business case' }).click();
  await expect(page).toHaveURL(/\/review\/[0-9a-f-]+$/);
  await expect(page.getByRole('heading', { name: 'Revisa tu business case' })).toBeVisible();
  await expect(page.locator('.review-index nav button')).toHaveCount(16);
  const sectionEditor = page.getByLabel(/Contenido de/);
  await sectionEditor.fill(`${await sectionEditor.inputValue()}\n\nEl piloto tendrá una duración objetivo de ocho semanas.`);
  await page.getByRole('button', { name: 'Guardar como nueva versión' }).click();
  await expect(page.getByText('Edición guardada como nueva versión.')).toBeVisible();
  await expect(page.getByRole('button', { name: /v2 ·/ })).toBeVisible();
  await page.getByLabel(/Retroalimentación para/).fill('Aclara el beneficio principal para el comité');
  await page.getByRole('button', { name: 'Preparar solicitud al agente' }).click();
  await expect(page.getByText('Comentario creado. Puedes solicitar una propuesta al agente.')).toBeVisible();
  await page.getByRole('button', { name: 'Solicitar propuesta' }).click();
  await expect(page.getByRole('dialog', { name: 'Revisar antes de aplicar' })).toBeVisible();
  await expect(page.getByText('Citas preservadas: sí')).toBeVisible();
  await page.getByRole('button', { name: 'Aceptar y crear versión' }).click();
  await expect(page.getByRole('button', { name: /v3 ·/ })).toBeVisible();
  await page.getByRole('button', { name: 'Comprobar calidad y finalizar' }).click();
  await expect(page.getByRole('heading', { name: 'Comprueba y comparte' })).toBeVisible();
  await page.getByRole('button', { name: 'Ejecutar validación integral' }).click();
  await expect(page.getByText('Quality gate aprobado.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Gate aprobado' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Inspección completada' })).toBeDisabled();
  await page.getByRole('button', { name: 'Marcar como Final' }).click();
  await expect(page.getByText('Versión finalizada y lista para exportar.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ya puedes exportar y compartir' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Abrir vista A4 / PDF' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Descargar Markdown' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Descargar JSON' })).toBeVisible();
  await page.getByRole('link', { name: 'Volver a revisión' }).click();
  await page.getByRole('link', { name: 'Mis business cases' }).first().click();
  const cleanup = page.getByRole('heading', { name: projectName }).locator('xpath=ancestor::article');
  await cleanup.getByRole('button', { name: 'Eliminar' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Eliminar' }).click();
});

test('routes an evidence finding back to sources and regeneration', async ({ page, request }) => {
  const created = await request.post('/api/v1/projects', { data: { name: `Corrección E2E ${Date.now()}`, organization: 'Organización E2E', currency: 'MXN', horizon_years: 2, discount_rate: 10 } });
  const project = await created.json();
  const generation = await request.post(`/api/v1/projects/${project.id}/generations`, { data: { sponsor: 'Dirección General', audience: 'Comité', decision: 'Aprobar fase 1', problem: 'El proceso manual genera demoras', solution: 'Automatizar el proceso', financial: { initial_investment: 100, annual_costs: [10, 10], annual_benefits: [80, 80] } } });
  const run = await generation.json();
  await request.post(`/api/v1/versions/${run.version_id}/validations`);

  await page.goto(`/quality/${project.id}`);
  await expect(page.getByRole('heading', { name: 'Corrige esta versión y vuelve a validarla' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Editar este borrador' })).toBeVisible();
  await page.getByRole('link', { name: 'Agregar fuentes y regenerar' }).click();
  await expect(page).toHaveURL(new RegExp(`/generate/${project.id}\\?step=sources$`));
  await expect(page.getByText('Estás corrigiendo un borrador existente')).toBeVisible();
  await expect(page.getByText(/Crear nueva versión corregida/)).toHaveCount(0);
  await page.getByRole('button', { name: /Finanzas/ }).click();
  await expect(page.getByRole('button', { name: 'Crear nueva versión corregida' })).toBeVisible();

  await request.delete(`/api/v1/projects/${project.id}`);
});

test('edits, validates, publishes and restores a section rule', async ({ page, request }) => {
  const restored = await request.post('/api/v1/rules/executive_summary/restore-default', {
    data: { actor: 'e2e-reset' }
  });
  expect(restored.ok()).toBe(true);
  const detailResponse = await request.get('/api/v1/rules/executive_summary');
  expect(detailResponse.ok()).toBe(true);
  const detail = await detailResponse.json() as {
    draft_version: number | null;
    published: { markdown: string } | null;
  };
  expect(detail.published).not.toBeNull();
  if (detail.draft_version !== null && detail.published !== null) {
    const synchronized = await request.put(`/api/v1/rules/executive_summary/drafts/${detail.draft_version}`, {
      data: { markdown: detail.published.markdown, actor: 'e2e-reset' }
    });
    expect(synchronized.ok()).toBe(true);
  }
  await page.goto('/rules');
  await expect(page.getByRole('heading', { name: 'Guía editorial del agente' })).toBeVisible();
  await expect(page.locator('.rules-nav button')).toHaveCount(17);
  await page.getByRole('button', { name: /Resumen ejecutivo y decisión solicitada/ }).click();
  const editor = page.getByLabel('Regla Markdown');
  await expect(editor).toHaveValue(/## Objetivo/);
  await editor.fill((await editor.inputValue()).replace('máximo 500 palabras', 'máximo 450 palabras') + '\n<script>window.ruleInjected=true</script>');
  await page.getByRole('tab', { name: 'Vista previa' }).click();
  await expect(page.locator('.rule-preview')).toContainText('<script>window.ruleInjected=true</script>');
  expect(await page.evaluate(() => 'ruleInjected' in window)).toBe(false);
  await page.getByRole('tab', { name: 'Editor' }).click();
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await expect(page.getByText('Borrador guardado. Las generaciones publicadas no cambiaron.')).toBeVisible();
  await page.getByRole('button', { name: 'Validar' }).click();
  await expect(page.getByText('Regla válida y lista para publicar.')).toBeVisible();
  await page.getByRole('button', { name: 'Publicar versión' }).click();
  await expect(page.getByText('Nueva versión publicada.')).toBeVisible();
  await page.getByRole('button', { name: 'Restaurar default' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Restaurar y publicar' }).click();
  await expect(page.getByText('Default restaurado como una nueva versión publicada.')).toBeVisible();
  await page.getByRole('tab', { name: 'Historial' }).click();
  await expect(page.getByRole('table')).toBeVisible();
});
