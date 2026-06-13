import { Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';

import { AuthApiService } from '../services/auth-api.service';

@Component({
  selector: 'app-nav',
  imports: [RouterLink, RouterLinkActive],
  template: `
    <nav class="navbar navbar-expand bg-dark border-bottom border-body mb-0" data-bs-theme="dark">
      <div class="container-fluid">
        <span class="navbar-brand mb-0">Consola de Operaciones</span>
        <ul class="navbar-nav me-auto">
          <li class="nav-item">
            <a class="nav-link" routerLink="/transactions" routerLinkActive="active"
               [routerLinkActiveOptions]="{ exact: false }">Transacciones</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" routerLink="/dashboard" routerLinkActive="active">Dashboard</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" routerLink="/activity" routerLinkActive="active">Mi actividad</a>
          </li>
        </ul>
        <button class="btn btn-outline-light btn-sm" (click)="logout()">Cerrar sesión</button>
      </div>
    </nav>
  `,
})
export class Nav {
  private readonly authApi = inject(AuthApiService);
  private readonly router = inject(Router);

  protected logout(): void {
    this.authApi.logout();
    void this.router.navigate(['/login']);
  }
}
