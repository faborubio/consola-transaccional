import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { TokenStore } from './token-store.service';

export const authGuard: CanActivateFn = () => {
  const store = inject(TokenStore);
  return store.isAuthenticated() ? true : inject(Router).createUrlTree(['/login']);
};
