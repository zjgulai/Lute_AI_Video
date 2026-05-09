"use client";

import { type ReactNode } from "react";

export type EmptyIllustration =
  | "influencers"
  | "materials"
  | "brand-kit"
  | "works"
  | "search-empty";

interface Props {
  illustration?: EmptyIllustration;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

const ILLUSTRATION_PROPS = {
  width: 80,
  height: 80,
  viewBox: "0 0 80 80",
  fill: "none",
  stroke: "var(--misty-pink)",
  strokeWidth: 1.4,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

function InfluencersIllustration() {
  return (
    <svg {...ILLUSTRATION_PROPS} aria-hidden="true">
      <circle cx="40" cy="30" r="10" />
      <path d="M20 64c0-11 9-20 20-20s20 9 20 20" />
      <circle cx="62" cy="52" r="6" strokeDasharray="2 2" />
      <path d="M62 46v-4M60 52h4" strokeWidth="1.2" />
    </svg>
  );
}

function MaterialsIllustration() {
  return (
    <svg {...ILLUSTRATION_PROPS} aria-hidden="true">
      <rect x="16" y="22" width="48" height="36" rx="3" />
      <line x1="16" y1="32" x2="64" y2="32" strokeDasharray="2 2" />
      <circle cx="24" cy="27" r="1.5" fill="var(--misty-pink)" stroke="none" />
      <circle cx="30" cy="27" r="1.5" fill="var(--misty-pink)" stroke="none" />
      <path d="M40 40v12M34 46l6-6 6 6" />
    </svg>
  );
}

function BrandKitIllustration() {
  return (
    <svg {...ILLUSTRATION_PROPS} aria-hidden="true">
      <path d="M40 16c13 0 24 10 24 22 0 6-5 10-11 10h-5c-3 0-5 2-5 5v3c0 4-3 8-8 8-13 0-24-11-24-24s11-24 29-24z" />
      <circle cx="28" cy="32" r="3" fill="var(--misty-pink)" stroke="none" />
      <circle cx="40" cy="26" r="3" fill="var(--gold-foil)" stroke="none" />
      <circle cx="52" cy="32" r="3" fill="var(--jade-accent)" stroke="none" />
    </svg>
  );
}

function WorksIllustration() {
  return (
    <svg {...ILLUSTRATION_PROPS} aria-hidden="true">
      <rect x="14" y="22" width="52" height="36" rx="4" />
      <rect x="14" y="22" width="52" height="6" fill="var(--misty-pink)" stroke="none" opacity="0.25" />
      <circle cx="20" cy="25" r="1.2" fill="var(--misty-pink)" stroke="none" />
      <circle cx="25" cy="25" r="1.2" fill="var(--misty-pink)" stroke="none" />
      <circle cx="30" cy="25" r="1.2" fill="var(--misty-pink)" stroke="none" />
      <path d="M35 38l12 7-12 7z" fill="var(--misty-pink)" stroke="none" opacity="0.5" />
    </svg>
  );
}

function SearchEmptyIllustration() {
  return (
    <svg {...ILLUSTRATION_PROPS} aria-hidden="true">
      <circle cx="34" cy="34" r="16" />
      <line x1="46" y1="46" x2="60" y2="60" />
      <path d="M34 28v6M34 38v1" strokeWidth="1.8" />
    </svg>
  );
}

const ILLUSTRATIONS: Record<EmptyIllustration, () => React.JSX.Element> = {
  influencers: InfluencersIllustration,
  materials: MaterialsIllustration,
  "brand-kit": BrandKitIllustration,
  works: WorksIllustration,
  "search-empty": SearchEmptyIllustration,
};

export default function EmptyState({
  illustration,
  title,
  description,
  action,
  className = "",
}: Props) {
  const Illustration = illustration ? ILLUSTRATIONS[illustration] : null;

  return (
    <div
      data-empty-state
      data-illustration={illustration}
      className={`apple-card p-12 text-center ${className}`}
    >
      {Illustration ? (
        <div
          data-illustration="true"
          className="w-20 h-20 mx-auto mb-4 flex items-center justify-center"
        >
          <Illustration />
        </div>
      ) : null}

      <p data-empty-title className="text-sm font-medium text-[var(--text-body)] mb-1">
        {title}
      </p>

      {description && (
        <p className="text-xs text-[var(--text-muted)] mb-4 max-w-[320px] mx-auto leading-relaxed">
          {description}
        </p>
      )}

      {action && <div data-empty-cta-wrapper className="flex justify-center">{action}</div>}
    </div>
  );
}
