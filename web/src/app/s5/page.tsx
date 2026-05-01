"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAppStore } from "@/stores/useAppStore";
import Home from "../page";

function S5Inner() {
  const searchParams = useSearchParams();
  const { setActiveScene, setMode, setStage, setShowSplash } = useAppStore();

  useEffect(() => {
    const modeParam = searchParams.get("mode") as "expert" | "smart" || "expert";
    setActiveScene("brand_vlog");
    setMode(modeParam);
    setStage("home");
    setShowSplash(false);
  }, [searchParams, setActiveScene, setMode, setStage, setShowSplash]);

  return <Home />;
}

export default function S5Page() {
  return (
    <Suspense fallback={null}>
      <S5Inner />
    </Suspense>
  );
}
