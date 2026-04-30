"use client";

import { useEffect } from "react";
import { useAppStore } from "@/stores/useAppStore";
import Home from "../page";

export default function FastPage() {
  const { setActiveScene, setStage } = useAppStore();

  useEffect(() => {
    setActiveScene("fast_mode");
    setStage("home");
  }, [setActiveScene, setStage]);

  return <Home />;
}
