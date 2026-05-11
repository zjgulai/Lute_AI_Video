"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/components/api";

const HEARTBEAT_INTERVAL_MS = 30_000;
const PING_TIMEOUT_MS = 3_000;

/**
 * Periodically pings the backend `/health` endpoint and reflects online state.
 * Also reacts to browser `online` / `offline` events for immediate feedback.
 *
 * Returns `{ online, ping }`:
 *  - `online`  — `true` when last ping succeeded or no ping has run yet
 *  - `ping`    — manual re-check (e.g. wired to a "Retry" button)
 */
export function useNetworkHealth(): { online: boolean; ping: () => Promise<void> } {
  const [online, setOnline] = useState(true);

  const ping = async () => {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), PING_TIMEOUT_MS);
      const res = await apiFetch("/health", { cache: "no-store", signal: ctrl.signal });
      clearTimeout(timer);
      setOnline(res.ok);
    } catch {
      setOnline(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const run = () => { if (!cancelled) void ping(); };

    const handleOnline = () => { if (!cancelled) void ping(); };
    const handleOffline = () => { if (!cancelled) setOnline(false); };

    run();
    const id = setInterval(run, HEARTBEAT_INTERVAL_MS);
    if (typeof window !== "undefined") {
      window.addEventListener("online", handleOnline);
      window.addEventListener("offline", handleOffline);
    }

    return () => {
      cancelled = true;
      clearInterval(id);
      if (typeof window !== "undefined") {
        window.removeEventListener("online", handleOnline);
        window.removeEventListener("offline", handleOffline);
      }
    };
  }, []);

  return { online, ping };
}
