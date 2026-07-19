"use client";

import type { VideoHTMLAttributes } from "react";

import { useSignedMediaUrl } from "@/hooks/useSignedMediaUrl";

type RuntimeMediaVideoProps = Omit<VideoHTMLAttributes<HTMLVideoElement>, "src" | "poster"> & {
  src: string;
  poster?: string;
};

export default function RuntimeMediaVideo({ src, poster, ...props }: RuntimeMediaVideoProps) {
  const { url } = useSignedMediaUrl(src, "view");
  const { url: posterUrl } = useSignedMediaUrl(poster ?? "", "view");
  if (!url) return null;

  return <video src={url} poster={poster ? posterUrl || undefined : undefined} {...props} />;
}
