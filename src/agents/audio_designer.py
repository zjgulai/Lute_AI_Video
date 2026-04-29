"""Audio Design Agent — TTS voiceover + BGM + SFX planning.

Uses ElevenLabs for real TTS synthesis.
Falls back to stub mode when API key is absent.
"""


import structlog

from src.models import AudioPlan, AudioSegment, Script
from src.tools.elevenlabs_client import VOICE_PRESETS, ElevenLabsClient

logger = structlog.get_logger()


class AudioDesignAgent:
    """Designs and synthesizes audio for each video script."""

    def __init__(self, use_mock: bool = False, elevenlabs_api_key: str | None = None):
        self.use_mock = use_mock
        self.tts = ElevenLabsClient(api_key=elevenlabs_api_key)

    async def run(self, scripts: list[Script]) -> list[AudioPlan]:
        plans = []
        for script in scripts:
            segments = []

            # Synthesize each segment with ElevenLabs
            for seg in script.segments:
                path = await self.tts.synthesize(
                    text=seg.voiceover,
                    language=script.language.value,
                )
                segments.append(
                    AudioSegment(
                        start_time=seg.start_time,
                        end_time=seg.end_time,
                        type="voiceover",
                        source=str(path),
                        text=seg.voiceover,
                        volume=1.0,
                    )
                )

            # BGM track (placeholder — Epidemic Sound / Artlist API in Phase 2)
            segments.append(
                AudioSegment(
                    start_time=0.0,
                    end_time=script.total_duration,
                    type="bgm",
                    source="epidemic_sound:warm_acoustic",
                    text="",
                    volume=0.25,
                )
            )

            plans.append(
                AudioPlan(
                    script_id=script.id,
                    voice_id=VOICE_PRESETS.get(script.language.value, VOICE_PRESETS["en"]),
                    bgm_track="warm_acoustic_instrumental",
                    segments=segments,
                )
            )

            logger.info(
                "audio: script synthesized",
                script_id=script.id,
                segments=len(segments) - 1,  # Exclude BGM
            )

        return plans
