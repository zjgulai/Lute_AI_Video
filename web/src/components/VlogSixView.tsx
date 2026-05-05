"use client";

import React from "react";
import type { ProductViewAngle } from "./types";

interface Props {
  views: ProductViewAngle[];
}

export default function VlogSixView({ views }: Props) {
  if (!views || views.length === 0) {
    return (
      <div className="apple-card p-8 text-center">
        <p className="text-xs text-[var(--text-body)]">请先选择产品SKU以自动回填六视图</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-3">
      {views.map((view, i) => (
        <div
          key={i}
          className="apple-card overflow-hidden hover:shadow-md transition-shadow duration-200"
        >
          {/* Color accent bar */}
          <div
            className="h-16 relative overflow-hidden"
            style={{
              background: `linear-gradient(135deg, ${view.color} 0%, ${view.color}88 100%)`,
            }}
          >
            <div className="absolute top-2.5 left-3 px-2 py-0.5 rounded-full bg-white/20 text-white text-[12px] font-medium backdrop-blur-sm">
              {view.label}
            </div>
            <div className="absolute left-3 bottom-3 right-3">
              <div className="text-white text-sm font-semibold leading-tight">
                {view.title}
              </div>
            </div>
          </div>
          {/* Footer */}
          <div className="p-3">
            <div className="text-[12px] text-[var(--text-body)] leading-relaxed">
              {view.usage_note}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
