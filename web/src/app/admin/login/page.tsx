"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { adminFetch, parseApiError } from "@/components/api";
import { Key, WarningCircle } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";

export default function AdminLoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);

  useEffect(() => {
    if (retryAfter <= 0) return;
    const id = setInterval(() => setRetryAfter((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, [retryAfter]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (retryAfter > 0) return;
    setError("");
    setLoading(true);

    try {
      const res = await adminFetch("/api/admin/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });

      if (!res.ok) {
        const info = await parseApiError(res);
        if (info.status === 429 && info.retryAfterSec) {
          setRetryAfter(info.retryAfterSec);
          setError(t("admin.login.rateLimited").replace("{seconds}", String(info.retryAfterSec)));
        } else if (info.status === 422) {
          setError(t("admin.login.invalidRequest"));
        } else {
          setError(t("admin.login.invalidCredentials"));
        }
        setLoading(false);
        return;
      }

      router.push("/admin/dashboard");
    } catch {
      setError(t("admin.login.networkError"));
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo area */}
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-xl bg-[var(--fortune-red)] flex items-center justify-center mx-auto mb-3 shadow-[0_0_16px_rgba(215,92,112,0.3)]">
            <Key size={20} weight="fill" className="text-white" />
          </div>
          <h1 className="text-lg font-semibold text-[var(--text-h1)]">
            AI Video Admin
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {t("admin.login.subtitle")}
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label htmlFor="admin-email" className="sr-only">
              {t("admin.login.email")}
            </label>
            <input
              id="admin-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@example.com"
              required
              autoFocus
              className="apple-input text-sm w-full"
            />
          </div>

          <div>
            <label htmlFor="admin-password" className="sr-only">
              {t("admin.login.password")}
            </label>
            <input
              id="admin-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("admin.login.passwordPlaceholder")}
              required
              className="apple-input text-sm w-full"
            />
          </div>

          {error && (
            <div
              id="admin-login-error"
              role="alert"
              className="flex items-center gap-2 p-2.5 rounded-lg bg-[rgba(208,78,90,0.1)] text-[var(--crimson-mist)] text-xs"
            >
              <WarningCircle size={14} weight="fill" className="shrink-0" />
              <span>
                {retryAfter > 0
                  ? t("admin.login.rateLimited").replace("{seconds}", String(retryAfter))
                  : error}
              </span>
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !email || !password || retryAfter > 0}
            aria-describedby={error ? "admin-login-error" : undefined}
            className="apple-btn apple-btn-primary text-sm w-full py-2.5 disabled:opacity-50"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                {t("admin.login.signingIn")}
              </span>
            ) : (
              t("admin.login.signIn")
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
