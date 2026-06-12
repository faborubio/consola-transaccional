import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { BASE_PATH } from '../../api-client';
import { TransactionDetail } from './transaction-detail';

const API = 'http://gateway.test';

const TXN = {
  id: 'txn_detalle01',
  amount: 1250000,
  currency: 'CLP',
  type: 'PAGO',
  status: 'EN_REVISION',
  version: 2,
  source: { accountId: 'CL-001-1', name: 'Origen SA' },
  destination: { accountId: 'CL-001-2', name: 'Destino SA' },
  reference: 'Pago factura 4471',
  createdBy: 'usr_01',
  reviewedBy: null,
  createdAt: '2026-03-01T12:00:00Z',
  updatedAt: null,
  metadata: { channel: 'WEB' },
};

const AUDIT = [
  {
    id: 'aud_1',
    transactionId: 'txn_detalle01',
    action: 'ENVIAR_A_REVISION',
    fromStatus: 'PENDIENTE',
    toStatus: 'EN_REVISION',
    actor: 'usr_09',
    reason: 'Monto sobre umbral',
    at: '2026-03-02T10:00:00Z',
  },
];

describe('TransactionDetail', () => {
  let testing: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [TransactionDetail],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: BASE_PATH, useValue: API },
        {
          provide: ActivatedRoute,
          useValue: { paramMap: of(convertToParamMap({ id: 'txn_detalle01' })) },
        },
      ],
    });
    testing = TestBed.inject(HttpTestingController);
  });

  afterEach(() => testing.verify());

  it('renderiza la transacción y su auditoría', async () => {
    const fixture = TestBed.createComponent(TransactionDetail);
    fixture.detectChanges();

    testing.expectOne(`${API}/transactions/txn_detalle01`).flush(TXN);
    testing.expectOne(`${API}/transactions/txn_detalle01/audit`).flush(AUDIT);
    await fixture.whenStable();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('txn_detalle01');
    expect(el.textContent).toContain('Origen SA');
    expect(el.textContent).toContain('Pago factura 4471');
    expect(el.textContent).toContain('ENVIAR_A_REVISION');
    expect(el.textContent).toContain('Monto sobre umbral');
  });

  it('muestra el error mapeado si la transacción no existe', async () => {
    const fixture = TestBed.createComponent(TransactionDetail);
    fixture.detectChanges();

    testing
      .expectOne(`${API}/transactions/txn_detalle01`)
      .flush({ code: 'NOT_FOUND', message: '...' }, { status: 404, statusText: 'Not Found' });
    // forkJoin cancela la otra request al fallar la primera
    for (const pending of testing.match(() => true)) {
      if (!pending.cancelled) {
        pending.flush([]);
      }
    }
    await fixture.whenStable();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('no existe');
    expect(el.textContent).toContain('Volver al listado');
  });
});
