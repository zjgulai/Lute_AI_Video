"""C2PA Content Credentials signing for AI-generated videos (Sprint 3 P3-1).

Closes diagnostic compliance requirement for EU AI Act 2026-08-02:
AI-generated content distributed in EU must carry tamper-evident metadata
identifying it as AI-generated, per Article 50 disclosure obligation.

Implementation:
- Uses official `c2pa-python` PyPI package (v0.32.x, Apache 2.0 / MIT).
- Embeds C2PA manifest into mp4 with `claim_generator_info` + a
  ``c2pa.actions`` assertion declaring ``c2pa.created`` with
  ``digitalSourceType: aiGeneratedContent`` (IPTC vocabulary).
- Lazy import: this module is only imported when called, so a missing
  c2pa-python install does not break unrelated test paths.
- Opt-in: signing is gated by ``C2PA_ENABLED`` env var. Default is
  disabled so existing test paths and dev-mode deploys are unaffected.
- Graceful degradation: if c2pa-python is missing, cert is not
  provisioned, or signing raises, ``sign_video`` logs and returns the
  unsigned input path so downstream pipelines never break.

Production deployment notes (TODO before EU launch):
- Provision an X.509 signing cert + private key. Self-signed dev certs
  work for local testing; production needs a real cert from a CAI-trusted
  issuer (e.g., DigiCert C2PA cert, Adobe Content Authenticity cert).
- Set env vars:
    C2PA_ENABLED=1
    C2PA_CERT_PATH=/path/to/cert.pem
    C2PA_KEY_PATH=/path/to/key.pem
    C2PA_TSA_URL=http://timestamp.digicert.com  (optional, for legal proof)
- Verify with c2patool / Adobe CAI's Content Credentials inspector before
  EU rollout.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


def is_enabled() -> bool:
    """Return True iff C2PA signing is enabled via env var."""
    return os.environ.get("C2PA_ENABLED", "").lower() in ("1", "true", "yes")


def build_manifest(
    title: str,
    *,
    pipeline_version: str = "0.3.0",
    pipeline_name: str = "AI_Video_Pipeline",
) -> dict[str, Any]:
    """Build the minimum C2PA manifest dict required for EU AI Act disclosure.

    Returns a dict suitable for c2pa-python's Builder. Includes:
    - ``claim_generator_info``: identifies our pipeline as the producer
    - ``format``: video/mp4
    - ``title``: caller-supplied human-readable title
    - ``assertions[c2pa.actions]``: declares the content as AI-generated
      via IPTC ``aiGeneratedContent`` digitalSourceType.

    See https://c2pa.org/specifications/specifications/2.0/specs/_attachments/C2PA_Specification.pdf
    section "Actions" for the assertion schema.
    """
    return {
        "claim_generator_info": [{"name": pipeline_name, "version": pipeline_version}],
        "format": "video/mp4",
        "title": title,
        "assertions": [
            {
                "label": "c2pa.actions",
                "data": {
                    "actions": [
                        {
                            "action": "c2pa.created",
                            "digitalSourceType": (
                                "http://cv.iptc.org/newscodes/digitalsourcetype/aiGeneratedContent"
                            ),
                        }
                    ]
                },
            }
        ],
    }


def sign_video(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> str:
    """Sign an mp4 with C2PA Content Credentials, returning the output path.

    Behavior:
    - If ``C2PA_ENABLED`` is not set → no-op, returns ``str(input_path)``.
    - If c2pa-python is not installed → logs warning, returns input path.
    - If cert / key env vars missing → logs warning, returns input path.
    - On signing exception → logs error, returns input path (NEVER raises).

    Args:
        input_path: source mp4 to sign.
        output_path: where to write the signed mp4. Defaults to a sibling
            file with `_signed.mp4` suffix.
        title: human-readable title for the manifest. Defaults to the file
            stem.

    Returns:
        Absolute path to the signed mp4 (or the original on no-op / failure).
    """
    src = Path(input_path)
    if not is_enabled():
        return str(src)

    if not src.exists() or src.stat().st_size == 0:
        logger.warning("c2pa: input not found or empty, skipping", path=str(src))
        return str(src)

    cert_path = os.environ.get("C2PA_CERT_PATH")
    key_path = os.environ.get("C2PA_KEY_PATH")
    if not cert_path or not key_path:
        logger.warning(
            "c2pa: cert/key env not configured, skipping signing",
            cert_set=bool(cert_path),
            key_set=bool(key_path),
        )
        return str(src)

    try:
        import c2pa  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("c2pa: c2pa-python not installed, skipping signing")
        return str(src)

    dest = Path(output_path) if output_path else src.with_name(f"{src.stem}_signed{src.suffix}")
    manifest = build_manifest(title=title or src.stem)
    tsa_url = os.environ.get("C2PA_TSA_URL", "http://timestamp.digicert.com")

    try:
        with open(cert_path, "rb") as f:
            certs_pem = f.read()
        with open(key_path, "rb") as f:
            key_pem = f.read()

        # c2pa-python's high-level API; signature shape may evolve. Wrap in a
        # broad except below so prod stays unbroken if the binding changes.
        builder = c2pa.Builder(manifest)
        signer = c2pa.create_signer(
            certs=certs_pem,
            private_key=key_pem,
            alg="es256",
            tsa_url=tsa_url,
        )
        builder.sign_file(str(src), str(dest), signer=signer)
        logger.info("c2pa: signed", input=str(src), output=str(dest))
        return str(dest)
    except Exception as exc:
        logger.error(
            "c2pa: signing failed, returning unsigned input",
            error=str(exc)[:300],
            path=str(src),
        )
        return str(src)
