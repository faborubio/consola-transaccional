import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  BehaviorSubject,
  Subject,
  catchError,
  combineLatest,
  debounceTime,
  map,
  of,
  startWith,
  switchMap,
} from 'rxjs';

import { AuditEntry, TransactionStatus, TransitionAction } from '../../api-client';
import { TokenStore } from '../../core/token-store.service';
import { MetricsApiService } from '../../services/metrics-api.service';
import { Nav } from '../../shared/nav';
import { describeApiError } from '../../shared/api-error';

interface ActivityVm {
  entries: AuditEntry[];
  error: string | null;
}

@Component({
  selector: 'app-activity',
  imports: [CommonModule, FormsModule, RouterLink, Nav],
  templateUrl: './activity.html',
})
export class Activity {
  private readonly api = inject(MetricsApiService);
  private readonly store = inject(TokenStore);

  // Solo el auditor puede mirar la actividad de otro actor (la autorización
  // real la impone el servidor; esto solo muestra/oculta el control).
  protected readonly isAuditor = this.store.hasRole('auditor');

  private readonly filter$ = new BehaviorSubject<TransitionAction | undefined>(undefined);
  private readonly actor$ = new Subject<string>();

  protected readonly vm$ = combineLatest([
    this.filter$,
    this.actor$.pipe(debounceTime(300), startWith('')),
  ]).pipe(
    switchMap(([action, actor]) =>
      this.api.myActivity(action, actor.trim() || undefined).pipe(
        map((entries): ActivityVm => ({ entries, error: null })),
        catchError((err: unknown) =>
          of<ActivityVm>({ entries: [], error: describeApiError(err) }),
        ),
        startWith<ActivityVm | null>(null),
      ),
    ),
  );

  protected setFilter(value: string): void {
    this.filter$.next((value as TransitionAction) || undefined);
  }

  protected setActor(value: string): void {
    this.actor$.next(value);
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
