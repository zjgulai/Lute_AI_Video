import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_SOCKET_PATH = "/run/rendering/rendering.sock";
const DEFAULT_TIMEOUT_MS = 20_000;

export function probeRendererHealth(
  socketPath = DEFAULT_SOCKET_PATH,
  timeoutMs = DEFAULT_TIMEOUT_MS,
) {
  return new Promise((resolve) => {
    let settled = false;
    let request;
    let response;
    const finish = (healthy) => {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      response?.destroy();
      request?.destroy();
      resolve(healthy);
    };
    const deadline = setTimeout(() => finish(false), timeoutMs);

    request = http.request(
      { socketPath, path: "/health" },
      (incoming) => {
        response = incoming;
        if (incoming.statusCode !== 200) {
          finish(false);
          return;
        }
        incoming.once("aborted", () => finish(false));
        incoming.once("error", () => finish(false));
        incoming.once("close", () => {
          if (!incoming.complete) finish(false);
        });
        incoming.once("end", () => finish(incoming.complete));
        incoming.resume();
      },
    );
    request.once("error", () => finish(false));
    request.end();
  });
}

const isMain = (
  process.argv[1]
  && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
);
if (isMain) {
  const socketPath = (
    process.env.RENDERING_SERVICE_SOCKET
    ?? DEFAULT_SOCKET_PATH
  );
  process.exit(await probeRendererHealth(socketPath) ? 0 : 1);
}
