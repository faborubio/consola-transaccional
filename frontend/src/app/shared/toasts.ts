import { Component, inject } from '@angular/core';
import { NgbToastModule } from '@ng-bootstrap/ng-bootstrap';

import { ToastService } from './toast.service';

@Component({
  selector: 'app-toasts',
  imports: [NgbToastModule],
  template: `
    <div class="toast-container position-fixed top-0 end-0 p-3" style="z-index: 1200">
      @for (toast of toastService.toasts(); track toast.id) {
        <ngb-toast
          [autohide]="true"
          [delay]="toast.kind === 'error' ? 8000 : 4000"
          [class]="toastClass(toast.kind)"
          (hidden)="toastService.dismiss(toast.id)"
        >
          {{ toast.message }}
        </ngb-toast>
      }
    </div>
  `,
})
export class Toasts {
  protected readonly toastService = inject(ToastService);

  protected toastClass(kind: string): string {
    return (
      {
        error: 'text-bg-danger',
        success: 'text-bg-success',
        info: 'text-bg-secondary',
      }[kind] ?? ''
    );
  }
}
