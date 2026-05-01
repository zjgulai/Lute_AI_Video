/**
 * Demo mock data for static GitHub Pages deployment.
 * Uses ONLY real files from public/portfolio/ so that all media previews work offline.
 */

import type { ProductSku, ModelProfile, VideoType, CardSequence, TemplatePreset } from "@/components/types";

// Real portfolio filenames (must match files in public/portfolio/)
const REAL_VIDEOS = {
  office: "seedance_W85PPT60_bff4.mp4",
  park: "seedance_EJYLRLHS_65f3.mp4",
  product: "seedance_COUUK507_3c5c.mp4",
  story: "seedance_IABYQA5H_5182.mp4",
  recycle: "seedance_LM39EHUL_355a.mp4",
};

const REAL_IMAGES = {
  thumb1: "poyo_img_s1_thumb_1_4b0b.webp",
  thumb2: "poyo_img_s1_thumb_2_b301.webp",
  thumb3: "poyo_img_s1_1777216783_thumb_3_35b9.webp",
  thumb2alt: "poyo_img_s1_thumb_2_2739.webp",
  kf1a: "poyo_img_keyframe_script-BRIEF-001-en_001_43ea.webp",
  kf1b: "poyo_img_keyframe_script-BRIEF-001-en_002_894f.webp",
  kf2a: "poyo_img_keyframe_script-BRIEF-002-en_000_1aff.webp",
  kf2b: "poyo_img_keyframe_script-BRIEF-002-en_002_6df5.webp",
  kf3: "poyo_img_keyframe_script-BRIEF-003-en_002_316b.webp",
  kf1c: "poyo_img_keyframe_script-BRIEF-001-en_002_30ec.webp",
};

export const DEMO_RESULT_1 = {
  success: true,
  label: "demo_001",
  scenario: "product_direct",
  video_duration: 30,
  errors: [],
  media_synthesis_errors: [],
  briefs: [
    {
      id: "BRIEF-001",
      platform: "tiktok",
      topic: "Smart Breast Pump — Hands-Free Freedom for Working Moms",
      target_audience: "Working mothers aged 25-35, urban, tech-savvy",
      key_message: "Pump anywhere without stopping your life. Silent, wearable, app-controlled.",
      hook_type: "Problem-Agitation-Solution",
      description:
        "Open with a stressed mom at a coffee shop trying to find a private place to pump. Transition to her wearing the device under her clothes while working on her laptop, completely unbothered. Close with the app showing milk volume tracking.",
    },
    {
      id: "BRIEF-002",
      platform: "facebook",
      topic: "Why 10,000+ Moms Switched to Wearable Pumping",
      target_audience: "New mothers 28-40, suburban, value-conscious",
      key_message: "Hospital-grade suction in a silent wearable. 50% less time, 100% more freedom.",
      hook_type: "Social Proof + Contrast",
      description:
        "Split-screen comparison: traditional pumping (tied to wall, loud, 30 min) vs wearable (walking, silent, 15 min). Overlay review quotes from real users.",
    },
  ],
  scripts: [
    {
      id: "SCRIPT-001",
      product_name: "Lute Smart Breast Pump",
      brand_name: "Lute",
      language: "en",
      segments: [
        {
          segment_type: "hook",
          start_time: 0,
          end_time: 3,
          voiceover: "What if pumping didn't mean stopping your life?",
          visual_description:
            "Close-up of mom's face, frustrated, looking at traditional pump. Quick cut to her glancing at her watch.",
          text_overlay: "STOP pumping. START living.",
        },
        {
          segment_type: "problem",
          start_time: 3,
          end_time: 8,
          voiceover:
            "Traditional pumps tie you to a wall for 30 minutes. Loud. Bulky. Impossible at work or in public.",
          visual_description:
            "Montage: mom hiding in bathroom stall, cords everywhere, machine humming loudly, coworkers looking.",
          text_overlay: "30 min. Stuck. Every. Single. Time.",
        },
        {
          segment_type: "solution",
          start_time: 8,
          end_time: 18,
          voiceover:
            "Lute fits in your bra. Silent as a whisper. App tracks every drop. Pump during meetings, walks, even while cooking dinner.",
          visual_description:
            "Mom wearing device under blouse, typing at laptop in open office, walking in park, cooking — all seamless. App UI showing real-time milk tracking.",
          text_overlay: "Silent. Wearable. App-Controlled.",
        },
        {
          segment_type: "cta",
          start_time: 18,
          end_time: 25,
          voiceover:
            "Join 10,000+ moms who reclaimed their time. Free shipping. 30-day trial. Tap the link now.",
          visual_description:
            "Happy mom with baby, holding phone showing order page. QR code and website URL appear.",
          text_overlay: "Try Risk-Free → lute.com/pump",
        },
      ],
    },
  ],
  storyboards: [
    {
      scene_title: "The Hook — Frustrated Mom",
      visual_description:
        "Tight close-up on mom's face. She looks exhausted. Quick cut to traditional pump with tangled cords. She checks her watch — late for a meeting.",
      shot_type: "Close-up + Quick cut",
      total_duration: 3,
    },
    {
      scene_title: "The Problem — Bathroom Stall",
      visual_description:
        "Mom squeezed into a bathroom stall, pump machine loud and bulky. Coworkers outside looking concerned. She looks embarrassed.",
      shot_type: "Medium shot, handheld feel",
      total_duration: 5,
    },
    {
      scene_title: "The Solution — Office Freedom",
      visual_description:
        "Same mom, now calm, wearing Lute under her blouse. Typing at laptop in open office. No one notices. App shows milk tracking.",
      shot_type: "Wide shot, smooth motion",
      total_duration: 5,
    },
    {
      scene_title: "The Payoff — Park Walk",
      visual_description:
        "Mom walking in sunny park with stroller, baby sleeping. She's smiling, checking phone. Device invisible under clothes.",
      shot_type: "Wide establishing shot",
      total_duration: 5,
    },
    {
      scene_title: "The CTA — Happy Ending",
      visual_description:
        "Mom at home, relaxed, holding baby. Phone shows 'Order Placed' confirmation. QR code and URL overlay.",
      shot_type: "Medium shot, warm lighting",
      total_duration: 4,
    },
  ],
  video_prompts: [
    {
      platform: "tiktok",
      prompt:
        "Cinematic lifestyle shot of a professional working mother in a modern open-plan office, wearing a discreet wearable breast pump under her blouse. She is confidently typing on a MacBook Pro while colleagues walk by in the background. Soft natural lighting from large windows, shallow depth of field, warm color grade. The pump is completely invisible. 4K, photorealistic, Apple commercial aesthetic.",
    },
    {
      platform: "facebook",
      prompt:
        "Split-screen comparison: left side shows a stressed mother tangled in cords with a traditional breast pump in a cramped bathroom stall, harsh fluorescent lighting. Right side shows the same mother walking confidently in a sunny park pushing a stroller, wearing a sleek invisible wearable pump under a casual dress. Dramatic lighting contrast. Professional product photography style.",
    },
  ],
  thumbnail_sets: [
    {
      platform: "tiktok",
      prompts: [
        "Young professional mom at coffee shop, wearable pump hidden under blazer, confidently on laptop, surprised coworker in background, bold text 'She's PUMPING?!', high contrast, viral thumbnail style",
      ],
    },
    {
      platform: "facebook",
      prompts: [
        "Before/after split: frustrated mom with bulky pump vs happy mom walking in park, bold headline '10,000+ Moms Made the Switch', warm colors, trustworthy aesthetic",
      ],
    },
  ],
  seedance_output: {
    clip_paths: ["/portfolio/" + REAL_VIDEOS.office, "/portfolio/" + REAL_VIDEOS.park],
    clip_details: [
      {
        path: "/portfolio/" + REAL_VIDEOS.office,
        duration: 14.0,
        is_stub: false,
        file_size: 7275516,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Cinematic lifestyle shot of a professional working mother...",
        continuity_frame: false,
      },
      {
        path: "/portfolio/" + REAL_VIDEOS.park,
        duration: 13.0,
        is_stub: false,
        file_size: 3584686,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Split-screen comparison: stressed mother vs confident mother...",
        continuity_frame: true,
      },
    ],
    total_duration: 27.0,
    target_duration: 30,
  },
  clip_paths: ["/portfolio/" + REAL_VIDEOS.office, "/portfolio/" + REAL_VIDEOS.park],
  audio_paths: [],
  lyrics_paths: [],
  thumbnail_image_paths: ["/portfolio/" + REAL_IMAGES.thumb1, "/portfolio/" + REAL_IMAGES.thumb2],
  final_video_path: "/portfolio/" + REAL_VIDEOS.office,
  audit_report: {
    overall_status: "PASS",
    overall_score: 0.87,
    summary:
      "Video meets all quality criteria. Strong hook, clear problem-solution structure, compelling CTA. Minor suggestion: shorten segment 2 by 1s to improve pacing.",
    criteria: [
      { name: "Hook Strength", status: "PASS", score: 0.92, feedback: "Strong emotional hook within first 3 seconds" },
      { name: "Visual Quality", status: "PASS", score: 0.88, feedback: "Professional lighting and composition" },
      { name: "Audio Clarity", status: "PASS", score: 0.85, feedback: "Clear voiceover, good pacing" },
      { name: "Brand Compliance", status: "PASS", score: 0.9, feedback: "All brand guidelines met" },
      { name: "Duration Target", status: "WARN", score: 0.75, feedback: "27s vs 30s target — slightly under" },
      { name: "CTA Clarity", status: "PASS", score: 0.95, feedback: "Clear URL and QR code" },
      { name: "Platform Fit", status: "PASS", score: 0.88, feedback: "Well-suited for TikTok and Facebook" },
    ],
  },
  steps_completed: 12,
};

export const DEMO_RESULT_2 = {
  success: true,
  label: "demo_002",
  scenario: "brand_campaign",
  video_duration: 45,
  errors: [],
  media_synthesis_errors: [],
  briefs: [
    {
      id: "BRIEF-003",
      platform: "youtube_shorts",
      topic: "Lute Brand Story — Born from a Mother's Frustration",
      target_audience: "Expectant and new mothers 24-38, emotionally-driven buyers",
      key_message: "Designed by moms, for moms. Every feature solves a real problem we faced.",
      hook_type: "Emotional Story + Founder Origin",
      description:
        "Founder Sarah shares her personal story: pumping in a car during a work trip, device leaking, missing an important meeting. This frustration led to creating Lute. Emotional music, authentic storytelling.",
    },
    {
      id: "BRIEF-004",
      platform: "instagram",
      topic: "Lute x Earth Day — Sustainable Pumping",
      target_audience: "Eco-conscious moms 26-35, urban, higher income",
      key_message: "The only breast pump with a recycling program. Pump for your baby, protect their planet.",
      hook_type: "Values Alignment + Sustainability",
      description:
        "Show the pump's eco-friendly packaging, recycled materials, and mail-back recycling program. Mom unboxing, showing the recycling label, dropping off at collection point. Soft green color palette.",
    },
  ],
  scripts: [
    {
      id: "SCRIPT-002",
      product_name: "Lute Eco Pump",
      brand_name: "Lute",
      language: "en",
      segments: [
        {
          segment_type: "hook",
          start_time: 0,
          end_time: 5,
          voiceover: "I was sitting in my car, crying, milk everywhere, missing the biggest meeting of my career.",
          visual_description:
            "Founder Sarah in car, emotional, traditional pump leaking. Flashback-style, grainy filter. She's on a video call, looking distressed.",
          text_overlay: "This was my breaking point.",
        },
        {
          segment_type: "story",
          start_time: 5,
          end_time: 18,
          voiceover:
            "That night I sketched the first Lute on a napkin. 2 years, 47 prototypes, and 10,000 mom interviews later — we built something that actually works for real life.",
          visual_description:
            "Time-lapse montage: sketch on napkin, 3D printing prototypes, moms testing and giving feedback, iterations improving. Warm, documentary style.",
          text_overlay: "47 prototypes. 10,000 moms. 1 mission.",
        },
        {
          segment_type: "product",
          start_time: 18,
          end_time: 32,
          voiceover:
            "Silent. Invisible. 15-minute sessions. Hospital-grade suction. And when you're done? Send it back. We recycle every component. Because your baby's future matters.",
          visual_description:
            "Clean product shots on white background, rotating 360. Mom wearing it under different outfits. Close-ups of app interface. Recycling process visualization.",
          text_overlay: "Silent. Invisible. Recyclable.",
        },
        {
          segment_type: "cta",
          start_time: 32,
          end_time: 40,
          voiceover:
            "Join 50,000 moms who chose better. Free 45-day trial. Full refund, no questions. Because we believe in this that much.",
          visual_description:
            "Grid of real mom testimonials with photos. Final shot: Sarah holding her baby, smiling. Company logo and URL.",
          text_overlay: "45-Day Trial. Full Refund. → lute.com",
        },
      ],
    },
  ],
  storyboards: [
    {
      scene_title: "The Breaking Point — Car Scene",
      visual_description:
        "Sarah in driver's seat, pump leaking on her blouse, video call on phone showing 'Meeting in Progress'. Tears in her eyes. Raw, emotional, handheld camera.",
      shot_type: "Close-up, handheld, emotional",
      total_duration: 5,
    },
    {
      scene_title: "The Origin — Napkin Sketch",
      visual_description:
        "Overhead shot of diner table. Sarah's hand sketching pump design on paper napkin. Coffee cup, late night atmosphere. Warm tungsten lighting.",
      shot_type: "Overhead, warm lighting",
      total_duration: 4,
    },
    {
      scene_title: "The Journey — Prototype Montage",
      visual_description:
        "Fast-cut montage: 3D printer in action, moms of different ethnicities testing prototypes, focus groups, design iterations on screen. Upbeat instrumental music.",
      shot_type: "Montage, mixed shots",
      total_duration: 6,
    },
    {
      scene_title: "The Product — 360 Showcase",
      visual_description:
        "Clean white cyclorama. Pump rotating on turntable. Cut to moms wearing it under business suit, workout clothes, casual dress. Invisible in all scenarios.",
      shot_type: "Product photography, clean",
      total_duration: 8,
    },
    {
      scene_title: "The Mission — Recycling",
      visual_description:
        "Mom putting used pump parts into prepaid recycling envelope. Aerial shot of recycling facility. Text overlay: '100% of returned components recycled into medical-grade plastic.'",
      shot_type: "Aerial + close-up mix",
      total_duration: 5,
    },
    {
      scene_title: "The Promise — Founder Close",
      visual_description:
        "Sarah holding her 2-year-old, both smiling at camera. Soft window light. Authentic, no makeup, real moment. URL and trial offer text overlay.",
      shot_type: "Medium close-up, natural light",
      total_duration: 4,
    },
  ],
  video_prompts: [
    {
      platform: "youtube_shorts",
      prompt:
        "Emotional documentary-style scene: a young professional mother sitting in her car, tears streaming down her face, a breast pump leaking milk onto her work blouse. She is on a video call on her phone, looking distressed. The lighting is dim, sunset through the windshield creating a golden-orange glow. Raw, authentic, iPhone documentary aesthetic. No music, just ambient sound.",
    },
    {
      platform: "instagram",
      prompt:
        "Aerial drone shot of a modern recycling facility with solar panels on the roof. Clean, bright, optimistic lighting. Transition to close-up of hands placing a small medical device into a biodegradable mailer envelope with a green recycling logo. Soft focus background showing a happy mother and baby. Eco-friendly color palette: greens, earth tones, natural whites.",
    },
  ],
  thumbnail_sets: [
    {
      platform: "youtube_shorts",
      prompts: [
        "Emotional thumbnail: crying mom in car with leaking pump, bold text 'I QUIT MY JOB Because of This', red accent color, high contrast, documentary style",
      ],
    },
    {
      platform: "instagram",
      prompts: [
        "Aesthetic flat lay: eco-friendly product packaging, recycled paper, green leaves, breast pump on natural wood surface, soft daylight, Instagram lifestyle aesthetic",
      ],
    },
  ],
  seedance_output: {
    clip_paths: ["/portfolio/" + REAL_VIDEOS.story, "/portfolio/" + REAL_VIDEOS.recycle, "/portfolio/" + REAL_VIDEOS.product],
    clip_details: [
      {
        path: "/portfolio/" + REAL_VIDEOS.story,
        duration: 15.0,
        is_stub: false,
        file_size: 1160683,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Emotional documentary-style scene: a young professional mother...",
        continuity_frame: false,
      },
      {
        path: "/portfolio/" + REAL_VIDEOS.recycle,
        duration: 14.0,
        is_stub: false,
        file_size: 1173601,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Aerial drone shot of a modern recycling facility...",
        continuity_frame: true,
      },
      {
        path: "/portfolio/" + REAL_VIDEOS.product,
        duration: 12.0,
        is_stub: false,
        file_size: 1296925,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Clean white cyclorama. Pump rotating on turntable...",
        continuity_frame: true,
        is_filler: true,
      },
    ],
    total_duration: 41.0,
    target_duration: 45,
  },
  clip_paths: ["/portfolio/" + REAL_VIDEOS.story, "/portfolio/" + REAL_VIDEOS.recycle, "/portfolio/" + REAL_VIDEOS.product],
  audio_paths: [],
  lyrics_paths: [],
  thumbnail_image_paths: ["/portfolio/" + REAL_IMAGES.thumb3, "/portfolio/" + REAL_IMAGES.kf3],
  final_video_path: "/portfolio/" + REAL_VIDEOS.story,
  audit_report: {
    overall_status: "PASS",
    overall_score: 0.91,
    summary:
      "Exceptional brand storytelling with strong emotional arc. Founder narrative creates authentic connection. Sustainability angle differentiates from competitors. Recommended for high-budget brand campaign.",
    criteria: [
      { name: "Hook Strength", status: "PASS", score: 0.95, feedback: "Powerful emotional hook — crying in car scene" },
      { name: "Visual Quality", status: "PASS", score: 0.9, feedback: "Documentary aesthetic feels authentic" },
      { name: "Audio Clarity", status: "PASS", score: 0.88, feedback: "Founder voiceover adds credibility" },
      { name: "Brand Compliance", status: "PASS", score: 0.93, feedback: "Brand values clearly communicated" },
      { name: "Duration Target", status: "PASS", score: 0.92, feedback: "41s vs 45s target — excellent pacing" },
      { name: "CTA Clarity", status: "PASS", score: 0.9, feedback: "Trial offer is compelling and clear" },
      { name: "Platform Fit", status: "PASS", score: 0.91, feedback: "Strong fit for YouTube and Instagram" },
    ],
  },
  steps_completed: 12,
};

// ── Brand VLOG demo result (S5 pipeline shape, 30s = 2 × 15s clips) ──
export const DEMO_RESULT_VLOG = {
  success: true,
  label: "demo_vlog_001",
  scenario: "brand_vlog",
  video_duration: 30,
  errors: [],
  media_synthesis_errors: [],
  brand_id: "momcozy",
  scene_id: "living-room",
  selected_models: ["mom_30s", "infant"],
  vlog_strategy: {
    theme: "Parent-Child Bonding — A Quiet Afternoon",
    arc: "Setup → Connection → Resolution",
    emotional_beats: ["calm", "warmth", "joy"],
    target_platforms: ["tiktok", "instagram"],
  },
  briefs: [
    {
      id: "VLOG-BRIEF-001",
      platform: "tiktok",
      topic: "A Mom's Afternoon — 30 Seconds of Quiet Joy",
      target_audience: "New mothers 28-38, urban, lifestyle-driven",
      key_message: "Real moments, real bonding — Momcozy moves with you.",
      hook_type: "Lifestyle Story",
      description:
        "Documentary-style 30s spot: mom in her living room with baby. Soft afternoon light. Wearing the device under casual clothes. Two natural beats — quiet pumping moment and joyful play moment.",
    },
  ],
  scripts: [
    {
      id: "VLOG-SCRIPT-001",
      product_name: "Momcozy Wearable Pump",
      brand_name: "Momcozy",
      language: "en",
      segments: [
        {
          segment_type: "scene_a",
          start_time: 0,
          end_time: 15,
          voiceover: "There are moments when I just want to be still — and Momcozy lets me.",
          visual_description:
            "Mom on living-room sofa, baby napping beside her. Wearing pump under cardigan. Soft natural window light, slow camera push-in.",
          text_overlay: "Quiet moments. Real bonding.",
        },
        {
          segment_type: "scene_b",
          start_time: 15,
          end_time: 30,
          voiceover: "Then he wakes up, and we just play. No interruptions, no schedule.",
          visual_description:
            "Same room, golden hour. Mom playing peek-a-boo with baby. Toys on rug. Genuine laughter, handheld camera, warm tones.",
          text_overlay: "Move with you. Live with you.",
        },
      ],
    },
  ],
  storyboards: [
    {
      scene_title: "Scene A — Quiet Afternoon",
      visual_description:
        "Mom seated on linen sofa with sleeping infant. Pump invisible under loose cardigan. Window light, dust motes, slow push-in. Calm music.",
      shot_type: "Medium close-up, slow dolly",
      total_duration: 15,
    },
    {
      scene_title: "Scene B — Golden-Hour Play",
      visual_description:
        "Same living room, sun lower. Mom and baby on rug, playing with wooden toys. Handheld, intimate. Warm 3200K, natural smiles.",
      shot_type: "Handheld, mixed angles",
      total_duration: 15,
    },
  ],
  video_prompts: [
    {
      platform: "tiktok",
      prompt:
        "Documentary-style scene: a young mother sits on a linen sofa in a sunlit living room, her infant napping beside her. She wears a wearable breast pump invisibly under a soft cardigan. The afternoon light streams through sheer curtains, dust motes floating. Slow push-in from medium to close-up. Warm color palette, ASMR-quiet ambient sound, no music. iPhone-cinematic aesthetic.",
    },
    {
      platform: "tiktok",
      prompt:
        "Same living room, golden hour. Mother and a 9-month-old baby on a soft rug, playing peek-a-boo with wooden toys. Warm 3200K lighting through window. Handheld camera follows their interaction naturally. Real laughter, genuine eye contact. Documentary intimate aesthetic. Color graded warm with slight film grain.",
    },
  ],
  thumbnail_sets: [
    {
      platform: "tiktok",
      prompts: [
        "Lifestyle thumbnail: mom and baby on sofa, soft window light, text overlay 'A Quiet Afternoon', warm tones, Momcozy logo bottom-right",
      ],
    },
  ],
  seedance_output: {
    clip_paths: ["/portfolio/" + REAL_VIDEOS.story, "/portfolio/" + REAL_VIDEOS.recycle],
    clip_details: [
      {
        path: "/portfolio/" + REAL_VIDEOS.story,
        duration: 15.0,
        is_stub: false,
        file_size: 1160683,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Documentary-style scene: a young mother sits on a linen sofa...",
        continuity_frame: false,
        scene_label: "Scene A — Quiet Afternoon",
      },
      {
        path: "/portfolio/" + REAL_VIDEOS.recycle,
        duration: 15.0,
        is_stub: false,
        file_size: 1173601,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Same living room, golden hour. Mother and a 9-month-old baby...",
        continuity_frame: true,
        scene_label: "Scene B — Golden-Hour Play",
      },
    ],
    total_duration: 30.0,
    target_duration: 30,
  },
  clip_paths: ["/portfolio/" + REAL_VIDEOS.story, "/portfolio/" + REAL_VIDEOS.recycle],
  audio_paths: [],
  lyrics_paths: [],
  thumbnail_image_paths: ["/portfolio/" + REAL_IMAGES.kf2a, "/portfolio/" + REAL_IMAGES.kf2b],
  final_video_path: "/portfolio/" + REAL_VIDEOS.story,
  audit_report: {
    overall_status: "PASS",
    overall_score: 0.89,
    summary:
      "Authentic lifestyle VLOG with strong emotional resonance. Two-scene structure provides natural narrative arc. Brand integration feels organic, not forced. Recommended for organic social distribution.",
    criteria: [
      { name: "Hook Strength", status: "PASS", score: 0.86, feedback: "Quiet opening builds intimacy quickly" },
      { name: "Visual Quality", status: "PASS", score: 0.91, feedback: "Documentary cinematography feels authentic" },
      { name: "Audio Clarity", status: "PASS", score: 0.84, feedback: "Ambient sound design supports mood" },
      { name: "Brand Compliance", status: "PASS", score: 0.92, feedback: "Brand presence subtle and on-tone" },
      { name: "Duration Target", status: "PASS", score: 0.95, feedback: "30s exactly matches target" },
      { name: "Emotional Arc", status: "PASS", score: 0.90, feedback: "Calm-to-joy beat lands well" },
      { name: "Platform Fit", status: "PASS", score: 0.88, feedback: "Strong fit for TikTok and Instagram Reels" },
    ],
  },
  steps_completed: 6,
};

// ── Fast Mode demo result (matches FastModeResult shape in api.ts) ──
export const DEMO_FAST_MODE_RESULT = {
  success: true,
  video_path: "/portfolio/" + REAL_VIDEOS.park,
  video_url: "/portfolio/" + REAL_VIDEOS.park,
  filename: REAL_VIDEOS.park,
  llm_prompt:
    "A breathtaking cinematic drone shot captures a lone hiker walking along a narrow mountain ridge during the golden hour. The camera starts in a wide establishing shot from behind the hiker, slowly tilting upward to reveal the expansive valley below, bathed in warm orange and pink hues. Dramatic clouds drift across the sky, casting moving shadows on the rugged terrain. The hiker's silhouette stands out against the vibrant horizon, emphasizing the scale and solitude of the landscape. Cinematic depth of field, smooth camera movement, professional color grading.",
  scene_description: "Mountain ridge hiker · golden hour · cinematic drone",
  user_prompt: "a hiker on a mountain ridge at sunset",
  duration_seconds: 15,
  file_size_bytes: 3584686,
  generation_time_ms: 1240,
  timing: {
    llm_ms: 320,
    video_ms: 820,
    tts_ms: 0,
  },
  model_info: {
    llm: "deepseek-v3",
    video: "seedance-pro",
    tts: "",
  },
  is_stub: false,
  tts_path: "",
};

export const DEMO_CONFIG_1 = {
  product_catalog: {
    name: "Lute Smart Breast Pump",
    products: [
      {
        name: "Lute Smart Breast Pump — Pro Edition",
        description: "Silent wearable breast pump with app control and hospital-grade suction.",
        price: 299.99,
        currency: "USD",
      },
    ],
  },
  brand_guidelines: {
    brand_name: "Lute",
    primary_color: "#7CB342",
    tone_of_voice: "Empowering, modern, supportive",
    tagline: "Pump anywhere. Live everywhere.",
  },
  target_platforms: ["tiktok", "facebook", "youtube_shorts"],
  target_languages: ["en"],
  video_duration: 30,
  content_scenario: "product_direct",
};

export const DEMO_CONFIG_2 = {
  product_catalog: {
    name: "Lute Eco Pump",
    products: [
      {
        name: "Lute Eco Pump — Sustainable Edition",
        description: "The world's first recyclable breast pump. Hospital-grade performance meets zero-waste commitment.",
        price: 349.99,
        currency: "USD",
      },
    ],
  },
  brand_guidelines: {
    brand_name: "Lute",
    primary_color: "#4CAF50",
    tone_of_voice: "Authentic, mission-driven, warm",
    tagline: "Pump for your baby. Protect their planet.",
  },
  target_platforms: ["youtube_shorts", "instagram", "tiktok"],
  target_languages: ["en"],
  video_duration: 45,
  content_scenario: "brand_campaign",
};

// ── Demo Asset Library (real portfolio files only) ──

export const DEMO_ASSETS = [
  {
    filename: REAL_VIDEOS.office,
    path: "/portfolio/" + REAL_VIDEOS.office,
    size: 7275516,
    type: "video",
    created: Math.floor(Date.now() / 1000) - 86400 * 3,
    label: "AI Generated Video — Office Freedom",
    platform: "tiktok",
    duration: 14,
    tags: ["ai-video", "seedance", "lifestyle", "product_direct"],
  },
  {
    filename: REAL_VIDEOS.park,
    path: "/portfolio/" + REAL_VIDEOS.park,
    size: 3584686,
    type: "video",
    created: Math.floor(Date.now() / 1000) - 86400 * 3,
    label: "AI Generated Video — Park Walk",
    platform: "facebook",
    duration: 13,
    tags: ["ai-video", "seedance", "outdoor", "product_direct"],
  },
  {
    filename: REAL_VIDEOS.product,
    path: "/portfolio/" + REAL_VIDEOS.product,
    size: 1296925,
    type: "video",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Generated Video — Product Close-up",
    platform: "tiktok",
    duration: 12,
    tags: ["ai-video", "seedance", "product", "brand_campaign"],
  },
  {
    filename: REAL_VIDEOS.story,
    path: "/portfolio/" + REAL_VIDEOS.story,
    size: 1160683,
    type: "video",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Generated Video — Brand Story",
    platform: "youtube_shorts",
    duration: 15,
    tags: ["ai-video", "seedance", "brand", "brand_campaign"],
  },
  {
    filename: REAL_VIDEOS.recycle,
    path: "/portfolio/" + REAL_VIDEOS.recycle,
    size: 1173601,
    type: "video",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Generated Video — Eco Mission",
    platform: "instagram",
    duration: 14,
    tags: ["ai-video", "seedance", "sustainability", "brand_campaign"],
  },
  {
    filename: REAL_IMAGES.thumb1,
    path: "/portfolio/" + REAL_IMAGES.thumb1,
    size: 2100661,
    type: "image",
    created: Math.floor(Date.now() / 1000) - 86400 * 3,
    label: "AI Thumbnail — TikTok Style",
    platform: "tiktok",
    tags: ["ai-image", "thumbnail", "viral", "product_direct"],
  },
  {
    filename: REAL_IMAGES.thumb2,
    path: "/portfolio/" + REAL_IMAGES.thumb2,
    size: 1820675,
    type: "image",
    created: Math.floor(Date.now() / 1000) - 86400 * 3,
    label: "AI Thumbnail — Facebook Style",
    platform: "facebook",
    tags: ["ai-image", "thumbnail", "social-proof", "product_direct"],
  },
  {
    filename: REAL_IMAGES.thumb3,
    path: "/portfolio/" + REAL_IMAGES.thumb3,
    size: 1467295,
    type: "image",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Thumbnail — YouTube Style",
    platform: "youtube_shorts",
    tags: ["ai-image", "thumbnail", "emotional", "brand_campaign"],
  },
  {
    filename: REAL_IMAGES.thumb2alt,
    path: "/portfolio/" + REAL_IMAGES.thumb2alt,
    size: 1780474,
    type: "image",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Thumbnail — Alternate Style",
    platform: "instagram",
    tags: ["ai-image", "thumbnail", "aesthetic", "brand_campaign"],
  },
  {
    filename: REAL_IMAGES.kf1a,
    path: "/portfolio/" + REAL_IMAGES.kf1a,
    size: 2082032,
    type: "image",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Keyframe — Scene 1A",
    platform: "tiktok",
    tags: ["ai-image", "keyframe", "storyboard", "product_direct"],
  },
  {
    filename: REAL_IMAGES.kf1b,
    path: "/portfolio/" + REAL_IMAGES.kf1b,
    size: 1640604,
    type: "image",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Keyframe — Scene 1B",
    platform: "tiktok",
    tags: ["ai-image", "keyframe", "storyboard", "product_direct"],
  },
  {
    filename: REAL_IMAGES.kf2a,
    path: "/portfolio/" + REAL_IMAGES.kf2a,
    size: 2000217,
    type: "image",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Keyframe — Scene 2A",
    platform: "facebook",
    tags: ["ai-image", "keyframe", "storyboard", "product_direct"],
  },
  {
    filename: REAL_IMAGES.kf2b,
    path: "/portfolio/" + REAL_IMAGES.kf2b,
    size: 1584075,
    type: "image",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Keyframe — Scene 2B",
    platform: "facebook",
    tags: ["ai-image", "keyframe", "storyboard", "product_direct"],
  },
  {
    filename: REAL_IMAGES.kf3,
    path: "/portfolio/" + REAL_IMAGES.kf3,
    size: 1880922,
    type: "image",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Keyframe — Scene 3",
    platform: "youtube_shorts",
    tags: ["ai-image", "keyframe", "storyboard", "brand_campaign"],
  },
  {
    filename: REAL_IMAGES.kf1c,
    path: "/portfolio/" + REAL_IMAGES.kf1c,
    size: 1955382,
    type: "image",
    created: Math.floor(Date.now() / 1000) - 86400 * 2,
    label: "AI Keyframe — Scene 1C",
    platform: "tiktok",
    tags: ["ai-image", "keyframe", "storyboard", "product_direct"],
  },
];

// ── Demo Brand Packages ──

export const DEMO_BRAND_PACKAGES = [
  {
    package_id: "bp-demo-001",
    name: "Lute Smart Breast Pump — Brand Kit",
    description: "Complete brand identity and creative assets for Lute wearable breast pump product line. Includes product shots, lifestyle imagery, brand guidelines, and campaign templates.",
    brand_name: "Lute",
    guidelines: "Brand Voice: Empowering, modern, supportive. Primary Color: #7CB342. Tagline: 'Pump anywhere. Live everywhere.' Tone should feel like a trusted friend who understands the challenges of modern motherhood.",
    created_at: new Date(Date.now() - 86400 * 7 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 86400 * 2 * 1000).toISOString(),
    logo_url: "",
    primary_color: "#7CB342",
    secondary_color: "#4CAF50",
    assets: [
      "/portfolio/" + REAL_VIDEOS.office,
      "/portfolio/" + REAL_VIDEOS.park,
      "/portfolio/" + REAL_IMAGES.thumb1,
      "/portfolio/" + REAL_IMAGES.thumb2,
      "/portfolio/" + REAL_IMAGES.kf1a,
    ],
  },
  {
    package_id: "bp-demo-002",
    name: "Lute Eco Pump — Sustainability Campaign",
    description: "Earth Day themed brand package highlighting Lute's commitment to sustainability. Features recycling program visuals, eco-friendly packaging shots, and founder story content.",
    brand_name: "Lute",
    guidelines: "Brand Voice: Authentic, mission-driven, warm. Primary Color: #4CAF50. Tagline: 'Pump for your baby. Protect their planet.' Emphasize transparency and genuine care for both mothers and the environment.",
    created_at: new Date(Date.now() - 86400 * 5 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 86400 * 1000).toISOString(),
    logo_url: "",
    primary_color: "#4CAF50",
    secondary_color: "#8BC34A",
    assets: [
      "/portfolio/" + REAL_VIDEOS.story,
      "/portfolio/" + REAL_VIDEOS.recycle,
      "/portfolio/" + REAL_VIDEOS.product,
      "/portfolio/" + REAL_IMAGES.thumb3,
      "/portfolio/" + REAL_IMAGES.kf3,
    ],
  },
  {
    package_id: "bp-demo-003",
    name: "Momcozy Trunk Organizer — Product Launch",
    description: "Car trunk organizer product launch package. Focus on convenience, organization, and family travel lifestyle. Includes product demonstration shots and use-case scenarios.",
    brand_name: "Momcozy",
    guidelines: "Brand Voice: Practical, family-focused, reliable. Highlight problem-solution narrative. Show real family moments in cars, road trips, and daily routines.",
    created_at: new Date(Date.now() - 86400 * 3 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 86400 * 1000).toISOString(),
    logo_url: "",
    primary_color: "#FF6B6B",
    secondary_color: "#FFE66D",
    assets: [],
  },
];

// ── Demo Influencers ──

export const DEMO_INFLUENCERS = [
  {
    influencer_id: "inf-demo-001",
    name: "Sarah Chen",
    handle: "sarahmomlife",
    platforms: ["tiktok", "instagram"],
    style_tags: ["unboxing", "review", "lifestyle"],
    notes: "Top performer for product_direct campaigns. Strong conversion on母婴 content.",
    is_active: true,
    created_at: new Date(Date.now() - 86400 * 30 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 86400 * 2 * 1000).toISOString(),
  },
  {
    influencer_id: "inf-demo-002",
    name: "Emily Johnson",
    handle: "emilyecofamily",
    platforms: ["youtube", "instagram"],
    style_tags: ["sustainability", "family-vlog", "tutorial"],
    notes: "Great fit for brand_campaign and eco-focused content. Authentic storytelling style.",
    is_active: true,
    created_at: new Date(Date.now() - 86400 * 20 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 86400 * 1 * 1000).toISOString(),
  },
  {
    influencer_id: "inf-demo-003",
    name: "Lisa Wang",
    handle: "lisatechmom",
    platforms: ["tiktok", "youtube_shorts"],
    style_tags: ["tech-review", "product-demo", "comparison"],
    notes: "Strong tech-savvy audience. Best for detailed product comparisons and feature highlights.",
    is_active: true,
    created_at: new Date(Date.now() - 86400 * 15 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 86400 * 3 * 1000).toISOString(),
  },
  {
    influencer_id: "inf-demo-004",
    name: "Jessica Miller",
    handle: "jessicamumtips",
    platforms: ["facebook", "instagram"],
    style_tags: ["parenting-tips", "testimonial", "daily-life"],
    notes: "Warm, relatable content. Excellent engagement rates on Facebook.",
    is_active: false,
    created_at: new Date(Date.now() - 86400 * 45 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 86400 * 10 * 1000).toISOString(),
  },
];

// ── Demo Footage Assets (same as DEMO_ASSETS but in footage-page format) ──

export const DEMO_FOOTAGE_ASSETS = DEMO_ASSETS.map((a, i) => ({
  asset_id: `demo-asset-${String(i + 1).padStart(3, "0")}`,
  filename: a.filename,
  original_name: a.label + " (" + a.filename + ")",
  file_path: a.path,
  file_size: a.size,
  mime_type: a.type === "video" ? "video/mp4" : a.type === "image" ? "image/png" : "application/octet-stream",
  tags: a.tags,
  metadata: {
    uploaded_at: new Date(a.created * 1000).toISOString(),
    platform: a.platform,
    duration: a.duration || 0,
    label: a.label,
  },
}));

// ═══ 品牌VLOG Mock 数据 ═══

export const VLOG_BRANDS: { id: string; name: string; tone: string; products: ProductSku[] }[] = [
  {
    id: "momcozy", name: "Momcozy", tone: "温柔真实的母婴家庭叙事",
    products: [
      {
        id: "m5", name: "M5 Wearable Breast Pump", shortName: "M5 Breast Pump",
        description: "主打免手扶、静音、轻量通勤，适合家庭和职场多场景切换。",
        tags: ["免手扶", "静音", "轻量通勤", "母婴场景"],
        views: [
          { label: "主视图", title: "Hero Angle", description: "正面展示杯体与佩戴形态", usage_note: "用于首屏封面和品牌主镜头", color: "#7f3dff" },
          { label: "45度视图", title: "Dynamic Angle", description: "突出轮廓和材质细节", usage_note: "适合和人物佩戴场景衔接", color: "#5b8cff" },
          { label: "侧视图", title: "Slim Profile", description: "展示轻薄弧线和贴合度", usage_note: "适合强调隐形与舒适卖点", color: "#02b96b" },
          { label: "背视图", title: "Back Detail", description: "展示结构与固定方式", usage_note: "用于解释佩戴稳定性和支撑感", color: "#ff8a34" },
          { label: "细节视图", title: "Material Close-up", description: "突出亲肤材质和工艺细节", usage_note: "适合插入局部材质和按钮特写", color: "#ff5c7a" },
          { label: "包装视图", title: "Packaging View", description: "强化套装完整度和礼盒感", usage_note: "适合作为收尾展示和购买引导", color: "#00b8d9" },
        ],
      },
    ],
  },
];

export const VLOG_MODELS: ModelProfile[] = [
  { id: "model-mom", name: "Ava", role: "母亲", description: "温柔母婴场景，适合哺乳器和居家内容", gradient: ["#ff7eb3", "#7f3dff"] },
  { id: "model-dad", name: "Liam", role: "父亲", description: "家庭陪伴和户外亲子场景", gradient: ["#2f80ed", "#56ccf2"] },
  { id: "model-baby", name: "Noah", role: "婴儿", description: "用于补充亲子互动和安睡镜头", gradient: ["#f6c667", "#f58b54"] },
  { id: "model-parent", name: "Emma", role: "孕妈", description: "适合孕产和母婴生活方式内容", gradient: ["#8e54e9", "#4776e6"] },
  { id: "model-caregiver", name: "Sophia", role: "护理师", description: "适合专业演示、护理流程和安全感表达", gradient: ["#02b96b", "#18c6a3"] },
  { id: "model-couple", name: "Mia & Jack", role: "父母双人", description: "适合家庭合拍和双人互动镜头", gradient: ["#ff5c7a", "#ffb347"] },
];

export const VLOG_SCENES = [
  { id: "office", name: "职场", desc: "突出高效与通勤节奏" },
  { id: "living-room", name: "客厅", desc: "轻松陪伴和家庭氛围" },
  { id: "bedroom", name: "卧室", desc: "安静、亲密、睡前场景" },
  { id: "nursery", name: "儿童房", desc: "亲子布景和成长陪伴" },
  { id: "outdoor", name: "户外", desc: "日常出行与生活方式" },
  { id: "kitchen", name: "厨房", desc: "高效家务和台面操作" },
];

export const VLOG_DURATION_OPTIONS = [
  { id: "5-15", label: "5-15s", note: "超短", seconds: 15 },
  { id: "15-30", label: "15-30s", note: "标准", seconds: 30 },
  { id: "30-45", label: "30-45s", note: "加长", seconds: 45 },
  { id: "45-60", label: "45-60s", note: "中长", seconds: 60 },
  { id: "60-90", label: "60-90s", note: "长片", seconds: 90 },
];

// ═══ 会说话的 UI 2.0 — 视频类型定义（纵轴）═══

export const SCENE_VIDEO_TYPES: Record<string, VideoType[]> = {
  brand_campaign: [
    { id: "brand_image", name: "品牌形象片", desc: "传递品牌调性和价值观" },
    { id: "product_seed", name: "产品种草", desc: "聚焦单品的卖点展示" },
    { id: "unbox_review", name: "开箱测评", desc: "真实开箱体验分享" },
    { id: "scene_narrative", name: "场景叙事", desc: "用故事包裹品牌信息" },
    { id: "comparison", name: "对比评测", desc: "与竞品横向对比" },
    { id: "event_promo", name: "活动宣发", desc: "限时活动与促销信息" },
  ],
  product_direct: [
    { id: "product_explain", name: "产品解说", desc: "清晰讲解产品功能" },
    { id: "usp_demo", name: "卖点演示", desc: "核心卖点可视化呈现" },
    { id: "spec_intro", name: "参数介绍", desc: "技术参数权威解读" },
    { id: "compare_show", name: "对比展示", desc: "使用前vs使用后" },
  ],
  influencer_remix: [
    { id: "employee_kol", name: "员工KOL二创", desc: "内部创作者IP输出" },
    { id: "civilian_review", name: "素人测评", desc: "真实用户口碑分享" },
    { id: "influencer_sales", name: "达人带货", desc: "签约网红分销内容" },
    { id: "ugc_mix", name: "UGC混剪", desc: "用户内容二次创作" },
  ],
  live_shoot_to_video: [
    { id: "store_live", name: "门店实拍", desc: "线下门店真实记录" },
    { id: "user_ugc", name: "用户UGC", desc: "用户生成内容收集" },
    { id: "event_record", name: "活动记录", desc: "品牌活动现场素材" },
    { id: "product_shoot", name: "产品拍摄", desc: "专业产品实拍素材" },
  ],
  brand_vlog: [
    { id: "product_experience", name: "产品体验", desc: "日常使用真实记录" },
    { id: "parent_child", name: "亲子日常", desc: "家庭生活温馨片段" },
    { id: "home_scene", name: "家居场景", desc: "居家生活方式展示" },
    { id: "travel_record", name: "出行记录", desc: "外出使用场景记录" },
  ],
  fast_mode: [
    { id: "quick_test", name: "快速测试", desc: "10秒验证视频生成" },
    { id: "idea_verify", name: "灵感验证", desc: "快速验证创意方向" },
  ],
};

// ═══ 会说话的 UI 2.0 — 引导卡片序列（6 场景 × 视频类型）═══

export const GUIDED_CARD_SEQUENCES: CardSequence[] = [
  // ── 4.1 品牌宣传片 → 品牌形象片 ──
  {
    scene: "brand_campaign",
    videoType: "brand_image",
    cards: [
      {
        priority: "required",
        stepName: "定主角",
        stepIcon: "🎯",
        question: "你的品牌叫什么？",
        reason: "品牌名是视频的锚点，所有视觉和叙事都围绕它展开。",
        connectionText: "",
        fieldKey: "brand_name",
        inputType: "text",
        placeholder: "例如：Momcozy",
      },
      {
        priority: "required",
        stepName: "找冲突",
        stepIcon: "💡",
        question: "这次宣传片的核心信息是什么？",
        reason: "核心信息决定了视频的叙事主线和情绪走向。",
        connectionText: "品牌定了，给视频清晰的目标",
        fieldKey: "campaign_theme",
        inputType: "text",
        placeholder: "例如：10周年，致每一位妈妈的陪伴",
      },
      {
        priority: "recommended",
        stepName: "定调性",
        stepIcon: "🎨",
        question: "你的品牌主张什么？",
        reason: "价值观决定镜头情绪温度——温暖、科技感还是活力？",
        connectionText: "价值观决定镜头情绪温度",
        fieldKey: "brand_values",
        inputType: "textarea",
        placeholder: "例如：为妈妈的舒适不断进化",
      },
      {
        priority: "recommended",
        stepName: "选舞台",
        stepIcon: "🎬",
        question: "谁会看到这个宣传片？",
        reason: "受众决定画面场景和语言风格。",
        connectionText: "受众决定画面场景",
        fieldKey: "target_audience",
        inputType: "text",
        placeholder: "例如：25-35岁新手妈妈",
      },
      {
        priority: "optional",
        stepName: "找差异",
        stepIcon: "🔍",
        question: "有没有参考风格？",
        reason: "参考风格让 AI 更懂你的审美偏好。",
        connectionText: "让 AI 更懂你的审美",
        fieldKey: "visual_identity",
        inputType: "textarea",
        placeholder: "例如：Apple 广告风格，极简明亮",
      },
      {
        priority: "optional",
        stepName: "补充",
        stepIcon: "📎",
        question: "有没有可以参考的素材？",
        reason: "参考素材让风格更精准，减少返工。",
        connectionText: "参考素材让风格更精准",
        fieldKey: "reference_assets",
        inputType: "image-upload",
      },
    ],
  },

  // ── 4.2 商品直拍 → 产品解说 ──
  {
    scene: "product_direct",
    videoType: "product_explain",
    cards: [
      {
        priority: "required",
        stepName: "定主角",
        stepIcon: "🎯",
        question: "你要拍什么产品？",
        reason: "产品是视频的主角，名称决定了 AI 对产品的理解起点。",
        connectionText: "",
        fieldKey: "product_name",
        inputType: "text",
        placeholder: "例如：M5 免手扶吸奶器",
      },
      {
        priority: "required",
        stepName: "找冲突",
        stepIcon: "💡",
        question: "这个产品好在哪？",
        reason: "卖点是视频的骨架，每个镜头都在证明它。",
        connectionText: "卖点是视频的骨架",
        fieldKey: "key_features",
        inputType: "textarea",
        placeholder: "每行一个卖点，例如：\n免手扶，直接放入内衣\n静音设计，办公室也可用\nAPP 智能记录奶量",
      },
      {
        priority: "recommended",
        stepName: "定调性",
        stepIcon: "🎨",
        question: "产品在什么场合用？",
        reason: "场景决定拍摄环境和氛围——居家温馨还是职场高效？",
        connectionText: "场景决定拍摄环境",
        fieldKey: "usage_scenario",
        inputType: "textarea",
        placeholder: "例如：产后妈妈居家使用、通勤路上、办公室午休",
      },
      {
        priority: "recommended",
        stepName: "选舞台",
        stepIcon: "🎬",
        question: "用什么语气介绍？",
        reason: "语气决定旁白感觉——亲切闺蜜还是专业顾问？",
        connectionText: "语气决定旁白感觉",
        fieldKey: "brand_voice",
        inputType: "textarea",
        placeholder: "例如：温暖、专业、像闺蜜一样分享",
      },
      {
        priority: "optional",
        stepName: "找差异",
        stepIcon: "🔍",
        question: "有没有竞品可以对比？",
        reason: "竞品是你的差异化坐标，帮助 AI 突出独特优势。",
        connectionText: "竞品是你的差异化坐标",
        fieldKey: "competitor_context",
        inputType: "textarea",
        placeholder: "例如：比美德乐更静音、比贝瑞克更便携",
      },
      {
        priority: "optional",
        stepName: "补充",
        stepIcon: "📎",
        question: "有没有参考素材？",
        reason: "上传竞品视频作风格参考，让输出更贴近预期。",
        connectionText: "上传竞品视频作风格参考",
        fieldKey: "reference_assets",
        inputType: "video-upload",
      },
    ],
  },

  // ── 4.3 网红二创 → 员工KOL二创 ──
  {
    scene: "influencer_remix",
    videoType: "employee_kol",
    cards: [
      {
        priority: "required",
        stepName: "定主角",
        stepIcon: "🎯",
        question: "原始视频在哪？",
        reason: "原始素材是二创的根基，决定了可使用的画面和节奏。",
        connectionText: "",
        fieldKey: "video_url",
        inputType: "text",
        placeholder: "粘贴视频链接，或上传本地文件",
      },
      {
        priority: "required",
        stepName: "找冲突",
        stepIcon: "💡",
        question: "要关联什么产品？",
        reason: "产品是链接的关键——视频必须自然引出购买转化。",
        connectionText: "产品是链接的关键",
        fieldKey: "product_name",
        inputType: "text",
        placeholder: "例如：M5 免手扶吸奶器",
      },
      {
        priority: "recommended",
        stepName: "定调性",
        stepIcon: "🎨",
        question: "创作者是谁？",
        reason: "创作者身份影响分发策略和受众预期。",
        connectionText: "标签影响分发策略",
        fieldKey: "influencer_name",
        inputType: "text",
        placeholder: "例如：品牌官方账号 / 签约达人名称",
      },
      {
        priority: "recommended",
        stepName: "选舞台",
        stepIcon: "🎬",
        question: "保留原声还是 AI 配音？",
        reason: "音频决定观感——原声真实，AI 配音统一品牌调性。",
        connectionText: "音频决定观感",
        fieldKey: "keep_original_audio",
        inputType: "toggle",
      },
      {
        priority: "optional",
        stepName: "补充",
        stepIcon: "📎",
        question: "有没有补充图片或音效？",
        reason: "补充素材丰富二创细节，提升完成度。",
        connectionText: "补充素材丰富二创细节",
        fieldKey: "reference_assets",
        inputType: "image-upload",
      },
    ],
  },

  // ── 4.4 实拍素材生成 → 门店实拍 ──
  {
    scene: "live_shoot_to_video",
    videoType: "store_live",
    cards: [
      {
        priority: "required",
        stepName: "定主角",
        stepIcon: "🎯",
        question: "上传你的实拍片段",
        reason: "实拍素材是视频的灵魂，AI 在此基础上进行剪辑和增强。",
        connectionText: "",
        fieldKey: "footage_assets",
        inputType: "video-upload",
      },
      {
        priority: "required",
        stepName: "找冲突",
        stepIcon: "💡",
        question: "素材里展示的是什么产品？",
        reason: "产品给 AI 上下文，帮助理解素材的叙事方向。",
        connectionText: "产品给 AI 上下文",
        fieldKey: "product_name",
        inputType: "text",
        placeholder: "例如：M5 免手扶吸奶器",
      },
      {
        priority: "recommended",
        stepName: "定调性",
        stepIcon: "🎨",
        question: "这条视频想表达什么？",
        reason: "主题聚拢素材叙事，避免内容散漫。",
        connectionText: "主题聚拢素材叙事",
        fieldKey: "topic",
        inputType: "text",
        placeholder: "例如：真实用户的使用体验分享",
      },
      {
        priority: "optional",
        stepName: "补充",
        stepIcon: "📎",
        question: "要不要加背景音乐或配音？",
        reason: "音频增强完成度，让视频更像专业制作。",
        connectionText: "音频增强完成度",
        fieldKey: "reference_assets",
        inputType: "image-upload",
      },
    ],
  },

  // ── 4.5 品牌VLOG → 产品体验 ──
  {
    scene: "brand_vlog",
    videoType: "product_experience",
    cards: [
      {
        priority: "required",
        stepName: "定主角",
        stepIcon: "🎯",
        question: "品牌是什么？",
        reason: "品牌是 VLOG 的灵魂，决定了整体的调性和叙事风格。",
        connectionText: "",
        fieldKey: "brand_id",
        inputType: "select",
        options: ["momcozy"],
      },
      {
        priority: "required",
        stepName: "找冲突",
        stepIcon: "💡",
        question: "上传 6 张产品角度图",
        reason: "六视图让 AI 精确理解产品外观，生成更准确的镜头。",
        connectionText: "六视图让 AI 精确理解产品",
        fieldKey: "product_views",
        inputType: "image-upload",
      },
      {
        priority: "required",
        stepName: "定调性",
        stepIcon: "🎨",
        question: "故事发生在哪里？",
        reason: "场景是 VLOG 的舞台，决定了氛围和光线。",
        connectionText: "场景是 VLOG 的舞台",
        fieldKey: "scene_id",
        inputType: "select",
        options: ["office", "living-room", "bedroom", "nursery", "outdoor", "kitchen"],
      },
      {
        priority: "required",
        stepName: "选舞台",
        stepIcon: "🎬",
        question: "谁来出镜？",
        reason: "人物是情感载体，观众通过他们产生共鸣。",
        connectionText: "人物是情感载体",
        fieldKey: "selected_models",
        inputType: "multiselect",
        options: ["model-mom", "model-dad", "model-baby", "model-parent", "model-caregiver", "model-couple"],
      },
      {
        priority: "recommended",
        stepName: "找差异",
        stepIcon: "🔍",
        question: "讲什么故事？",
        reason: "故事把卖点变成生活片段，让观众自然接受信息。",
        connectionText: "故事把卖点变成生活片段",
        fieldKey: "story_description",
        inputType: "textarea",
        placeholder: "例如：年轻母亲在客厅使用产品，穿插婴儿安静入睡的镜头...",
        maxLength: 300,
      },
      {
        priority: "recommended",
        stepName: "补充",
        stepIcon: "📎",
        question: "故事讲多久？",
        reason: "时长决定镜头数量和叙事密度。",
        connectionText: "时长决定镜头数量",
        fieldKey: "video_duration",
        inputType: "duration",
      },
      {
        priority: "optional",
        stepName: "参考",
        stepIcon: "📎",
        question: "有没有补充参考？",
        reason: "风格参考提升一致感，让输出更符合品牌调性。",
        connectionText: "风格参考提升一致感",
        fieldKey: "reference_assets",
        inputType: "image-upload",
      },
    ],
  },

  // ── 4.6 快速模式（无卡片，占位）──
  {
    scene: "fast_mode",
    videoType: "quick_test",
    cards: [],
  },
];

// ═══ 会说话的 UI 2.0 — 快捷模板预设 ═══

export const TEMPLATE_PRESETS: TemplatePreset[] = [
  {
    id: "momcozy-brand-image",
    name: "Momcozy M5 品牌形象片",
    nameEn: "Momcozy M5 Brand Image Film",
    scene: "brand_campaign",
    videoType: "brand_image",
    values: {
      brand_name: "Momcozy",
      campaign_theme: "为妈妈的舒适不断进化",
      brand_values: "温柔、真实、陪伴每一位妈妈",
      target_audience: "25-35岁新手妈妈，职场与家庭兼顾",
      visual_identity: "温暖自然光，居家场景，柔和色调",
    },
  },
  {
    id: "momcozy-product-seed",
    name: "Momcozy M5 产品种草",
    nameEn: "Momcozy M5 Product Seed",
    scene: "product_direct",
    videoType: "product_explain",
    values: {
      product_name: "Momcozy M5 免手扶吸奶器",
      key_features: "免手扶，直接放入内衣\n静音设计，办公室也可用\nAPP 智能记录奶量\n轻量便携，通勤无负担",
      usage_scenario: "产后妈妈居家使用、通勤路上、办公室午休",
      brand_voice: "温暖、专业、像闺蜜一样分享",
      competitor_context: "比美德乐更静音、比贝瑞克更便携",
    },
  },
  {
    id: "blank",
    name: "空白开始",
    nameEn: "Start from Blank",
    scene: "product_direct",
    videoType: "product_explain",
    values: {},
  },
];
