"use client";

import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  brief: any;
  onChange: (updated: any) => void;
}

export default function EditableBrief({ brief, onChange }: Props) {
  const { t } = useI18n();
  const handleChange = (field: string, value: string) => {
    onChange({ ...brief, [field]: value });
  };

  return (
    <div className="apple-card p-3 bg-white space-y-2">
      <div>
        <label className="block text-[10px] font-medium text-[#86868b] mb-0.5">{t("editors.productName")}</label>
        <input
          type="text"
          value={brief.product_name || ""}
          onChange={(e) => handleChange("product_name", e.target.value)}
          className="apple-input text-xs w-full"
          placeholder={t("editors.productName")}
        />
      </div>
      <div>
        <label className="block text-[10px] font-medium text-[#86868b] mb-0.5">{t("editors.description")}</label>
        <textarea
          value={brief.description || ""}
          onChange={(e) => handleChange("description", e.target.value)}
          className="apple-input text-xs w-full resize-none"
          rows={2}
          placeholder={t("editors.description")}
        />
      </div>
      <div>
        <label className="block text-[10px] font-medium text-[#86868b] mb-0.5">{t("editors.key_message")}</label>
        <input
          type="text"
          value={brief.key_message || ""}
          onChange={(e) => handleChange("key_message", e.target.value)}
          className="apple-input text-xs w-full"
          placeholder={t("editors.key_message")}
        />
      </div>
      <div>
        <label className="block text-[10px] font-medium text-[#86868b] mb-0.5">{t("editors.hook_type")}</label>
        <input
          type="text"
          value={brief.hook_type || ""}
          onChange={(e) => handleChange("hook_type", e.target.value)}
          className="apple-input text-xs w-full"
          placeholder={t("editors.hook_type")}
        />
      </div>
    </div>
  );
}
