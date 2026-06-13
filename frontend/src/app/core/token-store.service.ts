import { Injectable, computed, signal } from '@angular/core';

import { TokenPair } from '../api-client';

const STORAGE_KEY = 'consola.tokens';

/**
 * Tokens en localStorage: tradeoff consciente para una demo de portafolio
 * (un banco real usaría cookies httpOnly tras un BFF). Documentado en README.
 */
@Injectable({ providedIn: 'root' })
export class TokenStore {
  private readonly pair = signal<TokenPair | null>(this.load());

  readonly isAuthenticated = computed(() => this.pair() !== null);

  accessToken(): string | null {
    return this.pair()?.accessToken ?? null;
  }

  /** Roles desde el payload del JWT — para UX (mostrar/ocultar acciones).
   * La seguridad real es del servidor: el rol se exige en el endpoint. */
  roles(): string[] {
    const token = this.accessToken();
    if (!token) {
      return [];
    }
    try {
      const payload = JSON.parse(
        atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')),
      ) as { roles?: string[] };
      return payload.roles ?? [];
    } catch {
      return [];
    }
  }

  hasRole(role: string): boolean {
    return this.roles().includes(role);
  }

  refreshToken(): string | null {
    return this.pair()?.refreshToken ?? null;
  }

  save(pair: TokenPair): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pair));
    this.pair.set(pair);
  }

  clear(): void {
    localStorage.removeItem(STORAGE_KEY);
    this.pair.set(null);
  }

  private load(): TokenPair | null {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as TokenPair) : null;
    } catch {
      return null;
    }
  }
}
