FROM caddy:2.11.7-alpine@sha256:eb4d35b7452d1ab6171fbdbe8d9275b2301dad6dad92115d91e19fb9b24d510f

# Include distribution security fixes published after the upstream image build.
RUN apk upgrade --no-cache

RUN addgroup -g 1001 nestswipe && \
    adduser -D -u 1001 -G nestswipe nestswipe && \
    chown -R nestswipe:nestswipe /data /config

ARG GIT_REVISION
LABEL org.opencontainers.image.source="https://github.com/ThomsCody/nestswipe" \
      org.opencontainers.image.revision="${GIT_REVISION}" \
      com.datadoghq.image.source_path="deploy/caddy/Dockerfile"

USER 1001:1001
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:2019/config/ || exit 1
