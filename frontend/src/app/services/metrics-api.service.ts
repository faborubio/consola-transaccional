import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { AuditEntry, DashboardMetrics, MetricsService, TransitionAction } from '../api-client';

/** Capa propia sobre el cliente generado (igual que transactions/auth). */
@Injectable({ providedIn: 'root' })
export class MetricsApiService {
  private readonly client = inject(MetricsService);

  dashboard(): Observable<DashboardMetrics> {
    return this.client.getDashboardMetrics();
  }

  myActivity(action?: TransitionAction, actor?: string, limit = 50): Observable<AuditEntry[]> {
    return this.client.getMyActivity(actor, action, limit);
  }
}
