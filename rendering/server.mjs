import express from "express";
import { spawn } from "node:child_process";
import { mkdir, stat, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

const PORT = Number(process.env.PORT || 3001);
const OUTPUT_DIR = process.env.OUTPUT_DIR || "/app/output";
const RENDERS_DIR = path.join(OUTPUT_DIR, "renders");
const REMOTION_PROJECT = "/app";

const MIN_CLIP_BYTES = 1000;

const app = express();
app.use(express.json({ limit: "50mb" }));

function runCmd(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"], ...opts });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (d) => (stdout += d.toString()));
    proc.stderr.on("data", (d) => (stderr += d.toString()));
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code === 0) resolve({ stdout, stderr });
      else reject(new Error(`${cmd} exited ${code}: ${stderr.slice(-400)}`));
    });
  });
}

async function probeFile(p) {
  try {
    const s = await stat(p);
    return { exists: true, size: s.size };
  } catch {
    return { exists: false, size: 0 };
  }
}

async function probeRemotionVersion() {
  try {
    const pkg = await import("./node_modules/remotion/package.json", {
      with: { type: "json" },
    });
    return pkg.default?.version || pkg.version || null;
  } catch {
    return null;
  }
}

app.get("/health", async (_req, res) => {
  const remotionVersion = await probeRemotionVersion();
  let ffmpegOk = false;
  try {
    await runCmd("ffmpeg", ["-version"]);
    ffmpegOk = true;
  } catch {}
  let chromiumOk = false;
  try {
    await runCmd("chromium-browser", ["--version"]);
    chromiumOk = true;
  } catch {}
  const ready = Boolean(remotionVersion) && ffmpegOk && chromiumOk;
  res.status(ready ? 200 : 503).json({
    status: ready ? "ok" : "unready",
    node: process.version,
    remotion: remotionVersion,
    ffmpeg: ffmpegOk,
    chromium: chromiumOk,
    output_dir: OUTPUT_DIR,
  });
});

async function concatClips(clipPaths, outPath, label) {
  await mkdir(RENDERS_DIR, { recursive: true });
  const concatList = path.join(RENDERS_DIR, `${label}_concat.txt`);
  const valid = [];
  for (const p of clipPaths || []) {
    const probe = await probeFile(p);
    if (probe.exists && probe.size > MIN_CLIP_BYTES) valid.push(p);
  }
  if (valid.length < 2) return null;
  await writeFile(
    concatList,
    valid.map((p) => `file '${p.replace(/'/g, "'\\''")}'`).join("\n"),
  );
  try {
    await runCmd("ffmpeg", [
      "-y", "-f", "concat", "-safe", "0",
      "-i", concatList,
      "-c", "copy",
      "-movflags", "+faststart",
      outPath,
    ]);
  } catch (copyErr) {
    await runCmd("ffmpeg", [
      "-y", "-f", "concat", "-safe", "0",
      "-i", concatList,
      "-c:v", "libx264", "-preset", "fast", "-crf", "23",
      "-c:a", "aac", "-b:a", "128k",
      "-movflags", "+faststart",
      outPath,
    ]);
  }
  const probe = await probeFile(outPath);
  if (probe.exists && probe.size > 10000) return outPath;
  return null;
}

async function muxAudio(videoPath, audioPaths, label) {
  const valid = [];
  for (const p of audioPaths || []) {
    const probe = await probeFile(p);
    if (probe.exists && probe.size > 200) valid.push(p);
  }
  if (valid.length === 0) return null;
  const concatList = path.join(RENDERS_DIR, `${label}_audio_concat.txt`);
  await writeFile(
    concatList,
    valid.map((p) => `file '${p.replace(/'/g, "'\\''")}'`).join("\n"),
  );
  const concatAudio = path.join(RENDERS_DIR, `${label}_audio.mp3`);
  try {
    await runCmd("ffmpeg", [
      "-y", "-f", "concat", "-safe", "0",
      "-i", concatList,
      "-c", "copy",
      concatAudio,
    ]);
  } catch {
    return null;
  }
  const muxedPath = path.join(
    path.dirname(videoPath),
    `${path.basename(videoPath, ".mp4")}_with_audio.mp4`,
  );
  try {
    await runCmd("ffmpeg", [
      "-y",
      "-i", videoPath,
      "-i", concatAudio,
      "-c:v", "copy",
      "-c:a", "aac",
      "-shortest",
      muxedPath,
    ]);
    if (existsSync(muxedPath)) return muxedPath;
  } catch {}
  return null;
}

async function remotionRender(renderPayload, outPath, label) {
  await mkdir(RENDERS_DIR, { recursive: true });
  const inputJsonPath = path.join(RENDERS_DIR, `${label}_input.json`);
  await writeFile(inputJsonPath, JSON.stringify(renderPayload, null, 2));
  await runCmd(
    "npx",
    ["tsx", "src/render.ts", "--input", inputJsonPath, "--output", outPath],
    { cwd: REMOTION_PROJECT },
  );
  const probe = await probeFile(outPath);
  if (probe.exists && probe.size > 10000) return outPath;
  return null;
}

app.post("/assemble", async (req, res) => {
  const body = req.body || {};
  const label = body.output_label || `assemble_${Date.now()}`;
  const outPath = path.join(RENDERS_DIR, `${label}.mp4`);

  let videoPath = null;
  let renderMode = "none";
  let isStub = false;

  try {
    videoPath = await concatClips(body.clip_paths || [], outPath, label);
    if (videoPath) renderMode = "clip_concat";
  } catch (e) {
    console.warn("concat failed", e.message);
  }

  if (!videoPath) {
    try {
      const renderPayload = body.render_payload || {
        scripts: body.scripts || [],
        storyboards: body.storyboards || [],
        caption_plans: body.caption_plans || [],
        audio_plans: body.audio_plans || [],
        brand_guidelines: body.brand_guidelines || {},
      };
      videoPath = await remotionRender(renderPayload, outPath, label);
      if (videoPath) renderMode = "remotion";
    } catch (e) {
      console.error("remotion render failed", e.message);
    }
  }

  if (!videoPath) {
    isStub = true;
    renderMode = "stub";
    await mkdir(RENDERS_DIR, { recursive: true });
    try {
      await runCmd("ffmpeg", [
        "-y",
        "-f", "lavfi",
        "-i", "color=c=#100C0D:s=1080x1920:d=5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an",
        outPath,
      ]);
      videoPath = outPath;
    } catch (e) {
      return res.status(500).json({
        success: false,
        error: `all render paths failed: ${e.message}`,
        render_mode: renderMode,
      });
    }
  }

  if (!isStub && Array.isArray(body.audio_paths) && body.audio_paths.length > 0) {
    try {
      const muxed = await muxAudio(videoPath, body.audio_paths, label);
      if (muxed) videoPath = muxed;
    } catch (e) {
      console.warn("audio mux failed", e.message);
    }
  }

  const probe = await probeFile(videoPath);
  res.json({
    success: true,
    video_path: videoPath,
    file_size_bytes: probe.size,
    render_mode: renderMode,
    is_stub: isStub,
    label,
  });
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`rendering service listening on :${PORT}`);
});
