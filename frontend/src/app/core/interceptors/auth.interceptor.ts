import {
  HttpErrorResponse,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';

import { TokenStore } from '../token-store.service';
import { AuthApiService } from '../../services/auth-api.service';

/**
 * Adjunta el access token y, ante un 401, intenta UN refresh automático y
 * reintenta el request original. Si el refresh también falla, la sesión murió
 * (expirada o familia revocada): se limpia y se va a /login.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const store = inject(TokenStore);
  const authApi = inject(AuthApiService);
  const router = inject(Router);

  // los endpoints públicos de auth no llevan token ni deben reintentarse
  if (/\/auth\/(login|refresh|logout)$/.test(req.url)) {
    return next(req);
  }

  const withToken = (r: HttpRequest<unknown>) => {
    const token = store.accessToken();
    return token ? r.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : r;
  };

  const toLogin = () => {
    store.clear();
    void router.navigate(['/login']);
  };

  return next(withToken(req)).pipe(
    catchError((err: unknown) => {
      const is401 = err instanceof HttpErrorResponse && err.status === 401;
      if (!is401) {
        return throwError(() => err);
      }
      if (!store.refreshToken()) {
        toLogin();
        return throwError(() => err);
      }
      return authApi.refresh().pipe(
        switchMap(() => next(withToken(req))),
        catchError((refreshErr: unknown) => {
          toLogin();
          return throwError(() => refreshErr);
        }),
      );
    }),
  );
};
