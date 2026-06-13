import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';

import { BASE_PATH } from './api-client';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { correlationInterceptor } from './core/interceptors/correlation.interceptor';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([correlationInterceptor, authInterceptor])),
    provideCharts(withDefaultRegisterables()),
    // Mismo origen: el API cuelga de /api en el gateway (que reescribe a los paths
    // reales del contrato). Relativo a propósito — sin URL ni puerto hardcodeado y
    // sin CORS. En dev, proxy.conf.json reenvía /api al gateway (ver angular.json).
    { provide: BASE_PATH, useValue: '/api' },
  ],
};
