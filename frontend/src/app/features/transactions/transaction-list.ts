import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { ActivatedRoute, ParamMap, Router, RouterLink } from '@angular/router';
import {
  EMPTY,
  Subject,
  catchError,
  concatMap,
  map,
  scan,
  startWith,
  switchMap,
  tap,
} from 'rxjs';

import {
  TransactionStatus,
  TransactionType,
  Transaction,
  TransactionPagePageInfo as PageInfo,
} from '../../api-client';
import {
  TransactionFilters as Filters,
  TransactionsApiService,
} from '../../services/transactions-api.service';
import { AuthApiService } from '../../services/auth-api.service';
import { describeApiError } from '../../shared/api-error';
import { ToastService } from '../../shared/toast.service';
import { TransactionFilters } from './transaction-filters';

interface ListVm {
  items: Transaction[];
  pageInfo: PageInfo;
}

const EMPTY_VM: ListVm = { items: [], pageInfo: { hasNextPage: false } };

/** URL → filtros de API. Pura y exportada: el contrato de la consola con su URL. */
export function paramsToFilters(params: ParamMap): Filters {
  const num = (name: string): number | undefined => {
    const raw = params.get(name);
    const value = raw === null || raw === '' ? NaN : Number(raw);
    return Number.isFinite(value) ? value : undefined;
  };
  // Los date inputs entregan YYYY-MM-DD; el backend espera date-time:
  // desde = inicio del día, hasta = fin del día (inclusivo).
  const dateFrom = params.get('dateFrom');
  const dateTo = params.get('dateTo');
  return {
    status: params.getAll('status') as TransactionStatus[],
    type: (params.get('type') as TransactionType) || undefined,
    currency: params.get('currency') || undefined,
    counterparty: params.get('counterparty') || undefined,
    minAmount: num('minAmount'),
    maxAmount: num('maxAmount'),
    dateFrom: dateFrom ? `${dateFrom}T00:00:00Z` : undefined,
    dateTo: dateTo ? `${dateTo}T23:59:59.999Z` : undefined,
    sort: params.get('sort') ?? '-createdAt',
  };
}

@Component({
  selector: 'app-transaction-list',
  imports: [CommonModule, RouterLink, TransactionFilters],
  templateUrl: './transaction-list.html',
})
export class TransactionList {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(TransactionsApiService);
  private readonly authApi = inject(AuthApiService);
  private readonly toasts = inject(ToastService);

  // "Cargar más": el cursor es estado efímero de paginación, no va a la URL.
  private readonly loadMore$ = new Subject<string>();
  private nextCursor: string | null = null;

  /**
   * Los filtros viven en la URL. Cada cambio reinicia la acumulación;
   * "cargar más" anexa páginas. Errores → toast y la lista queda utilizable.
   */
  protected readonly vm$ = this.route.queryParamMap.pipe(
    map(paramsToFilters),
    switchMap((filters) =>
      this.loadMore$.pipe(
        startWith(undefined),
        concatMap((cursor) =>
          this.api.list(filters, cursor).pipe(
            catchError((err: unknown) => {
              this.toasts.error(describeApiError(err));
              return EMPTY;
            }),
          ),
        ),
        tap((page) => (this.nextCursor = page.pageInfo.nextCursor ?? null)),
        scan(
          (acc: ListVm, page): ListVm => ({
            items: [...acc.items, ...page.items],
            pageInfo: page.pageInfo,
          }),
          EMPTY_VM,
        ),
        startWith(null), // estado de carga al cambiar filtros
      ),
    ),
  );

  protected loadMore(): void {
    if (this.nextCursor) {
      this.loadMore$.next(this.nextCursor);
    }
  }

  protected logout(): void {
    this.authApi.logout();
    void this.router.navigate(['/login']);
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
