"use client";

import { useState, useEffect } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import {
  getApiBase,
  getApiKey,
  isDemoMode,
  setApiBase,
  setApiKey,
  setDemoMode,
  resetApiConfig,
  testConnection,
} from "./api";
import { X, Check, AlertCircle, RotateCcw, Server, Key, Zap } from "lucide-react";

interface Props {
  onClose: () => void;
}

export default function SettingsPanel({ onClose }: Props) {
  const { t } = useI18n();
  const [baseUrl, setBaseUrl] = useState(getApiBase());
  const [key, setKey] = useState(getApiKey());
  const [demo, setDemo] = useState(isDemoMode());
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok?: boolean;
    message?: string;
  } | null>(null);

  useEffect(() => {
    setBaseUrl(getApiBase());
    setKey(getApiKey());
    setDemo(isDemoMode());
  }, []);

  const handleSave = () => {
    setApiBase(baseUrl.trim());
    setApiKey(key.trim());
    setDemoMode(demo);
    setTestResult(null);
    onClose();
  };

  const handleReset = () => {
    resetApiConfig();
    setBaseUrl(getApiBase());
    setKey(getApiKey());
    setDemo(isDemoMode());
    setTestResult(null);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    // Temporarily set values for the test
    const prevBase = getApiBase();
    const prevKey = getApiKey();
    setApiBase(baseUrl.trim());
    setApiKey(key.trim());
    try {
      const result = await testConnection();
      if (result.ok) {
        setTestResult({ ok: true, message: "Connected — " + JSON.stringify(result.data) });
      } else {
        setTestResult({ ok: false, message: result.error || "Connection failed (" + result.status + ")" });
      }
    } catch (e: any) {
      setTestResult({ ok: false, message: e.message || "Unknown error" });
    } finally {
      // Restore previous values if user hasn't saved yet
      setApiBase(prevBase);
      setApiKey(prevKey);
      setTesting(false);
    }
  };

  return (
    <div className="apple-modal-overlay" onClick={onClose}>
      <div
        className="apple-card w-full max-w-md mx-4 flex flex-col animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#EDD3D1]">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-[#6A2B3A]/10 flex items-center justify-center">
              <Server className="w-4 h-4 text-[#6A2B3A]" />
            </div>
            <h2 className="text-base font-semibold text-[#35353B]">API Configuration</h2>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-[#FCE4E2] flex items-center justify-center cursor-pointer"
          >
            <X className="w-4 h-4 text-[#59585E]" />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-4">
          {/* Backend URL */}
          <div>
            <label className="flex items-center gap-1.5 text-[11px] font-medium text-[#59585E] mb-1.5">
              <Server className="w-3 h-3" />
              Backend URL
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://your-backend.onrender.com"
              className="apple-input text-sm"
            />
            <p className="text-[11px] text-[#9FA0A0] mt-1">
              e.g. https://lute-ai-video-backend.onrender.com or http://localhost:8001
            </p>
          </div>

          {/* API Key */}
          <div>
            <label className="flex items-center gap-1.5 text-[11px] font-medium text-[#59585E] mb-1.5">
              <Key className="w-3 h-3" />
              API Key
            </label>
            <input
              type="text"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="ai_video_demo_2026"
              className="apple-input text-sm"
            />
            <p className="text-[11px] text-[#9FA0A0] mt-1">
              Must match the API_KEY environment variable on your backend.
            </p>
          </div>

          {/* Demo mode toggle */}
          <div className="flex items-center justify-between p-3 rounded-xl bg-[#FCE4E2]">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-[#59585E]" />
              <div>
                <p className="text-xs font-medium text-[#35353B]">Demo Mode</p>
                <p className="text-[11px] text-[#9FA0A0]">Skip API calls, use mock data</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={demo}
                onChange={(e) => setDemo(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-10 h-5.5 bg-[#EDD3D1] rounded-full peer peer-checked:bg-[#6A2B3A] transition-colors after:content-[''] after:absolute after:top-[3px] after:left-[3px] after:w-[18px] after:h-[18px] after:bg-white after:rounded-full after:transition-all peer-checked:after:translate-x-[18px]" />
            </label>
          </div>

          {/* Test connection */}
          <button
            onClick={handleTest}
            disabled={testing || !baseUrl.trim()}
            className="w-full apple-btn text-xs py-2 border border-[#EDD3D1] hover:bg-[#FCE4E2] disabled:opacity-50"
          >
            {testing ? (
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 border-2 border-[#59585E] border-t-transparent rounded-full animate-spin" />
                Testing...
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <Server className="w-3.5 h-3.5" />
                Test Connection
              </span>
            )}
          </button>

          {/* Test result */}
          {testResult && (
            <div
              className={`flex items-center gap-2 p-2.5 rounded-lg text-xs ${
                testResult.ok
                  ? "bg-[#6A2B3A]/10 text-[#6A2B3A]"
                  : "bg-[#C45B50]/10 text-[#C45B50]"
              }`}
            >
              {testResult.ok ? (
                <Check className="w-4 h-4 shrink-0" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0" />
              )}
              <span className="break-all">{testResult.message}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-[#EDD3D1]">
          <button
            onClick={handleReset}
            className="flex items-center gap-1 text-[11px] text-[#59585E] hover:text-[#35353B] transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3 h-3" />
            Reset Defaults
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="apple-btn text-xs py-2 px-3"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="apple-btn apple-btn-primary text-xs py-2 px-3"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
