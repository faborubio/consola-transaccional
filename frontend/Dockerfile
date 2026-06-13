# Imagen edge: compila el SPA Angular y lo sirve con el mismo nginx que actúa de
# gateway (sirve estáticos + proxea /api). Una sola puerta de entrada en k8s.
#
# NOTA: el build context es la RAÍZ del repo (no frontend/), porque necesita tanto
# frontend/ como infra/gateway/nginx.conf. Construir con:
#   docker build -f frontend/Dockerfile -t consola-edge .

FROM node:24-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx ng build --configuration production

FROM nginx:1.27-alpine
# El build de Angular (application builder) emite los estáticos en dist/<proj>/browser.
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
# Mismo nginx.conf que el gateway de compose: el location / sirve el SPA aquí.
COPY infra/gateway/nginx.conf /etc/nginx/nginx.conf
EXPOSE 8080
