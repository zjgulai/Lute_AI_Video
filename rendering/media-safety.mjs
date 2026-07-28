import { constants as fsConstants } from "node:fs";
import { createHash } from "node:crypto";
import {
  lstat,
  mkdir,
  open,
  realpath,
} from "node:fs/promises";
import path from "node:path";

const SAFE_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
const SAFE_LABEL = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;
const SAFE_PATH_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const CONTROL_CHARACTERS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
const MAX_MEDIA_BYTES = 2 * 1024 * 1024 * 1024;
const MAX_MEDIA_FILES = 16;
const MAX_REQUEST_MEDIA_BYTES = 4 * 1024 * 1024 * 1024;
const MAX_TIMELINE_ITEMS = 64;
const MAX_JSON_DEPTH = 10;
const MAX_JSON_ARRAY_ITEMS = 256;
const MAX_JSON_OBJECT_KEYS = 64;
const MAX_JSON_STRING_BYTES = 16 * 1024;
const MAX_RENDER_SECONDS = 180;
const MAX_RENDER_TEXT_BYTES = 4 * 1024;
const ALLOWED_REQUEST_KEYS = new Set([
  "tenant_id",
  "artifact_disposition",
  "output_dir",
  "output_label",
  "clip_paths",
  "audio_paths",
  "render_payload",
]);
const ALLOWED_DISPOSITIONS = new Set(["pending_review", "quarantine"]);
const HASH_BUFFER_BYTES = 1024 * 1024;
const NOOP_DEADLINE_CHECK = () => {};

const VIDEO_CONTAINERS = new Map([
  [".mp4", { kind: "iso-bmff", demuxer: "mov" }],
  [".mov", { kind: "iso-bmff", demuxer: "mov" }],
  [".m4v", { kind: "iso-bmff", demuxer: "mov" }],
  [".webm", { kind: "matroska", demuxer: "matroska" }],
  [".mkv", { kind: "matroska", demuxer: "matroska" }],
]);
const AUDIO_CONTAINERS = new Map([
  [".m4a", { kind: "iso-bmff", demuxer: "mov" }],
  [".mp3", { kind: "mp3", demuxer: "mp3" }],
  [".wav", { kind: "wav", demuxer: "wav" }],
  [".ogg", { kind: "ogg", demuxer: "ogg" }],
  [".opus", { kind: "ogg", demuxer: "ogg" }],
  [".flac", { kind: "flac", demuxer: "flac" }],
]);

export class RendererBoundaryError extends Error {
  constructor(code, statusCode = 422, details = {}) {
    super(code);
    this.name = "RendererBoundaryError";
    this.code = code;
    this.statusCode = statusCode;
    this.details = Object.freeze({ ...details });
  }
}

function fail(code = "request_schema_invalid", statusCode = 422) {
  throw new RendererBoundaryError(code, statusCode);
}

function isPlainObject(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function validateBoundedJson(value, depth = 0, key = "") {
  if (depth > MAX_JSON_DEPTH) fail();
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) fail();
    return;
  }
  if (typeof value === "string") {
    if (
      Buffer.byteLength(value, "utf8") > MAX_JSON_STRING_BYTES
      || CONTROL_CHARACTERS.test(value)
    ) {
      fail();
    }
    if (
      key.endsWith("_path")
      || key.endsWith("_paths")
      || key === "videoSrc"
      || key === "audioSrc"
    ) {
      fail();
    }
    return;
  }
  if (Array.isArray(value)) {
    if (value.length > MAX_JSON_ARRAY_ITEMS) fail();
    for (const item of value) validateBoundedJson(item, depth + 1, key);
    return;
  }
  if (!isPlainObject(value)) fail();
  const entries = Object.entries(value);
  if (entries.length > MAX_JSON_OBJECT_KEYS) fail();
  for (const [childKey, childValue] of entries) {
    if (
      typeof childKey !== "string"
      || childKey.length > 128
      || CONTROL_CHARACTERS.test(childKey)
      || childKey === "__proto__"
      || childKey === "prototype"
      || childKey === "constructor"
    ) {
      fail();
    }
    validateBoundedJson(childValue, depth + 1, childKey);
  }
}

function assertExactKeys(value, keys) {
  if (!isPlainObject(value)) fail();
  const actual = Object.keys(value);
  if (
    actual.length !== keys.length
    || actual.some((key) => !keys.includes(key))
  ) {
    fail();
  }
}

function assertBoundedText(value, { allowEmpty = true } = {}) {
  if (
    typeof value !== "string"
    || (!allowEmpty && value.length === 0)
    || Buffer.byteLength(value, "utf8") > MAX_RENDER_TEXT_BYTES
    || CONTROL_CHARACTERS.test(value)
  ) {
    fail();
  }
  return value;
}

function assertTime(value, minimum, maximum) {
  if (
    typeof value !== "number"
    || !Number.isFinite(value)
    || value < minimum
    || value > maximum
  ) {
    fail();
  }
  return value;
}

function validateRenderPayload(payload, clipPaths) {
  assertExactKeys(payload, [
    "scripts",
    "storyboards",
    "caption_plans",
    "audio_plans",
    "brand_guidelines",
    "clip_paths",
    "transitions",
  ]);
  if (!arraysEqual(assertPathArray(payload.clip_paths), clipPaths)) fail();

  if (!Array.isArray(payload.scripts) || payload.scripts.length !== 1) fail();
  assertExactKeys(payload.scripts[0], ["id"]);
  validateLabel(payload.scripts[0].id);

  if (!Array.isArray(payload.storyboards) || payload.storyboards.length !== 1) {
    fail();
  }
  const storyboard = payload.storyboards[0];
  assertExactKeys(storyboard, ["total_duration", "shots"]);
  const duration = assertTime(
    storyboard.total_duration,
    1,
    MAX_RENDER_SECONDS,
  );
  if (!Array.isArray(storyboard.shots) || storyboard.shots.length > MAX_TIMELINE_ITEMS) {
    fail();
  }
  for (const shot of storyboard.shots) {
    assertExactKeys(shot, [
      "id",
      "start_time",
      "end_time",
      "text_overlay",
      "visual",
    ]);
    if (
      !(
        (Number.isInteger(shot.id) && shot.id >= 0 && shot.id <= 1_000_000)
        || (typeof shot.id === "string" && SAFE_IDENTIFIER.test(shot.id))
      )
    ) {
      fail();
    }
    const start = assertTime(shot.start_time, 0, duration);
    const end = assertTime(shot.end_time, 0, duration);
    if (end <= start) fail();
    assertBoundedText(shot.text_overlay);
    assertBoundedText(shot.visual);
  }

  if (!Array.isArray(payload.caption_plans) || payload.caption_plans.length !== 1) {
    fail();
  }
  assertExactKeys(payload.caption_plans[0], ["entries"]);
  const entries = payload.caption_plans[0].entries;
  if (!Array.isArray(entries) || entries.length > MAX_TIMELINE_ITEMS) fail();
  for (const entry of entries) {
    assertExactKeys(entry, ["start_time", "end_time", "text"]);
    const start = assertTime(entry.start_time, 0, duration);
    const end = assertTime(entry.end_time, 0, duration);
    if (end <= start) fail();
    assertBoundedText(entry.text);
  }

  if (!Array.isArray(payload.audio_plans) || payload.audio_plans.length > 1) fail();
  if (payload.audio_plans.length === 1) {
    assertExactKeys(payload.audio_plans[0], ["segments"]);
    const segments = payload.audio_plans[0].segments;
    if (!Array.isArray(segments) || segments.length > MAX_TIMELINE_ITEMS) fail();
    for (const segment of segments) {
      assertExactKeys(segment, ["type", "start_time", "end_time", "text"]);
      if (segment.type !== "voiceover") fail();
      const start = assertTime(segment.start_time, 0, duration);
      const end = assertTime(segment.end_time, 0, duration);
      if (end <= start) fail();
      assertBoundedText(segment.text);
    }
  }

  if (!isPlainObject(payload.brand_guidelines)) fail();
  if (payload.brand_guidelines.brand_name !== undefined) {
    assertBoundedText(payload.brand_guidelines.brand_name);
  }
  const colors = payload.brand_guidelines.colors;
  if (colors !== undefined) {
    if (!isPlainObject(colors)) fail();
    for (const color of [colors.primary, colors.secondary]) {
      if (
        color !== undefined
        && (
          typeof color !== "string"
          || !/^#[A-Fa-f0-9]{3,8}$/.test(color)
        )
      ) {
        fail();
      }
    }
  }

  if (!Array.isArray(payload.transitions) || payload.transitions.length > MAX_TIMELINE_ITEMS) {
    fail();
  }
  validateBoundedJson(payload.transitions);
}

function validateIdentifier(value) {
  if (typeof value !== "string" || !SAFE_IDENTIFIER.test(value)) fail();
  return value;
}

function validateLabel(value) {
  if (
    typeof value !== "string"
    || !SAFE_LABEL.test(value)
    || value.includes("..")
  ) {
    fail();
  }
  return value;
}

function assertCanonicalAbsolutePath(value) {
  if (
    typeof value !== "string"
    || !path.isAbsolute(value)
    || value.includes("\\")
    || value.includes("://")
    || CONTROL_CHARACTERS.test(value)
  ) {
    fail("media_path_invalid");
  }
  const segments = value.split("/").filter(Boolean);
  if (
    segments.some(
      (segment) => segment === "." || segment === "..",
    )
  ) {
    fail("media_path_invalid");
  }
  return path.resolve(value);
}

function relativeWithin(candidate, root) {
  const relative = path.relative(root, candidate);
  if (
    relative === ""
    || relative.startsWith(`..${path.sep}`)
    || relative === ".."
    || path.isAbsolute(relative)
  ) {
    fail("media_path_invalid");
  }
  const segments = relative.split(path.sep);
  if (segments.some((segment) => !SAFE_PATH_SEGMENT.test(segment))) {
    fail("media_path_invalid");
  }
  return relative;
}

function classifyHeader(header) {
  const stripped = header.subarray(0, 64).toString("binary").trimStart().toLowerCase();
  if (
    stripped.startsWith("<")
    || stripped.startsWith("#extm3u")
    || stripped.startsWith("[playlist]")
  ) {
    return null;
  }
  if (header.length >= 12 && header.subarray(4, 8).toString("ascii") === "ftyp") {
    return "iso-bmff";
  }
  if (header.subarray(0, 4).equals(Buffer.from([0x1a, 0x45, 0xdf, 0xa3]))) {
    return "matroska";
  }
  if (header.subarray(0, 3).toString("ascii") === "ID3") return "mp3";
  if (
    header.length >= 2
    && header[0] === 0xff
    && (header[1] & 0xe0) === 0xe0
  ) {
    return "mp3";
  }
  if (header.subarray(0, 4).toString("ascii") === "OggS") return "ogg";
  if (header.subarray(0, 4).toString("ascii") === "fLaC") return "flac";
  if (
    header.subarray(0, 4).toString("ascii") === "RIFF"
    && header.subarray(8, 12).toString("ascii") === "WAVE"
  ) {
    return "wav";
  }
  return null;
}

function wavFormatTag(header) {
  let offset = 12;
  while (offset + 8 <= header.length) {
    const chunk = header.subarray(offset, offset + 4).toString("ascii");
    const size = header.readUInt32LE(offset + 4);
    const start = offset + 8;
    const end = start + size;
    if (end > header.length) return null;
    if (chunk === "fmt ") {
      if (size < 2) return null;
      const tag = header.readUInt16LE(start);
      if (tag !== 0xfffe) return tag;
      if (size < 40) return null;
      const extensionSize = header.readUInt16LE(start + 16);
      if (extensionSize < 22 || 18 + extensionSize > size) return null;
      const guidTail = header.subarray(start + 28, start + 40);
      const expectedTail = Buffer.from("00001000800000aa00389b71", "hex");
      if (!guidTail.equals(expectedTail)) return null;
      const effective = header.readUInt32LE(start + 24);
      return effective <= 0xffff ? effective : null;
    }
    offset = end + (size & 1);
  }
  return null;
}

function resolveDeadlineCheck(value) {
  if (value === undefined) return NOOP_DEADLINE_CHECK;
  if (typeof value !== "function") fail();
  return value;
}

async function hashFileHandle(
  handle,
  size,
  checkDeadline = NOOP_DEADLINE_CHECK,
) {
  const digest = createHash("sha256");
  const buffer = Buffer.alloc(Math.min(HASH_BUFFER_BYTES, size));
  let offset = 0;
  while (offset < size) {
    checkDeadline();
    const length = Math.min(buffer.length, size - offset);
    const { bytesRead } = await handle.read(buffer, 0, length, offset);
    if (bytesRead <= 0) fail("media_path_invalid");
    digest.update(buffer.subarray(0, bytesRead));
    offset += bytesRead;
  }
  checkDeadline();
  return digest.digest("hex");
}

async function preflightMediaPath(
  mediaPath,
  {
    tenantRoot,
    runRoot = tenantRoot,
    kind,
    minimumBytes,
    checkDeadline = NOOP_DEADLINE_CHECK,
  },
) {
  checkDeadline();
  const canonical = assertCanonicalAbsolutePath(mediaPath);
  const canonicalTenantRoot = path.resolve(tenantRoot);
  const canonicalRunRoot = path.resolve(runRoot);
  relativeWithin(canonicalRunRoot, canonicalTenantRoot);
  const relativePath = relativeWithin(canonical, canonicalRunRoot);
  const extension = path.extname(canonical).toLowerCase();
  const containers = kind === "video" ? VIDEO_CONTAINERS : AUDIO_CONTAINERS;
  const expected = containers.get(extension);
  if (!expected) fail("media_path_invalid");

  let pathStat;
  let resolved;
  try {
    [pathStat, resolved] = await Promise.all([lstat(canonical), realpath(canonical)]);
  } catch {
    fail("media_path_invalid");
  }
  checkDeadline();
  if (
    pathStat.isSymbolicLink()
    || !pathStat.isFile()
    || resolved !== canonical
    || pathStat.size <= minimumBytes
    || pathStat.size > MAX_MEDIA_BYTES
  ) {
    fail("media_path_invalid");
  }

  return Object.freeze({
    path: canonical,
    relativePath,
    extension,
    demuxer: expected.demuxer,
    expectedKind: expected.kind,
    size: pathStat.size,
    device: pathStat.dev,
    inode: pathStat.ino,
    modifiedMs: pathStat.mtimeMs,
  });
}

async function finalizeMediaPath(
  preflight,
  checkDeadline = NOOP_DEADLINE_CHECK,
) {
  checkDeadline();
  let handle;
  let digest;
  try {
    handle = await open(
      preflight.path,
      fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW || 0),
    );
    const openedStat = await handle.stat();
    if (
      !openedStat.isFile()
      || openedStat.dev !== preflight.device
      || openedStat.ino !== preflight.inode
      || openedStat.size !== preflight.size
      || openedStat.mtimeMs !== preflight.modifiedMs
    ) {
      fail("media_path_invalid");
    }
    const header = Buffer.alloc(Math.min(4096, openedStat.size));
    const { bytesRead } = await handle.read(header, 0, header.length, 0);
    const actualKind = classifyHeader(header.subarray(0, bytesRead));
    if (actualKind !== preflight.expectedKind) fail("media_path_invalid");
    if (actualKind === "wav") {
      const tag = wavFormatTag(header.subarray(0, bytesRead));
      if (tag === null || tag === 0x0011) fail("media_path_invalid");
    }
    digest = await hashFileHandle(handle, openedStat.size, checkDeadline);
  } catch (error) {
    if (error instanceof RendererBoundaryError) throw error;
    fail("media_path_invalid");
  } finally {
    await handle?.close();
  }

  return Object.freeze({
    path: preflight.path,
    relativePath: preflight.relativePath,
    extension: preflight.extension,
    demuxer: preflight.demuxer,
    size: preflight.size,
    device: preflight.device,
    inode: preflight.inode,
    modifiedMs: preflight.modifiedMs,
    sha256: digest,
  });
}

export function assertMediaBudget(items) {
  if (!Array.isArray(items) || items.length > MAX_MEDIA_FILES) {
    fail("media_budget_exceeded", 413);
  }
  const paths = new Set();
  let totalBytes = 0;
  for (const item of items) {
    if (
      !item
      || typeof item.path !== "string"
      || !Number.isSafeInteger(item.size)
      || item.size < 0
      || paths.has(item.path)
    ) {
      fail("media_budget_exceeded", 413);
    }
    paths.add(item.path);
    totalBytes += item.size;
    if (!Number.isSafeInteger(totalBytes) || totalBytes > MAX_REQUEST_MEDIA_BYTES) {
      fail("media_budget_exceeded", 413);
    }
  }
  return totalBytes;
}

export async function validateMediaPath(mediaPath, options) {
  const checkDeadline = resolveDeadlineCheck(options?.checkDeadline);
  const preflight = await preflightMediaPath(mediaPath, {
    ...options,
    checkDeadline,
  });
  assertMediaBudget([preflight]);
  return finalizeMediaPath(preflight, checkDeadline);
}

function assertPathArray(value) {
  if (
    !Array.isArray(value)
    || value.length > MAX_MEDIA_FILES
    || !value.every(
      (item) => (
        typeof item === "string"
        && Buffer.byteLength(item, "utf8") <= MAX_RENDER_TEXT_BYTES
      ),
    )
  ) {
    fail();
  }
  return value;
}

function arraysEqual(left, right) {
  return left.length === right.length
    && left.every((item, index) => item === right[index]);
}

export async function validateAssembleRequest(
  body,
  { outputRoot, checkDeadline: rawDeadlineCheck },
) {
  const checkDeadline = resolveDeadlineCheck(rawDeadlineCheck);
  checkDeadline();
  if (!isPlainObject(body)) fail();
  if (Object.keys(body).some((key) => !ALLOWED_REQUEST_KEYS.has(key))) fail();
  if (Object.keys(body).length !== ALLOWED_REQUEST_KEYS.size) fail();

  const tenantId = validateIdentifier(body.tenant_id);
  if (!ALLOWED_DISPOSITIONS.has(body.artifact_disposition)) fail();
  const outputLabel = validateLabel(body.output_label);
  const outputRootCanonical = path.resolve(outputRoot);
  const tenantRoot = path.join(
    outputRootCanonical,
    "tenants",
    tenantId,
    body.artifact_disposition,
  );
  const outputDir = assertCanonicalAbsolutePath(body.output_dir);
  const outputRelative = relativeWithin(outputDir, tenantRoot);
  const outputSegments = outputRelative.split(path.sep);
  if (outputSegments.length < 2) fail();
  const runRoot = path.join(tenantRoot, outputSegments[0]);

  let outputStat;
  let outputResolved;
  try {
    [outputStat, outputResolved] = await Promise.all([
      lstat(outputDir),
      realpath(outputDir),
    ]);
  } catch {
    fail();
  }
  checkDeadline();
  if (
    outputStat.isSymbolicLink()
    || !outputStat.isDirectory()
    || outputResolved !== outputDir
  ) {
    fail();
  }

  const clipPaths = assertPathArray(body.clip_paths);
  const audioPaths = assertPathArray(body.audio_paths);
  if (!isPlainObject(body.render_payload)) fail();
  validateBoundedJson({
    ...body.render_payload,
    // This is the sole protocol-approved nested path field. It is checked
    // byte-for-byte against the top-level array below, then every source path
    // is opened, canonicalized, hashed, and probed before use.
    clip_paths: [],
  });
  validateRenderPayload(body.render_payload, clipPaths);

  const clipPreflights = [];
  for (const mediaPath of clipPaths) {
    clipPreflights.push(await preflightMediaPath(mediaPath, {
      tenantRoot,
      runRoot,
      kind: "video",
      minimumBytes: 1_000,
      checkDeadline,
    }));
  }
  const audioPreflights = [];
  for (const mediaPath of audioPaths) {
    audioPreflights.push(await preflightMediaPath(mediaPath, {
      tenantRoot,
      runRoot,
      kind: "audio",
      minimumBytes: 200,
      checkDeadline,
    }));
  }
  assertMediaBudget([...clipPreflights, ...audioPreflights]);

  const clips = [];
  for (const item of clipPreflights) {
    clips.push(await finalizeMediaPath(item, checkDeadline));
  }
  const audios = [];
  for (const item of audioPreflights) {
    audios.push(await finalizeMediaPath(item, checkDeadline));
  }
  checkDeadline();

  return Object.freeze({
    tenantId,
    artifactDisposition: body.artifact_disposition,
    tenantRoot,
    runRoot,
    outputDir,
    outputLabel,
    clips,
    audios,
    renderPayload: structuredClone(body.render_payload),
  });
}

export function buildConcatManifest(mediaPaths, root) {
  const canonicalRoot = path.resolve(root);
  const lines = mediaPaths.map((item) => {
    const candidate = typeof item === "string" ? item : item.path;
    const canonical = path.resolve(candidate);
    const relative = relativeWithin(canonical, canonicalRoot)
      .split(path.sep)
      .join("/");
    return `file '${relative}'`;
  });
  return `${lines.join("\n")}\n`;
}

export async function reserveRenderOperation(
  outputDir,
  label,
  { checkDeadline: rawDeadlineCheck } = {},
) {
  const checkDeadline = resolveDeadlineCheck(rawDeadlineCheck);
  checkDeadline();
  const safeLabel = validateLabel(label);
  const outputPath = path.join(outputDir, `${safeLabel}.mp4`);
  try {
    const existing = await lstat(outputPath);
    let details = {};
    try {
      const resolved = await realpath(outputPath);
      if (
        !existing.isSymbolicLink()
        && existing.isFile()
        && resolved === outputPath
        && (existing.mode & 0o777) === 0o440
        && existing.size > 0
      ) {
        const handle = await open(
          outputPath,
          fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW || 0),
        );
        try {
          const opened = await handle.stat();
          if (
            opened.isFile()
            && opened.dev === existing.dev
            && opened.ino === existing.ino
            && opened.size === existing.size
          ) {
            details = {
              video_path: outputPath,
              file_size_bytes: existing.size,
              artifact_sha256: await hashFileHandle(
                handle,
                existing.size,
                checkDeadline,
              ),
            };
          }
        } finally {
          await handle.close();
        }
      }
    } catch (error) {
      if (error instanceof RendererBoundaryError) throw error;
      details = {};
    }
    throw new RendererBoundaryError("render_output_conflict", 409, details);
  } catch (error) {
    if (error instanceof RendererBoundaryError) throw error;
    if (error?.code !== "ENOENT") fail("render_output_conflict", 409);
  }
  const workDir = path.join(outputDir, `.renderer-${safeLabel}.lock`);
  checkDeadline();
  try {
    await mkdir(workDir, { mode: 0o700 });
  } catch {
    fail("render_output_conflict", 409);
  }
  return Object.freeze({ workDir, outputPath });
}
