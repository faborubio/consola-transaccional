import { HttpInterceptorFn } from '@angular/common/http';

/**
 * Genera un correlation ID por request; el gateway y los microservicios lo
 * propagan a sus logs estructurados — un request se sigue de punta a punta.
 */
export const correlationInterceptor: HttpInterceptorFn = (req, next) =>
  next(req.clone({ setHeaders: { 'X-Correlation-Id': crypto.randomUUID() } }));
