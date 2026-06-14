import ToolboxToolPage from "@/components/toolbox/ToolboxToolPage";
import { TOOL_ORDER } from "@/components/toolbox/toolboxToolIds";

export function generateStaticParams() {
  return TOOL_ORDER.map((toolId) => ({ toolId }));
}

export default async function ToolboxToolRoutePage({
  params,
}: {
  params: Promise<{ toolId: string }>;
}) {
  const { toolId } = await params;
  return <ToolboxToolPage toolId={toolId} />;
}
