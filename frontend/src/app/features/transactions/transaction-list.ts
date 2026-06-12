import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Subject, map, scan, startWith, switchMap, concatMap, tap } from 'rxjs';

import {
  TransactionStatus,
  Transaction,
  TransactionPagePageInfo as PageInfo,
} from '../../api-client';
import {
  TransactionFilters,
  TransactionsApiService,
} from '../../services/transactions-api.service';

interface ListVm {
  items: Transaction[];
  pageInfo: PageInfo;
}

const EMPTY_VM: ListVm = { items: [], pageInfo: { hasNextPage: false } };

@Component({
  selector: 'app-transaction-list',
  imports: [CommonModule],
  templateUrl: './transaction-list.html',
})
export class TransactionList {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(TransactionsApiService);

  protected readonly statuses = Object.values(TransactionStatus);

  // "Cargar más": el cursor es estado efímero de paginación, no va a la URL.
  private readonly loadMore$ = new Subject<string>();
  private nextCursor: string | null = null;

  /**
   * Los filtros viven en la URL (deep-linkeables, botón atrás funciona).
   * Cada cambio de filtros reinicia la acumulación; "cargar más" anexa páginas.
   */
  protected readonly vm$ = this.route.queryParamMap.pipe(
    map((params) => ({
      status: params.getAll('status') as TransactionStatus[],
      sort: params.get('sort') ?? '-createdAt',
    })),
    switchMap((filters: TransactionFilters) =>
      this.loadMore$.pipe(
        startWith(undefined),
        concatMap((cursor) => this.api.list(filters, cursor)),
        tap((page) => (this.nextCursor = page.pageInfo.nextCursor ?? null)),
        scan(
          (acc: ListVm, page): ListVm => ({
            items: [...acc.items, ...page.items],
            pageInfo: page.pageInfo,
          }),
          EMPTY_VM,
        ),
      ),
    ),
  );

  protected toggleStatus(status: string, checked: boolean): void {
    const current = this.route.snapshot.queryParamMap.getAll('status');
    const updated = checked ? [...current, status] : current.filter((s) => s !== status);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { status: updated.length ? updated : null },
      queryParamsHandling: 'merge',
    });
  }

  protected isActive(status: string): boolean {
    return this.route.snapshot.queryParamMap.getAll('status').includes(status);
  }

  protected loadMore(): void {
    if (this.nextCursor) {
      this.loadMore$.next(this.nextCursor);
    }
  }

  protected statusBadge(status: TransactionStatus): string {
    const classes = {
      APROBADA: 'text-bg-success',
      RECHAZADA: 'text-bg-danger',
      PENDIENTE: 'text-bg-warning',
      EN_REVISION: 'text-bg-info',
      REVERTIDA: 'text-bg-secondary',
    } satisfies Record<TransactionStatus, string>;
    return classes[status] ?? 'text-bg-light';
  }
}
