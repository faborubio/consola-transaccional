// Load test del camino caliente: el listado filtrado (estado + orden por fecha, que usa
// el índice ESR) con paginación por cursor — la query dominante del operador sobre 500k.
//
// Pega DIRECTO a los servicios (no por el gateway): el rate-limit del edge (20 r/s)
// mediría el límite, no la capacidad del backend. `make load` lo corre como contenedor
// en la red de compose con AUTH_BASE/TXN_BASE = http://{auth,transactions}:8000.
import http from 'k6/http';
import { check, sleep } from 'k6';

const AUTH_BASE = __ENV.AUTH_BASE || 'http://localhost:8001';
const TXN_BASE = __ENV.TXN_BASE || 'http://localhost:8002';
const USER = __ENV.K6_USER || 'operador1';
const PASS = __ENV.K6_PASS || 'Demo1234!';
// status + sort=-createdAt usa el índice compuesto (estado, createdAt); el patrón real.
const QUERY = __ENV.K6_QUERY || 'status=APROBADA&sort=-createdAt&limit=25';

export const options = {
  stages: [
    { duration: '30s', target: 25 }, // ramp-up
    { duration: '1m', target: 25 }, //  carga sostenida
    { duration: '15s', target: 0 }, //  ramp-down
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'], // <1% de errores
    http_req_duration: ['p(95)<800'], // ajustar tras la primera medición en la VM
  },
};

export function setup() {
  const res = http.post(
    `${AUTH_BASE}/auth/login`,
    JSON.stringify({ username: USER, password: PASS }),
    { headers: { 'Content-Type': 'application/json' } },
  );
  check(res, { 'login 200': (r) => r.status === 200 });
  return { token: res.json('accessToken') };
}

export default function (data) {
  const params = { headers: { Authorization: `Bearer ${data.token}` } };

  // Primera página del listado filtrado.
  let res = http.get(`${TXN_BASE}/transactions?${QUERY}`, params);
  check(res, { 'listado 200': (r) => r.status === 200 });

  // Seguir una página por el cursor (simula el scroll/paginación del operador).
  const cursor = res.json('pageInfo.nextCursor');
  if (cursor) {
    res = http.get(`${TXN_BASE}/transactions?${QUERY}&cursor=${encodeURIComponent(cursor)}`, params);
    check(res, { 'pagina 2 200': (r) => r.status === 200 });
  }

  sleep(1);
}
