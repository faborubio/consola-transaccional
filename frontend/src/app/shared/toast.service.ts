import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  message: string;
  kind: 'error' | 'success' | 'info';
}

let nextId = 0;

@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([]);

  error(message: string): void {
    this.push(message, 'error');
  }

  success(message: string): void {
    this.push(message, 'success');
  }

  dismiss(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }

  private push(message: string, kind: Toast['kind']): void {
    const toast: Toast = { id: nextId++, message, kind };
    this.toasts.update((list) => [...list, toast]);
  }
}
