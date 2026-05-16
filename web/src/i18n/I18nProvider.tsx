"use client";

import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from "react";
import type { Locale } from "./translations";
import { translations } from "./translations";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, fallback?: string) => string;
}

const STORAGE_KEY = "app-locale";
const COOKIE_KEY = "app-locale";

const I18nContext = createContext<I18nContextValue | null>(null);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()\[\]\\\/+^])/g, "\\$1") + "=([^;]*)")
  );
  return match ? decodeURIComponent(match[1]) : null;
}

function writeCookie(name: string, value: string, days = 365) {
  if (typeof document === "undefined") return;
  const d = new Date();
  d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
  document.cookie = `${name}=${encodeURIComponent(value)};expires=${d.toUTCString()};path=/;SameSite=Lax`;
}

function detectBrowserLocale(): Locale {
  if (typeof navigator === "undefined") return "zh";
  const langs = [navigator.language, ...(navigator.languages || [])];
  for (const lang of langs) {
    if (!lang) continue;
    const lower = lang.toLowerCase();
    if (lower.startsWith("zh")) return "zh";
    if (lower.startsWith("en")) return "en";
  }
  return "zh";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("zh");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    let chosen: Locale = "zh";
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "zh" || stored === "en") {
        chosen = stored;
      } else {
        const cookied = readCookie(COOKIE_KEY);
        if (cookied === "zh" || cookied === "en") {
          chosen = cookied;
        } else {
          chosen = detectBrowserLocale();
        }
      }
    } catch {
      chosen = detectBrowserLocale();
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocaleState(chosen);
    setHydrated(true);
    if (typeof document !== "undefined") {
      document.documentElement.lang = chosen === "zh" ? "zh-CN" : "en";
    }
  }, []);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    try {
      localStorage.setItem(STORAGE_KEY, newLocale);
    } catch {
      writeCookie(COOKIE_KEY, newLocale);
    }
    writeCookie(COOKIE_KEY, newLocale);
    if (typeof document !== "undefined") {
      document.documentElement.lang = newLocale === "zh" ? "zh-CN" : "en";
    }
  }, []);

  const t = useCallback(
    (key: string, fallback?: string): string => {
      const value = translations[locale]?.[key];
      if (value !== undefined) return value;
      if (fallback !== undefined) return fallback;
      const segments = key.split(".");
      const last = segments[segments.length - 1];
      return last && last !== key ? last : key;
    },
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      <span data-i18n-hydrated={hydrated ? "true" : "false"} style={{ display: "none" }} />
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return ctx;
}
