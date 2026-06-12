import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AuditEntry,
  TransactionsService,
  Transaction,
  TransactionPage,
  TransactionStatus,
  TransactionType,
} from '../api-client';

/**
 * Capa propia sobre el cliente generado: los componentes consumen esta API,
 * nunca el cliente directamente. Aísla al frontend de regeneraciones del
 * contrato (la firma posicional del generador cambia con cada parámetro nuevo).
 */
export interface TransactionFilters {
  status?: TransactionStatus[];
  type?: TransactionType;
  minAmount?: number;
  maxAmount?: number;
  currency?: string;
  counterparty?: string;
  dateFrom?: string;
  dateTo?: string;
  sort?: string;
}

@Injectable({ providedIn: 'root' })
export class TransactionsApiService {
  private readonly client = inject(TransactionsService);

  list(
    filters: TransactionFilters = {},
    cursor?: string,
    limit = 25,
  ): Observable<TransactionPage> {
    return this.client.listTransactions(
      cursor,
      limit,
      filters.status,
      filters.type,
      filters.minAmount,
      filters.maxAmount,
      filters.currency,
      filters.counterparty,
      filters.dateFrom,
      filters.dateTo,
      filters.sort ?? '-createdAt',
    );
  }

  get(id: string): Observable<Transaction> {
    return this.client.getTransaction(id);
  }

  audit(id: string): Observable<AuditEntry[]> {
    return this.client.getTransactionAudit(id);
  }
}
