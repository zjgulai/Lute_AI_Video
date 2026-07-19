"use client";

import type { ImgHTMLAttributes } from "react";

import { useSignedMediaUrl } from "@/hooks/useSignedMediaUrl";

type RuntimeMediaImageProps = Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "alt"> & {
  src: string;
  alt: string;
};

export default function RuntimeMediaImage({
  src,
  alt,
  loading = "lazy",
  ...props
}: RuntimeMediaImageProps) {
  const { url } = useSignedMediaUrl(src, "view");
  if (!url) return null;

  return (
    // eslint-disable-next-line @next/next/no-img-element -- Runtime media URLs come from backend/user assets and are not guaranteed to be statically allowlisted for next/image.
    <img src={url} alt={alt} loading={loading} {...props} />
  );
}
