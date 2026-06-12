import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { catchError, forkJoin, map, of, switchMap } from 'rxjs';

import { AuditEntry, Transaction, TransactionStatus } from '../../api-client';
import { TransactionsApiService } from '../../services/transactions-api.service';
import { describeApiError } from '../../shared/api-error';

interface DetailVm {
  txn: Transaction | null;
  audit: AuditEntry[];
  error: string | null;
}

@Component({
  selector: 'app-transaction-detail',
  imports: [CommonModule, RouterLink],
  templateUrl: './transaction-detail.html',
})
export class TransactionDetail {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(TransactionsApiService);

  protected readonly vm$ = this.route.paramMap.pipe(
    map((params) => params.get('id') ?? ''),
    switchMap((id) =>
      forkJoin({
        txn: this.api.get(id),
        audit: this.api.audit(id),
      }).pipe(
        map(({ txn, audit }): DetailVm => ({ txn, audit, error: null })),
        catchError((err: unknown) =>
          of<DetailVm>({ txn: null, audit: [], error: describeApiError(err) }),
        ),
      ),
    ),
  );

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
