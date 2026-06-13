import { Routes } from '@angular/router';

import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login').then((m) => m.Login),
  },
  {
    path: 'transactions',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/transactions/transaction-list').then((m) => m.TransactionList),
  },
  {
    path: 'transactions/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/transactions/transaction-detail').then((m) => m.TransactionDetail),
  },
  {
    path: 'dashboard',
    canActivate: [authGuard],
    loadComponent: () => import('./features/dashboard/dashboard').then((m) => m.Dashboard),
  },
  {
    path: 'activity',
    canActivate: [authGuard],
    loadComponent: () => import('./features/dashboard/activity').then((m) => m.Activity),
  },
  { path: '', pathMatch: 'full', redirectTo: 'transactions' },
];
