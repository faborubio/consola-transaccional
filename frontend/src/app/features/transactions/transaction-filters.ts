import { Component, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { Subject, debounceTime, distinctUntilChanged } from 'rxjs';

import { TransactionStatus, TransactionType } from '../../api-client';

/**
 * Barra de filtros de la consola. Los filtros NO viven aquí: viven en la URL.
 * Este componente solo lee los query params actuales y navega al cambiar —
 * deep-linkeable, el botón atrás funciona, y el listado reacciona a la URL.
 */
@Component({
  selector: 'app-transaction-filters',
  templateUrl: './transaction-filters.html',
})
export class TransactionFilters {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly statuses = Object.values(TransactionStatus);
  protected readonly types = Object.values(TransactionType);
  protected readonly currencies = ['CLP', 'USD', 'EUR'];
  protected readonly sorts = [
    { value: '-createdAt', label: 'Más recientes' },
    { value: 'createdAt', label: 'Más antiguas' },
    { value: '-amount', label: 'Mayor monto' },
    { value: 'amount', label: 'Menor monto' },
  ];

  // Texto y números van con debounce; selects y checkboxes navegan directo.
  private readonly debounced$ = new Subject<{ param: string; value: string }>();

  constructor() {
    this.debounced$
      .pipe(
        debounceTime(300),
        distinctUntilChanged((a, b) => a.param === b.param && a.value === b.value),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ param, value }) => this.setParam(param, value));
  }

  protected param(name: string): string {
    return this.route.snapshot.queryParamMap.get(name) ?? '';
  }

  protected statusActive(status: string): boolean {
    return this.route.snapshot.queryParamMap.getAll('status').includes(status);
  }

  protected toggleStatus(status: string, checked: boolean): void {
    const current = this.route.snapshot.queryParamMap.getAll('status');
    const updated = checked ? [...current, status] : current.filter((s) => s !== status);
    this.navigate({ status: updated.length ? updated : null });
  }

  protected setParam(param: string, value: string): void {
    this.navigate({ [param]: value || null });
  }

  protected setDebounced(param: string, value: string): void {
    this.debounced$.next({ param, value });
  }

  protected clearAll(): void {
    this.navigate(
      Object.fromEntries(
        ['status', 'type', 'currency', 'counterparty', 'minAmount', 'maxAmount',
         'dateFrom', 'dateTo', 'sort'].map((k) => [k, null]),
      ),
    );
  }

  protected get hasFilters(): boolean {
    return this.route.snapshot.queryParamMap.keys.length > 0;
  }

  private navigate(queryParams: Record<string, unknown>): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams,
      queryParamsHandling: 'merge',
    });
  }
}
