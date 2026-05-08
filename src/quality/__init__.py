"""Quality assessment modules — optional ML-powered checks for video pipeline.

All modules use lazy imports so they don't require heavy dependencies
(transformers, torch, opencv, mediapipe) unless explicitly used.

Modules:
    clip_alignment:      CLIP text-image alignment checker (P1-5)
    nr_quality:          No-reference image/video quality (BRISQUE-like) (P1-6)
    safe_zone:           Platform UI safe zone checker (P2-13)
    ab_tracker:          A/B test tracking for gate variants (P2-14)
    scene_analysis:      PySceneDetect video scene analysis (P2-11)
    face_consistency:    MediaPipe/DeepFace identity verification (P2-12)
    viral_predictor:     Viral potential scoring (P3-15)
    ctr_estimator:       CTR/conversion estimation (P3-16)
    dynamic_thresholds:  Auto-tune thresholds from feedback (P3-17)
    skill_versioning:    Skill performance monitoring (P3-18)
"""
