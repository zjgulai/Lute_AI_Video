"""Caption Agent — generates timed subtitle tracks.

MVP: outputs caption entries from script text.
Phase 2: Whisper transcription + Remotion caption rendering.
"""

import structlog

from src.models import CaptionEntry, CaptionPlan, Script

logger = structlog.get_logger()


class CaptionAgent:
    """Generates timed captions from scripts."""

    async def run(self, scripts: list[Script]) -> list[CaptionPlan]:
        plans = []
        for script in scripts:
            entries = []
            idx = 0
            for seg in script.segments:
                voiceover = seg.voiceover.strip()

                # Degradation guard: skip segments with placeholder text
                # (e.g. "[HOOK for: ...]" or "[Pain point expansion]")
                if voiceover.startswith("[") and voiceover.endswith("]"):
                    logger.warning(
                        "caption: skipping placeholder segment",
                        script_id=script.id,
                        segment_type=seg.segment_type,
                        voiceover_preview=voiceover[:60],
                    )
                    continue

                # Degradation guard: empty or whitespace-only voiceover
                if not voiceover:
                    continue

                # Split voiceover into ~3 caption chunks per segment
                words = voiceover.split()
                chunk_size = max(1, len(words) // 3)
                for i in range(0, len(words), chunk_size):
                    chunk = " ".join(words[i : i + chunk_size])
                    t_start = seg.start_time + (i / len(words)) * (seg.end_time - seg.start_time)
                    t_end = t_start + (chunk_size / len(words)) * (seg.end_time - seg.start_time)
                    entries.append(
                        CaptionEntry(
                            index=idx,
                            start_time=round(t_start, 2),
                            end_time=round(min(t_end, seg.end_time), 2),
                            text=chunk,
                            style="default",
                        )
                    )
                    idx += 1
            plans.append(
                CaptionPlan(
                    script_id=script.id,
                    language=script.language,
                    entries=entries,
                )
            )
        logger.info("caption: done", plan_count=len(plans))
        return plans
