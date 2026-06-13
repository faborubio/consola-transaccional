import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, combineLatest, forkJoin, map, of, switchMap } from 'rxjs';

import {
  AuditEntry,
  Transaction,
  TransactionStatus,
  TransitionAction,
} from '../../api-client';
import { TokenStore } from '../../core/token-store.service';
import { TransactionsApiService } from '../../services/transactions-api.service';
import { describeApiError } from '../../shared/api-error';
import { ToastService } from '../../shared/toast.service';

interface DetailVm {
  txn: Transaction | null;
  audit: AuditEntry[];
  error: string | null;
}

/** Espejo UX de la máquina de estados del backend: decide qué botones mostrar.
 * La validación real vive en el servidor — esto solo evita ofrecer acciones
 * que van a fallar. */
const UI_ACTIONS: Partial<Record<TransactionStatus, TransitionAction[]>> = {
  PENDIENTE: ['APROBAR', 'RECHAZAR', 'ENVIAR_A_REVISION'],
  EN_REVISION: ['APROBAR', 'RECHAZAR'],
  APROBADA: ['REVERTIR'],
};

const NEEDS_REASON: TransitionAction[] = ['RECHAZAR', 'REVERTIR'];

const ACTION_LABELS: Record<TransitionAction, string> = {
  APROBAR: 'Aprobar',
  RECHAZAR: 'Rechazar',
  ENVIAR_A_REVISION: 'Enviar a revisión',
  REVERTIR: 'Revertir',
};

@Component({
  selector: 'app-transaction-detail',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './transaction-detail.html',
})
export class TransactionDetail {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(TransactionsApiService);
  private readonly toasts = inject(ToastService);
  private readonly store = inject(TokenStore);

  private readonly reload$ = new BehaviorSubject<void>(undefined);

  protected readonly isSupervisor = this.store.hasRole('supervisor');
  protected reason = '';
  protected readonly pending = signal(false);
  protected readonly actionError = signal<string | null>(null);

  protected readonly vm$ = combineLatest([this.route.paramMap, this.reload$]).pipe(
    map(([params]) => params.get('id') ?? ''),
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

  protected actionsFor(status: TransactionStatus): TransitionAction[] {
    return UI_ACTIONS[status] ?? [];
  }

  protected label(action: TransitionAction): string {
    return ACTION_LABELS[action];
  }

  protected needsReason(action: TransitionAction): boolean {
    return NEEDS_REASON.includes(action);
  }

  protected submit(txn: Transaction, action: TransitionAction): void {
    this.actionError.set(null);
    if (this.needsReason(action) && !this.reason.trim()) {
      this.actionError.set(`${ACTION_LABELS[action]} exige un motivo.`);
      return;
    }
    this.pending.set(true);
    this.api
      .transition(txn.id, action, txn.version, this.reason.trim() || undefined)
      .subscribe({
        next: (updated) => {
          this.pending.set(false);
          this.reason = '';
          this.toasts.success(`Transición aplicada: ahora está ${updated.status}.`);
          this.reload$.next();
        },
        error: (err: unknown) => {
          this.pending.set(false);
          this.toasts.error(describeApiError(err));
          // STALE_VERSION: otro actor mutó primero — recargar muestra la verdad
          if (
            err instanceof HttpErrorResponse &&
            (err.error as { code?: string })?.code === 'STALE_VERSION'
          ) {
            this.reload$.next();
          }
        },
      });
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
