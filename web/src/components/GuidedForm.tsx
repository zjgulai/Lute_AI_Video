"use client";

import React, { useState, useCallback, useMemo } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import {
  GUIDED_CARD_SEQUENCES,
  SCENE_VIDEO_TYPES,
} from "@/demo-data";
import { CONTENT_SCENARIOS } from "./types";
import type { GuidedCard as GuidedCardType } from "./types";
import GuidedCard from "./GuidedCard";
import CardConnector from "./CardConnector";
import LiveSummary from "./LiveSummary";
import QuickTemplate from "./QuickTemplate";
import StickyActionBar from "./StickyActionBar";
import { CaretRight, Play } from "@phosphor-icons/react";

interface Props {
  scene: string;
  onSubmit: (config: any) => void;
  loading: boolean;
  fieldErrors?: Record<string, string>;
}

export default function GuidedForm({ scene, onSubmit, loading, fieldErrors }: Props) {
  const { t } = useI18n();

  // 视频类型选择
  const videoTypes = SCENE_VIDEO_TYPES[scene] || [];
  const [selectedVideoType, setSelectedVideoType] = useState(
    videoTypes[0]?.id || ""
  );

  // 查找当前场景的卡片序列
  const cardSequence = useMemo(() => {
    return (
      GUIDED_CARD_SEQUENCES.find(
        (s) => s.scene === scene && s.videoType === selectedVideoType
      ) ||
      GUIDED_CARD_SEQUENCES.find((s) => s.scene === scene) || {
        scene,
        videoType: selectedVideoType,
        cards: [],
      }
    );
  }, [scene, selectedVideoType]);

  const cards = cardSequence.cards;

  // 表单值状态
  const [values, setValues] = useState<Record<string, string>>({
    brand_name: "Momcozy",
    brand_id: "momcozy",
  });
  const [focusedIndex, setFocusedIndex] = useState(0);

  // 卡片标签映射（用于 LiveSummary）
  const cardLabels = useMemo(() => {
    const map: Record<string, string> = {};
    cards.forEach((c) => {
      map[c.fieldKey] = c.stepName;
    });
    return map;
  }, [cards]);

  const handleValueChange = useCallback(
    (fieldKey: string, value: string) => {
      setValues((prev) => ({ ...prev, [fieldKey]: value }));
    },
    []
  );

  const handleApplyTemplate = useCallback((presetValues: Record<string, string>) => {
    setValues((prev) => ({ ...prev, ...presetValues }));
  }, []);

  const handleSubmit = useCallback(() => {
    // 构建提交配置
    const config: any = {
      content_scenario: scene,
      content_scenario_subtype: selectedVideoType,
      target_platforms: ["tiktok"],
      target_languages: ["en"],
    };

    // 根据场景组装数据
    if (scene === "product_direct") {
      config.product_catalog = {
        products: [
          {
            name: values.product_name || "",
            usps: (values.key_features || "")
              .split("\n")
              .filter(Boolean)
              .map((text, i) => ({
                priority: i === 0 ? "P0" : i === 1 ? "P1" : "P2",
                text: text.trim(),
              })),
            usage_scenario: values.usage_scenario || "",
            pain_points: [],
            target_audience: values.target_audience || "",
            competitor_context: (values.competitor_context || "")
              .split("\n")
              .filter(Boolean),
          },
        ],
      };
      config.brand_guidelines = {
        brand_name: values.brand_name || "",
        tone_of_voice: {
          archetype: "Caregiver",
          keywords: ["warm", "empowering"],
          do_examples: values.brand_voice
            ? [values.brand_voice]
            : [],
        },
      };
    } else if (scene === "brand_campaign") {
      config.brand_package = values.brand_name || "";
      config.campaign_theme = values.campaign_theme || "";
      config.key_message = values.brand_values || "";
      config.target_audience = values.target_audience || "";
      config.brand_guidelines = {
        brand_name: values.brand_name || "",
        tone_of_voice: {},
        visual_identity: values.visual_identity || "",
      };
      config.product_catalog = { products: [] };
    } else if (scene === "influencer_remix") {
      config.video_url = values.video_url || "";
      config.product_catalog = {
        products: [
          {
            name: values.product_name || "",
            usps: [],
          },
        ],
      };
      config.influencer_name = values.influencer_name || "";
      config.keep_original_audio = values.keep_original_audio === "true";
    } else if (scene === "brand_vlog") {
      config.brand_id = values.brand_id || "momcozy";
      config.scene_id = values.scene_id || "living-room";
      config.selected_models = (values.selected_models || "")
        .split(",")
        .filter(Boolean);
      config.story_description = values.story_description || "";
      config.video_duration = parseInt(values.video_duration || "30");
    } else if (scene === "live_shoot_to_video") {
      config.footage_assets = [];
      config.product_info = { name: values.product_name || "" };
      config.topic = values.topic || "";
    }

    onSubmit(config);
  }, [scene, selectedVideoType, values, onSubmit]);

  // 检查必填项是否完成
  const canSubmit = useMemo(() => {
    const requiredFields = cards
      .filter((c) => c.priority === "required")
      .map((c) => c.fieldKey);
    return requiredFields.every((f) => values[f]?.trim()?.length > 0);
  }, [cards, values]);

  const filledCount = cards.filter(
    (c) => values[c.fieldKey]?.trim()?.length > 0
  ).length;
  const progress = cards.length > 0 ? Math.round((filledCount / cards.length) * 100) : 0;

  const missingFieldLabels = useMemo(() => {
    return cards
      .filter((c) => c.priority === "required" && !values[c.fieldKey]?.trim()?.length)
      .map((c) => c.stepName);
  }, [cards, values]);

  const cardErrors = useMemo(() => {
    const out: Record<string, string> = {};
    if (!fieldErrors) return out;
    const entries = Object.entries(fieldErrors);
    for (const card of cards) {
      const direct = fieldErrors[card.fieldKey];
      if (direct) { out[card.fieldKey] = direct; continue; }
      const match = entries.find(([path]) => {
        const tail = path.split(".").pop() || "";
        return tail === card.fieldKey;
      });
      if (match) out[card.fieldKey] = match[1];
    }
    return out;
  }, [cards, fieldErrors]);

  // 获取连接文字
  const getConnectionText = (index: number): string => {
    if (index >= cards.length - 1) return "";
    return cards[index + 1]?.connectionText || "";
  };

  const scenarioTitle = CONTENT_SCENARIOS.find((s: { id: string; title: string }) => s.id === scene)?.title || scene;

  const progressText = (
    <span>
      <span className="font-semibold text-[var(--text-h1)]">{filledCount}</span>
      <span className="text-[var(--text-muted)]"> / {cards.length}</span>
      <span className="ml-2">{t("step.fields")}</span>
      <span className="ml-3 text-[var(--text-muted)]">·</span>
      <span className="ml-3">{progress}%</span>
    </span>
  );

  return (
    <div data-guided-form className="space-y-3">
      {/* 顶部：场景标题 + 视频类型选择 + 模板 */}
      <div className="apple-card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
              {scenarioTitle}
            </h3>
            <CaretRight size={14} weight="fill" className="text-[var(--color-text-tertiary)]" />
            <span className="text-sm text-[var(--color-accent)]">
              {t("scene.selectVideoType")}
            </span>
          </div>
          <QuickTemplate scene={scene} onApply={handleApplyTemplate} />
        </div>

        {/* 视频类型选择 */}
        {videoTypes.length > 0 && (
          <div
            role="radiogroup"
            aria-label={t("scene.selectVideoType")}
            className="grid grid-cols-2 sm:grid-cols-3 gap-2"
          >
            {videoTypes.map((vt) => (
              <button
                key={vt.id}
                type="button"
                role="radio"
                aria-checked={selectedVideoType === vt.id}
                onClick={() => {
                  setSelectedVideoType(vt.id);
                  setValues({});
                  setFocusedIndex(0);
                }}
                className={`text-left px-3 py-2.5 rounded-xl border transition-all ${
                  selectedVideoType === vt.id
                    ? "border-[var(--fortune-red)] bg-[rgba(215,92,112,0.12)] ring-1 ring-[rgba(215,92,112,0.25)] shadow-[0_0_12px_rgba(215,92,112,0.18)]"
                    : "border-[var(--border-default)] bg-[var(--bg-card)] hover:border-[var(--fortune-red)] hover:bg-[rgba(215,92,112,0.04)]"
                }`}
              >
                <div className="text-xs font-semibold text-[var(--color-text-primary)]">
                  {t(`videoType.${vt.id}`, vt.name)}
                </div>
                <div className="text-[12px] text-[var(--color-text-tertiary)] mt-0.5">
                  {t(`videoTypeDesc.${vt.id}`, vt.desc)}
                </div>
              </button>
            ))}
          </div>
        )}

        <p className="text-[12px] text-[var(--color-text-tertiary)] mt-2">
          {t("scene.videoTypeHint")}
        </p>
      </div>

      {/* 主体：左侧卡片流 + 右侧预览 */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
        {/* 左侧：卡片流 */}
        <div className="space-y-0">
          {cards.map((card: GuidedCardType, index: number) => (
            <React.Fragment key={card.fieldKey}>
              {index > 0 && (
                <CardConnector text={getConnectionText(index - 1)} />
              )}
              <div className="stagger-item" style={{ animationDelay: `${index * 0.05}s` }}>
                <GuidedCard
                  card={card}
                  value={values[card.fieldKey] || ""}
                  onChange={handleValueChange}
                  isFocused={focusedIndex === index}
                  onFocus={() => setFocusedIndex(index)}
                  error={cardErrors[card.fieldKey]}
                />
              </div>
            </React.Fragment>
          ))}

          {cards.length === 0 && (
            <div className="apple-card p-8 text-center text-[var(--color-text-tertiary)]">
              <p className="text-sm">{t("common.empty")}</p>
            </div>
          )}
        </div>

        {/* 右侧：实时预览面板（桌面端） */}
        <div className="hidden lg:block">
          <LiveSummary values={values} cardLabels={cardLabels} />
        </div>
      </div>

      <StickyActionBar
        primaryLabel={
          <span className="flex items-center gap-2">
            <Play size={14} weight="fill" />
            {t("sceneForm.continue")}
          </span>
        }
        onPrimary={handleSubmit}
        disabled={!canSubmit}
        loading={loading}
        missingFields={missingFieldLabels}
        missingLabel={t("form.stillNeed")}
        progressText={progressText}
      />
    </div>
  );
}
