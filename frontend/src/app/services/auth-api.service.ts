import { Injectable, inject } from '@angular/core';
import { Observable, finalize, shareReplay, tap } from 'rxjs';

import { AuthService, TokenPair, User } from '../api-client';
import { TokenStore } from '../core/token-store.service';

@Injectable({ providedIn: 'root' })
export class AuthApiService {
  private readonly client = inject(AuthService);
  private readonly store = inject(TokenStore);

  /**
   * Refresh compartido: si N requests reciben 401 en paralelo, solo UNO llama
   * a /auth/refresh. Con rotación + detección de reuso en el backend, dos
   * refresh paralelos con el mismo token quemarían la familia completa
   * (el segundo parece un robo) — este shareReplay es la protección.
   */
  private refreshInFlight$: Observable<TokenPair> | null = null;

  login(username: string, password: string): Observable<TokenPair> {
    return this.client
      .login({ username, password })
      .pipe(tap((pair) => this.store.save(pair)));
  }

  refresh(): Observable<TokenPair> {
    if (!this.refreshInFlight$) {
      this.refreshInFlight$ = this.client
        .refreshToken({ refreshToken: this.store.refreshToken() ?? '' })
        .pipe(
          tap((pair) => this.store.save(pair)),
          finalize(() => (this.refreshInFlight$ = null)),
          shareReplay(1),
        );
    }
    return this.refreshInFlight$;
  }

  me(): Observable<User> {
    return this.client.getCurrentUser();
  }

  /** Limpia local de inmediato y revoca la familia en el servidor
   * (best-effort: el 204 está garantizado, pero si la red falla el TTL
   * del refresh sigue siendo la cota superior). */
  logout(): void {
    const refreshToken = this.store.refreshToken();
    this.store.clear();
    if (refreshToken) {
      this.client.logout({ refreshToken }).subscribe({ error: () => undefined });
    }
  }
}
