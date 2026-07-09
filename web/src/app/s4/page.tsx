"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAppStore } from "@/stores/useAppStore";
import GateDirectAccess from "@/components/GateDirectAccess";
import { RoutePageSkeleton } from "@/components/Skeleton";
import Home from "../page";

function S4Inner() {
  const searchParams = useSearchParams();
  const { setActiveScene, setMode, setStage, setShowSplash } = useAppStore();

  const label = searchParams.get("label");
  const gateRaw = searchParams.get("gate");
  const gateNumber = gateRaw ? (parseInt(gateRaw, 10) as 1 | 2 | 3 | 4) : null;
  const isGateDirect = Boolean(label && gateNumber && gateNumber >= 1 && gateNumber <= 4);

  useEffect(() => {
    if (isGateDirect) return;
    const modeParam = searchParams.get("mode") as "expert" | "smart" || "expert";
    setActiveScene("live_shoot_to_video");
    setMode(modeParam);
    setStage("home");
    setShowSplash(false);
  }, [searchParams, isGateDirect, setActiveScene, setMode, setStage, setShowSplash]);

  if (isGateDirect && label && gateNumber) {
    return <GateDirectAccess scene="s4" label={label} gateNumber={gateNumber} />;
  }
  return <Home />;
}

export default function S4Page() {
  return (
    <Suspense fallback={<RoutePageSkeleton />}>
      <S4Inner />
    </Suspense>
  );
}
