/**
 * Demo mock data for static GitHub Pages deployment.
 * Used when no backend API is available.
 */

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
    clip_paths: ["/api/media/clip_office_demo.mp4", "/api/media/clip_park_demo.mp4"],
    clip_details: [
      {
        path: "/api/media/clip_office_demo.mp4",
        duration: 14.5,
        is_stub: true,
        file_size: 2840000,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Cinematic lifestyle shot of a professional working mother...",
        continuity_frame: false,
      },
      {
        path: "/api/media/clip_park_demo.mp4",
        duration: 13.2,
        is_stub: true,
        file_size: 2560000,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Split-screen comparison: stressed mother vs confident mother...",
        continuity_frame: true,
      },
    ],
    total_duration: 27.7,
    target_duration: 30,
  },
  clip_paths: ["/api/media/clip_office_demo.mp4", "/api/media/clip_park_demo.mp4"],
  audio_paths: ["/api/media/audio_demo_track.mp3"],
  lyrics_paths: [],
  thumbnail_image_paths: ["/api/media/thumb_tiktok_demo.png", "/api/media/thumb_fb_demo.png"],
  final_video_path: "/api/media/final_demo_video.mp4",
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
      { name: "Duration Target", status: "WARN", score: 0.75, feedback: "27.7s vs 30s target — slightly under" },
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
    clip_paths: ["/api/media/clip_story_demo.mp4", "/api/media/clip_recycle_demo.mp4", "/api/media/clip_product_demo.mp4"],
    clip_details: [
      {
        path: "/api/media/clip_story_demo.mp4",
        duration: 14.8,
        is_stub: true,
        file_size: 3200000,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Emotional documentary-style scene: a young professional mother...",
        continuity_frame: false,
      },
      {
        path: "/api/media/clip_recycle_demo.mp4",
        duration: 15.2,
        is_stub: true,
        file_size: 3100000,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Aerial drone shot of a modern recycling facility...",
        continuity_frame: true,
      },
      {
        path: "/api/media/clip_product_demo.mp4",
        duration: 14.0,
        is_stub: true,
        file_size: 2950000,
        verification: { all_ok: true, file_exists: true, size_ok: true, header_ok: true, duration_ok: true },
        prompt_used: "Clean white cyclorama. Pump rotating on turntable...",
        continuity_frame: true,
        is_filler: true,
      },
    ],
    total_duration: 44.0,
    target_duration: 45,
  },
  clip_paths: ["/api/media/clip_story_demo.mp4", "/api/media/clip_recycle_demo.mp4", "/api/media/clip_product_demo.mp4"],
  audio_paths: ["/api/media/audio_brand_demo.mp3"],
  lyrics_paths: [],
  thumbnail_image_paths: ["/api/media/thumb_yt_demo.png", "/api/media/thumb_ig_demo.png"],
  final_video_path: "/api/media/final_brand_demo.mp4",
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
      { name: "Duration Target", status: "PASS", score: 0.92, feedback: "44s vs 45s target — excellent pacing" },
      { name: "CTA Clarity", status: "PASS", score: 0.9, feedback: "Trial offer is compelling and clear" },
      { name: "Platform Fit", status: "PASS", score: 0.91, feedback: "Strong fit for YouTube and Instagram" },
    ],
  },
  steps_completed: 12,
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
