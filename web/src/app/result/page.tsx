"use client";

import { useEffect } from "react";
import { useAppStore } from "@/stores/useAppStore";
import Home from "../page";

export default function ResultPage() {
  const { setStage } = useAppStore();

  useEffect(() => {
    setStage("result");
  }, [setStage]);

  return <Home />;
}
