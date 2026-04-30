"use client";

import { useState } from "react";
import { Zap, Clock, Volume2, ChevronDown, ChevronUp, Copy, RotateCcw, Play, FileText, Cpu, Timer, HardDrive } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import { generateFastMode, getMediaUrl, type FastModeResult } from "./api";

export default function FastModePanel() {
  const { t } = useI18n();
  const [userPrompt, setUserPrompt] = useState("");
  const [duration, setDuration] = useState<10 | 15>(15);
  const [enableTTS, setEnableTTS] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FastModeResult | null>(null);
  const [error, setError] = useState("");
  const [showDebug, setShowDebug] = useState(false);
  const [copied, setCopied] = useState(false);

  async function handleGenerate() {
    if (!userPrompt.trim() || loading) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await generateFastMode({
        user_prompt: userPrompt.trim(),
        duration,
        enable_tts: enableTTS,
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  function handleCopyPrompt() {
    if (!result?.llm_prompt) return;
    navigator.clipboard.writeText(result.llm_prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatTime(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Header */}
      <div className="apple-card p-4">
        <div className="flex items-center gap-2 mb-2">
          <Zap size={20} className="text-[#FF6B35]" strokeWidth={1.5} />
          <h2 className="text-base font-semibold text-[#1d1d1f]">{t("fastMode.title")}</h2>
        </div>
        <p className="text-xs text-[#86868b]">{t("fastMode.subtitle")}</p>
      </div>

      {/* Input Panel */}
      <div className="apple-card p-4 space-y-4">
        {/* Text input */}
        <div>
          <label className="block text-[11px] font-semibold text-[#86868b] uppercase tracking-wider mb-1.5">
            {t("fastMode.title")}
          </label>
          <textarea
            value={userPrompt}
            onChange={(e) => setUserPrompt(e.target.value)}
            placeholder={t("fastMode.inputPlaceholder")}
            rows={4}
            className="w-full px-3 py-2 text-sm bg-[#f5f5f7] border border-[#e8e8ed] rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-[#FF6B35]/30 focus:border-[#FF6B35] transition-all"
          />
          <p className="text-[10px] text-[#aeaeb2] mt-1">{t("fastMode.inputHint")}</p>
        </div>

        {/* Duration selector */}
        <div>
          <label className="block text-[11px] font-semibold text-[#86868b] uppercase tracking-wider mb-1.5">
            <Clock size={12} className="inline mr-1" />
            {t("fastMode.duration")}
          </label>
          <div className="flex gap-2">
            {[10, 15].map((d) => (
              <button
                key={d}
                onClick={() => setDuration(d as 10 | 15)}
                className={`text-xs px-4 py-1.5 rounded-full font-medium transition-all cursor-pointer ${
                  duration === d
                    ? "bg-[#FF6B35] text-white"
                    : "bg-[#f5f5f7] text-[#86868b] hover:bg-[#e8e8ed]"
                }`}
              >
                {d === 10 ? t("fastMode.duration10s") : t("fastMode.duration15s")}
              </button>
            ))}
          </div>
        </div>

        {/* TTS toggle */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setEnableTTS(!enableTTS)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full transition-all cursor-pointer ${
              enableTTS
                ? "bg-[#7CB342]/10 text-[#7CB342] ring-1 ring-[#7CB342]/20"
                : "bg-[#f5f5f7] text-[#86868b] hover:bg-[#e8e8ed]"
            }`}
          >
            <Volume2 size={12} />
            {t("fastMode.enableTTS")}
          </button>
        </div>

        {/* Generate button */}
        <button
          onClick={handleGenerate}
          disabled={loading || !userPrompt.trim()}
          className="w-full apple-btn apple-btn-primary text-sm py-2.5 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          style={{ backgroundColor: "#FF6B35" }}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              {t("fastMode.generating")}
            </span>
          ) : (
            <span className="flex items-center justify-center gap-2">
              <Zap size={16} />
              {t("fastMode.generate")}
            </span>
          )}
        </button>

        {error && (
          <div className="text-xs text-[#ff453a] bg-[#ff453a]/5 px-3 py-2 rounded-lg">
            {error}
          </div>
        )}
      </div>

      {/* Result Panel */}
      {result && (
        <div className="apple-card p-4 space-y-4 animate-slide-up">
          <div className="flex items-center gap-2 mb-2">
            <Play size={18} className="text-[#7CB342]" strokeWidth={1.5} />
            <h3 className="text-sm font-semibold text-[#1d1d1f]">{t("fastMode.result.title")}</h3>
            {result.is_stub && (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#FF9500]/10 text-[#FF9500]">
                STUB
              </span>
            )}
          </div>

          {/* Video Player */}
          {result.video_url && (
            <div className="rounded-xl overflow-hidden bg-black">
              <video
                src={result.video_url}
                controls
                className="w-full max-h-[400px]"
                poster=""
              />
            </div>
          )}

          {/* Video info */}
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-[#f5f5f7] rounded-lg p-2 text-center">
              <Timer size={14} className="mx-auto mb-1 text-[#86868b]" />
              <p className="text-[10px] text-[#86868b]">{t("fastMode.result.generationTime")}</p>
              <p className="text-xs font-semibold text-[#1d1d1f]">{formatTime(result.generation_time_ms)}</p>
            </div>
            <div className="bg-[#f5f5f7] rounded-lg p-2 text-center">
              <HardDrive size={14} className="mx-auto mb-1 text-[#86868b]" />
              <p className="text-[10px] text-[#86868b]">{t("fastMode.result.videoInfo")}</p>
              <p className="text-xs font-semibold text-[#1d1d1f]">{formatBytes(result.file_size_bytes)}</p>
            </div>
            <div className="bg-[#f5f5f7] rounded-lg p-2 text-center">
              <Cpu size={14} className="mx-auto mb-1 text-[#86868b]" />
              <p className="text-[10px] text-[#86868b]">{t("fastMode.result.modelInfo")}</p>
              <p className="text-xs font-semibold text-[#1d1d1f]">{result.model_info.video}</p>
            </div>
          </div>

          {/* Timing breakdown */}
          <div className="text-[10px] text-[#86868b] flex gap-3">
            <span>LLM: {formatTime(result.timing.llm_ms)}</span>
            <span>Video: {formatTime(result.timing.video_ms)}</span>
            {result.timing.tts_ms > 0 && <span>TTS: {formatTime(result.timing.tts_ms)}</span>}
          </div>

          {/* Debug Info (collapsible) */}
          <div className="border border-[#e8e8ed] rounded-xl overflow-hidden">
            <button
              onClick={() => setShowDebug(!showDebug)}
              className="w-full flex items-center justify-between px-3 py-2 text-xs text-[#86868b] hover:bg-[#f5f5f7] transition-colors cursor-pointer"
            >
              <span className="flex items-center gap-1.5">
                <FileText size={12} />
                {t("fastMode.result.debugInfo")}
              </span>
              {showDebug ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {showDebug && (
              <div className="px-3 pb-3 space-y-3">
                {/* LLM Prompt */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-medium text-[#86868b]">{t("fastMode.result.llmPrompt")}</span>
                    <button
                      onClick={handleCopyPrompt}
                      className="text-[10px] flex items-center gap-1 text-[#FF6B35] hover:underline cursor-pointer"
                    >
                      <Copy size={10} />
                      {copied ? "Copied!" : t("fastMode.result.copyPrompt")}
                    </button>
                  </div>
                  <div className="bg-[#f5f5f7] rounded-lg p-2.5 text-[11px] text-[#1d1d1f] leading-relaxed max-h-40 overflow-y-auto">
                    {result.llm_prompt}
                  </div>
                </div>

                {/* User Prompt */}
                <div>
                  <span className="text-[10px] font-medium text-[#86868b] block mb-1">Original Input</span>
                  <div className="bg-[#f5f5f7] rounded-lg p-2.5 text-[11px] text-[#86868b] leading-relaxed">
                    {result.user_prompt}
                  </div>
                </div>

                {/* Models */}
                <div className="grid grid-cols-2 gap-2 text-[10px]">
                  <div className="bg-[#f5f5f7] rounded-lg p-2">
                    <span className="text-[#86868b]">LLM: </span>
                    <span className="font-medium text-[#1d1d1f]">{result.model_info.llm}</span>
                  </div>
                  <div className="bg-[#f5f5f7] rounded-lg p-2">
                    <span className="text-[#86868b]">Video: </span>
                    <span className="font-medium text-[#1d1d1f]">{result.model_info.video}</span>
                  </div>
                  {result.model_info.tts && (
                    <div className="bg-[#f5f5f7] rounded-lg p-2">
                      <span className="text-[#86868b]">TTS: </span>
                      <span className="font-medium text-[#1d1d1f]">{result.model_info.tts}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Regenerate */}
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 text-xs text-[#FF6B35] hover:bg-[#FF6B35]/5 py-2 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
          >
            <RotateCcw size={14} />
            {t("fastMode.result.regenerate")}
          </button>
        </div>
      )}
    </div>
  );
}
