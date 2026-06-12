import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthApiService } from '../../services/auth-api.service';

@Component({
  selector: 'app-login',
  imports: [FormsModule],
  templateUrl: './login.html',
})
export class Login {
  private readonly authApi = inject(AuthApiService);
  private readonly router = inject(Router);

  protected username = '';
  protected password = '';
  protected readonly error = signal<string | null>(null);
  protected readonly loading = signal(false);

  protected submit(): void {
    this.error.set(null);
    this.loading.set(true);
    this.authApi.login(this.username, this.password).subscribe({
      next: () => void this.router.navigate(['/transactions']),
      error: (err: unknown) => {
        this.loading.set(false);
        if (err instanceof HttpErrorResponse && err.status === 401) {
          this.error.set('Credenciales inválidas.');
        } else if (err instanceof HttpErrorResponse && err.status === 429) {
          this.error.set('Demasiados intentos; espere un momento.');
        } else {
          this.error.set('Error inesperado al iniciar sesión.');
        }
      },
    });
  }
}
