import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { ChartConfiguration } from 'chart.js';
import { BaseChartDirective } from 'ng2-charts';
import { catchError, map, of, startWith } from 'rxjs';

import { DashboardMetrics } from '../../api-client';
import { MetricsApiService } from '../../services/metrics-api.service';
import { Nav } from '../../shared/nav';
import { describeApiError } from '../../shared/api-error';

interface DashboardVm {
  metrics: DashboardMetrics | null;
  statusChart: ChartConfiguration<'doughnut'>['data'] | null;
  monthChart: ChartConfiguration<'bar'>['data'] | null;
  error: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  APROBADA: '#198754',
  RECHAZADA: '#dc3545',
  PENDIENTE: '#ffc107',
  EN_REVISION: '#0dcaf0',
  REVERTIDA: '#6c757d',
};

@Component({
  selector: 'app-dashboard',
  imports: [CommonModule, BaseChartDirective, Nav],
  templateUrl: './dashboard.html',
})
export class Dashboard {
  private readonly api = inject(MetricsApiService);

  protected readonly doughnutOptions: ChartConfiguration<'doughnut'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'right' } },
  };

  protected readonly barOptions: ChartConfiguration<'bar'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true } },
  };

  protected readonly vm$ = this.api.dashboard().pipe(
    map((metrics): DashboardVm => ({
      metrics,
      statusChart: {
        labels: metrics.byStatus.map((b) => b.status),
        datasets: [
          {
            data: metrics.byStatus.map((b) => b.count),
            backgroundColor: metrics.byStatus.map((b) => STATUS_COLORS[b.status] ?? '#adb5bd'),
          },
        ],
      },
      monthChart: {
        labels: metrics.byMonth.map((b) => b.month),
        datasets: [{ data: metrics.byMonth.map((b) => b.count), backgroundColor: '#0d6efd' }],
      },
      error: null,
    })),
    catchError((err: unknown) =>
      of<DashboardVm>({ metrics: null, statusChart: null, monthChart: null,
        error: describeApiError(err) }),
    ),
    startWith<DashboardVm | null>(null),
  );

  protected count(metrics: DashboardMetrics, status: string): number {
    return metrics.byStatus.find((b) => b.status === status)?.count ?? 0;
  }
}
