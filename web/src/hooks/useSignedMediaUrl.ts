"use client";

import { useEffect, useState } from "react";

import { getMediaUrl, getSignedMediaUrl } from "@/components/api";

export type SignedMediaState = {
  url: string;
  loading: boolean;
  error: string | null;
};

type MediaPurpose = "view" | "download";
type ProtectedMedia = {
  kind: "protected";
  signingPath: string;
  initialUrl: string;
  initialExpiresAt: number | null;
};
type MediaDescriptor =
  | ProtectedMedia
  | { kind: "public"; url: string }
  | { kind: "invalid" };

type KeyedSignedMediaState = SignedMediaState & { key: string };

const REFRESH_EARLY_MS = 30_000;
const MAX_TIMER_DELAY_MS = 2_147_000_000;

function signedUrlMetadata(url: string): { expiresAt: number; purpose: MediaPurpose } | null {
  const queryIndex = url.indexOf("?");
  if (queryIndex < 0) return null;
  const params = new URLSearchParams(url.slice(queryIndex + 1));
  const expires = params.get("expires") ?? "";
  const purpose = params.get("purpose") ?? "";
  if (!/^\d+$/.test(expires) || (purpose !== "view" && purpose !== "download")) return null;
  const expiresAt = Number(expires) * 1000;
  return Number.isSafeInteger(expiresAt) ? { expiresAt, purpose } : null;
}

function apiMediaPath(url: string): string | null {
  try {
    const parsed = url.startsWith("http") ? new URL(url) : new URL(url, "http://runtime.local");
    return parsed.pathname.startsWith("/api/media/")
      ? parsed.pathname.slice("/api/media/".length)
      : null;
  } catch {
    return null;
  }
}

function describeMedia(filePath: string, purpose: MediaPurpose): MediaDescriptor {
  const safeUrl = getMediaUrl(filePath);
  if (!safeUrl) return { kind: "invalid" };
  const mediaPath = apiMediaPath(safeUrl);
  if (mediaPath === null) return { kind: "public", url: safeUrl };

  const queryIndex = safeUrl.indexOf("?");
  const unsignedUrl = queryIndex < 0 ? safeUrl : safeUrl.slice(0, queryIndex);
  if (mediaPath.startsWith("brand_assets/") || mediaPath.startsWith("demo/")) {
    return { kind: "public", url: unsignedUrl };
  }

  const metadata = signedUrlMetadata(safeUrl);
  if (!metadata) {
    const signingPath = filePath.startsWith("http") ? `/api/media/${mediaPath}` : filePath;
    return { kind: "protected", signingPath, initialUrl: "", initialExpiresAt: null };
  }
  if (metadata.purpose !== purpose || metadata.expiresAt <= Date.now()) return { kind: "invalid" };
  return {
    kind: "protected",
    signingPath: `/api/media/${mediaPath}`,
    initialUrl: safeUrl,
    initialExpiresAt: metadata.expiresAt,
  };
}

export function useSignedMediaUrl(
  filePath: string,
  purpose: MediaPurpose = "view",
): SignedMediaState {
  const key = `${purpose}:${filePath}`;
  const descriptor = describeMedia(filePath, purpose);
  const initialState: SignedMediaState = descriptor.kind === "protected"
    ? { url: descriptor.initialUrl, loading: !descriptor.initialUrl, error: null }
    : descriptor.kind === "public"
      ? { url: descriptor.url, loading: false, error: null }
      : { url: "", loading: false, error: filePath ? "Invalid media URL" : null };
  const isProtected = descriptor.kind === "protected";
  const signingPath = isProtected ? descriptor.signingPath : "";
  const initialUrl = isProtected ? descriptor.initialUrl : "";
  const initialExpiresAt = isProtected ? descriptor.initialExpiresAt : null;
  const [state, setState] = useState<KeyedSignedMediaState>({ key, ...initialState });

  useEffect(() => {
    if (!isProtected) return;

    let active = true;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    let expiryTimer: ReturnType<typeof setTimeout> | undefined;

    const clearTimers = () => {
      if (refreshTimer) clearTimeout(refreshTimer);
      if (expiryTimer) clearTimeout(expiryTimer);
    };

    const failClosed = (message: string) => {
      if (!active) return;
      clearTimers();
      setState({ key, url: "", loading: false, error: message });
    };

    const scheduleExpiry = (expiresAt: number, expiringUrl: string) => {
      const delay = expiresAt - Date.now();
      if (delay <= 0) {
        failClosed("Signed media URL expired");
        return;
      }
      const timerDelay = Math.min(delay, MAX_TIMER_DELAY_MS);
      expiryTimer = setTimeout(() => {
        if (delay > MAX_TIMER_DELAY_MS) {
          scheduleExpiry(expiresAt, expiringUrl);
          return;
        }
        if (!active) return;
        setState((current) => {
          if (current.key === key && current.url && current.url !== expiringUrl) return current;
          return { key, url: "", loading: false, error: "Signed media URL expired" };
        });
      }, timerDelay);
    };

    const scheduleRefresh = (expiresAt: number) => {
      const delay = expiresAt - Date.now() - REFRESH_EARLY_MS;
      if (delay <= 0) return false;
      const timerDelay = Math.min(delay, MAX_TIMER_DELAY_MS);
      refreshTimer = setTimeout(() => {
        if (delay > MAX_TIMER_DELAY_MS) {
          scheduleRefresh(expiresAt);
        } else {
          void resolveSignedUrl();
        }
      }, timerDelay);
      return true;
    };

    const acceptSignedUrl = (candidate: string) => {
      const safeUrl = getMediaUrl(candidate);
      const metadata = signedUrlMetadata(safeUrl);
      if (
        !safeUrl
        || safeUrl !== candidate
        || !metadata
        || metadata.purpose !== purpose
        || metadata.expiresAt <= Date.now()
      ) {
        failClosed("Media signing failed");
        return;
      }
      clearTimers();
      scheduleExpiry(metadata.expiresAt, safeUrl);
      scheduleRefresh(metadata.expiresAt);
      setState({ key, url: safeUrl, loading: false, error: null });
    };

    async function resolveSignedUrl() {
      if (!active) return;
      setState((current) => ({
        key,
        url: current.key === key ? current.url : initialUrl,
        loading: true,
        error: null,
      }));
      const signedUrl = await getSignedMediaUrl(signingPath, purpose);
      if (!active) return;
      if (!signedUrl) {
        failClosed("Media signing failed");
        return;
      }
      acceptSignedUrl(signedUrl);
    }

    if (initialUrl && initialExpiresAt) {
      scheduleExpiry(initialExpiresAt, initialUrl);
      if (!scheduleRefresh(initialExpiresAt)) void resolveSignedUrl();
    } else {
      void resolveSignedUrl();
    }

    return () => {
      active = false;
      clearTimers();
    };
  }, [initialExpiresAt, initialUrl, isProtected, key, purpose, signingPath]);

  if (descriptor.kind !== "protected") return initialState;
  if (state.key !== key) return initialState;
  return { url: state.url, loading: state.loading, error: state.error };
}
