import { describe, expect, it } from "vitest";

import {
  extractFinalVideoPath,
  extractRenderJsonPath,
  extractSeedanceClipOutput,
  extractThumbnailImagePaths,
  extractTtsAudioPaths,
} from "./pipelineStepOutput";

describe("pipeline step output selectors", () => {
  it("extracts detailed Seedance clip output from the current object shape", () => {
    expect(
      extractSeedanceClipOutput({
        clip_paths: ["/clips/a.mp4", 42, "/clips/b.mp4"],
        clip_details: [
          { duration: 4.2, is_stub: true, continuity_frame: { path: "/frame.png" } },
          { duration: 3, is_filler: true, verification: { all_ok: false } },
        ],
        total_duration: 7.2,
        target_duration: 10,
      }),
    ).toEqual({
      paths: ["/clips/a.mp4", "/clips/b.mp4"],
      details: [
        {
          duration: 4.2,
          is_stub: true,
          is_filler: false,
          continuity_frame: { path: "/frame.png" },
          verification: { all_ok: undefined },
        },
        {
          duration: 3,
          is_stub: false,
          is_filler: true,
          continuity_frame: undefined,
          verification: { all_ok: false },
        },
      ],
      totalDuration: 7.2,
      targetDuration: 10,
      hasDurationTarget: true,
    });
  });

  it("extracts legacy clip arrays and media paths", () => {
    expect(extractSeedanceClipOutput(["/clips/legacy.mp4", 123]).paths).toEqual([
      "/clips/legacy.mp4",
    ]);
    expect(extractTtsAudioPaths({ audio_paths: ["/audio/a.wav", false] })).toEqual([
      "/audio/a.wav",
    ]);
    expect(extractTtsAudioPaths({ urls: ["/audio/from-url.wav"] })).toEqual([
      "/audio/from-url.wav",
    ]);
    expect(extractThumbnailImagePaths({ image_paths: ["/thumb.png"] })).toEqual([
      "/thumb.png",
    ]);
  });

  it("extracts final video and render JSON paths across compatible shapes", () => {
    expect(extractFinalVideoPath("/final.mp4")).toBe("/final.mp4");
    expect(extractFinalVideoPath(["/array-final.mp4"])).toBe("/array-final.mp4");
    expect(extractFinalVideoPath({ final_video_url: "/url-final.mp4" })).toBe("/url-final.mp4");
    expect(extractFinalVideoPath({ final_video_path: "/path-final.mp4" })).toBe("/path-final.mp4");
    expect(extractFinalVideoPath({ video_path: "/video-final.mp4" })).toBe("/video-final.mp4");
    expect(extractRenderJsonPath({ render_json_path: "/render.json" })).toBe("/render.json");
    expect(extractRenderJsonPath({})).toBe("");
  });
});
