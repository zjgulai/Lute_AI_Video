---
title: S1 Continuity Storyboard Design
doc_type: architecture
module: s1-product-direct
topic: continuity-storyboard
status: stable
created: 2026-05-20
updated: 2026-05-20
owner: self
source: human+ai
---

# S1 Continuity Storyboard Design

## Context

Two production S1 runs around a bottle warmer exposed a specific quality problem: the pipeline can generate real clips and assemble a playable video, but clip boundaries feel abrupt. The issue is not only a missing transition effect. The current pipeline generates each Seedance clip as an independent narrative segment, then Remotion places the clips in sequence. This creates three visible breaks:

- Visual continuity breaks: product, space, lighting, and camera language can jump between clips.
- Action continuity breaks: important in-between actions are skipped.
- Editing continuity breaks: Remotion currently performs hard cuts without match cuts, J-cuts, L-cuts, or transition metadata.

The target for this design is the S1 Product Direct path, first optimized for a 15-30 second bottle warmer asset. S2-S5 are out of scope for the first implementation.

## Goal

Create a continuity-directed S1 video flow that produces:

- A 12-grid director storyboard for bottle-warmer product videos.
- Four coherent Seedance clip groups instead of three isolated large clips.
- Lightweight editorial transitions in final assembly.
- Separate asset-level and publish-level quality gates.

The desired first-pass acceptance target is:

```text
asset_ready_audit = PASS
continuity_score >= 0.8
publish_ready_audit may WARN without blocking asset output
```

## Non-Goals

- Do not make 24-grid the default.
- Do not generate one Seedance clip per micro-shot.
- Do not introduce a new editing engine.
- Do not refactor the whole pipeline.
- Do not expand the change to S2-S5 in the first implementation.
- Do not make thumbnail generation block asset-level success.

## Architecture

Add a Continuity Director layer between script/storyboard generation and video generation.

```text
strategy
-> scripts
-> storyboards
-> continuity_storyboard_grid
-> keyframe_images
-> video_prompts
-> seedance_clips
-> tts_audio
-> thumbnail_images
-> assemble_final
-> audit
```

Existing `storyboards` remain script-level storyboards. The new `continuity_storyboard_grid` step creates a director-level 12-grid plan with micro-shots, continuity anchors, and clip grouping instructions.

The first bottle-warmer grid is:

```text
1. 2 AM clock
2. Cold bottle problem
3. Parent approaches warmer
4. Bottle placed into warmer
5. Button press
6. Indicator light
7. Short waiting moment
8. Bottle removed
9. Temperature check
10. Calm doorway or nursery context
11. Product beauty shot
12. CTA or phone shop action
```

The 12 micro-shots are grouped into four Seedance clips:

```text
Clip A: shots 1-3, pain setup, about 4s
Clip B: shots 4-6, product action, about 6s
Clip C: shots 7-9, result proof, about 6s
Clip D: shots 10-12, emotional close and CTA, about 4-5s
```

## Data Model

`continuity_storyboard_grid` should persist a structure like:

```json
{
  "grid_type": "12-grid",
  "product_name": "Momcozy Nutri Bottle Warmer",
  "visual_identity": {
    "location": "warm night kitchen and nursery doorway",
    "lighting": "soft warm low-light",
    "product_anchor": "same bottle warmer on the same countertop",
    "color_palette": ["warm white", "soft green indicator", "matte neutral counter"]
  },
  "micro_shots": [
    {
      "index": 1,
      "beat": "pain_setup",
      "duration": 1.5,
      "visual": "2:00 AM clock in dim kitchen",
      "action": "clock ticks, parent enters frame",
      "camera": "close-up, slow push-in",
      "continuity_in": "dark quiet kitchen",
      "continuity_out": "parent reaches for cold bottle",
      "transition_out": "match cut on hand movement",
      "safety_notes": ["no close-up infant face"]
    }
  ],
  "clip_groups": [
    {
      "clip_index": 1,
      "shot_indices": [1, 2, 3],
      "duration": 4,
      "purpose": "pain setup",
      "seedance_prompt": "continuous three-beat action prompt",
      "transition_to_next": "match cut from hand carrying bottle to placing bottle"
    }
  ]
}
```

Required invariants:

- Every micro-shot has `continuity_in` and `continuity_out`.
- Every clip group has `transition_to_next`, except the final group.
- All clip groups reference existing micro-shot indices.
- Product and scene anchors are explicit.
- Safety notes avoid infant close-ups, medical claims, and distress-heavy imagery.

## API Contract

Extend S1 request config with optional fields:

```json
{
  "storyboard_grid": "auto | 9 | 12 | 24",
  "continuity_mode": "standard | high_quality",
  "transition_style": "clean | soft_crossfade | match_cut"
}
```

Defaults:

```text
storyboard_grid = 12
continuity_mode = standard
transition_style = match_cut
```

The frontend should expose this as a simple two-option control, not as a large advanced panel:

```text
Video Continuity
- Standard: 12-grid director storyboard, balanced speed and quality
- High Quality: 12-grid plus previous-clip end-frame continuity, slower
```

## Generation Strategy

The default mode keeps bounded concurrency but changes what is generated:

- Generate four clip groups from the 12-grid plan.
- Each clip prompt contains a short action chain, not a single isolated visual.
- Each clip prompt repeats the same product anchor, location anchor, lighting, and camera continuity.
- Solution scenes are split so the product action is easier for Seedance to execute.

High-quality mode changes Seedance generation only:

- Generate clip groups sequentially.
- Extract the final frame from clip N.
- Feed that frame into clip N+1 as continuity reference when supported.
- Accept longer runtime in exchange for stronger visual continuity.

This mode should be opt-in because it can turn a 9-12 minute run into a 15-25 minute run.

## Transition Strategy

Remotion should stop treating all shot boundaries as hard cuts. First implementation should support:

- `match_cut`: action continuity cut, for hand-to-bottle or bottle-to-warmer movement.
- `action_cut`: direct cut on a visible action, such as button press to indicator light.
- `soft_crossfade`: emotional or CTA transition, about 8-12 frames.

Bottle-warmer default:

```text
Clip A -> Clip B: match cut
Cold bottle carried toward counter -> bottle placed into warmer

Clip B -> Clip C: action cut
Indicator light -> bottle removed or temperature check

Clip C -> Clip D: soft crossfade
Temperature check -> product beauty shot or CTA
```

Audio should use light J-cut/L-cut behavior:

- Next voiceover may start 0.2-0.4s before the visual cut.
- Previous audio tail may extend about 0.2s after the cut.
- Captions follow semantic voiceover timing, not raw clip boundaries.

## Audit Strategy

Split audit into asset-level and publish-level results.

`asset_ready_audit` answers whether the output is useful as source material:

- No all-stub clip set.
- Final video is playable.
- Real Seedance clips are accessible.
- The product scenario is recognizable.
- Micro-shot action sequence is present.
- Transitions are defined and applied.

`publish_ready_audit` answers whether it is ready for direct ad publishing:

- 1080x1920 or target channel output exists.
- FPS matches target.
- Duration matches the requested target.
- Brand and product names are prominent.
- Thumbnail count and quality meet target.
- Captions and audio are complete.

`continuity_score` should be separate:

```text
continuity_score = visual_consistency + action_bridge + pacing + transition_fit
```

First version can use structured checks rather than computer vision:

- Micro-shots include continuity fields.
- Adjacent groups define transition instructions.
- Remotion receives and applies transition metadata.
- Product and scene anchors are stable.
- Clip set is not all stub.
- Total clip duration reaches the requested asset target.

## Testing Plan

Unit tests:

- `continuity_storyboard_grid` generates 12 micro-shots for bottle-warmer input.
- Every micro-shot has `continuity_in` and `continuity_out`.
- Every non-final clip group has `transition_to_next`.
- Clip groups cover all 12 micro-shots exactly once.
- Seedance prompt generation can consume clip groups.
- Audit distinguishes asset-ready from publish-ready.

Integration tests:

- Mock S1 run includes the new continuity step.
- Existing S1 request without the new fields defaults to 12-grid standard mode.
- Render JSON includes transition metadata.
- Existing auth, API key injection, and state persistence behavior remain unchanged.

Production validation:

- Run the bottle-warmer S1 path.
- Record total time, Seedance time, clip count, stub count, continuity score, final video URL.
- Human review checks whether clip boundaries still feel abrupt.

## Rollout

Phase 1:

- Add `continuity_storyboard_grid` skill.
- Persist the new step in S1 state.
- Keep old pipeline behavior behind a fallback path.

Phase 2:

- Change video prompt generation to use clip groups.
- Generate four clip groups for the bottle-warmer path.
- Keep standard mode concurrent.

Phase 3:

- Add Remotion transition metadata and light J-cut/L-cut behavior.
- Add asset-ready and publish-ready audit split.

Phase 4:

- Add high-quality continuity mode using previous-clip end frames.
- Only expose it as an opt-in setting.

## Open Risks

- More structured prompts may still be rejected by supplier moderation if infant-feeding content is too direct.
- Four clips may cost more than three clips, though fewer than 12 clips.
- High-quality mode can materially increase runtime.
- Remotion transition changes must preserve current rendering fallback behavior.

## Decision

Proceed with 12-grid director storyboard plus four grouped Seedance clips as the default S1 continuity design. Use Remotion transitions as a support layer, not the primary fix. Keep sequential end-frame continuity as a high-quality opt-in mode.
