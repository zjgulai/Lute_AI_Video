"use client";

import { useEffect } from "react";
import { useAppStore } from "@/stores/useAppStore";
import Home from "../page";

export default function FastPage() {
  const { setActiveScene, setStage, setShowSplash } = useAppStore();

  useEffect(() => {
    setActiveScene("fast_mode");
    setStage("home");
    setShowSplash(false);
  }, [setActiveScene, setStage, setShowSplash]);

  return <Home />;
}
