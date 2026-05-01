"use client";

import { useState, useCallback } from "react";

export interface ExecutionBarState {
  isGenerating: boolean;
  generatingLabel: string;
  generatingProgress: number;
}

export function useExecutionBar() {
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatingLabel, setGeneratingLabel] = useState("");
  const [generatingProgress, setGeneratingProgress] = useState(0);

  const startGenerating = useCallback((label?: string) => {
    setIsGenerating(true);
    setGeneratingLabel(label || "");
    setGeneratingProgress(0);
  }, []);

  const updateProgress = useCallback((progress: number) => {
    setGeneratingProgress(progress);
  }, []);

  const stopGenerating = useCallback(() => {
    setIsGenerating(false);
    setGeneratingLabel("");
    setGeneratingProgress(0);
  }, []);

  return {
    isGenerating,
    generatingLabel,
    generatingProgress,
    startGenerating,
    updateProgress,
    stopGenerating,
  };
}
