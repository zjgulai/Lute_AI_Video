"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAppStore } from "@/stores/useAppStore";
import Home from "../page";

export default function S3Page() {
  const searchParams = useSearchParams();
  const { setActiveScene, setMode, setStage } = useAppStore();

  useEffect(() => {
    const modeParam = searchParams.get("mode") as "expert" | "smart" || "expert";
    setActiveScene("influencer_remix");
    setMode(modeParam);
    setStage("home");
  }, [searchParams, setActiveScene, setMode, setStage]);

  return <Home />;
}
