FROM node:22-alpine

# Chromium + ffmpeg + fonts for headless rendering and clip concatenation.
# Alpine's chromium ships with required deps; ffmpeg is needed for both
# Seedance clip concat and audio mux; ttf-* + font-noto-cjk give CJK glyph
# coverage in burned-in subtitles.
RUN apk add --no-cache \
      chromium \
      ffmpeg \
      ttf-freefont \
      font-noto \
      font-noto-cjk \
      ca-certificates

ENV PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser \
    REMOTION_CHROME_EXECUTABLE=/usr/bin/chromium-browser \
    NODE_ENV=production

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --omit=dev --no-audit --no-fund

COPY src ./src
COPY server.mjs ./

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3001/health || exit 1

CMD ["node", "server.mjs"]
