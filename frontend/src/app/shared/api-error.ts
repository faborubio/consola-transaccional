import { HttpErrorResponse } from '@angular/common/http';

interface ApiErrorBody {
  code?: string;
  message?: string;
  details?: { field?: string; issue?: string }[];
}

/**
 * Mapea el esquema de error uniforme del contrato (code/message/details) a
 * mensajes para el operador. Un solo lugar: los componentes no interpretan
 * códigos HTTP por su cuenta.
 */
export function describeApiError(err: unknown): string {
  if (!(err instanceof HttpErrorResponse)) {
    return 'Error inesperado.';
  }
  const body = (err.error ?? {}) as ApiErrorBody;
  switch (body.code) {
    case 'NOT_FOUND':
      return 'La transacción no existe o fue removida.';
    case 'VALIDATION_ERROR': {
      const detalle = body.details?.[0];
      return detalle?.field
        ? `Filtro inválido (${detalle.field}): ${detalle.issue ?? 'revise el valor'}.`
        : 'Parámetros inválidos; revise los filtros.';
    }
    case 'RATE_LIMITED':
      return 'Demasiadas solicitudes; espere unos segundos.';
    case 'FORBIDDEN_ROLE':
      return 'Su rol no permite esta acción.';
    case 'SEGREGATION_OF_DUTIES':
      return 'Quien inicia una transacción no puede aprobarla (segregación de funciones).';
    case 'INVALID_TRANSITION':
      return body.message ?? 'La transición de estado no es válida.';
    case 'STALE_VERSION':
      return 'La transacción fue modificada por otro usuario; recargue e intente de nuevo.';
    case 'UNAUTHORIZED':
      return 'Su sesión expiró; vuelva a iniciar sesión.';
  }
  if (err.status === 0) {
    return 'Sin conexión con el servidor.';
  }
  if (err.status >= 500) {
    return 'Error del servidor; intente nuevamente.';
  }
  return body.message ?? 'Error inesperado.';
}
