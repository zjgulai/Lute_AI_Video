"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAppStore } from "@/stores/useAppStore";
import Home from "../page";

function S2Inner() {
  const searchParams = useSearchParams();
  const { setActiveScene, setMode, setStage, setShowSplash } = useAppStore();

  useEffect(() => {
    const modeParam = searchParams.get("mode") as "expert" | "smart" || "expert";
    setActiveScene("brand_campaign");
    setMode(modeParam);
    setStage("home");
    setShowSplash(false);
  }, [searchParams, setActiveScene, setMode, setStage, setShowSplash]);

  return <Home />;
}

export default function S2Page() {
  return (
    <Suspense fallback={null}>
      <S2Inner />
    </Suspense>
  );
}
