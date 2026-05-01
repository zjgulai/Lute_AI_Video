"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAppStore } from "@/stores/useAppStore";
import Home from "../page";

function S4Inner() {
  const searchParams = useSearchParams();
  const { setActiveScene, setMode, setStage } = useAppStore();

  useEffect(() => {
    const modeParam = searchParams.get("mode") as "expert" | "smart" || "expert";
    setActiveScene("live_shoot");
    setMode(modeParam);
    setStage("home");
  }, [searchParams, setActiveScene, setMode, setStage]);

  return <Home />;
}

export default function S4Page() {
  return (
    <Suspense fallback={null}>
      <S4Inner />
    </Suspense>
  );
}
