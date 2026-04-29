"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  onEnter: () => void;
}

const IMAGE_W = 1536;
const IMAGE_H = 1024;
const IMAGE_RATIO = IMAGE_W / IMAGE_H; // 1.5

// Button pixel coordinates on the original image (1536x1024), estimated from main_page_01.png
const BTN_X = 72;
const BTN_Y = 820;
const BTN_W = 216;
const BTN_H = 54;

function useContainMetrics() {
  const [m, setM] = useState({ offsetX: 0, offsetY: 0, displayW: 0, displayH: 0 });

  const update = useCallback(() => {
    const screenW = window.innerWidth;
    const screenH = window.innerHeight;
    const screenRatio = screenW / screenH;

    let displayW: number, displayH: number, offsetX: number, offsetY: number;
    if (screenRatio > IMAGE_RATIO) {
      // Screen wider: image fills height, letterbox left/right
      displayH = screenH;
      displayW = displayH * IMAGE_RATIO;
      offsetX = (screenW - displayW) / 2;
      offsetY = 0;
    } else {
      // Screen narrower: image fills width, pillar-box top/bottom
      displayW = screenW;
      displayH = displayW / IMAGE_RATIO;
      offsetX = 0;
      offsetY = (screenH - displayH) / 2;
    }
    setM({ offsetX, offsetY, displayW, displayH });
  }, []);

  useEffect(() => {
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [update]);

  return m;
}

export default function SplashScreen({ onEnter }: Props) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(true);
  const [animating, setAnimating] = useState(false);
  const { offsetX, offsetY, displayW, displayH } = useContainMetrics();

  useEffect(() => {
    const timer = setTimeout(() => setAnimating(true), 100);
    return () => clearTimeout(timer);
  }, []);

  const handleEnter = () => {
    setAnimating(false);
    setTimeout(() => {
      setVisible(false);
      onEnter();
    }, 600);
  };

  if (!visible) return null;

  // Map original image pixel coords to screen coords (contain mode)
  const scale = displayW / IMAGE_W;
  const btnLeft = offsetX + BTN_X * scale;
  const btnTop = offsetY + BTN_Y * scale;
  const btnWidth = BTN_W * scale;
  const btnHeight = BTN_H * scale;

  return (
    <div
      className={`fixed inset-0 z-[100] transition-opacity duration-700 ease-in-out ${
        animating ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
      }`}
      style={{ backgroundColor: "#7CB342" }}
    >
      {/* Fullscreen container: image centered with contain */}
      <div className="absolute inset-0 flex items-center justify-center">
        <img
          src="/splash-final.png"
          alt=""
          className="max-w-full max-h-full"
          style={{
            width: displayW,
            height: displayH,
            objectFit: "contain",
            imageRendering: "auto",
          }}
          draggable={false}
        />
      </div>

      {/* Actual clickable button — precisely overlaid on the splash button area */}
      <button
        onClick={handleEnter}
        className="absolute bg-white text-[#4a8a2a] font-semibold rounded-full shadow-lg hover:shadow-xl hover:scale-[1.03] active:scale-[0.97] transition-all duration-300 cursor-pointer flex items-center justify-center gap-2"
        style={{
          left: btnLeft,
          top: btnTop,
          width: btnWidth,
          height: btnHeight,
          fontSize: Math.max(12, btnHeight * 0.38),
          letterSpacing: "0.05em",
        }}
      >
        <span>{t("splash.enter")}</span>
        <svg
          width={Math.max(14, btnHeight * 0.35)}
          height={Math.max(14, btnHeight * 0.35)}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="5" y1="12" x2="19" y2="12" />
          <polyline points="12 5 19 12 12 19" />
        </svg>
      </button>
    </div>
  );
}
