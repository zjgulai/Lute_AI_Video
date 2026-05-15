"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAppStore } from "@/stores/useAppStore";
import GateDirectAccess from "@/components/GateDirectAccess";
import Home from "../page";

function S5Inner() {
  const searchParams = useSearchParams();
  const { setActiveScene, setMode, setStage, setShowSplash } = useAppStore();

  const label = searchParams.get("label");
  const gateRaw = searchParams.get("gate");
  const gateNumber = gateRaw ? (parseInt(gateRaw, 10) as 1 | 2 | 3 | 4) : null;
  const isGateDirect = Boolean(label && gateNumber && gateNumber >= 1 && gateNumber <= 4);

  useEffect(() => {
    if (isGateDirect) return;
    const modeParam = searchParams.get("mode") as "expert" | "smart" || "expert";
    setActiveScene("brand_vlog");
    setMode(modeParam);
    setStage("home");
    setShowSplash(false);
  }, [searchParams, isGateDirect, setActiveScene, setMode, setStage, setShowSplash]);

  if (isGateDirect && label && gateNumber) {
    return <GateDirectAccess scene="s5" label={label} gateNumber={gateNumber} />;
  }
  return <Home />;
}

export default function S5Page() {
  return (
    <Suspense fallback={null}>
      <S5Inner />
    </Suspense>
  );
}
