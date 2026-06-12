import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, afterEach, describe, expect, it } from 'vitest';

import { BASE_PATH, TokenPair } from '../../api-client';
import { TokenStore } from '../token-store.service';
import { authInterceptor } from './auth.interceptor';
import { correlationInterceptor } from './correlation.interceptor';

const API = 'http://gateway.test';

const PAIR_VIEJO: TokenPair = {
  accessToken: 'access-viejo',
  refreshToken: 'refresh-viejo',
  tokenType: 'Bearer',
  expiresIn: 900,
};

const PAIR_NUEVO: TokenPair = {
  accessToken: 'access-nuevo',
  refreshToken: 'refresh-nuevo',
  tokenType: 'Bearer',
  expiresIn: 900,
};

describe('authInterceptor', () => {
  let http: HttpClient;
  let testing: HttpTestingController;
  let store: TokenStore;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([correlationInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([{ path: 'login', children: [] }]),
        { provide: BASE_PATH, useValue: API },
      ],
    });
    http = TestBed.inject(HttpClient);
    testing = TestBed.inject(HttpTestingController);
    store = TestBed.inject(TokenStore);
    store.save(PAIR_VIEJO);
  });

  afterEach(() => {
    testing.verify();
    localStorage.clear();
  });

  it('adjunta el access token a los requests', () => {
    http.get(`${API}/transactions`).subscribe();
    const req = testing.expectOne(`${API}/transactions`);
    expect(req.request.headers.get('Authorization')).toBe('Bearer access-viejo');
    req.flush({});
  });

  it('dos 401 paralelos disparan UN solo refresh y ambos reintentan con el token nuevo', () => {
    // Con rotación + detección de reuso en el backend, dos refresh paralelos
    // con el mismo token quemarían la familia: este test protege esa garantía.
    const resultados: unknown[] = [];
    http.get(`${API}/transactions`).subscribe((r) => resultados.push(r));
    http.get(`${API}/transactions/txn_1`).subscribe((r) => resultados.push(r));

    for (const pendiente of testing.match(() => true)) {
      pendiente.flush(
        { code: 'UNAUTHORIZED', message: 'expirado' },
        { status: 401, statusText: 'Unauthorized' },
      );
    }

    // exactamente UN refresh — expectOne falla si hubo dos
    const refresh = testing.expectOne(`${API}/auth/refresh`);
    expect(refresh.request.body).toEqual({ refreshToken: 'refresh-viejo' });
    refresh.flush(PAIR_NUEVO);

    const reintentos = testing.match(() => true);
    expect(reintentos.length).toBe(2);
    for (const r of reintentos) {
      expect(r.request.headers.get('Authorization')).toBe('Bearer access-nuevo');
      r.flush({ ok: true });
    }

    expect(resultados.length).toBe(2);
    expect(store.accessToken()).toBe('access-nuevo');
  });

  it('si el refresh falla, limpia la sesión y propaga el error', () => {
    let error: unknown;
    http.get(`${API}/transactions`).subscribe({ error: (e: unknown) => (error = e) });

    testing
      .expectOne(`${API}/transactions`)
      .flush({}, { status: 401, statusText: 'Unauthorized' });
    testing
      .expectOne(`${API}/auth/refresh`)
      .flush({}, { status: 401, statusText: 'Unauthorized' });

    expect(error).toBeDefined();
    expect(store.isAuthenticated()).toBe(false);
  });

  it('errores que no son 401 pasan sin tocar la sesión', () => {
    let status = 0;
    http.get(`${API}/transactions`).subscribe({
      error: (e: { status: number }) => (status = e.status),
    });
    testing
      .expectOne(`${API}/transactions`)
      .flush({}, { status: 500, statusText: 'Server Error' });

    expect(status).toBe(500);
    expect(store.isAuthenticated()).toBe(true);
  });
});
