"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAppStore } from "@/stores/useAppStore";
import Home from "../page";

function S1Inner() {
  const searchParams = useSearchParams();
  const { setActiveScene, setMode, setStage, setShowSplash } = useAppStore();

  useEffect(() => {
    const modeParam = searchParams.get("mode") as "expert" | "smart" || "expert";
    setActiveScene("product_direct");
    setMode(modeParam);
    setStage("home");
    setShowSplash(false);
  }, [searchParams, setActiveScene, setMode, setStage, setShowSplash]);

  return <Home />;
}

export default function S1Page() {
  return (
    <Suspense fallback={null}>
      <S1Inner />
    </Suspense>
  );
}
