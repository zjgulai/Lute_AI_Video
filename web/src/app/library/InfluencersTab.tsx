"use client";

import { useCallback, useEffect, useState } from "react";
import { Users, Plus, PencilSimple, Trash, X, WarningCircle, Spinner } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { apiFetch, isDemoMode } from "@/components/api";
import TagInput from "@/components/TagInput";
import EmptyState from "@/components/EmptyState";

interface InfluencerProfile {
  influencer_id: string;
  name: string;
  handle: string;
  platforms: string[];
  style_tags: string[];
  notes: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export default function InfluencersTab() {
  const { t } = useI18n();
  const [influencers, setInfluencers] = useState<InfluencerProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const [formName, setFormName] = useState("");
  const [formHandle, setFormHandle] = useState("");
  const [formPlatforms, setFormPlatforms] = useState<string[]>([]);
  const [formStyleTags, setFormStyleTags] = useState<string[]>([]);
  const [formNotes, setFormNotes] = useState("");
  const [formIsActive, setFormIsActive] = useState(true);

  const fetchInfluencers = useCallback(async () => {
    setLoading(true);
    setError(null);
    if (isDemoMode()) {
      try {
        const { DEMO_INFLUENCERS } = await import("@/demo-data");
        setInfluencers(DEMO_INFLUENCERS || []);
      } catch (e: any) {
        setError(e.message || t("common.fetchFailed"));
      } finally {
        setLoading(false);
      }
      return;
    }
    try {
      const res = await apiFetch("/api/assets/influencers");
      if (!res.ok) throw new Error(`${t("common.fetchFailed")} (${res.status})`);
      const data = await res.json();
      setInfluencers(data.influencers || []);
    } catch (e: any) {
      setError(e.message || t("common.fetchFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { fetchInfluencers(); }, [fetchInfluencers]);

  const openCreateForm = () => {
    setEditingId(null);
    setFormName("");
    setFormHandle("");
    setFormPlatforms([]);
    setFormStyleTags([]);
    setFormNotes("");
    setFormIsActive(true);
    setShowForm(true);
  };

  const openEditForm = (inf: InfluencerProfile) => {
    setEditingId(inf.influencer_id);
    setFormName(inf.name || "");
    setFormHandle(inf.handle || "");
    setFormPlatforms(inf.platforms || []);
    setFormStyleTags(inf.style_tags || []);
    setFormNotes(inf.notes || "");
    setFormIsActive(inf.is_active);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!formName.trim()) return;
    if (isDemoMode()) {
      setError(t("library.demoModeEditDisabled"));
      return;
    }
    setSaving(true);
    try {
      const body: Record<string, any> = {
        name: formName.trim(),
        handle: formHandle.trim() || undefined,
        platforms: formPlatforms,
        style_tags: formStyleTags,
        notes: formNotes.trim() || undefined,
        is_active: formIsActive,
      };
      if (editingId) {
        const res = await apiFetch("/api/assets/influencers/" + editingId, {
          method: "PUT",
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`${t("common.updateFailed")} (${res.status})`);
      } else {
        const res = await apiFetch("/api/assets/influencers", {
          method: "POST",
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`${t("common.createFailed")} (${res.status})`);
      }
      setShowForm(false);
      await fetchInfluencers();
    } catch (e: any) {
      setError(e.message || t("common.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (influencerId: string) => {
    if (isDemoMode()) {
      setError(t("library.demoModeDeleteDisabled"));
      setDeleteConfirm(null);
      return;
    }
    try {
      const res = await apiFetch("/api/assets/influencers/" + influencerId, { method: "DELETE" });
      if (!res.ok) throw new Error(`${t("common.deleteFailed")} (${res.status})`);
      setDeleteConfirm(null);
      await fetchInfluencers();
    } catch (e: any) {
      setError(e.message || t("common.deleteFailed"));
    }
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return "-";
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[12px] text-[var(--text-muted)]">
          {influencers.length} {t("library.influencerCountSuffix")}
        </p>
        {!loading && influencers.length > 0 && (
          <button
            onClick={openCreateForm}
            className="apple-btn apple-btn-primary text-xs py-2 px-3"
          >
            <Plus size={14} weight="fill" />
            {t("inf.add")}
          </button>
        )}
      </div>

      {error && (
        <div className="apple-card p-3 border-l-4 border-[var(--crimson-mist)] bg-[rgba(196,91,80,0.08)] flex items-center gap-2">
          <WarningCircle size={16} weight="fill" className="text-[var(--crimson-mist)] shrink-0" />
          <span className="text-xs text-[var(--crimson-mist)] font-medium">{error}</span>
          <button onClick={() => setError(null)} className="ml-auto text-[var(--crimson-mist)] hover:opacity-70 cursor-pointer">
            <X size={16} weight="fill" />
          </button>
        </div>
      )}

      {loading && (
        <div
          className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4"
          aria-busy="true"
          aria-live="polite"
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="apple-card p-4 space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full skeleton shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-3/4 skeleton rounded" />
                  <div className="h-2.5 w-1/2 skeleton rounded" />
                </div>
              </div>
              <div className="flex gap-1.5">
                <div className="h-4 w-12 skeleton rounded-full" />
                <div className="h-4 w-16 skeleton rounded-full" />
                <div className="h-4 w-10 skeleton rounded-full" />
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && influencers.length === 0 && (
        <EmptyState
          illustration="influencers"
          title={t("inf.empty")}
          description={t("inf.emptyHint")}
          action={
            <button
              data-empty-cta
              onClick={openCreateForm}
              className="apple-btn apple-btn-primary text-xs py-2 px-3"
            >
              <Plus size={14} weight="fill" />
              {t("inf.add")}
            </button>
          }
        />
      )}

      {!loading && influencers.length > 0 && (
        <div className="grid gap-3">
          {influencers.map((inf) => (
            <div
              key={inf.influencer_id}
              data-asset-card
              data-kind="influencer"
              className="apple-card p-4 hover:shadow-md transition-all duration-200"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0 flex-1">
                  <div className="w-10 h-10 rounded-full bg-[rgba(215,92,112,0.10)] flex items-center justify-center shrink-0">
                    <Users size={20} weight="fill" className="text-[var(--fortune-red)]" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-[var(--text-h1)] truncate">{inf.name}</h3>
                      {!inf.is_active && (
                        <span className="text-[11px] text-[var(--text-muted)] bg-[var(--bg-panel)] px-1.5 py-0.5 rounded">
                          {t("inf.inactive")}
                        </span>
                      )}
                    </div>
                    {inf.handle && (
                      <p className="text-[12px] text-[var(--fortune-red)] font-medium mt-0.5">@{inf.handle}</p>
                    )}
                    {inf.platforms && inf.platforms.length > 0 && (
                      <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                        {inf.platforms.map((platform, i) => (
                          <span
                            key={i}
                            className="text-[11px] text-[var(--fortune-red)] bg-[rgba(215,92,112,0.12)] px-2 py-0.5 rounded-full font-medium"
                          >
                            {platform}
                          </span>
                        ))}
                      </div>
                    )}
                    {inf.style_tags && inf.style_tags.length > 0 && (
                      <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                        {inf.style_tags.map((tag, i) => (
                          <span key={i} className="text-[11px] text-[var(--text-body)] bg-[var(--bg-panel)] px-2 py-0.5 rounded-full">
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                    {inf.notes && (
                      <p className="text-[12px] text-[var(--text-body)] mt-1.5 line-clamp-1">{inf.notes}</p>
                    )}
                    <span className="text-[11px] text-[var(--text-muted)] block mt-1.5">
                      {t("inf.createdAt")} {formatDate(inf.created_at)}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => openEditForm(inf)}
                    className="p-2 rounded-lg text-[var(--text-body)] hover:text-[var(--fortune-red)] hover:bg-[rgba(215,92,112,0.05)] transition-all cursor-pointer"
                    aria-label={t("inf.editTooltip")}
                  >
                    <PencilSimple size={16} weight="fill" />
                  </button>
                  <button
                    onClick={() => setDeleteConfirm(inf.influencer_id)}
                    className="p-2 rounded-lg text-[var(--text-body)] hover:text-[var(--crimson-mist)] hover:bg-[rgba(196,91,80,0.05)] transition-all cursor-pointer"
                    aria-label={t("inf.deleteTooltip")}
                  >
                    <Trash size={16} weight="fill" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="apple-card w-full max-w-lg mx-4 p-5 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">
                {editingId ? t("inf.editProfile") : t("inf.addProfile")}
              </h2>
              <button
                onClick={() => setShowForm(false)}
                className="p-1 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-h1)] hover:bg-[var(--bg-panel)] transition-all cursor-pointer"
                aria-label="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label htmlFor="inf-name" className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                  {t("inf.nameRequired")}
                </label>
                <input
                  id="inf-name"
                  name="name"
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder={t("inf.namePlaceholder")}
                  className="apple-input text-sm"
                />
              </div>

              <div>
                <label htmlFor="inf-handle" className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                  {t("inf.handle")}
                </label>
                <input
                  id="inf-handle"
                  name="handle"
                  type="text"
                  value={formHandle}
                  onChange={(e) => setFormHandle(e.target.value)}
                  placeholder={t("inf.handlePlaceholder")}
                  className="apple-input text-sm"
                />
                <p className="text-[11px] text-[var(--text-muted)] mt-0.5">{t("inf.handleHint")}</p>
              </div>

              <div>
                <label htmlFor="inf-platforms" className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                  {t("inf.platforms")}
                </label>
                <TagInput
                  id="inf-platforms"
                  name="platforms"
                  value={formPlatforms}
                  onChange={setFormPlatforms}
                  placeholder={t("inf.platformsPlaceholder")}
                  ariaLabel={t("inf.platforms")}
                  ariaDescribedBy="inf-platforms-hint"
                />
                <p id="inf-platforms-hint" className="text-[11px] text-[var(--text-muted)] mt-0.5">{t("inf.platformsHint")}</p>
              </div>

              <div>
                <label htmlFor="inf-style" className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                  {t("inf.styleTags")}
                </label>
                <TagInput
                  id="inf-style"
                  name="style_tags"
                  value={formStyleTags}
                  onChange={setFormStyleTags}
                  placeholder={t("inf.styleTagsPlaceholder")}
                  ariaLabel={t("inf.styleTags")}
                  ariaDescribedBy="inf-style-hint"
                />
                <p id="inf-style-hint" className="text-[11px] text-[var(--text-muted)] mt-0.5">{t("inf.styleTagsHint")}</p>
              </div>

              <div>
                <label htmlFor="inf-notes" className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                  {t("inf.notes")}
                </label>
                <textarea
                  id="inf-notes"
                  name="notes"
                  value={formNotes}
                  onChange={(e) => setFormNotes(e.target.value)}
                  placeholder={t("inf.notesPlaceholder")}
                  className="apple-input resize-none text-sm"
                  rows={3}
                />
              </div>

              <div className="flex items-center gap-2">
                <label htmlFor="inf-active" className="relative inline-flex items-center cursor-pointer">
                  <input
                    id="inf-active"
                    name="is_active"
                    type="checkbox"
                    checked={formIsActive}
                    onChange={(e) => setFormIsActive(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-8 h-4.5 bg-[rgba(215,92,112,0.18)] rounded-full peer peer-checked:bg-[var(--fortune-red)] transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:w-3.5 after:h-3.5 after:bg-white after:rounded-full after:transition-all peer-checked:after:translate-x-3.5" />
                </label>
                <span className="text-[12px] text-[var(--text-body)] font-medium">{t("inf.active")}</span>
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-5 pt-3 border-t border-[rgba(215,92,112,0.18)]">
              <button
                onClick={() => setShowForm(false)}
                className="apple-btn text-xs py-2 px-3"
                disabled={saving}
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !formName.trim()}
                className="apple-btn apple-btn-primary text-xs py-2 px-3"
              >
                {saving ? (
                  <span className="flex items-center gap-1.5">
                    <Spinner size={12} weight="fill" className="animate-spin" />
                    {t("common.loading")}
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5">
                    <Users className="w-3.5 h-3.5" />
                    {editingId ? t("brand.update") : t("common.create")}
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="apple-card p-5 max-w-sm mx-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-8 h-8 rounded-full bg-[rgba(196,91,80,0.10)] flex items-center justify-center">
                <WarningCircle size={16} weight="fill" className="text-[var(--crimson-mist)]" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-[var(--text-h1)]">{t("inf.deleteConfirm")}</h3>
                <p className="text-[12px] text-[var(--text-body)]">{t("inf.deleteHint")}</p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="apple-btn text-xs py-2 px-3"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={() => handleDelete(deleteConfirm)}
                className="apple-btn apple-btn-danger text-xs py-2 px-3"
              >
                <Trash size={14} weight="fill" />
                {t("common.delete")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
