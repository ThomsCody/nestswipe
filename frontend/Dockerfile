FROM node:24.22.1-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS dev
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM node:24.22.1-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
ARG VITE_DD_APPLICATION_ID
ARG VITE_DD_CLIENT_TOKEN
ARG VITE_DD_SITE
ARG VITE_DD_ENV
ARG VITE_DD_ALLOWED_TRACING_URL
ENV VITE_DD_APPLICATION_ID=$VITE_DD_APPLICATION_ID
ENV VITE_DD_CLIENT_TOKEN=$VITE_DD_CLIENT_TOKEN
ENV VITE_DD_SITE=$VITE_DD_SITE
ENV VITE_DD_ENV=$VITE_DD_ENV
ENV VITE_DD_ALLOWED_TRACING_URL=$VITE_DD_ALLOWED_TRACING_URL
RUN npm run build

ARG GIT_REVISION
LABEL org.opencontainers.image.source="https://github.com/ThomsCody/nestswipe" \
      org.opencontainers.image.revision="${GIT_REVISION}" \
      com.datadoghq.image.source_path="frontend/Dockerfile"

FROM nginx:alpine
ARG GIT_REVISION
LABEL org.opencontainers.image.source="https://github.com/ThomsCody/nestswipe" \
      org.opencontainers.image.revision="${GIT_REVISION}" \
      com.datadoghq.image.source_path="frontend/Dockerfile"
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN sed -i '/^user /d; s@/var/run/nginx.pid@/tmp/nginx.pid@; s@/run/nginx.pid@/tmp/nginx.pid@' /etc/nginx/nginx.conf && \
    chown -R nginx:nginx /var/cache/nginx
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
