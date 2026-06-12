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
