ARG NODE_IMAGE=node:22.23.2-trixie-slim@sha256:7b8a0c89c54499bee567618f96578e1a12a800f062fbdbfd1fb6a443fa6f6284
ARG FFMPEG_BUILDER_IMAGE=python:3.12.14-slim-trixie@sha256:e5c9fa26ffb76e11e0f054f30dc2523a2f9693f0c36c0cf1e39b27e152d899fc
ARG CHROME_PACKAGE_STAGE=chrome-download

FROM ${FFMPEG_BUILDER_IMAGE} AS ffmpeg-h10-build
ARG APT_MIRROR=deb.debian.org
COPY docker/ffmpeg/install-h10-build-deps.sh /usr/local/bin/install-h10-build-deps.sh
RUN chmod 0555 /usr/local/bin/install-h10-build-deps.sh \
    && /usr/local/bin/install-h10-build-deps.sh
ADD --checksum=sha256:de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f \
  https://deb.debian.org/debian/pool/main/f/ffmpeg/ffmpeg_7.1.5.orig.tar.xz \
  /opt/ffmpeg/ffmpeg_7.1.5.orig.tar.xz
ADD --checksum=sha256:a1be51d8a10744952fe94fa318bf71bbc8074bed0951382c079ab7ef227f74ef \
  https://deb.debian.org/debian-security/pool/updates/main/f/ffmpeg/ffmpeg_7.1.5-0+deb13u1.debian.tar.xz \
  /opt/ffmpeg/ffmpeg_7.1.5-0+deb13u1.debian.tar.xz
COPY docker/ffmpeg/86708357d126af84c16f80d9c57335d1e8c845c5.patch /opt/ffmpeg/
COPY docker/ffmpeg/02fc47e13f903768b75f7985a2706a6223ab4506.patch /opt/ffmpeg/
COPY docker/ffmpeg/16b2049d4d5222db6cd7c031409058571c94f6a9.patch /opt/ffmpeg/
COPY docker/ffmpeg/9d786e4b5e9b8482651928574de33772aeee7be1.patch /opt/ffmpeg/
COPY docker/ffmpeg/1c10bcc2e17255dacb717a25ab3db142ce390602.patch /opt/ffmpeg/
COPY docker/ffmpeg/1cdeb3c4e7f1f8566d846b9b451e01c376398818.patch /opt/ffmpeg/
COPY docker/ffmpeg/65b0dab903e5975e036b30ecc58f5935d4f151e0-debian-7.1.5-backport.patch /opt/ffmpeg/
COPY docker/ffmpeg/aca41d3d9327be4d6ab036f494b700118fcc04e1-ffmpeg-7.1.5-backport.patch /opt/ffmpeg/
COPY docker/ffmpeg/build-h10-debs.sh /usr/local/bin/build-h10-debs.sh
RUN chmod 0555 /usr/local/bin/build-h10-debs.sh \
    && /usr/local/bin/build-h10-debs.sh

FROM ${NODE_IMAGE} AS chrome-download
ADD --checksum=sha256:4193e00b6d5d5969ee63f7a69596868f546aa0e8cb077b3e0bf9cc1e2c719d00 \
  https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_150.0.7871.186-1_amd64.deb \
  /google-chrome-stable.deb

FROM ${CHROME_PACKAGE_STAGE} AS chrome-package

FROM ${NODE_IMAGE}

ARG RELEASE_SOURCE_SHA
ARG APP_VERSION
LABEL org.opencontainers.image.revision="${RELEASE_SOURCE_SHA}" \
      org.opencontainers.image.version="${APP_VERSION}"

ARG TARGETARCH
ARG APT_MIRROR=deb.debian.org
ARG GOOGLE_CHROME_VERSION=150.0.7871.186-1
ARG GOOGLE_CHROME_SHA256=4193e00b6d5d5969ee63f7a69596868f546aa0e8cb077b3e0bf9cc1e2c719d00
ARG DEBIAN_FRONTEND=noninteractive

# Chrome is fixed to the first upstream stable build after the vulnerable
# 150.0.7871.128-r0 package. The exact .deb is checksum-bound. H10 rebuilds
# Debian FFmpeg from checksum-pinned source with eight upstream fixes (two
# version-context backports) and removes the unused IAMF demuxer; release scans remain
# blocking unless every High/Critical is absent or covered by an exact,
# unexpired reviewed rule.
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
COPY --from=ffmpeg-h10-build /ffmpeg-debs /tmp/ffmpeg-debs
COPY docker/ffmpeg/verify-h10-runtime.sh /usr/local/bin/verify-h10-runtime.sh
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
      fonts-freefont-ttf \
      fonts-noto \
      fonts-noto-cjk \
      /tmp/ffmpeg-debs/*.deb \
      /tmp/google-chrome-stable.deb \
    && test "$(dpkg-query -W -f='${Version}' google-chrome-stable)" = \
      "${GOOGLE_CHROME_VERSION}" \
    && chmod 0555 /usr/local/bin/verify-h10-runtime.sh \
    && /usr/local/bin/verify-h10-runtime.sh \
    && rm -f /tmp/google-chrome-stable.deb \
    && rm -rf /tmp/ffmpeg-debs /usr/local/bin/verify-h10-runtime.sh \
      /var/lib/apt/lists/*

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
COPY rendering/healthcheck.mjs rendering/media-safety.mjs rendering/server.mjs ./

RUN (getent group 999 >/dev/null || groupadd --gid 999 renderer) \
    && (getent passwd 999 >/dev/null \
      || useradd --uid 999 --gid 999 --no-create-home --shell /usr/sbin/nologin renderer) \
    && mkdir -p /app/output /run/rendering \
    && chown 999:999 /app/output /run/rendering

USER 999:999

HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
  CMD ["node", "/app/healthcheck.mjs"]

CMD ["node", "server.mjs"]
