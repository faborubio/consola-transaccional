import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';

import { BASE_PATH } from '../../api-client';
import { Dashboard } from './dashboard';

const API = 'http://gateway.test';

const METRICS = {
  byStatus: [
    { status: 'APROBADA', count: 350000, totalAmount: 1e9 },
    { status: 'RECHAZADA', count: 60000, totalAmount: 2e8 },
    { status: 'EN_REVISION', count: 25000, totalAmount: 1e8 },
    { status: 'PENDIENTE', count: 50000, totalAmount: 3e8 },
    { status: 'REVERTIDA', count: 15000, totalAmount: 5e7 },
  ],
  byMonth: [
    { month: '2026-01', count: 40000, totalAmount: 1e8 },
    { month: '2026-02', count: 42000, totalAmount: 1.1e8 },
  ],
  totalCount: 500000,
  approvalRate: 0.85,
  inReview: 25000,
  generatedAt: '2026-06-13T00:00:00Z',
};

describe('Dashboard', () => {
  let testing: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideCharts(withDefaultRegisterables()),
        { provide: BASE_PATH, useValue: API },
      ],
    });
    testing = TestBed.inject(HttpTestingController);
  });

  afterEach(() => testing.verify());

  it('pide las métricas y arma KPIs + datos de gráficos', async () => {
    const fixture = TestBed.createComponent(Dashboard);
    fixture.detectChanges();

    testing.expectOne(`${API}/metrics/dashboard`).flush(METRICS);
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('500,000'); // total
    expect(el.textContent).toContain('85%'); // tasa de aprobación
    expect(el.textContent).toContain('25,000'); // en revisión
  });

  it('muestra error mapeado si las métricas fallan', async () => {
    const fixture = TestBed.createComponent(Dashboard);
    fixture.detectChanges();

    testing
      .expectOne(`${API}/metrics/dashboard`)
      .flush({ code: 'INTERNAL', message: '...' }, { status: 500, statusText: 'Error' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('servidor');
  });
});
