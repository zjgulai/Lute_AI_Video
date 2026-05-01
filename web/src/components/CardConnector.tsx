"use client";

import React from "react";

interface Props {
  text: string;
}

export default function CardConnector({ text }: Props) {
  if (!text) return null;

  return (
    <div className="flex flex-col items-center py-1 px-4">
      {/* 竖线 */}
      <div className="w-px h-3 bg-[var(--color-border-light)]" />
      {/* 引导文字 */}
      <div className="flex items-center gap-2 my-0.5">
        <div className="w-8 h-px bg-gradient-to-r from-transparent to-[var(--color-border-light)]" />
        <span className="text-[11px] text-[var(--color-text-tertiary)] italic whitespace-nowrap">
          {text}
        </span>
        <div className="w-8 h-px bg-gradient-to-l from-transparent to-[var(--color-border-light)]" />
      </div>
      {/* 竖线 + 箭头 */}
      <div className="relative">
        <div className="w-px h-3 bg-[var(--color-border-light)]" />
        <div className="absolute -bottom-0.5 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[3px] border-r-[3px] border-t-[3px] border-l-transparent border-r-transparent border-t-[var(--color-border-light)]" />
      </div>
    </div>
  );
}
