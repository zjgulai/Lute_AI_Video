import express from "express";
import { AsyncLocalStorage } from "node:async_hooks";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  chmod,
  link,
  lstat,
  mkdir,
  open,
  readFile,
  realpath,
  rm,
  stat,
  unlink,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

import {
  RendererBoundaryError,
  buildConcatManifest,
  reserveRenderOperation,
  validateAssembleRequest,
} from "./media-safety.mjs";

const OUTPUT_DIR = process.env.OUTPUT_DIR || "/app/output";
const REMOTION_PROJECT = "/app";
const PRODUCTION_RENDERER_HOME = "/tmp/renderer-home";
const RENDERING_SERVICE_SOCKET = (
  process.env.RENDERING_SERVICE_SOCKET || "/run/rendering/rendering.sock"
);
const CHROME_EXECUTABLE = "/usr/bin/google-chrome-stable";
const COMMAND_OUTPUT_LIMIT = 64 * 1024;
const MAX_RENDER_CONCURRENCY = 1;
const SERVER_RENDER_DEADLINE_MS = 540_000;
// Keep dependency probes below the container's 30s healthcheck deadline while
// allowing cold Chrome/FFmpeg startup on constrained or emulated hosts.
const HEALTH_PROBE_TIMEOUT_MS = 20_000;
const MAX_MEDIA_DURATION_SECONDS = 180;
const MAX_VIDEO_DIMENSION = 7680;
const MAX_VIDEO_PIXELS = 7680 * 4320;
const VIDEO_CODEC_ALLOWLIST = new Set(["h264", "vp8", "vp9"]);
const AUDIO_CODEC_ALLOWLIST = new Set([
  "aac",
  "flac",
  "mp3",
  "opus",
  "pcm_s16le",
  "pcm_s24le",
  "vorbis",
]);
const deadlineContext = new AsyncLocalStorage();

function deadlineError() {
  return new RendererBoundaryError("render_deadline_exceeded", 503);
}

export function assertRenderDeadline() {
  const state = deadlineContext.getStore();
  if (!state) return;
  if (state.committed) return;
  if (state.signal.aborted || Date.now() >= state.expiresAt) {
    if (!state.signal.aborted) state.controller.abort();
    throw deadlineError();
  }
}

function markRenderCommitted() {
  const state = deadlineContext.getStore();
  if (state) state.committed = true;
}

function terminateProcessGroup(proc) {
  if (!proc.pid) return;
  try {
    process.kill(-proc.pid, "SIGKILL");
  } catch {
    try {
      proc.kill("SIGKILL");
    } catch {
      // The process already exited.
    }
  }
}

export async function runWithRenderDeadline(durationMs, operation) {
  if (!Number.isFinite(durationMs) || durationMs <= 0) {
    throw deadlineError();
  }
  const controller = new AbortController();
  const state = {
    committed: false,
    controller,
    expiresAt: Date.now() + durationMs,
    signal: controller.signal,
  };
  const timer = setTimeout(() => controller.abort(), durationMs);
  timer.unref();
  try {
    return await deadlineContext.run(state, async () => {
      assertRenderDeadline();
      const result = await operation(state.signal);
      assertRenderDeadline();
      return result;
    });
  } finally {
    clearTimeout(timer);
  }
}

export function runCmd(cmd, args, { cwd, timeoutMs = 600_000 } = {}) {
  const deadline = deadlineContext.getStore();
  try {
    assertRenderDeadline();
  } catch (error) {
    return Promise.reject(error);
  }
  const remainingMs = deadline === undefined
    ? timeoutMs
    : deadline.expiresAt - Date.now();
  const effectiveTimeoutMs = Math.min(timeoutMs, remainingMs);
  if (!Number.isFinite(effectiveTimeoutMs) || effectiveTimeoutMs <= 0) {
    return Promise.reject(new Error("command_timeout"));
  }
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, args, {
      cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
      detached: true,
    });
    let stdout = "";
    let stderr = "";
    let outputBytes = 0;
    let settled = false;
    let terminationError = null;
    let timer;
    const abortProcess = () => {
      terminationError ||= deadlineError();
      terminateProcessGroup(proc);
    };
    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      deadline?.signal.removeEventListener("abort", abortProcess);
      if (error) reject(error);
      else resolve(value);
    };
    const collect = (target) => (chunk) => {
      outputBytes += chunk.length;
      if (outputBytes > COMMAND_OUTPUT_LIMIT) {
        terminationError ||= new Error("command_output_limit");
        terminateProcessGroup(proc);
        return;
      }
      if (target === "stdout") stdout += chunk.toString();
      else stderr += chunk.toString();
    };
    proc.stdout.on("data", collect("stdout"));
    proc.stderr.on("data", collect("stderr"));
    proc.on("error", () => finish(new Error("command_start_failed")));
    proc.on("close", (code) => {
      if (terminationError) finish(terminationError);
      else if (code === 0) finish(null, { stdout, stderr });
      else finish(new Error("command_failed"));
    });
    deadline?.signal.addEventListener("abort", abortProcess, { once: true });
    if (deadline?.signal.aborted) abortProcess();
    timer = setTimeout(() => {
      terminationError ||= deadlineError();
      terminateProcessGroup(proc);
    }, effectiveTimeoutMs);
    timer.unref();
  });
}

async function hashFile(filePath) {
  assertRenderDeadline();
  const handle = await open(filePath, fsConstants.O_RDONLY);
  const digest = createHash("sha256");
  const buffer = Buffer.alloc(1024 * 1024);
  let offset = 0;
  try {
    while (true) {
      assertRenderDeadline();
      const { bytesRead } = await handle.read(
        buffer,
        0,
        buffer.length,
        offset,
      );
      if (bytesRead === 0) break;
      digest.update(buffer.subarray(0, bytesRead));
      offset += bytesRead;
    }
    assertRenderDeadline();
  } finally {
    await handle.close();
  }
  return digest.digest("hex");
}

async function probeFile(filePath) {
  assertRenderDeadline();
  try {
    const result = await stat(filePath);
    assertRenderDeadline();
    return { exists: result.isFile(), size: result.size };
  } catch (error) {
    if (error instanceof RendererBoundaryError) throw error;
    return { exists: false, size: 0 };
  }
}

async function probeRemotionVersion() {
  try {
    const pkg = JSON.parse(
      await readFile(
        path.join(REMOTION_PROJECT, "node_modules", "remotion", "package.json"),
        "utf8",
      ),
    );
    return pkg.version || null;
  } catch {
    return null;
  }
}

async function probeCommand(command, args) {
  try {
    await runCmd(command, args, { timeoutMs: HEALTH_PROBE_TIMEOUT_MS });
    return true;
  } catch {
    return false;
  }
}

async function snapshotMedia(validated, destination) {
  assertRenderDeadline();
  let sourceHandle;
  let destinationHandle;
  let completed = false;
  try {
    sourceHandle = await open(
      validated.path,
      fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW || 0),
    );
    destinationHandle = await open(
      destination,
      fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL,
      0o400,
    );
    const sourceBefore = await sourceHandle.stat();
    if (
      !sourceBefore.isFile()
      || sourceBefore.dev !== validated.device
      || sourceBefore.ino !== validated.inode
      || sourceBefore.size !== validated.size
      || sourceBefore.mtimeMs !== validated.modifiedMs
    ) {
      throw new RendererBoundaryError("media_snapshot_changed", 409);
    }
    const digest = createHash("sha256");
    const buffer = Buffer.alloc(1024 * 1024);
    let offset = 0;
    while (offset < validated.size) {
      assertRenderDeadline();
      const length = Math.min(buffer.length, validated.size - offset);
      const { bytesRead } = await sourceHandle.read(buffer, 0, length, offset);
      if (bytesRead <= 0) {
        throw new RendererBoundaryError("media_snapshot_changed", 409);
      }
      let written = 0;
      while (written < bytesRead) {
        assertRenderDeadline();
        const result = await destinationHandle.write(
          buffer,
          written,
          bytesRead - written,
          offset + written,
        );
        if (result.bytesWritten <= 0) {
          throw new RendererBoundaryError("media_snapshot_changed", 409);
        }
        written += result.bytesWritten;
      }
      digest.update(buffer.subarray(0, bytesRead));
      offset += bytesRead;
    }
    await destinationHandle.sync();
    assertRenderDeadline();
    const [sourceAfter, snapshot] = await Promise.all([
      sourceHandle.stat(),
      destinationHandle.stat(),
    ]);
    if (
      sourceAfter.dev !== sourceBefore.dev
      || sourceAfter.ino !== sourceBefore.ino
      || sourceAfter.size !== sourceBefore.size
      || sourceAfter.mtimeMs !== sourceBefore.mtimeMs
      || snapshot.size !== validated.size
      || digest.digest("hex") !== validated.sha256
    ) {
      throw new RendererBoundaryError("media_snapshot_changed", 409);
    }
    completed = true;
    return destination;
  } finally {
    await Promise.allSettled([sourceHandle?.close(), destinationHandle?.close()]);
    if (!completed) await rm(destination, { force: true }).catch(() => {});
  }
}

export function validateProbePayload(payload, expectedKind) {
  if (
    !payload
    || !Array.isArray(payload.streams)
    || payload.streams.length === 0
    || payload.streams.length > 16
    || !payload.format
  ) {
    throw new RendererBoundaryError("media_codec_invalid");
  }
  const duration = Number(payload.format.duration);
  if (
    !Number.isFinite(duration)
    || duration <= 0
    || duration > MAX_MEDIA_DURATION_SECONDS
  ) {
    throw new RendererBoundaryError("media_codec_invalid");
  }
  let videoStreams = 0;
  let audioStreams = 0;
  for (const stream of payload.streams) {
    if (
      !stream
      || typeof stream.codec_type !== "string"
      || typeof stream.codec_name !== "string"
    ) {
      throw new RendererBoundaryError("media_codec_invalid");
    }
    if (stream.codec_type === "video") {
      const width = Number(stream.width);
      const height = Number(stream.height);
      if (
        !VIDEO_CODEC_ALLOWLIST.has(stream.codec_name)
        || !Number.isInteger(width)
        || !Number.isInteger(height)
        || width < 16
        || height < 16
        || width > MAX_VIDEO_DIMENSION
        || height > MAX_VIDEO_DIMENSION
        || width * height > MAX_VIDEO_PIXELS
      ) {
        throw new RendererBoundaryError("media_codec_invalid");
      }
      videoStreams += 1;
      continue;
    }
    if (stream.codec_type === "audio") {
      const sampleRate = Number(stream.sample_rate);
      const channels = Number(stream.channels);
      if (
        !AUDIO_CODEC_ALLOWLIST.has(stream.codec_name)
        || !Number.isInteger(sampleRate)
        || sampleRate < 8_000
        || sampleRate > 192_000
        || !Number.isInteger(channels)
        || channels < 1
        || channels > 8
      ) {
        throw new RendererBoundaryError("media_codec_invalid");
      }
      audioStreams += 1;
      continue;
    }
    throw new RendererBoundaryError("media_codec_invalid");
  }
  if (
    (expectedKind === "video" && videoStreams === 0)
    || (expectedKind === "audio" && (audioStreams === 0 || videoStreams !== 0))
  ) {
    throw new RendererBoundaryError("media_codec_invalid");
  }
  return duration;
}

export function buildProbeArgs(mediaPath, demuxer, expectedKind) {
  const codecWhitelist = expectedKind === "audio"
    ? [...AUDIO_CODEC_ALLOWLIST].join(",")
    : [...VIDEO_CODEC_ALLOWLIST, ...AUDIO_CODEC_ALLOWLIST].join(",");
  return [
    "-v", "error",
    "-protocol_whitelist", "file,pipe",
    "-codec_whitelist", codecWhitelist,
    "-probesize", "5242880",
    "-analyzeduration", "5000000",
    "-max_streams", "16",
    "-f", demuxer,
    "-show_entries", [
      "stream=codec_type,codec_name,width,height,sample_rate,channels",
      "format=duration",
    ].join(":"),
    "-of", "json",
    mediaPath,
  ];
}

export async function probeCodecs(mediaPath, demuxer, expectedKind) {
  let result;
  try {
    result = await runCmd(
      "ffprobe",
      buildProbeArgs(mediaPath, demuxer, expectedKind),
      { timeoutMs: 30_000 },
    );
  } catch (error) {
    if (error instanceof RendererBoundaryError) throw error;
    throw new RendererBoundaryError("media_codec_invalid");
  }
  let payload;
  try {
    payload = JSON.parse(result.stdout);
  } catch {
    throw new RendererBoundaryError("media_codec_invalid");
  }
  return validateProbePayload(payload, expectedKind);
}

async function prepareSnapshots(validated, workDir) {
  assertRenderDeadline();
  const clipsDir = path.join(workDir, "clips");
  const audioDir = path.join(workDir, "audio");
  await Promise.all([
    mkdir(clipsDir, { mode: 0o700 }),
    mkdir(audioDir, { mode: 0o700 }),
  ]);
  const clips = [];
  let totalClipDuration = 0;
  for (const [index, item] of validated.clips.entries()) {
    assertRenderDeadline();
    const snapshot = path.join(
      clipsDir,
      `clip-${String(index).padStart(3, "0")}${item.extension}`,
    );
    await snapshotMedia(item, snapshot);
    totalClipDuration += await probeCodecs(snapshot, item.demuxer, "video");
    if (totalClipDuration > MAX_MEDIA_DURATION_SECONDS) {
      throw new RendererBoundaryError("media_codec_invalid");
    }
    clips.push(snapshot);
  }
  const audios = [];
  let totalAudioDuration = 0;
  for (const [index, item] of validated.audios.entries()) {
    assertRenderDeadline();
    const snapshot = path.join(
      audioDir,
      `audio-${String(index).padStart(3, "0")}${item.extension}`,
    );
    await snapshotMedia(item, snapshot);
    totalAudioDuration += await probeCodecs(snapshot, item.demuxer, "audio");
    if (totalAudioDuration > MAX_MEDIA_DURATION_SECONDS) {
      throw new RendererBoundaryError("media_codec_invalid");
    }
    audios.push(snapshot);
  }
  return { clips, audios };
}

async function concatClips(clipPaths, workDir) {
  assertRenderDeadline();
  if (clipPaths.length < 2) return null;
  const concatList = path.join(workDir, "clips.concat");
  await writeFile(
    concatList,
    buildConcatManifest(clipPaths, workDir),
    { encoding: "utf8", flag: "wx", mode: 0o400 },
  );
  const outputPath = path.join(workDir, "concat.mp4");
  try {
    await runCmd("ffmpeg", [
      "-nostdin", "-n",
      "-protocol_whitelist", "file,pipe",
      "-f", "concat", "-safe", "1",
      "-codec_whitelist", "h264,vp8,vp9,aac,mp3,opus,vorbis,flac,pcm_s16le,pcm_s24le",
      "-i", concatList,
      "-c", "copy",
      "-movflags", "+faststart",
      outputPath,
    ]);
  } catch {
    assertRenderDeadline();
    await rm(outputPath, { force: true });
    await runCmd("ffmpeg", [
      "-nostdin", "-n",
      "-protocol_whitelist", "file,pipe",
      "-f", "concat", "-safe", "1",
      "-codec_whitelist", "h264,vp8,vp9,aac,mp3,opus,vorbis,flac,pcm_s16le,pcm_s24le",
      "-i", concatList,
      "-c:v", "libx264", "-preset", "fast", "-crf", "23",
      "-c:a", "aac", "-b:a", "128k",
      "-movflags", "+faststart",
      outputPath,
    ]);
  }
  const probe = await probeFile(outputPath);
  return probe.exists && probe.size > 10_000 ? outputPath : null;
}

async function muxAudio(videoPath, audioPaths, workDir) {
  assertRenderDeadline();
  if (audioPaths.length === 0) return null;
  const concatList = path.join(workDir, "audio.concat");
  await writeFile(
    concatList,
    buildConcatManifest(audioPaths, workDir),
    { encoding: "utf8", flag: "wx", mode: 0o400 },
  );
  const concatAudio = path.join(workDir, "audio.mka");
  await runCmd("ffmpeg", [
    "-nostdin", "-n",
    "-protocol_whitelist", "file,pipe",
    "-f", "concat", "-safe", "1",
    "-codec_whitelist", "aac,mp3,opus,vorbis,flac,pcm_s16le,pcm_s24le",
    "-i", concatList,
    "-c", "copy",
    concatAudio,
  ]);
  const muxedPath = path.join(workDir, "muxed.mp4");
  await runCmd("ffmpeg", [
    "-nostdin", "-n",
    "-protocol_whitelist", "file,pipe",
    "-f", "mov", "-i", videoPath,
    "-protocol_whitelist", "file,pipe",
    "-f", "matroska", "-i", concatAudio,
    "-c:v", "copy",
    "-c:a", "aac",
    "-shortest",
    muxedPath,
  ]);
  const probe = await probeFile(muxedPath);
  return probe.exists && probe.size > 10_000 ? muxedPath : null;
}

async function remotionRender(renderPayload, clipPaths, workDir) {
  assertRenderDeadline();
  const safePayload = structuredClone(renderPayload);
  safePayload.clip_paths = clipPaths;
  const inputJsonPath = path.join(workDir, "render-input.json");
  const outputPath = path.join(workDir, "remotion.mp4");
  await writeFile(
    inputJsonPath,
    JSON.stringify(safePayload),
    { encoding: "utf8", flag: "wx", mode: 0o400 },
  );
  await runCmd(
    "/app/node_modules/.bin/tsx",
    ["src/render.ts", "--input", inputJsonPath, "--output", outputPath],
    { cwd: REMOTION_PROJECT },
  );
  const probe = await probeFile(outputPath);
  return probe.exists && probe.size > 10_000 ? outputPath : null;
}

async function createStub(workDir) {
  assertRenderDeadline();
  const outputPath = path.join(workDir, "stub.mp4");
  await runCmd("ffmpeg", [
    "-nostdin", "-n",
    "-f", "lavfi",
    "-i", "color=c=#100C0D:s=1080x1920:d=5",
    "-c:v", "libx264", "-pix_fmt", "yuv420p",
    "-an",
    outputPath,
  ]);
  const probe = await probeFile(outputPath);
  return probe.exists && probe.size > 1_000 ? outputPath : null;
}

export async function publishNoClobber(
  source,
  destination,
  {
    setMode = chmod,
    publishLink = link,
    checkDeadline = assertRenderDeadline,
  } = {},
) {
  checkDeadline();
  await setMode(source, 0o440);
  checkDeadline();
  const handle = await open(
    source,
    fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW || 0),
  );
  let sourceStat;
  try {
    sourceStat = await handle.stat();
    if (!sourceStat.isFile() || sourceStat.size <= 0) {
      throw new Error("publish_source_invalid");
    }
    await handle.sync();
    checkDeadline();
  } finally {
    await handle.close();
  }
  const sha256 = await hashFile(source);
  checkDeadline();
  try {
    await publishLink(source, destination);
  } catch (error) {
    if (error?.code === "EEXIST") {
      throw new RendererBoundaryError("render_output_conflict", 409);
    }
    throw error;
  }
  markRenderCommitted();
  return Object.freeze({
    path: destination,
    fileSizeBytes: sourceStat.size,
    sha256,
  });
}

export async function cleanupWorkDir(
  workDir,
  { remove = rm, log = console.warn } = {},
) {
  if (!workDir) return true;
  try {
    await remove(workDir, { recursive: true, force: true });
    return true;
  } catch {
    log("renderer_workdir_cleanup_failed");
    return false;
  }
}

export function createRendererApp() {
  const app = express();
  let activeRenders = 0;
  app.use(express.json({ limit: "1mb", strict: true }));

  app.get("/health", async (_request, response) => {
    const [remotionVersion, ffmpegOk, ffprobeOk, chromiumOk] = await Promise.all([
      probeRemotionVersion(),
      probeCommand("ffmpeg", ["-version"]),
      probeCommand("ffprobe", ["-version"]),
      probeCommand(CHROME_EXECUTABLE, ["--version"]),
    ]);
    const ready = Boolean(remotionVersion)
      && ffmpegOk
      && ffprobeOk
      && chromiumOk;
    response.status(ready ? 200 : 503).json({
      status: ready ? "ok" : "unready",
      node: process.version,
      remotion: remotionVersion,
      ffmpeg: ffmpegOk,
      ffprobe: ffprobeOk,
      chromium: chromiumOk,
    });
  });

  app.post("/assemble", async (request, response) => {
    if (activeRenders >= MAX_RENDER_CONCURRENCY) {
      response.status(429).json({
        success: false,
        error: "renderer_busy",
      });
      return;
    }
    activeRenders += 1;
    let reservation;
    try {
      const result = await runWithRenderDeadline(
        SERVER_RENDER_DEADLINE_MS,
        async () => {
          const validated = await validateAssembleRequest(request.body, {
            outputRoot: OUTPUT_DIR,
            checkDeadline: assertRenderDeadline,
          });
          reservation = await reserveRenderOperation(
            validated.outputDir,
            validated.outputLabel,
            { checkDeadline: assertRenderDeadline },
          );
          const snapshots = await prepareSnapshots(
            validated,
            reservation.workDir,
          );

          let videoPath = null;
          let renderMode = "none";
          let isStub = false;
          try {
            videoPath = await concatClips(snapshots.clips, reservation.workDir);
            if (videoPath) renderMode = "clip_concat";
          } catch {
            assertRenderDeadline();
            videoPath = null;
          }
          if (!videoPath) {
            try {
              videoPath = await remotionRender(
                validated.renderPayload,
                snapshots.clips,
                reservation.workDir,
              );
              if (videoPath) renderMode = "remotion";
            } catch {
              assertRenderDeadline();
              videoPath = null;
            }
          }
          if (!videoPath) {
            videoPath = await createStub(reservation.workDir);
            isStub = true;
            renderMode = "stub";
          }
          if (!videoPath) throw new Error("render_failed");

          let audioMuxed = false;
          if (!isStub && snapshots.audios.length > 0) {
            const muxed = await muxAudio(
              videoPath,
              snapshots.audios,
              reservation.workDir,
            );
            if (!muxed) throw new Error("audio_mux_failed");
            videoPath = muxed;
            audioMuxed = true;
          }
          const published = await publishNoClobber(
            videoPath,
            reservation.outputPath,
          );
          return {
            success: true,
            video_path: published.path,
            file_size_bytes: published.fileSizeBytes,
            artifact_sha256: published.sha256,
            render_mode: renderMode,
            is_stub: isStub,
            audio_muxed: audioMuxed,
            label: validated.outputLabel,
          };
        },
      );
      response.json(result);
    } catch (error) {
      if (error instanceof RendererBoundaryError) {
        response.status(error.statusCode).json({
          success: false,
          error: error.code,
          ...error.details,
        });
        return;
      }
      response.status(500).json({
        success: false,
        error: "render_processing_failed",
      });
    } finally {
      await cleanupWorkDir(reservation?.workDir);
      activeRenders -= 1;
    }
  });

  app.use((error, _request, response, _next) => {
    const bodyError = error?.type === "entity.too.large"
      ? "request_body_too_large"
      : "request_body_invalid";
    response.status(400).json({ success: false, error: bodyError });
  });
  return app;
}

async function removeStaleSocket(socketPath) {
  try {
    const socketStat = await lstat(socketPath);
    const resolvedParent = await realpath(path.dirname(socketPath));
    if (
      socketStat.isSymbolicLink()
      || !socketStat.isSocket()
      || resolvedParent !== path.dirname(socketPath)
    ) {
      throw new Error("renderer_socket_path_invalid");
    }
    await unlink(socketPath);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

export async function prepareRendererHome(
  expectedHome = PRODUCTION_RENDERER_HOME,
) {
  if (process.env.NODE_ENV !== "production") return;
  const configuredHome = process.env.HOME;
  if (configuredHome !== expectedHome || !path.isAbsolute(configuredHome)) {
    throw new Error("renderer_home_invalid");
  }
  await mkdir(configuredHome, { recursive: true, mode: 0o700 });
  const [homeStat, resolvedHome] = await Promise.all([
    lstat(configuredHome),
    realpath(configuredHome),
  ]);
  if (
    homeStat.isSymbolicLink()
    || !homeStat.isDirectory()
    || resolvedHome !== configuredHome
  ) {
    throw new Error("renderer_home_invalid");
  }
  await chmod(configuredHome, 0o700);
}

export async function startRendererServer(
  socketPath = RENDERING_SERVICE_SOCKET,
) {
  await prepareRendererHome();
  const socketDir = path.dirname(socketPath);
  await mkdir(socketDir, { recursive: true, mode: 0o750 });
  await removeStaleSocket(socketPath);
  const app = createRendererApp();
  const server = await new Promise((resolve, reject) => {
    const candidate = app.listen(socketPath);
    candidate.once("error", reject);
    candidate.once("listening", () => resolve(candidate));
  });
  try {
    await chmod(socketPath, 0o660);
  } catch {
    server.close();
    await unlink(socketPath).catch(() => {});
    throw new Error("renderer_socket_permission_failed");
  }
  console.log("rendering service listening on unix socket");
  const close = async () => {
    server.close();
    await unlink(socketPath).catch(() => {});
  };
  process.once("SIGTERM", close);
  process.once("SIGINT", close);
  return server;
}

if (
  process.argv[1]
  && import.meta.url === pathToFileURL(process.argv[1]).href
) {
  startRendererServer().catch(() => {
    process.exitCode = 1;
  });
}
