"use client";

import type { AudioHTMLAttributes } from "react";

import { useSignedMediaUrl } from "@/hooks/useSignedMediaUrl";

type RuntimeMediaAudioProps = Omit<AudioHTMLAttributes<HTMLAudioElement>, "src"> & {
  src: string;
};

export default function RuntimeMediaAudio({ src, ...props }: RuntimeMediaAudioProps) {
  const { url } = useSignedMediaUrl(src, "view");
  if (!url) return null;

  return <audio src={url} {...props} />;
}
