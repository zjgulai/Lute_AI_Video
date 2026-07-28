# syntax=docker/dockerfile:1.7

ARG NODE_IMAGE=node:22-trixie-slim@sha256:e6d9a389d34ff9678438af985c9913fbd1eb6ed36e80fea56644f4b4f6dd70ba
ARG CHROME_PACKAGE_STAGE=chrome-download

FROM ${NODE_IMAGE} AS chrome-download
ADD --checksum=sha256:4193e00b6d5d5969ee63f7a69596868f546aa0e8cb077b3e0bf9cc1e2c719d00 \
  https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_150.0.7871.186-1_amd64.deb \
  /google-chrome-stable.deb

FROM ${CHROME_PACKAGE_STAGE} AS chrome-package

FROM ${NODE_IMAGE}

ARG RELEASE_SOURCE_SHA
LABEL org.opencontainers.image.revision="${RELEASE_SOURCE_SHA}"

ARG TARGETARCH
ARG APT_MIRROR=deb.debian.org
ARG GOOGLE_CHROME_VERSION=150.0.7871.186-1
ARG GOOGLE_CHROME_SHA256=4193e00b6d5d5969ee63f7a69596868f546aa0e8cb077b3e0bf9cc1e2c719d00
ARG DEBIAN_FRONTEND=noninteractive

# Chrome is fixed to the first upstream stable build after the vulnerable
# 150.0.7871.128-r0 package. The exact .deb is checksum-bound. FFmpeg is
# supplied by supported Debian 13; release scans remain blocking unless every
# High/Critical is either absent or covered by an exact, unexpired reviewed rule.
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get install -y --no-install-recommends \
      -o Acquire::Retries=5 \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=chrome-package /google-chrome-stable.deb /tmp/google-chrome-stable.deb
RUN echo "${GOOGLE_CHROME_SHA256}  /tmp/google-chrome-stable.deb" | sha256sum -c - \
    && if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i \
        -e "s|http://${APT_MIRROR}|https://${APT_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get -o Acquire::Retries=5 update \
    && test "${TARGETARCH}" = "amd64" \
    && apt-get install -y --no-install-recommends \
      -o Acquire::Retries=5 \
      ffmpeg \
      fonts-freefont-ttf \
      fonts-noto \
      fonts-noto-cjk \
      /tmp/google-chrome-stable.deb \
    && test "$(dpkg-query -W -f='${Version}' google-chrome-stable)" = \
      "${GOOGLE_CHROME_VERSION}" \
    && rm -f /tmp/google-chrome-stable.deb \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_DOWNLOAD=true \
    RENDERING_SERVICE_SOCKET=/run/rendering/rendering.sock \
    HOME=/tmp/renderer-home \
    XDG_DATA_HOME=/usr/share \
    NODE_ENV=production

WORKDIR /app

COPY rendering/package.json rendering/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx \
    && rm -rf /tmp/renderer-home \
    && test ! -e /usr/local/lib/node_modules/npm

COPY rendering/src ./src
COPY rendering/media-safety.mjs rendering/server.mjs ./

RUN (getent group 999 >/dev/null || groupadd --gid 999 renderer) \
    && (getent passwd 999 >/dev/null \
      || useradd --uid 999 --gid 999 --no-create-home --shell /usr/sbin/nologin renderer) \
    && mkdir -p /app/output /run/rendering \
    && chown 999:999 /app/output /run/rendering

USER 999:999

HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
  CMD ["node", "-e", "const h=require('node:http');const r=h.request({socketPath:'/run/rendering/rendering.sock',path:'/health'},x=>process.exit(x.statusCode===200?0:1));r.on('error',()=>process.exit(1));r.end()"]

CMD ["node", "server.mjs"]
