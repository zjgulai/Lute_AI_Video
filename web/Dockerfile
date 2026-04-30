# Multi-stage Dockerfile for AI Video frontend
# P3-3: Pre-built image — no runtime npm install/build

# ── Stage 1: Build ──
FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts 2>/dev/null || npm install --ignore-scripts

COPY . .

# NEXT_PUBLIC_* vars must be set at build time (Next.js inlines them).
# Override with --build-arg at docker build time.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8001
ARG NEXT_PUBLIC_IS_DEMO=false
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_IS_DEMO=${NEXT_PUBLIC_IS_DEMO}

RUN npm run build

# ── Stage 2: Runtime ──
FROM node:22-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Re-declare build args so they are available as ENV at runtime
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_IS_DEMO
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_IS_DEMO=${NEXT_PUBLIC_IS_DEMO}

# Copy only the production artifacts
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# P3-6: Health check (use 127.0.0.1 to avoid IPv6 ::1 fallback)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:3000 || exit 1

EXPOSE 3000

CMD ["node", "server.js"]
