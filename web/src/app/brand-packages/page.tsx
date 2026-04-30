"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { API_BASE, isDemoMode } from "@/components/api";
import { Package, Upload, Edit, Trash2, Plus, X, AlertCircle, Loader2 } from "lucide-react";

interface BrandPackage {
  package_id: string;
  name: string;
  description?: string;
  brand_name?: string;
  guidelines?: string;
  created_at: string;
  updated_at: string;
  logo_url?: string;
  primary_color?: string;
  secondary_color?: string;
  assets?: string[];
}

export default function BrandPackagesPage() {
  const { t } = useI18n();
  const [packages, setPackages] = useState<BrandPackage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form state
  const [formName, setFormName] = useState("");
  const [formBrandName, setFormBrandName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formGuidelines, setFormGuidelines] = useState("");

  const fetchPackages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(API_BASE + "/api/assets/brand-packages", {
        headers: { "X-API-Key": "ai_video_demo_2026" },
      });
      if (!res.ok) throw new Error(`${t("common.fetchFailed")} (${res.status})`);
      const data = await res.json();
      setPackages(data.packages || []);
    } catch (e: any) {
      setError(e.message || t("common.fetchFailed"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Demo mode: skip API, load mock data
    if (isDemoMode()) {
      import("@/demo-data").then((mod) => {
        setPackages(mod.DEMO_BRAND_PACKAGES || []);
        setLoading(false);
      });
      return;
    }
    fetchPackages();
  }, [fetchPackages]);

  const openCreateForm = () => {
    setEditingId(null);
    setFormName("");
    setFormBrandName("");
    setFormDescription("");
    setFormGuidelines("");
    setUploadedFiles([]);
    setShowForm(true);
  };

  const openEditForm = (pkg: BrandPackage) => {
    setEditingId(pkg.package_id);
    setFormName(pkg.name || "");
    setFormBrandName(pkg.brand_name || "");
    setFormDescription(pkg.description || "");
    setFormGuidelines(pkg.guidelines || "");
    setUploadedFiles([]);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!formName.trim()) return;
    if (isDemoMode()) {
      setError("Demo mode — create/edit is not available");
      setShowForm(false);
      return;
    }
    setSaving(true);
    try {
      const body: any = {
        name: formName.trim(),
        brand_name: formBrandName.trim() || undefined,
        description: formDescription.trim() || undefined,
        guidelines: formGuidelines.trim() || undefined,
      };

      if (editingId) {
        const res = await fetch(API_BASE + "/api/assets/brand-packages/" + editingId, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "X-API-Key": "ai_video_demo_2026" },
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`${t("common.updateFailed")} (${res.status})`);
      } else {
        const res = await fetch(API_BASE + "/api/assets/brand-packages", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-API-Key": "ai_video_demo_2026" },
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`${t("common.createFailed")} (${res.status})`);
      }

      // Upload files if any
      for (const file of uploadedFiles) {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("tags", "brand-asset");
        await fetch(API_BASE + "/api/assets/upload", {
          method: "POST",
          headers: { "X-API-Key": "ai_video_demo_2026" },
          body: formData,
        });
      }

      setShowForm(false);
      await fetchPackages();
    } catch (e: any) {
      setError(e.message || t("common.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (packageId: string) => {
    if (isDemoMode()) {
      setError("Demo mode — delete is not available");
      setDeleteConfirm(null);
      return;
    }
    try {
      const res = await fetch(API_BASE + "/api/assets/brand-packages/" + packageId, {
        method: "DELETE",
        headers: { "X-API-Key": "ai_video_demo_2026" },
      });
      if (!res.ok) throw new Error(`${t("common.deleteFailed")} (${res.status})`);
      setDeleteConfirm(null);
      await fetchPackages();
    } catch (e: any) {
      setError(e.message || t("common.deleteFailed"));
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    setUploadedFiles((prev) => [...prev, ...files]);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    setUploadedFiles((prev) => [...prev, ...files]);
  };

  const removeFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return "-";
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#7CB342]/10 flex items-center justify-center">
              <Package className="w-5 h-5 text-[#7CB342]" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[#1d1d1f]">{t("brand.manageTitle")}</h1>
              <p className="text-[11px] text-[#86868b] mt-0.5">
                {t("brand.manageDesc")}
              </p>
            </div>
          </div>
          <button
            onClick={openCreateForm}
            className="apple-btn apple-btn-primary text-xs py-2 px-3"
          >
            <Plus className="w-3.5 h-3.5" />
            {t("brand.create")}
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="apple-card p-3 border-l-4 border-[#ff453a] bg-[#fff5f5] flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-[#ff453a] shrink-0" />
            <span className="text-xs text-[#ff453a] font-medium">{error}</span>
            <button
              onClick={() => setError(null)}
              className="ml-auto text-[#ff453a] hover:opacity-70 cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div className="apple-card p-12 text-center">
            <Loader2 className="w-8 h-8 text-[#7CB342] mx-auto mb-3 animate-spin" />
            <p className="text-sm text-[#86868b]">{t("brand.loading")}</p>
          </div>
        )}

        {/* Empty state — branded */}
        {!loading && packages.length === 0 && (
          <div className="apple-card p-12 text-center" style={{background: "linear-gradient(180deg, rgba(124,179,66,0.03) 0%, #fff 100%)"}}>
            <div className="w-14 h-14 rounded-2xl bg-[#7CB342]/10 flex items-center justify-center mx-auto mb-4">
              <Package className="w-7 h-7 text-[#7CB342]" strokeWidth={1.5} />
            </div>
            <h3 className="text-base font-semibold text-[#1d1d1f] mb-1">{t("brand.empty")}</h3>
            <p className="text-sm text-[#86868b] mb-5 max-w-xs mx-auto leading-relaxed">{t("brand.emptyHint")}</p>
            <button
              onClick={openCreateForm}
              className="apple-btn apple-btn-primary text-sm py-2.5 px-5"
            >
              <Plus className="w-4 h-4" />
              {t("brand.create")}
            </button>
          </div>
        )}

        {/* Package list */}
        {!loading && packages.length > 0 && (
          <div className="grid gap-3">
            {packages.map((pkg) => {
              const assetCount = pkg.assets?.length || 0;
              return (
                <div
                  key={pkg.package_id}
                  className="apple-card p-4 hover:shadow-md transition-all duration-200"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="w-10 h-10 rounded-xl bg-[#7CB342]/10 flex items-center justify-center shrink-0">
                        <Package className="w-5 h-5 text-[#7CB342]" />
                      </div>
                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold text-[#1d1d1f] truncate">
                          {pkg.name}
                        </h3>
                        {pkg.brand_name && (
                          <p className="text-[11px] text-[#7CB342] font-medium mt-0.5">
                            {pkg.brand_name}
                          </p>
                        )}
                        {pkg.description && (
                          <p className="text-xs text-[#86868b] mt-1 line-clamp-2">
                            {pkg.description}
                          </p>
                        )}
                        <div className="flex items-center gap-3 mt-2">
                          <span className="text-[10px] text-[#aeaeb2] flex items-center gap-1">
                            <Package className="w-3 h-3" />
                            {assetCount}{t("brand.assetCount")}
                          </span>
                          <span className="text-[10px] text-[#aeaeb2]">
                            {t("brand.updatedAt")} {formatDate(pkg.updated_at)}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => openEditForm(pkg)}
                        className="p-2 rounded-lg text-[#86868b] hover:text-[#7CB342] hover:bg-[#7CB342]/5 transition-all cursor-pointer"
                        title={t("brand.editTooltip")}
                      >
                        <Edit className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setDeleteConfirm(pkg.package_id)}
                        className="p-2 rounded-lg text-[#86868b] hover:text-[#ff453a] hover:bg-[#ff453a]/5 transition-all cursor-pointer"
                        title={t("brand.deleteTooltip")}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Create/Edit Form Modal */}
        {showForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <div className="apple-card w-full max-w-lg mx-4 p-5 max-h-[85vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-[#1d1d1f]">
                  {editingId ? t("brand.editPackage") : t("brand.newPackage")}
                </h2>
                <button
                  onClick={() => setShowForm(false)}
                  className="p-1 rounded-lg text-[#aeaeb2] hover:text-[#1d1d1f] hover:bg-[#f5f5f7] transition-all cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3">
                {/* Brand package name */}
                <div>
                  <label className="block text-[11px] font-medium text-[#86868b] mb-1">
                    {t("brand.packageNameRequired")}
                  </label>
                  <input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder={t("brand.packageNamePlaceholder")}
                    className="apple-input text-sm"
                  />
                </div>

                {/* Brand name */}
                <div>
                  <label className="block text-[11px] font-medium text-[#86868b] mb-1">
                    {t("brand.brandName")}
                  </label>
                  <input
                    type="text"
                    value={formBrandName}
                    onChange={(e) => setFormBrandName(e.target.value)}
                    placeholder={t("brand.brandNamePlaceholder")}
                    className="apple-input text-sm"
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="block text-[11px] font-medium text-[#86868b] mb-1">
                    {t("brand.description")}
                  </label>
                  <input
                    type="text"
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    placeholder={t("brand.descriptionPlaceholder")}
                    className="apple-input text-sm"
                  />
                </div>

                {/* Guidelines textarea */}
                <div>
                  <label className="block text-[11px] font-medium text-[#86868b] mb-1">
                    {t("brand.guidelinesLabel")}
                  </label>
                  <textarea
                    value={formGuidelines}
                    onChange={(e) => setFormGuidelines(e.target.value)}
                    placeholder={t("brand.guidelinesPlaceholder")}
                    className="apple-input resize-none text-sm"
                    rows={4}
                  />
                  <p className="text-[10px] text-[#aeaeb2] mt-0.5">
                    {t("brand.guidelinesHint")}
                  </p>
                </div>

                {/* File upload zone */}
                <div>
                  <label className="block text-[11px] font-medium text-[#86868b] mb-1">
                    {t("brand.uploadAssets")}
                  </label>
                  <div
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                      dragOver
                        ? "border-[#7CB342] bg-[#7CB342]/5"
                        : "border-[#e8e8ed] hover:border-[#d2d2d7] hover:bg-[#fafafc]"
                    }`}
                  >
                    <Upload className="w-6 h-6 text-[#aeaeb2] mx-auto mb-2" />
                    <p className="text-xs text-[#86868b] font-medium">
                      {t("brand.dragUpload")}
                    </p>
                    <p className="text-[10px] text-[#aeaeb2] mt-1">
                      {t("brand.supportedFormats")}
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      accept="image/*,video/*"
                      onChange={handleFileSelect}
                      className="hidden"
                    />
                  </div>
                </div>

                {/* Uploaded files list */}
                {uploadedFiles.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[10px] font-medium text-[#86868b]">
                      {t("brand.filesSelected")} {uploadedFiles.length}{t("brand.filesCount")}
                    </p>
                    <div className="space-y-1 max-h-[120px] overflow-y-auto">
                      {uploadedFiles.map((file, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between px-2 py-1 rounded-lg bg-[#f5f5f7]"
                        >
                          <span className="text-[10px] text-[#1d1d1f] truncate">
                            {file.name}
                          </span>
                          <button
                            onClick={() => removeFile(i)}
                            className="text-[#aeaeb2] hover:text-[#ff453a] transition-colors cursor-pointer shrink-0 ml-2"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Form actions */}
              <div className="flex justify-end gap-2 mt-5 pt-3 border-t border-[#e8e8ed]">
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
                      <Loader2 className="w-3 h-3 animate-spin" />
                      {t("common.loading")}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5">
                      <Package className="w-3.5 h-3.5" />
                      {editingId ? t("brand.update") : t("common.create")}
                    </span>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Delete confirmation dialog */}
        {deleteConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <div className="apple-card p-5 max-w-sm mx-4">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-8 h-8 rounded-full bg-[#ff453a]/10 flex items-center justify-center">
                  <AlertCircle className="w-4 h-4 text-[#ff453a]" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-[#1d1d1f]">{t("brand.deleteConfirm")}</h3>
                  <p className="text-[11px] text-[#86868b]">
                    {t("brand.deleteHint")}
                  </p>
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
                  <Trash2 className="w-3.5 h-3.5" />
                  {t("common.delete")}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
