# Multi-stage Dockerfile for AI Video frontend
# P3-3: Pre-built image — no runtime dependency install/build

ARG NODE_IMAGE=node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32

# ── Stage 1: Build ──
FROM ${NODE_IMAGE} AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .

# NEXT_PUBLIC_* vars must be set at build time (Next.js inlines them).
# Override with --build-arg at docker build time.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8001
ARG NEXT_PUBLIC_IS_DEMO=false
ARG NEXT_PUBLIC_API_KEY=
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_IS_DEMO=${NEXT_PUBLIC_IS_DEMO}
ENV NEXT_PUBLIC_API_KEY=${NEXT_PUBLIC_API_KEY}

RUN npm run build

# ── Stage 2: Runtime ──
FROM ${NODE_IMAGE} AS runner

ARG RELEASE_SOURCE_SHA
ARG APP_VERSION
LABEL org.opencontainers.image.revision="${RELEASE_SOURCE_SHA}" \
      org.opencontainers.image.version="${APP_VERSION}"

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0

# Re-declare build args so they are available as ENV at runtime
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_IS_DEMO
ARG NEXT_PUBLIC_API_KEY
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_IS_DEMO=${NEXT_PUBLIC_IS_DEMO}
ENV NEXT_PUBLIC_API_KEY=${NEXT_PUBLIC_API_KEY}

# The standalone server needs Node.js only. Remove the bundled package manager
# so its build-time dependency tree is not retained in the runtime image.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx \
    && test ! -e /usr/local/lib/node_modules/npm

# Copy only the production artifacts
COPY --chown=1000:1000 --from=builder /app/.next/standalone ./
COPY --chown=1000:1000 --from=builder /app/.next/static ./.next/static
COPY --chown=1000:1000 --from=builder /app/public ./public

# P3-6: Health check (use 127.0.0.1 to avoid IPv6 ::1 fallback)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:3000 || exit 1

EXPOSE 3000

USER 1000:1000

CMD ["node", "server.js"]
