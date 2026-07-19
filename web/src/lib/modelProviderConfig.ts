export const PROVIDER_API_KEY_NAMES = [
  "DEEPSEEK_API_KEY",
  "POYO_API_KEY",
  "SILICONFLOW_API_KEY",
  "SEEDANCE_API_KEY",
  "OPENAI_API_KEY",
  "ANTHROPIC_API_KEY",
  "ELEVENLABS_API_KEY",
] as const;

export type ProviderApiKeyName = (typeof PROVIDER_API_KEY_NAMES)[number];

export type ProviderRouteStatus = "production" | "fallback" | "candidate" | "legacy";

export type ProviderKeySpec = {
  envName: ProviderApiKeyName;
  provider: string;
  scope: string;
  status: ProviderRouteStatus;
  requiredForProduction?: boolean;
};

export type ModelRouteSpec = {
  provider: string;
  role: string;
  status: ProviderRouteStatus;
  keyEnv: ProviderApiKeyName;
  baseEnv?: string;
  modelEnv?: string;
  currentDefault: string;
  candidateModels: string[];
  note?: string;
};

export type ModelRouteGroup = {
  id: "text" | "image" | "video" | "voice" | "music";
  title: string;
  routes: ModelRouteSpec[];
};

export const REQUEST_PROVIDER_API_KEY_NAMES: ProviderApiKeyName[] = [
  "DEEPSEEK_API_KEY",
  "POYO_API_KEY",
  "SILICONFLOW_API_KEY",
  "SEEDANCE_API_KEY",
  "OPENAI_API_KEY",
  "ANTHROPIC_API_KEY",
  "ELEVENLABS_API_KEY",
];

export const PROVIDER_KEY_SPECS: ProviderKeySpec[] = [
  {
    envName: "DEEPSEEK_API_KEY",
    provider: "DeepSeek",
    scope: "Text reasoning / script / strategy",
    status: "production",
    requiredForProduction: true,
  },
  {
    envName: "POYO_API_KEY",
    provider: "poyo.ai",
    scope: "Image, video, and poyo music/TTS proxy",
    status: "production",
    requiredForProduction: true,
  },
  {
    envName: "SILICONFLOW_API_KEY",
    provider: "SiliconFlow CosyVoice",
    scope: "Voiceover and TTS",
    status: "production",
    requiredForProduction: true,
  },
  {
    envName: "SEEDANCE_API_KEY",
    provider: "Seedance native",
    scope: "Native video backend fallback",
    status: "fallback",
  },
  {
    envName: "OPENAI_API_KEY",
    provider: "OpenAI compatible",
    scope: "OpenAI fallback, Kimi compatible route, image fallback",
    status: "fallback",
  },
  {
    envName: "ANTHROPIC_API_KEY",
    provider: "Anthropic Claude",
    scope: "Text reasoning fallback",
    status: "candidate",
  },
  {
    envName: "ELEVENLABS_API_KEY",
    provider: "ElevenLabs",
    scope: "Legacy TTS fallback",
    status: "legacy",
  },
];

export const MODEL_ROUTE_GROUPS: ModelRouteGroup[] = [
  {
    id: "text",
    title: "Text reasoning",
    routes: [
      {
        provider: "DeepSeek",
        role: "Production default",
        status: "production",
        keyEnv: "DEEPSEEK_API_KEY",
        baseEnv: "DEEPSEEK_API_BASE",
        modelEnv: "DEEPSEEK_MODEL",
        currentDefault: "deepseek-v4-pro",
        candidateModels: ["deepseek-v4-pro", "deepseek-v4-flash"],
      },
      {
        provider: "OpenAI",
        role: "OpenAI-compatible fallback",
        status: "fallback",
        keyEnv: "OPENAI_API_KEY",
        currentDefault: "gpt-4o",
        candidateModels: ["gpt-4o", "gpt-4.1", "o-series reasoning"],
      },
      {
        provider: "Anthropic Claude",
        role: "Text reasoning candidate",
        status: "candidate",
        keyEnv: "ANTHROPIC_API_KEY",
        currentDefault: "claude-sonnet-4-20250514",
        candidateModels: ["claude-sonnet-4-20250514"],
      },
      {
        provider: "Kimi / Moonshot",
        role: "OpenAI-compatible text candidate",
        status: "candidate",
        keyEnv: "OPENAI_API_KEY",
        baseEnv: "https://api.moonshot.cn/v1",
        modelEnv: "KIMI_MODEL",
        currentDefault: "kimi-k2-0905-preview",
        candidateModels: ["kimi-k2-0905-preview"],
        note: "Current backend maps Kimi through the OpenAI-compatible key slot.",
      },
    ],
  },
  {
    id: "image",
    title: "Image generation",
    routes: [
      {
        provider: "poyo.ai GPT Image",
        role: "Production image route",
        status: "production",
        keyEnv: "POYO_API_KEY",
        baseEnv: "POYO_API_BASE_URL",
        modelEnv: "POYO_IMAGE_MODEL",
        currentDefault: "gpt-image-2",
        candidateModels: ["gpt-image-2", "gpt-image-1", "gpt-4o-image", "seedream"],
      },
      {
        provider: "OpenAI image",
        role: "Native fallback",
        status: "fallback",
        keyEnv: "OPENAI_API_KEY",
        currentDefault: "native OpenAI image",
        candidateModels: ["gpt-image-1", "dall-e-3"],
      },
    ],
  },
  {
    id: "video",
    title: "Video generation",
    routes: [
      {
        provider: "poyo.ai Seedance",
        role: "Production video route",
        status: "production",
        keyEnv: "POYO_API_KEY",
        baseEnv: "POYO_API_BASE_URL",
        modelEnv: "POYO_VIDEO_MODEL",
        currentDefault: "seedance-2",
        candidateModels: ["seedance-2", "seedance-2.0"],
      },
      {
        provider: "Seedance native",
        role: "Native fallback",
        status: "fallback",
        keyEnv: "SEEDANCE_API_KEY",
        baseEnv: "SEEDANCE_API_BASE_URL",
        currentDefault: "native Seedance",
        candidateModels: ["seedance-2.0"],
      },
    ],
  },
  {
    id: "voice",
    title: "Voice and TTS",
    routes: [
      {
        provider: "SiliconFlow CosyVoice",
        role: "Production voice route",
        status: "production",
        keyEnv: "SILICONFLOW_API_KEY",
        baseEnv: "SILICONFLOW_API_BASE",
        modelEnv: "COSYVOICE_MODEL",
        currentDefault: "FunAudioLLM/CosyVoice2-0.5B",
        candidateModels: ["FunAudioLLM/CosyVoice2-0.5B"],
      },
      {
        provider: "ElevenLabs",
        role: "Legacy voice fallback",
        status: "legacy",
        keyEnv: "ELEVENLABS_API_KEY",
        currentDefault: "eleven_multilingual_v2",
        candidateModels: ["eleven_multilingual_v2"],
      },
    ],
  },
  {
    id: "music",
    title: "Music and audio",
    routes: [
      {
        provider: "poyo.ai music",
        role: "Planned toolbox route",
        status: "candidate",
        keyEnv: "POYO_API_KEY",
        modelEnv: "POYO_TTS_MODEL",
        currentDefault: "generate-music",
        candidateModels: ["generate-music", "ai-music", "extend-music"],
      },
    ],
  },
];
