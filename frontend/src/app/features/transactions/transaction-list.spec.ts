import { convertToParamMap } from '@angular/router';

import { paramsToFilters } from './transaction-list';

describe('paramsToFilters (contrato URL → API)', () => {
  it('URL vacía produce los defaults', () => {
    const f = paramsToFilters(convertToParamMap({}));
    expect(f.status).toEqual([]);
    expect(f.sort).toBe('-createdAt');
    expect(f.type).toBeUndefined();
    expect(f.minAmount).toBeUndefined();
    expect(f.dateFrom).toBeUndefined();
  });

  it('mapea todos los filtros combinados', () => {
    const f = paramsToFilters(
      convertToParamMap({
        status: ['PENDIENTE', 'EN_REVISION'],
        type: 'PAGO',
        currency: 'CLP',
        counterparty: 'comercial',
        minAmount: '1000',
        maxAmount: '500000',
        dateFrom: '2026-03-01',
        dateTo: '2026-03-31',
        sort: '-amount',
      }),
    );
    expect(f.status).toEqual(['PENDIENTE', 'EN_REVISION']);
    expect(f.type).toBe('PAGO');
    expect(f.currency).toBe('CLP');
    expect(f.counterparty).toBe('comercial');
    expect(f.minAmount).toBe(1000);
    expect(f.maxAmount).toBe(500000);
    expect(f.sort).toBe('-amount');
  });

  it('expande fechas a día completo inclusivo', () => {
    const f = paramsToFilters(
      convertToParamMap({ dateFrom: '2026-03-01', dateTo: '2026-03-31' }),
    );
    expect(f.dateFrom).toBe('2026-03-01T00:00:00Z');
    expect(f.dateTo).toBe('2026-03-31T23:59:59.999Z');
  });

  it('ignora montos no numéricos en vez de mandarlos al API', () => {
    const f = paramsToFilters(convertToParamMap({ minAmount: 'abc', maxAmount: '' }));
    expect(f.minAmount).toBeUndefined();
    expect(f.maxAmount).toBeUndefined();
  });

  it('no envía prefijos de contraparte menores a 3 caracteres', () => {
    // un prefijo de 1-2 letras matchea una fracción enorme del índice multikey
    expect(paramsToFilters(convertToParamMap({ counterparty: 'co' })).counterparty)
      .toBeUndefined();
    expect(paramsToFilters(convertToParamMap({ counterparty: 'com' })).counterparty)
      .toBe('com');
  });
});
