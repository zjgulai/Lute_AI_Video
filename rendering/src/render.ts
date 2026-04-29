/**
 * CLI render script — takes pipeline JSON and renders .mp4 via Remotion.
 *
 * Usage:
 *   npx tsx src/render.ts --input ../output/pipeline_state.json --output ../output/video.mp4
 */

import path from "path";
import fs from "fs";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";

interface RenderConfig {
  input: string;
  output: string;
  compositionId?: string;
  fps?: number;
  width?: number;
  height?: number;
}

async function parseArgs(): Promise<RenderConfig> {
  const args = process.argv.slice(2);
  const config: RenderConfig = {
    input: "../output/pipeline_state.json",
    output: "../output/video.mp4",
    compositionId: "ShortVideo",
    fps: 30,
    width: 1080,
    height: 1920,
  };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--input" && args[i + 1]) config.input = args[++i];
    if (args[i] === "--output" && args[i + 1]) config.output = args[++i];
    if (args[i] === "--composition" && args[i + 1])
      config.compositionId = args[++i];
  }

  return config;
}

function loadPipelineData(inputPath: string): any {
  const absPath = path.resolve(inputPath);
  if (!fs.existsSync(absPath)) {
    console.error(`Input file not found: ${absPath}`);
    process.exit(1);
  }
  const raw = fs.readFileSync(absPath, "utf-8");
  return JSON.parse(raw);
}

function buildRenderProps(pipelineState: any): any {
  // Extract the first video's data
  const firstScript = pipelineState.scripts?.[0];
  const firstStoryboard = pipelineState.storyboards?.[0];
  const firstCaption = pipelineState.caption_plans?.[0];
  const firstAudio = pipelineState.audio_plans?.[0];
  const brandGuidelines = pipelineState.brand_guidelines || {};

  const shots = (firstStoryboard?.shots || []).map((shot: any) => ({
    id: shot.id,
    start_time: shot.start_time,
    end_time: shot.end_time,
    text_overlay: shot.text_overlay || "",
    voiceover: "",
    visual: shot.visual || `Shot ${shot.id}`,
  }));

  // Inject voiceover text from audio plan segments
  if (firstAudio?.segments) {
    for (const seg of firstAudio.segments) {
      if (seg.type === "voiceover") {
        // Find matching shot by time
        for (const shot of shots) {
          if (seg.start_time >= shot.start_time && seg.start_time < shot.end_time) {
            shot.voiceover = seg.text || "";
            break;
          }
        }
      }
    }
  }

  const captions = (firstCaption?.entries || []).map((e: any) => ({
    start_time: e.start_time,
    end_time: e.end_time,
    text: e.text,
  }));

  const totalDuration = firstStoryboard?.total_duration || 45;

  return {
    data: {
      script_id: firstScript?.id || "RENDER",
      total_duration: totalDuration,
      shots,
      captions,
    },
    audioSrc: null, // Set to actual audio file path
    backgroundColor: "#FFF5F7",
    primaryColor: brandGuidelines.colors?.primary || "#FF6B9D",
    textColor: brandGuidelines.colors?.secondary || "#2D3436",
  };
}

async function main() {
  const config = await parseArgs();

  console.log("🎬 Remotion Renderer");
  console.log(`   Input:  ${config.input}`);
  console.log(`   Output: ${config.output}`);

  // Load pipeline data
  const pipelineState = loadPipelineData(config.input);
  const renderProps = buildRenderProps(pipelineState);

  console.log(
    `   Shots: ${renderProps.data.shots.length}, Duration: ${renderProps.data.total_duration}s`
  );

  // Bundle the Remotion project
  const entry = path.resolve(__dirname, "Root.tsx");
  console.log("   Bundling...");
  const bundleLocation = await bundle({ entryPoint: entry });

  // Select composition
  console.log("   Selecting composition...");
  const composition = await selectComposition({
    serveUrl: bundleLocation,
    id: config.compositionId || "ShortVideo",
    inputProps: renderProps,
  });

  // Render
  console.log("   Rendering...");
  const outputPath = path.resolve(config.output);
  const outputDir = path.dirname(outputPath);
  if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

  await renderMedia({
    composition,
    serveUrl: bundleLocation,
    codec: "h264",
    outputLocation: outputPath,
    inputProps: renderProps,
    onProgress: ({ progress }) => {
      process.stdout.write(`\r   Progress: ${Math.round(progress * 100)}%`);
    },
  });

  console.log(`\n✅ Video rendered: ${outputPath}`);
}

main().catch((err) => {
  console.error("Render failed:", err);
  process.exit(1);
});
