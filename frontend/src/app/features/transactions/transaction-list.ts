import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { ActivatedRoute, ParamMap, RouterLink } from '@angular/router';
import {
  BehaviorSubject,
  Subject,
  catchError,
  combineLatest,
  concatMap,
  map,
  of,
  scan,
  startWith,
  switchMap,
  tap,
} from 'rxjs';

import {
  TransactionStatus,
  TransactionType,
  Transaction,
  TransactionPage,
  TransactionPagePageInfo as PageInfo,
} from '../../api-client';
import {
  TransactionFilters as Filters,
  TransactionsApiService,
} from '../../services/transactions-api.service';
import { describeApiError } from '../../shared/api-error';
import { Nav } from '../../shared/nav';
import { TransactionFilters } from './transaction-filters';

interface ListVm {
  items: Transaction[];
  pageInfo: PageInfo;
  error: string | null;
}

interface PageResult {
  page: TransactionPage | null;
  error: string | null;
}

const EMPTY_VM: ListVm = { items: [], pageInfo: { hasNextPage: false }, error: null };

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
  // Prefijos de <3 caracteres degradan el índice multikey: no se envían
  // (el backend además los rechaza con 422 — minLength 3 en el contrato).
  const counterparty = params.get('counterparty') ?? '';
  return {
    status: params.getAll('status') as TransactionStatus[],
    type: (params.get('type') as TransactionType) || undefined,
    currency: params.get('currency') || undefined,
    counterparty: counterparty.length >= 3 ? counterparty : undefined,
    minAmount: num('minAmount'),
    maxAmount: num('maxAmount'),
    dateFrom: dateFrom ? `${dateFrom}T00:00:00Z` : undefined,
    dateTo: dateTo ? `${dateTo}T23:59:59.999Z` : undefined,
    sort: params.get('sort') ?? '-createdAt',
  };
}

@Component({
  selector: 'app-transaction-list',
  imports: [CommonModule, RouterLink, TransactionFilters, Nav],
  templateUrl: './transaction-list.html',
})
export class TransactionList {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(TransactionsApiService);

  // "Cargar más": el cursor es estado efímero de paginación, no va a la URL.
  private readonly loadMore$ = new Subject<string>();
  private readonly reload$ = new BehaviorSubject<void>(undefined);
  private nextCursor: string | null = null;

  /**
   * Los filtros viven en la URL. Cada cambio (o reintento) reinicia la
   * acumulación; "cargar más" anexa páginas. Un error NO deja la lista en
   * spinner eterno: produce un vm con error y botón de reintento.
   */
  protected readonly vm$ = combineLatest([
    this.route.queryParamMap.pipe(map(paramsToFilters)),
    this.reload$,
  ]).pipe(
    map(([filters]) => filters),
    switchMap((filters) =>
      this.loadMore$.pipe(
        startWith(undefined),
        concatMap((cursor) =>
          this.api.list(filters, cursor).pipe(
            map((page): PageResult => ({ page, error: null })),
            catchError((err: unknown) =>
              of<PageResult>({ page: null, error: describeApiError(err) }),
            ),
          ),
        ),
        tap(({ page }) => {
          if (page) {
            this.nextCursor = page.pageInfo.nextCursor ?? null;
          }
        }),
        scan(
          (acc: ListVm, { page, error }): ListVm =>
            error
              ? { ...acc, error }
              : {
                  items: [...acc.items, ...page!.items],
                  pageInfo: page!.pageInfo,
                  error: null,
                },
          EMPTY_VM,
        ),
        startWith(null), // estado de carga al cambiar filtros
      ),
    ),
  );

  protected retry(): void {
    this.reload$.next();
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
