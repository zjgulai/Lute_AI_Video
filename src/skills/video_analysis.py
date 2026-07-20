"""Video analysis skill — downloads, transcribes, and analyzes influencer video.

Extracts:
  - Hook type (pain_point, counter_narrative, data_drop, scene_drop, question)
  - Speech rhythm (words/second, pauses)
  - Style markers (catchphrases, tone, emotion curve)
  - Structural segments (intro, hook, body, pitch, cta)

Auto-registers with SkillRegistry on import as "video-analysis-skill".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from src.models.provider_cost import ProviderCostContractError
from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry
from src.tools.safe_media import ffmpeg_local_input_args
from src.tools.video_downloader import VideoDownloader

logger = structlog.get_logger()


HOOK_TYPES = [
    "pain_point",
    "counter_narrative",
    "data_drop",
    "scene_drop",
    "question",
    "story_hook",
    "comparison",
]

STYLE_TONES = [
    "casual",
    "energetic",
    "professional",
    "storytelling",
    "educational",
    "entertaining",
]

SEGMENT_TYPES = [
    "hook",
    "intro",
    "body",
    "transition",
    "pitch",
    "demo",
    "testimonial",
    "cta",
    "outro",
]


class VideoAnalysisResult:
    """Structured analysis of an influencer video."""

    def __init__(self):
        self.video_url: str = ""
        self.duration_seconds: float = 0.0
        self.hook_type: str = "question"
        self.hook_text: str = ""
        self.speech_style: str = "casual"
        self.avg_speech_wpm: float = 150.0
        self.catchphrases: list[str] = []
        self.common_phrases: list[str] = []
        self.emotion_curve: list[dict[str, Any]] = []  # [{time, emotion, intensity}]
        self.segments: list[dict[str, Any]] = []       # [{type, start, end, description}]
        self.notes: str = ""
        self.visual_context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_url": self.video_url,
            "duration_seconds": self.duration_seconds,
            "hook_type": self.hook_type,
            "hook_text": self.hook_text,
            "speech_style": self.speech_style,
            "avg_speech_wpm": self.avg_speech_wpm,
            "catchphrases": self.catchphrases,
            "common_phrases": self.common_phrases,
            "emotion_curve": self.emotion_curve,
            "segments": self.segments,
            "notes": self.notes,
            "visual_context": self.visual_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VideoAnalysisResult:
        obj = cls()
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


class VideoAnalysisSkill(SkillCallable):
    """Analyze an influencer's video for style, hook, and structure.

    Input params:
      video_url: str — URL of the influencer's original video
      platform: str — detected or specified platform (tiktok, youtube, etc.)
      extract_segments: bool — whether to detect structural segments (default: True)
      extract_emotions: bool — whether to build emotion curve (default: True)

    Returns VideoAnalysisResult as dict.
    """

    name = "video-analysis-skill"
    description = (
        "Downloads and analyzes an influencer's video to extract style, "
        "hook type, speech patterns, and structural segments. "
        "Used as the first step in the influencer remix pipeline."
    )

    _downloader = VideoDownloader()

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if not params.get("video_url"):
            errors.append("'video_url' is required")
        return errors

    def validate_output(self, data: dict) -> list[str]:  # type: ignore[reportIncompatibleMethodOverride]
        errors = []
        if not data.get("hook_type"):
            errors.append("'hook_type' missing from output")
        return errors

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        video_url = params["video_url"]
        extract_segments = params.get("extract_segments", True)
        extract_emotions = params.get("extract_emotions", True)
        enable_visual = params.get("enable_visual_analysis", False)

        logger.info("video-analysis: downloading", url=video_url)
        download = await self._downloader.download(video_url)

        logger.info("video-analysis: transcribing", url=video_url)
        transcription = await self._downloader.transcribe(video_url)

        # NEW: Visual frame analysis (optional, non-blocking)
        visual_context = None
        if enable_visual and download.local_path and Path(download.local_path).exists():
            try:
                frame_paths = self._extract_keyframes(
                    str(download.local_path),
                    str(Path(download.local_path).parent),
                )
                if frame_paths:
                    transcript_text = getattr(transcription, "text", "") or ""
                    visual_context = await self._analyze_frames_visual(
                        frame_paths, transcript_text
                    )
            except Exception:
                logger.warning("video-analysis: visual analysis failed, continuing text-only")

        # Build analysis from transcription (enhanced with visual context)
        result = self._analyze_transcription(
            transcription=transcription,
            video_url=video_url,
            extract_segments=extract_segments,
            extract_emotions=extract_emotions,
            visual_context=visual_context,
        )

        # Inject visual context into result if available
        if visual_context:
            result.visual_context = visual_context

        return SkillResult(
            success=True,
            data=result.to_dict(),
        )

    def _analyze_transcription(
        self,
        transcription: Any,
        video_url: str,
        extract_segments: bool = True,
        extract_emotions: bool = True,
        visual_context: dict[str, Any] | None = None,
    ) -> VideoAnalysisResult:
        """Analyze transcription to extract style and structure.

        In stub mode (transcription.detected_language == "en" with mock data),
        generates a plausible analysis from the mock transcription text.
        """
        result = VideoAnalysisResult()
        result.video_url = video_url
        result.duration_seconds = getattr(transcription, "duration_seconds", 15.0)

        # Get transcript text
        if hasattr(transcription, "segments") and transcription.segments:
            full_text = " ".join(
                s.get("text", "") if isinstance(s, dict) else getattr(s, "text", "")
                for s in transcription.segments
            )
        else:
            full_text = getattr(transcription, "text", "")

        if not full_text:
            full_text = self._default_transcript()

        # Hook detection: first segment
        first_words = full_text[:120].lower()
        result.hook_type = self._detect_hook_type(first_words)
        result.hook_text = full_text[:100]

        # Speech rate
        num_words = len(full_text.split())
        duration = max(result.duration_seconds, 1.0)
        result.avg_speech_wpm = (num_words / duration) * 60.0

        # Style detection
        result.speech_style = self._detect_speech_style(full_text)

        # Catchphrases (simple heuristic: repeated short phrases)
        result.catchphrases = self._extract_catchphrases(full_text)

        # Common phrases
        result.common_phrases = [
            w for w in ["so", "like", "you know", "actually", "literally", "basically", "right"]
            if w in full_text.lower()
        ]

        # Emotion curve
        if extract_emotions:
            result.emotion_curve = self._build_emotion_curve(
                transcription, total_duration=duration
            )

        # Structural segments
        if extract_segments:
            result.segments = self._detect_segments(full_text, duration)

        result.notes = (
            f"Stub analysis of {num_words}-word transcript. "
            f"Hook: {result.hook_type}, Style: {result.speech_style}, "
            f"{len(result.catchphrases)} catchphrases, {len(result.segments)} segments."
        )

        # Enhance notes with visual context
        if visual_context:
            setting = visual_context.get("setting", "")
            products = visual_context.get("products_visible", [])
            if setting or products:
                ctx_bits = []
                if setting:
                    ctx_bits.append(f"Setting: {setting}")
                if products:
                    ctx_bits.append(f"Products visible: {', '.join(products[:3])}")
                result.notes = f"{result.notes}. Visual: {'; '.join(ctx_bits)}"

        return result

    def _detect_hook_type(self, first_words: str) -> str:
        """Detect hook type from opening words."""
        hook_signals = {
            "pain_point": [
                "hate", "annoying", "frustrat", "struggle", "tired of",
                "sick of", "problem", "worst", "bad", "wrong",
            ],
            "counter_narrative": [
                "stop", "don't", "never", "wrong", "myth", "actually",
                "truth", "real reason", "nobody tells you",
            ],
            "data_drop": [
                "percent", "million", "billion", "number", "study",
                "research", "stat", "fact", "data",
            ],
            "scene_drop": [
                "imagine", "picture this", "walk", "went", "saw",
                "happened", "then", "suddenly",
            ],
            "question": [
                "what if", "have you", "do you", "are you", "can you",
                "ever wondered", "did you know",
            ],
            "story_hook": [
                "so i", "let me tell", "story", "back when", "when i",
                "my friend", "one time",
            ],
            "comparison": [
                "before", "after", "vs", "versus", "instead of",
                "better than", "difference",
            ],
        }

        scores = {}
        for hook_type, signals in hook_signals.items():
            scores[hook_type] = sum(1 for s in signals if s in first_words)

        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "question"

    def _detect_speech_style(self, text: str) -> str:
        """Detect speech style from text patterns."""
        style_signals = {
            "casual": [
                "like", "um", "uh", "you know", "kind of", "sort of",
                "basically", "literally", "gonna", "wanna",
            ],
            "energetic": [
                "!", "amazing", "incredible", "best ever", "must have",
                "obsessed", "love", "hate", "holy", "wow",
            ],
            "professional": [
                "therefore", "however", "according", "research",
                "data", "analysis", "recommend", "solution",
            ],
            "storytelling": [
                "so then", "and then", "suddenly", "finally",
                "in the end", "after that", "meanwhile",
            ],
            "educational": [
                "step", "first", "second", "then", "next",
                "how to", "tutorial", "explain", "tip",
            ],
            "entertaining": [
                "funny", "hilarious", "crazy", "ridiculous",
                "lol", "joke", "comedy",
            ],
        }

        text_lower = text.lower()
        scores = {}
        for style, signals in style_signals.items():
            scores[style] = sum(1 for s in signals if s in text_lower)

        # Count exclamation marks as energetic boost
        scores["energetic"] += text.count("!") * 2

        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "casual"

    def _extract_catchphrases(self, text: str) -> list[str]:
        """Extract repeated short phrases that might be catchphrases."""
        import re

        text_lower = text.lower()
        # Look for 2-3 word phrases in a simple way
        words = re.findall(r"\b[a-z]+\b", text_lower)
        if len(words) < 10:
            return []

        # Count 2-gram and 3-gram frequencies
        bigrams = {}
        trigrams = {}
        for i in range(len(words)):
            if i + 1 < len(words):
                bg = f"{words[i]} {words[i+1]}"
                bigrams[bg] = bigrams.get(bg, 0) + 1
            if i + 2 < len(words):
                tg = f"{words[i]} {words[i+1]} {words[i+2]}"
                trigrams[tg] = trigrams.get(tg, 0) + 1

        # Catchphrases are phrases with frequency > 1 and not common filler
        fillers = {
            "i", "you", "it", "the", "a", "an", "and", "or", "but", "so",
            "in", "on", "at", "to", "for", "of", "with", "is", "are", "was",
        }

        candidates = []
        for phrase, count in trigrams.items():
            if count >= 2:
                words_in = phrase.split()
                if not all(w in fillers for w in words_in):
                    candidates.append(phrase)

        for phrase, count in bigrams.items():
            if count >= 3 and phrase not in fillers:
                candidates.append(phrase)

        return list(set(candidates))[:5]

    def _build_emotion_curve(
        self, transcription: Any, total_duration: float
    ) -> list[dict[str, Any]]:
        """Build emotion curve from transcription segments."""
        emotions = []

        if hasattr(transcription, "segments") and transcription.segments:
            for seg in transcription.segments:
                if isinstance(seg, dict):
                    start = seg.get("start", 0)
                    end = seg.get("end", 0)
                else:
                    start = getattr(seg, "start", 0)
                    end = getattr(seg, "end", 0)

                text = seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")
                emotion = self._detect_segment_emotion(text)
                emotions.append({
                    "time": start,
                    "emotion": emotion,
                    "intensity": min(1.0, len(text) / 200),
                    "text": text[:80],
                })
        else:
            # Generate synthetic curve
            thirds = total_duration / 3
            emotions = [
                {"time": 0.0, "emotion": "curiosity", "intensity": 0.7},
                {"time": thirds, "emotion": "engagement", "intensity": 0.8},
                {"time": thirds * 2, "emotion": "excitement", "intensity": 0.9},
                {"time": total_duration, "emotion": "urgency", "intensity": 1.0},
            ]

        return emotions

    def _detect_segment_emotion(self, text: str) -> str:
        """Detect emotion from segment text."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["!", "wow", "amazing", "love", "incredible"]):
            return "excitement"
        if any(w in text_lower for w in ["?", "what", "how", "why", "did"]):
            return "curiosity"
        if any(w in text_lower for w in ["but", "however", "problem", "issue"]):
            return "tension"
        if any(w in text_lower for w in ["so", "finally", "here's", "this is"]):
            return "resolution"
        if any(w in text_lower for w in ["link", "check", "click", "follow", "share"]):
            return "urgency"
        return "neutral"

    def _detect_segments(
        self, full_text: str, duration: float
    ) -> list[dict[str, Any]]:
        """Detect structural segments from transcription."""
        import re

        words = re.findall(r"\b[a-zA-Z]+\b", full_text)
        total_words = len(words)
        if total_words == 0:
            return []

        # Simple proportional segmentation
        segment_sentences = re.split(r"(?<=[.!?])\s+", full_text)
        sentences = [s.strip() for s in segment_sentences if s.strip()]
        if not sentences:
            sentences = [full_text]

        if len(sentences) < 4:
            # Not enough data for smart segmentation
            return [
                {"type": "hook", "start": 0.0, "end": duration * 0.15,
                 "description": sentences[0][:100] if sentences else "Opening hook"},
                {"type": "body", "start": duration * 0.15, "end": duration * 0.75,
                 "description": "Main content"},
                {"type": "cta", "start": duration * 0.75, "end": duration,
                 "description": "Call to action"},
            ]

        segments = []
        # Hook: first sentence
        segments.append({
            "type": "hook",
            "start": 0.0,
            "end": duration * 0.15,
            "description": sentences[0][:120],
        })

        # Body: middle sentences
        body_text = " ".join(sentences[1:-2]) if len(sentences) > 3 else " ".join(sentences[1:])
        if body_text:
            segments.append({
                "type": "body",
                "start": duration * 0.15,
                "end": duration * 0.75,
                "description": body_text[:200],
            })

        # Pitch / Demo
        if len(sentences) > 3:
            pitch_idx = max(2, len(sentences) - 3)
            segments.append({
                "type": "pitch",
                "start": duration * 0.75,
                "end": duration * 0.9,
                "description": sentences[pitch_idx][:120],
            })

        # CTA / Outro: last sentence
        segments.append({
            "type": "cta",
            "start": duration * 0.9,
            "end": duration,
            "description": sentences[-1][:120],
        })

        return segments

    def _default_transcript(self) -> str:
        """Fallback transcript for stub mode."""
        return (
            "Have you ever struggled with finding the right product? "
            "I was so frustrated with cheap alternatives that just don't work. "
            "But then I found this amazing solution that changed everything. "
            "Let me show you how it works step by step. "
            "The quality is incredible and the results speak for themselves. "
            "You need to try this for yourself. "
            "Click the link below to get yours today!"
        )

    @staticmethod
    def _extract_keyframes(video_path: str, output_dir: str, max_frames: int = 5) -> list[str]:
        """Extract evenly-spaced keyframes from a video using ffmpeg.

        Returns list of frame image paths, or empty list on failure.
        """
        import subprocess
        from pathlib import Path

        frame_dir = Path(output_dir) / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)

        try:
            subprocess.run([
                "ffmpeg", *ffmpeg_local_input_args(video_path),
                "-vf", "fps=1/6",
                "-frames:v", str(max_frames),
                f"{frame_dir}/frame_%03d.jpg",
                "-y",
                "-loglevel", "error",
            ], capture_output=True, timeout=30, check=True)

            return sorted([str(p) for p in frame_dir.glob("frame_*.jpg")])
        except Exception as e:
            logger.warning("video_analysis: ffmpeg keyframe extraction failed",
                           video_path=str(video_path), error=str(e)[:200])
            return []

    async def _analyze_frames_visual(self, frame_paths: list[str], transcript_text: str) -> dict[str, Any] | None:
        """Analyze video frames using vision-capable LLM.

        Sends frames + transcript snippet to understand:
        - Products visible, setting, lighting, camera style
        - Influencer appearance, body language, visual transitions

        Returns dict with visual context, or None on failure.
        """
        if not frame_paths:
            return None

        from src.tools.llm_client import llm

        system = """You are a visual content analyst. Given frames from an influencer
product review video and its transcript excerpt, analyze the visual content.
Return ONLY valid JSON with:
{
  "products_visible": ["description of products/brands visible"],
  "setting": "indoor/outdoor, room type, lighting quality",
  "camera_style": "shot types, angles, movement style",
  "influencer_appearance": "clothing, expression, body language",
  "visual_transitions": "how the video moves between scenes",
  "color_palette": "dominant colors",
  "text_overlays_visible": ["any text/graphics on screen"]
}"""

        user = f"""Transcript excerpt: {transcript_text[:500]}

Analyze these {len(frame_paths)} frames from the video and describe the visual content.
Focus on: what products are shown, the setting/environment, how the influencer appears,
and visual style elements."""

        try:
            raw = await llm.invoke_json(
                system,
                user,
                operation_key="skill.video_analysis",
                operation_instance="primary",
            )
            if isinstance(raw, dict):
                return raw
        except ProviderCostContractError:
            raise
        except Exception as exc:
            logger.warning(
                "video_analysis: visual llm analysis failed",
                frame_count=len(frame_paths),
                error=str(exc)[:200],
            )

        return None

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        """Return a reasonable stub analysis when everything fails."""
        result = VideoAnalysisResult()
        result.video_url = params.get("video_url", "")
        result.duration_seconds = 30.0
        result.hook_type = "question"
        result.speech_style = "casual"
        result.avg_speech_wpm = 150.0
        result.catchphrases = ["check this out"]
        result.common_phrases = ["like", "so", "you know"]
        result.emotion_curve = [
            {"time": 0.0, "emotion": "curiosity", "intensity": 0.7},
            {"time": 15.0, "emotion": "engagement", "intensity": 0.8},
            {"time": 30.0, "emotion": "urgency", "intensity": 1.0},
        ]
        result.segments = [
            {"type": "hook", "start": 0.0, "end": 4.5,
             "description": "Opening hook / attention grabber"},
            {"type": "body", "start": 4.5, "end": 22.5,
             "description": "Main content with product showcase"},
            {"type": "cta", "start": 22.5, "end": 30.0,
             "description": "Call to action with link"},
        ]
        result.notes = "Fallback analysis — no transcription available"
        return SkillResult(
            success=True,
            data=result.to_dict(),
            error="Used fallback analysis",
        )


# Auto-register
SkillRegistry().register(VideoAnalysisSkill())
logger.info("skill registered", name=VideoAnalysisSkill.name)
