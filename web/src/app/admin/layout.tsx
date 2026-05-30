"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import AdminSidebar from "@/components/admin/AdminSidebar";
import { adminFetchJson } from "@/components/api";
import { SignOut } from "@phosphor-icons/react";

interface AdminUser {
  admin_id: string;
  email: string;
  authenticated: boolean;
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<AdminUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Skip auth for login page
  const isLoginPage = pathname === "/admin/login";

  useEffect(() => {
    if (isLoginPage) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoading(false);
      return;
    }

    adminFetchJson<AdminUser>("/api/admin/auth/session")
      .then((data) => {
        if (data.authenticated) {
          setUser(data);
        }
      })
      .catch(() => {
        router.push("/admin/login");
      })
      .finally(() => setLoading(false));
  }, [pathname, isLoginPage, router]);

  const handleLogout = async () => {
    await adminFetchJson("/api/admin/auth/logout", { method: "POST" }).catch(() => {});
    setUser(null);
    router.push("/admin/login");
  };

  // Login page — no sidebar
  if (isLoginPage) {
    return <div className="min-h-screen bg-[var(--bg-page)]">{children}</div>;
  }

  // Loading
  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--bg-page)] flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-[var(--fortune-red)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Not authenticated
  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[var(--bg-page)] flex">
      <AdminSidebar />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-12 border-b border-[var(--divider-light)] bg-[var(--bg-panel)] flex items-center justify-between px-4 shrink-0">
          <div className="text-xs text-[var(--text-muted)]">
            {user.email}
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer"
          >
            <SignOut size={14} weight="fill" />
            Logout
          </button>
        </header>

        {/* Content */}
        <main className="flex-1 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
