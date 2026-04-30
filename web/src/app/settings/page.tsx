"use client";

import { useEffect } from "react";
import { useAppStore } from "@/stores/useAppStore";
import Home from "../page";

export default function SettingsPage() {
  const { setShowSettings } = useAppStore();

  useEffect(() => {
    setShowSettings(true);
  }, [setShowSettings]);

  return <Home />;
}
