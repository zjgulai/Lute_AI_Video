import assert from "node:assert/strict";
import {
  access,
  chmod,
  mkdir,
  mkdtemp,
  realpath,
  symlink,
  writeFile,
} from "node:fs/promises";
import { execFile } from "node:child_process";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { once } from "node:events";
import { promisify } from "node:util";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";

import {
  assertMediaBudget,
  buildConcatManifest,
  reserveRenderOperation,
  validateAssembleRequest,
  validateMediaPath,
} from "../media-safety.mjs";
import {
  buildProbeArgs,
  cleanupWorkDir,
  prepareRendererHome,
  probeCodecs,
  publishNoClobber,
  runCmd,
  runWithRenderDeadline,
  startRendererServer,
  validateProbePayload,
} from "../server.mjs";
import { probeRendererHealth } from "../healthcheck.mjs";

const execFileAsync = promisify(execFile);

const MP4_HEADER = Buffer.from([
  0x00, 0x00, 0x00, 0x18,
  0x66, 0x74, 0x79, 0x70,
  0x69, 0x73, 0x6f, 0x6d,
  0x00, 0x00, 0x02, 0x00,
  0x69, 0x73, 0x6f, 0x6d,
  0x69, 0x73, 0x6f, 0x32,
]);

async function fixtureTree() {
  const outputRoot = await realpath(
    await mkdtemp(path.join(os.tmpdir(), "renderer-safety-")),
  );
  const tenantRoot = path.join(
    outputRoot,
    "tenants",
    "tenant-a",
    "pending_review",
  );
  const runRoot = path.join(tenantRoot, "run-001");
  const clipsDir = path.join(runRoot, "clips");
  const audioDir = path.join(runRoot, "audio");
  const outputDir = path.join(runRoot, "assemble");
  await Promise.all([
    mkdir(clipsDir, { recursive: true }),
    mkdir(audioDir, { recursive: true }),
    mkdir(outputDir, { recursive: true }),
  ]);
  const clip = path.join(clipsDir, "clip-01.mp4");
  await writeFile(clip, Buffer.concat([MP4_HEADER, Buffer.alloc(2_000)]));
  return { outputRoot, tenantRoot, runRoot, clipsDir, outputDir, clip };
}

function requestFor({ outputDir, clip }) {
  return {
    tenant_id: "tenant-a",
    artifact_disposition: "pending_review",
    output_dir: outputDir,
    output_label: "video-001",
    clip_paths: [clip],
    audio_paths: [],
    render_payload: {
      scripts: [{ id: "video-001" }],
      storyboards: [{
        total_duration: 5,
        shots: [{
          id: 1,
          start_time: 0,
          end_time: 5,
          text_overlay: "",
          visual: "",
        }],
      }],
      caption_plans: [{ entries: [] }],
      audio_plans: [],
      brand_guidelines: {},
      clip_paths: [clip],
      transitions: [],
    },
  };
}

test("strict request schema rejects unknown keys and nested path substitution", async () => {
  const fixture = await fixtureTree();
  const valid = requestFor(fixture);
  const validated = await validateAssembleRequest(
    valid,
    { outputRoot: fixture.outputRoot },
  );
  assert.equal(validated.clips.length, 1);

  await assert.rejects(
    validateAssembleRequest(
      { ...valid, unexpected: true },
      { outputRoot: fixture.outputRoot },
    ),
    /request_schema_invalid/,
  );
  await assert.rejects(
    validateAssembleRequest(
      {
        ...valid,
        render_payload: {
          ...valid.render_payload,
          clip_paths: [path.join(fixture.clipsDir, "other.mp4")],
        },
      },
      { outputRoot: fixture.outputRoot },
    ),
    /request_schema_invalid/,
  );
  await assert.rejects(
    validateAssembleRequest(
      {
        ...valid,
        render_payload: {
          ...valid.render_payload,
          storyboards: [{
            ...valid.render_payload.storyboards[0],
            total_duration: 181,
          }],
        },
      },
      { outputRoot: fixture.outputRoot },
    ),
    /request_schema_invalid/,
  );
  await assert.rejects(
    validateAssembleRequest(
      {
        ...valid,
        render_payload: {
          ...valid.render_payload,
          caption_plans: [{
            entries: Array.from({ length: 65 }, (_, index) => ({
              start_time: 0,
              end_time: 1,
              text: `caption-${index}`,
            })),
          }],
        },
      },
      { outputRoot: fixture.outputRoot },
    ),
    /request_schema_invalid/,
  );
});

test("media path rejects URL, traversal, symlink, cross-tenant, and AVI before tools", async () => {
  const fixture = await fixtureTree();
  const otherTenant = path.join(
    fixture.outputRoot,
    "tenants",
    "tenant-b",
    "pending_review",
    "run-001",
    "clips",
  );
  await mkdir(otherTenant, { recursive: true });
  const otherClip = path.join(otherTenant, "clip.mp4");
  await writeFile(otherClip, Buffer.concat([MP4_HEADER, Buffer.alloc(2_000)]));
  const linked = path.join(fixture.clipsDir, "linked.mp4");
  await symlink(fixture.clip, linked);
  const avi = path.join(fixture.clipsDir, "crafted.avi");
  await writeFile(
    avi,
    Buffer.concat([
      Buffer.from("RIFF"),
      Buffer.alloc(4),
      Buffer.from("AVI "),
      Buffer.alloc(2_000),
    ]),
  );

  const options = {
    tenantRoot: fixture.tenantRoot,
    runRoot: fixture.runRoot,
    kind: "video",
    minimumBytes: 1_000,
  };
  await assert.rejects(
    validateMediaPath("https://example.invalid/clip.mp4", options),
    /media_path_invalid/,
  );
  await assert.rejects(
    validateMediaPath(
      path.join(fixture.tenantRoot, "run-001", "..", "..", "escape.mp4"),
      options,
    ),
    /media_path_invalid/,
  );
  await assert.rejects(
    validateMediaPath(linked, options),
    /media_path_invalid/,
  );
  await assert.rejects(
    validateMediaPath(otherClip, options),
    /media_path_invalid/,
  );
  await assert.rejects(
    validateMediaPath(avi, options),
    /media_path_invalid/,
  );
});

test("concat manifest contains only safe tenant-relative paths", async () => {
  const fixture = await fixtureTree();
  const manifest = buildConcatManifest(
    [fixture.clip],
    fixture.tenantRoot,
  );

  assert.equal(manifest, "file 'run-001/clips/clip-01.mp4'\n");
  assert.equal(manifest.includes(".."), false);
  assert.equal(manifest.includes(fixture.outputRoot), false);
});

test("validated media freezes an exact SHA-256 digest", async () => {
  const fixture = await fixtureTree();
  const validated = await validateMediaPath(fixture.clip, {
    tenantRoot: fixture.tenantRoot,
    runRoot: fixture.runRoot,
    kind: "video",
    minimumBytes: 1_000,
  });

  assert.match(validated.sha256, /^[a-f0-9]{64}$/);
});

test("media request budget rejects duplicate paths and aggregate bytes before I/O", () => {
  assert.throws(
    () => assertMediaBudget([
      { path: "/run/a.mp4", size: 1_000 },
      { path: "/run/a.mp4", size: 1_000 },
    ]),
    /media_budget_exceeded/,
  );
  assert.throws(
    () => assertMediaBudget([
      { path: "/run/a.mp4", size: 3 * 1024 * 1024 * 1024 },
      { path: "/run/b.mp4", size: 2 * 1024 * 1024 * 1024 },
    ]),
    /media_budget_exceeded/,
  );
});

test("codec probe contract rejects excessive dimensions, duration, and audio shape", () => {
  assert.equal(
    validateProbePayload({
      streams: [{
        codec_type: "video",
        codec_name: "h264",
        width: 1280,
        height: 720,
      }],
      format: { duration: "15.0" },
    }, "video"),
    15,
  );
  assert.throws(
    () => validateProbePayload({
      streams: [{
        codec_type: "video",
        codec_name: "h264",
        width: 100_000,
        height: 100_000,
      }],
      format: { duration: "15.0" },
    }, "video"),
    /media_codec_invalid/,
  );
  assert.throws(
    () => validateProbePayload({
      streams: [{
        codec_type: "audio",
        codec_name: "aac",
        sample_rate: "48000",
        channels: 64,
      }],
      format: { duration: "181.0" },
    }, "audio"),
    /media_codec_invalid/,
  );
});

test("ffprobe is bounded by protocol, codec, analysis, and stream allowlists", () => {
  const args = buildProbeArgs("/private/clip.mp4", "mov", "video");
  const inputIndex = args.indexOf("/private/clip.mp4");

  assert.ok(inputIndex > 0);
  for (const flag of [
    "-protocol_whitelist",
    "-codec_whitelist",
    "-probesize",
    "-analyzeduration",
    "-max_streams",
  ]) {
    const index = args.indexOf(flag);
    assert.ok(index >= 0 && index < inputIndex, `${flag} must precede the input`);
  }
  assert.equal(args[args.indexOf("-codec_whitelist") + 1].includes("mpeg4"), false);
});

test("allowed MP4 container with forbidden codec fails inside the probe allowlist", async () => {
  const fixture = await fixtureTree();
  const forbidden = path.join(fixture.clipsDir, "forbidden-mpeg4.mp4");
  await execFileAsync("ffmpeg", [
    "-v", "error", "-nostdin", "-n",
    "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10",
    "-t", "0.5", "-c:v", "mpeg4", forbidden,
  ]);

  await assert.rejects(
    probeCodecs(forbidden, "mov", "video"),
    /media_codec_invalid/,
  );
});

test("command timeout terminates the entire spawned process group", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "renderer-process-tree-"));
  const marker = path.join(root, "grandchild-survived");
  const grandchild = `setTimeout(() => require("node:fs").writeFileSync(${JSON.stringify(marker)}, "bad"), 500)`;
  const parent = [
    "const {spawn}=require(\"node:child_process\");",
    `spawn(process.execPath,[\"-e\",${JSON.stringify(grandchild)}],{stdio:\"ignore\"});`,
    "setInterval(()=>{},1000);",
  ].join("");

  await assert.rejects(
    runWithRenderDeadline(150, () => runCmd(
      process.execPath,
      ["-e", parent],
      { timeoutMs: 5_000 },
    )),
    /render_deadline_exceeded/,
  );
  await delay(700);
  await assert.rejects(access(marker));
});

test("overall deadline rejects non-command work and forbids late publication", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "renderer-deadline-"));
  const source = path.join(root, "source.mp4");
  const destination = path.join(root, "published.mp4");
  await writeFile(source, Buffer.concat([MP4_HEADER, Buffer.alloc(20_000)]));

  await assert.rejects(
    runWithRenderDeadline(20, async () => {
      await delay(80);
      return publishNoClobber(source, destination);
    }),
    /render_deadline_exceeded/,
  );
  await assert.rejects(access(destination));
});

test("publication is permission-safe before atomic link and cleanup cannot change truth", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "renderer-publish-"));
  const source = path.join(root, "source.mp4");
  const destination = path.join(root, "published.mp4");
  await writeFile(source, Buffer.concat([MP4_HEADER, Buffer.alloc(20_000)]));
  let linkCalls = 0;

  await assert.rejects(
    publishNoClobber(source, destination, {
      setMode: async () => {
        throw new Error("injected chmod failure");
      },
      publishLink: async () => {
        linkCalls += 1;
      },
    }),
    /injected chmod failure/,
  );
  assert.equal(linkCalls, 0);
  await assert.rejects(access(destination));

  const published = await publishNoClobber(source, destination);
  assert.equal(published.fileSizeBytes, 20_024);
  assert.match(published.sha256, /^[a-f0-9]{64}$/);
  let cleanupWarnings = 0;
  assert.equal(await cleanupWorkDir(root, {
    remove: async () => {
      throw new Error("injected cleanup failure");
    },
    log: () => {
      cleanupWarnings += 1;
    },
  }), false);
  assert.equal(cleanupWarnings, 1);
  await access(destination);
});

test("existing safe output returns stable digest evidence with the conflict", async () => {
  const fixture = await fixtureTree();
  const existing = path.join(fixture.outputDir, "video-existing.mp4");
  await writeFile(existing, Buffer.concat([MP4_HEADER, Buffer.alloc(20_000)]));
  await chmod(existing, 0o440);

  await assert.rejects(
    reserveRenderOperation(fixture.outputDir, "video-existing"),
    (error) => {
      assert.equal(error.code, "render_output_conflict");
      assert.equal(error.details.file_size_bytes, 20_024);
      assert.match(error.details.artifact_sha256, /^[a-f0-9]{64}$/);
      return true;
    },
  );
});

test("same label is atomically no-clobber under concurrency", async () => {
  const fixture = await fixtureTree();
  const first = await reserveRenderOperation(fixture.outputDir, "video-001");

  await assert.rejects(
    reserveRenderOperation(fixture.outputDir, "video-001"),
    /render_output_conflict/,
  );
  assert.equal(first.outputPath, path.join(fixture.outputDir, "video-001.mp4"));
  assert.equal(first.workDir.startsWith(fixture.outputDir), true);
});

test("production renderer home is fixed and prepared for the non-root runtime", async () => {
  const originalNodeEnv = process.env.NODE_ENV;
  const originalHome = process.env.HOME;
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), "renderer-home-"));
  const canonicalTempRoot = await realpath(tempRoot);
  try {
    process.env.NODE_ENV = "production";
    process.env.HOME = canonicalTempRoot;
    await assert.rejects(prepareRendererHome(), /renderer_home_invalid/);
    await prepareRendererHome(canonicalTempRoot);
    assert.equal(await realpath(process.env.HOME), process.env.HOME);
  } finally {
    if (originalNodeEnv === undefined) delete process.env.NODE_ENV;
    else process.env.NODE_ENV = originalNodeEnv;
    if (originalHome === undefined) delete process.env.HOME;
    else process.env.HOME = originalHome;
  }
});

test("production entrypoint listens only on a Unix socket and rejects bad schema", async () => {
  const originalNodeEnv = process.env.NODE_ENV;
  const socketDir = await mkdtemp(path.join(os.tmpdir(), "renderer-socket-"));
  const socketPath = path.join(socketDir, "rendering.sock");
  let server;

  try {
    process.env.NODE_ENV = "test";
    server = await startRendererServer(socketPath);
    if (!server.listening) await once(server, "listening");
    const response = await new Promise((resolve, reject) => {
      const request = http.request(
        {
          socketPath,
          path: "/assemble",
          method: "POST",
          headers: { "content-type": "application/json" },
        },
        (incoming) => {
          let body = "";
          incoming.setEncoding("utf8");
          incoming.on("data", (chunk) => {
            body += chunk;
          });
          incoming.on("end", () => resolve({
            statusCode: incoming.statusCode,
            body: JSON.parse(body),
          }));
        },
      );
      request.on("error", reject);
      request.end(JSON.stringify({ unexpected: true }));
    });

    assert.equal(response.statusCode, 422);
    assert.deepEqual(response.body, {
      success: false,
      error: "request_schema_invalid",
    });
  } finally {
    if (server !== undefined) {
      await new Promise((resolve) => server.close(resolve));
    }
    if (originalNodeEnv === undefined) delete process.env.NODE_ENV;
    else process.env.NODE_ENV = originalNodeEnv;
  }
});

test("renderer health probe requires a complete 200 response before its deadline", async () => {
  const socketDir = await mkdtemp(path.join(os.tmpdir(), "renderer-health-"));
  const healthySocket = path.join(socketDir, "healthy.sock");
  const stalledSocket = path.join(socketDir, "stalled.sock");
  const healthyServer = http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/json" });
    response.end('{"status":"ok"}');
  });
  const stalledServer = http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/json" });
    response.write('{"status":');
  });

  try {
    healthyServer.listen(healthySocket);
    stalledServer.listen(stalledSocket);
    await Promise.all([
      once(healthyServer, "listening"),
      once(stalledServer, "listening"),
    ]);

    assert.equal(await probeRendererHealth(healthySocket, 1_000), true);
    assert.equal(await probeRendererHealth(stalledSocket, 50), false);
  } finally {
    await Promise.all([
      new Promise((resolve) => healthyServer.close(resolve)),
      new Promise((resolve) => stalledServer.close(resolve)),
    ]);
  }
});
