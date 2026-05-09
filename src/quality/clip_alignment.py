"""CLIP text-image alignment checker — optional, lazy-imported.

Detects "text doesn't match image" by computing cosine similarity between
CLIP text embedding and CLIP image embedding.

Usage:
    from src.quality.clip_alignment import ClipAligner
    score = ClipAligner().score(image_path, text_prompt)  # 0-1 float or None

If transformers / torch are not installed, score() returns None silently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Thresholds tuned on CLIP cosine similarity (range roughly 0-1)
CLIP_ALIGN_STRONG = 0.28   # good alignment
CLIP_ALIGN_WEAK = 0.18     # questionable


class ClipAligner:
    """Lazy-loaded CLIP model for text-image alignment scoring."""

    def __init__(self):
        self._model = None
        self._processor = None
        self._available: bool | None = None

    def _load(self) -> bool:
        """Attempt to load CLIP model. Returns True on success."""
        if self._available is not None:
            return self._available
        try:
            from transformers import CLIPModel, CLIPProcessor  # type: ignore[import-untyped]

            self._processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            self._model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            self._model.eval()
            self._available = True
            logger.info("clip_aligner: CLIP model loaded")
        except Exception as e:
            self._available = False
            logger.warning(
                "clip_aligner: transformers/torch not available — "
                "text-image alignment checks will be skipped. "
                "Install with: pip install transformers torch Pillow",
                error=str(e),
            )
        return self._available

    def score(self, image_path: str | Path, text: str) -> float | None:
        """Return cosine similarity between image and text embeddings.

        Returns:
            float in [0, 1] — higher = better alignment.
            None if CLIP is unavailable or image/text is invalid.
        """
        if not self._load():
            return None

        path = Path(image_path)
        if not path.exists() or path.stat().st_size < 100:
            return None
        if not text or not isinstance(text, str):
            return None

        try:
            import torch
            from PIL import Image

            image = Image.open(path).convert("RGB")
            inputs = self._processor(
                text=[text],
                images=image,
                return_tensors="pt",
                padding=True,
            )
            with torch.no_grad():
                outputs = self._model(**inputs)  # type: ignore[misc]

            # logits_per_image shape: [1, 1]
            logits = outputs.logits_per_image[0][0]
            # Normalize to roughly 0-1 using sigmoid-like scaling
            # CLIP raw logits can be 10-40; we scale to a sensible 0-1 range
            score = float(torch.nn.functional.sigmoid(logits / 10.0))  # type: ignore[attr-defined]
            return round(score, 3)
        except Exception as e:
            logger.warning("clip_aligner: scoring failed", error=str(e), path=str(path))
            return None

    def check_batch(
        self,
        image_text_pairs: list[tuple[str | Path, str]],
    ) -> list[dict[str, Any]]:
        """Score multiple image-text pairs.

        Returns list of dicts with keys:
            image_path, text, score, aligned (bool), reason
        """
        if not self._load():
            return [
                {
                    "image_path": str(img),
                    "text": txt,
                    "score": None,
                    "aligned": None,
                    "reason": "CLIP unavailable (install transformers+torch)",
                }
                for img, txt in image_text_pairs
            ]

        results = []
        for img_path, txt in image_text_pairs:
            score = self.score(img_path, txt)
            if score is None:
                aligned = None
                reason = "scoring failed or invalid input"
            elif score >= CLIP_ALIGN_STRONG:
                aligned = True
                reason = f"strong alignment ({score:.2f})"
            elif score >= CLIP_ALIGN_WEAK:
                aligned = True
                reason = f"moderate alignment ({score:.2f})"
            else:
                aligned = False
                reason = f"weak alignment ({score:.2f}) — text may not match image"
            results.append({
                "image_path": str(img_path),
                "text": txt,
                "score": score,
                "aligned": aligned,
                "reason": reason,
            })
        return results
