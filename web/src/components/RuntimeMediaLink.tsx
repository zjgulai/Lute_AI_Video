"use client";

import type { AnchorHTMLAttributes } from "react";

import { useSignedMediaUrl } from "@/hooks/useSignedMediaUrl";

type RuntimeMediaLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
  purpose?: "view" | "download";
};

export default function RuntimeMediaLink({
  href,
  purpose,
  download,
  ...props
}: RuntimeMediaLinkProps) {
  const resolvedPurpose = purpose ?? (download ? "download" : "view");
  const { url } = useSignedMediaUrl(href, resolvedPurpose);
  if (!url) return null;

  return <a href={url} download={download} {...props} />;
}
