"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  onEnter: () => void;
}

const SCENE_CARDS = [
  { emoji: "📦", name: "商品直拍", desc: "输入产品名+卖点，AI 自动生成策略、脚本、视频、缩略图。适合电商产品快速出片。" },
  { emoji: "🎬", name: "品牌宣传片", desc: "品牌形象大片，统一视觉调性。含合规检查+4 道人工审核关口。" },
  { emoji: "📱", name: "网红二创", desc: "已有视频素材 → AI 重混脚本 → 嵌入商品链接 → 多平台分发。" },
  { emoji: "🎥", name: "实拍素材生成", desc: "上传实拍素材，AI 自动添加旁白、字幕和品牌包装。" },
  { emoji: "📹", name: "品牌VLOG", desc: "六视图+模特角色+空间场景+故事描述 → AI 生成分镜 → 逐镜出片。" },
  { emoji: "⚡", name: "快速模式", desc: "一句话描述，10-15 秒快速测试大模型矩阵能力。" },
];

const DESIGN_PHILOSOPHY = [
  { icon: "🎯", title: "教练式引导", desc: "每张输入卡片都会告诉你「为什么填」和「填了会怎样」。不只是表单——是你的视频创作教练，一步步带你完成策略构思。" },
  { icon: "🔄", title: "信息只填一次", desc: "从输入到生成到发布到复盘，同一份信息全链路自动流转。选了品牌形象片，后面的发布平台和数据看板都自动适配。" },
  { icon: "📐", title: "方法论内置", desc: "🎯定主角 → 💡找冲突 → 🎨定调性 → 🎬选舞台 → 🔍找差异。完成每一步，你也在学会如何策划一条好视频。" },
  { icon: "📊", title: "按目标衡量成功", desc: "品牌片和种草片不该用同一把尺。我们自动根据你选的视频类型，展示不同的数据指标和优化建议。" },
];

const NOTICES = [
  { title: "API 连接", desc: "首次使用需检查后端连接。点击顶栏 ⚙ 设置 → 测试连接，确认返回 OK。Demo 模式无需配置。" },
  { title: "中途中止", desc: "长等待中点击「取消」可中断当前步骤。Expert Studio 模式保留已完成步骤，Smart Create 尝试恢复部分结果。" },
  { title: "生成质量", desc: "卖点写得越具体、品牌语气定义越清晰，AI 产出质量越高。Expert Studio 每步可重做优化。" },
  { title: "时长限制", desc: "Happy Horse 视频模型单次最长 15 秒。长片会自动拆分为多段拼接。配音由 CosyVoice 生成。" },
  { title: "视频版权", desc: "AI 生成视频仅供品牌内部使用和营销投放。二次分发请遵守平台内容政策。" },
];

export default function SplashScreen({ onEnter }: Props) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(true);
  const [animating, setAnimating] = useState(true);
  const [showGuide, setShowGuide] = useState(false);
  const [showBlueprint, setShowBlueprint] = useState(false);

  const handleEnter = () => {
    setAnimating(false);
    setTimeout(() => { setVisible(false); onEnter(); }, 600);
  };
  if (!visible) return null;

  const btnBase =
    "px-5 py-2.5 rounded-[24px] text-[14px] font-medium cursor-pointer " +
    "transition-all duration-300 ease-out bg-[var(--bg-hover)] text-[var(--text-h2)] border border-[var(--border-default)] " +
    "hover:bg-[var(--bg-panel)] hover:border-[var(--border-hover-strong)] active:scale-[0.98]";

  return (
    <div
      className={`fixed inset-0 z-[100] flex flex-col items-center justify-center transition-opacity duration-700 ease-in-out ${
        animating ? "opacity-100" : "opacity-0 pointer-events-none"
      }`}
      style={{ background: "radial-gradient(ellipse at 30% 20%, rgba(215,92,112,0.10) 0%, #FDF8F6 55%, #FCF5F2 100%)" }}
    >

      {/* Main */}
      <div className="relative z-10 flex flex-col items-center gap-5 md:gap-7 px-6 text-center">
        <div className="animate-splash-in px-4 py-1.5 rounded-full bg-[rgba(215,92,112,0.12)] border border-[rgba(215,92,112,0.18)]" style={{ animationDelay: "0ms" }}>
          <span className="text-[12px] font-semibold tracking-wider text-[var(--fortune-red)]">{t("app.title")}</span>
        </div>
        <div className="animate-splash-in" style={{ animationDelay: "80ms" }}>
          <h1 className="text-[52px] md:text-[64px] font-medium tracking-[0.02em] text-[var(--text-h1)] leading-none" style={{ fontFamily: "'Montserrat', -apple-system, sans-serif" }}>Momcozy</h1>
        </div>
        <div className="animate-splash-in flex flex-col items-center gap-2" style={{ animationDelay: "160ms" }}>
          <div className="w-10 h-0.5 rounded-full bg-[var(--fortune-red)] opacity-60" />
          <p className="text-[18px] leading-relaxed text-[var(--text-body)] pt-1" style={{ fontFamily: "'Noto Sans SC', 'PingFang SC', -apple-system, sans-serif" }}>{t("splash.sloganZh")}</p>
          <p className="text-[14px] text-[var(--text-muted)]" style={{ fontFamily: "'Inter', -apple-system, sans-serif" }}>Evolving for Mom and Cozy</p>
        </div>
        <p className="animate-splash-in text-[12px] text-[var(--text-placeholder)]" style={{ animationDelay: "200ms" }}>{t("splash.departmentCredit")}</p>
      </div>

      {/* CTA */}
      <div className="animate-splash-in absolute bottom-[12%] flex flex-wrap items-center justify-center gap-3 px-4" style={{ animationDelay: "280ms" }}>
        <button className={btnBase} onClick={() => setShowGuide(true)}>{t("splash.creationGuide")}</button>
        <button onClick={handleEnter} className="px-8 py-3 rounded-[24px] text-[16px] font-medium cursor-pointer transition-all duration-300 ease-out bg-[var(--fortune-red)] text-white border border-[var(--fortune-red)] hover:bg-[var(--fortune-red-600)] hover:border-[var(--fortune-red-600)] hover:scale-[1.02] active:scale-[0.98] shadow-lg">{t("splash.enter")}</button>
        <button className={btnBase} onClick={() => setShowBlueprint(true)}>{t("splash.blueprint")}</button>
      </div>

      {/* ═══ GUIDE OVERLAY ═══ */}
      {showGuide && (
        <div className="absolute inset-0 z-50 overflow-y-auto bg-[var(--cinema-black)]" style={{ fontFamily: "'Inter', 'Noto Sans SC', -apple-system, sans-serif" }}>
          {/* Sticky header */}
          <div className="sticky top-0 z-20 flex items-center justify-between px-6 md:px-12 py-4 bg-[var(--cinema-black)]/90 backdrop-blur-md border-b border-[var(--border-default)]">
            <h2 className="text-[16px] font-semibold text-[var(--text-h1)]">{t("app.title")} · {t("splash.creationGuide")}</h2>
            <button onClick={() => setShowGuide(false)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[13px] font-medium text-[var(--text-muted)] hover:bg-[rgba(215,92,112,0.10)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
              返回
            </button>
          </div>

          <div className="max-w-4xl mx-auto px-6 md:px-12 py-8 space-y-12 pb-20">
            {/* ── Hero ── */}
            <div className="text-center space-y-3 py-6">
              <h1 className="text-[28px] md:text-[36px] font-semibold text-[var(--text-h1)] tracking-tight">AI 视频创作平台</h1>
              <p className="text-[14px] text-[var(--text-body)] max-w-2xl mx-auto leading-relaxed">
                面向品牌营销团队的智能视频生产工具。输入产品信息和创作方向，AI 自动完成策略生成、脚本撰写、视频生成、配音配乐、质量审计——从创意到成片，全链路自动化。
              </p>
              <div className="flex flex-wrap justify-center gap-2 pt-2">
                {["DeepSeek-V4-Pro 文本", "GPT-4o Image 图像", "Happy Horse 视频", "CosyVoice2 语音"].map(m => (
                  <span key={m} className="px-3 py-1 rounded-full bg-[rgba(215,92,112,0.10)] text-[12px] font-medium text-[var(--fortune-red)] border border-[rgba(215,92,112,0.18)]">{m}</span>
                ))}
              </div>
            </div>

            {/* ── 6 Scenes ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[var(--text-h1)] mb-4">视频创作场景</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {SCENE_CARDS.map(s => (
                  <div key={s.name} className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] hover:border-[var(--fortune-red)] transition-colors">
                    <div className="text-lg mb-1">{s.emoji}</div>
                    <div className="text-[14px] font-semibold text-[var(--text-h1)]">{s.name}</div>
                    <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1">{s.desc}</div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── Modes ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[var(--text-h1)] mb-4">两种操作模式</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-5 rounded-xl bg-gradient-to-br from-[rgba(215,92,112,0.14)] to-[rgba(215,92,112,0.06)] border border-[rgba(215,92,112,0.20)]">
                  <div className="text-[15px] font-semibold text-[var(--fortune-red)]">Smart Create 一键模式</div>
                  <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-2">
                    选场景 → 填信息 → 点生成。AI 做全部决策，适合快速验证、批量生产。30s-5min 等待后直接查看完整结果。
                  </div>
                </div>
                <div className="p-5 rounded-xl bg-gradient-to-br from-[rgba(220,190,120,0.12)] to-[rgba(215,92,112,0.06)] border border-[rgba(220,190,120,0.20)]">
                  <div className="text-[15px] font-semibold text-[var(--gold-foil)]">Expert Studio 逐步模式</div>
                  <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-2">
                    12 个步骤逐步执行，每步可查看、编辑、重做。4 个 Gate 关口自动暂停等待审核。适合需要精细控制和品牌审查的场景。
                  </div>
                </div>
              </div>
            </section>

            {/* ── Design Philosophy ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[var(--text-h1)] mb-4">设计理念</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {DESIGN_PHILOSOPHY.map((p, i) => (
                  <div key={i} className="p-4 rounded-xl bg-gradient-to-br from-[var(--film-reel)] to-[rgba(215,92,112,0.04)] border border-[var(--border-default)]">
                    <div className="text-lg mb-1">{p.icon}</div>
                    <div className="text-[14px] font-semibold text-[var(--text-h1)]">{p.title}</div>
                    <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-1">{p.desc}</div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── Examples ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[var(--text-h1)] mb-4">场景示例 · 输入参考</h3>
              <p className="text-[12px] text-[var(--text-muted)] mb-4 leading-relaxed">以下示例基于 Momcozy M5 穿戴式吸奶器，展示每种场景的实际输入方式。直接参考填入即可获得高质量产出。</p>
              <div className="space-y-4">
                {/* 商品直拍 */}
                <div className="rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] overflow-hidden">
                  <div className="px-5 py-3 bg-[rgba(215,92,112,0.10)] border-b border-[var(--border-default)] text-[13px] font-semibold text-[var(--fortune-red)]">📦 商品直拍</div>
                  <div className="p-5 space-y-2 text-[12px] text-[var(--text-body)]">
                    <div><span className="font-semibold text-[var(--text-h1)]">产品名称:</span> M5 Wearable Breast Pump</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">品牌名:</span> Momcozy</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">核心卖点:</span> &quot;免手扶穿戴式设计 · 3 秒快速佩戴 · 静音马达 &lt; 35dB · 轻量通勤可放入内衣 · APP 智能控制&quot;</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">使用场景(高级):</span> &quot;职场妈妈通勤泵奶、夜间低噪不惊扰宝宝、出差途中单手操作&quot;</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">痛点(高级):</span> &quot;传统吸奶器线缆杂乱、体积大不便携、噪音尴尬影响睡眠&quot;</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">品牌语气 Do:</span> &quot;温柔、真实、像妈妈之间分享使用心得&quot;</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">品牌语气 Don&apos;t:</span> &quot;不用&apos;革命性&apos;、&apos;全球首创&apos;等夸大词&quot;</div>
                  </div>
                </div>
                {/* 品牌VLOG */}
                <div className="rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] overflow-hidden">
                  <div className="px-5 py-3 bg-[rgba(220,190,120,0.10)] border-b border-[var(--border-default)] text-[13px] font-semibold text-[var(--gold-foil)]">📹 品牌VLOG</div>
                  <div className="p-5 space-y-2 text-[12px] text-[var(--text-body)]">
                    <div><span className="font-semibold text-[var(--text-h1)]">品牌:</span> Momcozy · 产品SKU: M5 Breast Pump（选定后自动回填六视图）</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">场景:</span> 客厅</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">模特:</span> 多选 — Ava(母亲) + Noah(婴儿)</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">故事描述:</span> &quot;以年轻母亲在客厅使用 M5 为核心，穿插婴儿安静入睡的镜头。开场 3 秒展示 M5 主视图建立产品认知，中段切换过肩镜头展示职场妈妈单手操作泵奶，背景婴儿在沙发安睡，突出免手扶和静音卖点。结尾品牌收尾——&apos;为妈妈的舒适不断进化&apos;——妈妈抱着宝宝微笑。&quot;</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">时长:</span> 30-45s（加长）</div>
                  </div>
                </div>
                {/* 网红二创 */}
                <div className="rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] overflow-hidden">
                  <div className="px-5 py-3 bg-[rgba(215,92,112,0.10)] border-b border-[var(--border-default)] text-[13px] font-semibold text-[var(--fortune-red)]">📱 网红二创</div>
                  <div className="p-5 space-y-2 text-[12px] text-[var(--text-body)]">
                    <div><span className="font-semibold text-[var(--text-h1)]">视频URL:</span> 员工/KOL 原始口播视频链接</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">产品:</span> M5 Wearable Breast Pump</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">网红名称:</span> Sophie（可选）</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">说明:</span> 上传已有员工或 KOL 的产品讲解视频 → AI 提取核心卖点 → 重混脚本 → 嵌入 Shopee/Amazon 产品链接 → 批量分发多平台</div>
                  </div>
                </div>
                {/* 快速模式 */}
                <div className="rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] overflow-hidden">
                  <div className="px-5 py-3 bg-[rgba(220,190,120,0.10)] border-b border-[var(--border-default)] text-[13px] font-semibold text-[var(--gold-foil)]">⚡ 快速模式</div>
                  <div className="p-5 space-y-2 text-[12px] text-[var(--text-body)]">
                    <div><span className="font-semibold text-[var(--text-h1)]">描述:</span> &quot;Wearable breast pump, silent motor, mom using it in living room while baby sleeps nearby, natural warm light, cozy home atmosphere&quot;</div>
                    <div><span className="font-semibold text-[var(--text-h1)]">时长:</span> 10s · <span className="font-semibold text-[var(--text-h1)]">说明:</span> 直接测试大模型矩阵，不走完整 pipeline，10-15s 快速验证视频质量</div>
                  </div>
                </div>
              </div>
            </section>

            {/* ── Scene-specific SOP ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[var(--text-h1)] mb-2">各场景操作 SOP</h3>
              <p className="text-[12px] text-[var(--text-muted)] mb-4 leading-relaxed">不同场景的操作流程有差异，请按场景查阅对应 SOP。</p>
              <div className="space-y-4">
                {[
                  { emoji:"📦", name:"商品直拍", color:"rgba(215,92,112,0.10)", titleColor:"var(--fortune-red)",
                    steps:[
                      "① 输入产品名称、品牌名、核心卖点（每行一个）",
                      "②（可选）展开高级设置：使用场景、用户痛点、竞品对比、品牌语气 Do/Don't",
                      "③ 选择模式：Smart Create 全自动 / Expert Studio 逐步控制",
                      "④ Smart Create：点击「开始生成」→ 等待 12 步完成 → 查看结果",
                      "⑤ Expert Studio：逐步点击「执行此步」→ 每步可查看/编辑/重做 → 4 个 Gate 关口审核 → 完成",
                    ]
                  },
                  { emoji:"🎬", name:"品牌宣传片", color:"rgba(220,190,120,0.10)", titleColor:"var(--gold-foil)",
                    steps:[
                      "① 选择品牌规范包（从品牌资产页面预先创建）",
                      "② 输入活动主题、关键信息、目标受众",
                      "③（可选）展开高级：活动目标、品牌价值观、视觉风格、竞品活动",
                      "④ Smart Create 一键执行 / Expert Studio 逐步审核",
                      "⑤ 品牌宣传片有 4 道人工审核（策略→脚本→成片→缩略图），每道需点击「通过」继续",
                    ]
                  },
                  { emoji:"📱", name:"网红二创", color:"rgba(215,92,112,0.10)", titleColor:"var(--fortune-red)",
                    steps:[
                      "① 输入现有视频 URL（员工/KOL 原始口播素材）",
                      "② 输入要关联的产品名称",
                      "③（可选）输入网红名称、保留原音频开关",
                      "④ AI 自动分析原视频 → 生成重混脚本 → 嵌入产品链接",
                      "⑤ 产出多平台适配版本（Shopify/Amazon/TikTok/Reddit）",
                    ]
                  },
                  { emoji:"📹", name:"品牌VLOG", color:"rgba(220,190,120,0.10)", titleColor:"var(--gold-foil)",
                    steps:[
                      "① 选择品牌规范 + 产品 SKU（选定后六视图自动回填）",
                      "② 选择空间场景（6 选 1：职场/客厅/卧室/儿童房/户外/厨房）",
                      "③ 选择模特角色（支持多选：母亲/父亲/婴儿/孕妈/护理师/父母双人）",
                      "④ 输入故事描述（≤300字，描述人物动作+情绪+卖点节奏+结尾指令）",
                      "⑤ 选择视频时长（5-15s / 15-30s / 30-45s / 45-60s / 60-90s）",
                      "⑥ 点击「AI生成视频」→ AI 根据六视图+模特+场景+故事生成分镜脚本 → 逐镜出片",
                    ]
                  },
                  { emoji:"🎥", name:"实拍素材生成", color:"rgba(215,92,112,0.10)", titleColor:"var(--fortune-red)",
                    steps:[
                      "① 上传实拍素材文件（视频/图片，支持拖拽）",
                      "② 输入产品信息、主题",
                      "③ AI 分析素材内容 → 自动生成旁白文案 → 同步字幕时间轴",
                      "④ 合成最终成片（含 AI 配音 + 字幕）",
                    ]
                  },
                  { emoji:"⚡", name:"快速模式", color:"rgba(220,190,120,0.10)", titleColor:"var(--gold-foil)",
                    steps:[
                      "① 输入一段描述（中英文均可，建议包含：产品+场景+氛围）",
                      "② 选择时长（10s 或 15s）",
                      "③ 点击「快速生成」→ 直接测试大模型矩阵能力",
                      "④ 不走完整 pipeline，10-15s 快速出片验证效果",
                    ]
                  },
                ].map((s, i) => (
                  <div key={i} className="rounded-xl bg-[var(--bg-card)] border border-[var(--border-default)] overflow-hidden">
                    <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: s.color, borderBottom: "1px solid var(--border-default)" }}>
                      <span>{s.emoji}</span>
                      <span className="text-[13px] font-semibold" style={{ color: s.titleColor }}>{s.name}</span>
                    </div>
                    <div className="p-4 space-y-1.5 text-[12px] text-[var(--text-body)] leading-relaxed">
                      {s.steps.map((st, j) => <div key={j}>{st}</div>)}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── Notices ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[var(--text-h1)] mb-4">注意事项</h3>
              <div className="space-y-2">
                {NOTICES.map((n, i) => (
                  <div key={i} className="flex gap-3 p-4 rounded-xl bg-[var(--film-reel)] border border-[var(--border-default)]">
                    <span className="text-[var(--gold-foil)] text-sm shrink-0 mt-0.5">⚠</span>
                    <div>
                      <div className="text-[13px] font-semibold text-[var(--text-h1)]">{n.title}</div>
                      <div className="text-[12px] text-[var(--text-body)] leading-relaxed mt-0.5">{n.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── Footer CTA ── */}
            <div className="text-center pt-4">
              <button onClick={() => { setShowGuide(false); handleEnter(); }}
                className="px-10 py-3.5 rounded-xl text-[16px] font-semibold text-white bg-[var(--fortune-red)] hover:bg-[var(--neon-red)] active:scale-[0.98] transition-all cursor-pointer shadow-[0_0_24px_rgba(215,92,112,0.35)]">
                {t("splash.enter")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Blueprint IFrame Modal ── */}
      {showBlueprint && (
        <div className="absolute inset-0 z-50 flex flex-col bg-[var(--cinema-black)]">
          <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border-default)] bg-[var(--cinema-black)]/90 backdrop-blur-md">
            <span className="text-[14px] font-semibold text-[var(--text-h1)]">{t("splash.blueprint")}</span>
            <button onClick={() => setShowBlueprint(false)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[13px] font-medium text-[var(--text-muted)] hover:bg-[rgba(215,92,112,0.10)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
              返回
            </button>
          </div>
          <iframe src="https://vozjd5k2equj6.ok.kimi.link" className="flex-1 w-full border-0" title={t("splash.blueprint")} />
        </div>
      )}

      {/* Animations */}
      <style>{`
        .animate-splash-in { opacity: 0; animation: splashSlideUp 500ms ease-out forwards; }
        @keyframes splashSlideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .animate-lens-breathe { animation: lensBreathe 3s ease-in-out infinite; }
        @keyframes lensBreathe { 0%,100% { opacity: 0.5; transform: scale(1); } 50% { opacity: 1; transform: scale(1.06); } }
        .animate-timeline-pulse { animation: timelinePulse 2s ease-in-out infinite; }
        @keyframes timelinePulse { 0%,100% { opacity: 0.45; } 50% { opacity: 0.85; } }
      `}</style>
    </div>
  );
}
