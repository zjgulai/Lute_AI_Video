"use client";

import { use } from "react";
import ToolboxToolPage from "@/components/toolbox/ToolboxToolPage";

export default function ToolboxToolRoutePage({
  params,
}: {
  params: Promise<{ toolId: string }>;
}) {
  const { toolId } = use(params);
  return <ToolboxToolPage toolId={toolId} />;
}
