import { HttpErrorResponse } from '@angular/common/http';

import { describeApiError } from './api-error';

function httpError(status: number, body: unknown): HttpErrorResponse {
  return new HttpErrorResponse({ status, error: body });
}

describe('describeApiError', () => {
  it('mapea los códigos del contrato a mensajes de operador', () => {
    expect(describeApiError(httpError(404, { code: 'NOT_FOUND' }))).toContain('no existe');
    expect(describeApiError(httpError(403, { code: 'SEGREGATION_OF_DUTIES' }))).toContain(
      'segregación',
    );
    expect(describeApiError(httpError(409, { code: 'STALE_VERSION' }))).toContain('recargue');
    expect(describeApiError(httpError(429, { code: 'RATE_LIMITED' }))).toContain('espere');
    expect(describeApiError(httpError(403, { code: 'FORBIDDEN_ROLE' }))).toContain('rol');
  });

  it('usa el detalle de campo en errores de validación', () => {
    const err = httpError(422, {
      code: 'VALIDATION_ERROR',
      details: [{ field: 'minAmount', issue: 'debe ser >= 0' }],
    });
    expect(describeApiError(err)).toContain('minAmount');
    expect(describeApiError(err)).toContain('debe ser >= 0');
  });

  it('distingue caída de red de error de servidor', () => {
    expect(describeApiError(httpError(0, null))).toContain('Sin conexión');
    expect(describeApiError(httpError(503, {}))).toContain('servidor');
  });

  it('no explota con errores que no son HTTP', () => {
    expect(describeApiError(new Error('x'))).toBe('Error inesperado.');
    expect(describeApiError(undefined)).toBe('Error inesperado.');
  });
});
