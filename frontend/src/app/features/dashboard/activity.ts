import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { BehaviorSubject, catchError, map, of, startWith, switchMap } from 'rxjs';

import { AuditEntry, TransactionStatus, TransitionAction } from '../../api-client';
import { MetricsApiService } from '../../services/metrics-api.service';
import { Nav } from '../../shared/nav';
import { describeApiError } from '../../shared/api-error';

interface ActivityVm {
  entries: AuditEntry[];
  error: string | null;
}

@Component({
  selector: 'app-activity',
  imports: [CommonModule, RouterLink, Nav],
  templateUrl: './activity.html',
})
export class Activity {
  private readonly api = inject(MetricsApiService);

  protected readonly actions: (TransitionAction | '')[] = [
    '',
    'APROBAR',
    'RECHAZAR',
    'ENVIAR_A_REVISION',
    'REVERTIR',
  ];
  private readonly filter$ = new BehaviorSubject<TransitionAction | undefined>(undefined);

  protected readonly vm$ = this.filter$.pipe(
    switchMap((action) =>
      this.api.myActivity(action).pipe(
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
