import AdminTenantDetailClient from "./AdminTenantDetailClient";

const STATIC_TENANT_IDS = ["default", "momcozy-marketing"] as const;

export function generateStaticParams() {
  return STATIC_TENANT_IDS.map((tenantId) => ({ tenantId }));
}

export const dynamicParams = false;

export default async function AdminTenantDetailPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  return <AdminTenantDetailClient tenantId={tenantId} />;
}
