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
    "transition-all duration-300 ease-out bg-white/8 text-white border border-white/12 " +
    "hover:bg-white/15 hover:border-white/25 active:scale-[0.98]";

  return (
    <div
      className={`fixed inset-0 z-[100] flex flex-col items-center justify-center transition-opacity duration-700 ease-in-out ${
        animating ? "opacity-100" : "opacity-0 pointer-events-none"
      }`}
      style={{ background: "radial-gradient(ellipse at 30% 20%, #B27A7E 0%, #8A4A5A 45%, #6A2B3A 100%)" }}
    >
      {/* Film grain */}
      <div className="absolute inset-0 pointer-events-none" style={{
        backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E\")",
        backgroundSize: "256px 256px",
      }} />

      {/* Main */}
      <div className="relative z-10 flex flex-col items-center gap-5 md:gap-7 px-6 text-center">
        <div className="animate-splash-in px-4 py-1.5 rounded-full bg-white/8 border border-white/10 backdrop-blur-sm" style={{ animationDelay: "0ms" }}>
          <span className="text-[12px] font-medium tracking-wider" style={{ color: "rgba(255,255,255,0.7)" }}>{t("app.title")}</span>
        </div>
        <div className="animate-splash-in relative flex items-center justify-center" style={{ animationDelay: "80ms" }}>
          <div className="absolute rounded-full animate-lens-breathe" style={{ width: 220, height: 220, border: "1px solid rgba(178,122,126,0.12)", boxShadow: "0 0 80px rgba(178,122,126,0.06)" }} />
          <h1 className="relative text-[48px] md:text-[56px] font-medium tracking-[0.03em] text-white leading-none" style={{ fontFamily: "'Montserrat', -apple-system, sans-serif" }}>Momcozy</h1>
        </div>
        <div className="animate-splash-in flex flex-col items-center gap-1.5" style={{ animationDelay: "160ms" }}>
          <p className="text-[18px] leading-relaxed" style={{ fontFamily: "'Noto Sans SC', 'PingFang SC', -apple-system, sans-serif", color: "rgba(255,255,255,0.85)" }}>{t("splash.sloganZh")}</p>
          <p className="text-[14px]" style={{ fontFamily: "'Inter', -apple-system, sans-serif", color: "rgba(255,255,255,0.55)" }}>Evolving for Mom and Cozy</p>
        </div>
        <p className="animate-splash-in text-[11px]" style={{ color: "rgba(255,255,255,0.35)", animationDelay: "200ms" }}>{t("splash.departmentCredit")}</p>
      </div>

      {/* CTA */}
      <div className="animate-splash-in absolute bottom-[12%] flex flex-wrap items-center justify-center gap-3 px-4" style={{ animationDelay: "280ms" }}>
        <button className={btnBase} onClick={() => setShowGuide(true)}>{t("splash.guide")}</button>
        <button onClick={handleEnter} className="px-8 py-3 rounded-[24px] text-[16px] font-medium cursor-pointer transition-all duration-300 ease-out bg-white/15 text-white border border-white/20 hover:bg-white/25 hover:border-white/40 hover:scale-[1.02] active:scale-[0.98]">{t("splash.enter")}</button>
        <button className={btnBase} onClick={() => setShowBlueprint(true)}>{t("splash.blueprint")}</button>
      </div>

      {/* Timeline */}
      <div className="animate-splash-in absolute bottom-[4%] flex items-center gap-2" style={{ animationDelay: "350ms" }}>
        <div className="w-2 h-2 rounded-full animate-timeline-pulse" style={{ background: "rgba(255,255,255,0.25)" }} />
        <div className="w-[60vw] max-w-[480px] h-px" style={{ background: "rgba(255,255,255,0.1)" }} />
        <div className="w-2 h-2 rounded-full" style={{ background: "rgba(255,255,255,0.15)" }} />
        <span className="text-[10px] ml-1.5" style={{ color: "rgba(255,255,255,0.2)" }}>00:00</span>
      </div>

      {/* ═══ GUIDE OVERLAY ═══ */}
      {showGuide && (
        <div className="absolute inset-0 z-50 overflow-y-auto bg-[#FEF9F6]" style={{ fontFamily: "'Inter', 'Noto Sans SC', -apple-system, sans-serif" }}>
          {/* Sticky header */}
          <div className="sticky top-0 z-20 flex items-center justify-between px-6 md:px-12 py-4 bg-[#FEF9F6]/90 backdrop-blur-md border-b border-[#EDD3D1]">
            <h2 className="text-[16px] font-semibold text-[#35353B]">{t("app.title")} · {t("splash.guide")}</h2>
            <button onClick={() => setShowGuide(false)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[13px] font-medium text-[#59585E] hover:bg-[#FCE4E2] hover:text-[#6A2B3A] transition-colors cursor-pointer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
              返回
            </button>
          </div>

          <div className="max-w-4xl mx-auto px-6 md:px-12 py-8 space-y-12 pb-20">
            {/* ── Hero ── */}
            <div className="text-center space-y-3 py-6">
              <h1 className="text-[28px] md:text-[36px] font-semibold text-[#35353B] tracking-tight">AI 视频创作平台</h1>
              <p className="text-[14px] text-[#59585E] max-w-2xl mx-auto leading-relaxed">
                面向品牌营销团队的智能视频生产工具。输入产品信息和创作方向，AI 自动完成策略生成、脚本撰写、视频生成、配音配乐、质量审计——从创意到成片，全链路自动化。
              </p>
              <div className="flex flex-wrap justify-center gap-2 pt-2">
                {["DeepSeek-V4-Pro 文本", "GPT-4o Image 图像", "Happy Horse 视频", "CosyVoice2 语音"].map(m => (
                  <span key={m} className="px-3 py-1 rounded-full bg-[#FCE4E2] text-[11px] font-medium text-[#6A2B3A]">{m}</span>
                ))}
              </div>
            </div>

            {/* ── 6 Scenes ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[#35353B] mb-4">视频创作场景</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {SCENE_CARDS.map(s => (
                  <div key={s.name} className="p-4 rounded-xl bg-white border border-[#EDD3D1] hover:border-[#D9A8A3] transition-colors">
                    <div className="text-lg mb-1">{s.emoji}</div>
                    <div className="text-[14px] font-semibold text-[#35353B]">{s.name}</div>
                    <div className="text-[12px] text-[#59585E] leading-relaxed mt-1">{s.desc}</div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── Modes ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[#35353B] mb-4">两种操作模式</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-5 rounded-xl bg-gradient-to-br from-[#FCE4E2] to-[#FFF0EF] border border-[#EDD3D1]">
                  <div className="text-[15px] font-semibold text-[#6A2B3A]">Smart Create 一键模式</div>
                  <div className="text-[12px] text-[#59585E] leading-relaxed mt-2">
                    选场景 → 填信息 → 点生成。AI 做全部决策，适合快速验证、批量生产。30s-5min 等待后直接查看完整结果。
                  </div>
                </div>
                <div className="p-5 rounded-xl bg-gradient-to-br from-[#F8EEE8] to-[#FFF0EF] border border-[#EDD3D1]">
                  <div className="text-[15px] font-semibold text-[#6A2B3A]">Expert Studio 逐步模式</div>
                  <div className="text-[12px] text-[#59585E] leading-relaxed mt-2">
                    12 个步骤逐步执行，每步可查看、编辑、重做。4 个 Gate 关口自动暂停等待审核。适合需要精细控制和品牌审查的场景。
                  </div>
                </div>
              </div>
            </section>

            {/* ── Examples ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[#35353B] mb-4">场景示例 · 输入参考</h3>
              <p className="text-[12px] text-[#59585E] mb-4 leading-relaxed">以下示例基于 Momcozy M5 穿戴式吸奶器，展示每种场景的实际输入方式。直接参考填入即可获得高质量产出。</p>
              <div className="space-y-4">
                {/* 商品直拍 */}
                <div className="rounded-xl bg-white border border-[#EDD3D1] overflow-hidden">
                  <div className="px-5 py-3 bg-[#FCE4E2] border-b border-[#EDD3D1] text-[13px] font-semibold text-[#6A2B3A]">📦 商品直拍</div>
                  <div className="p-5 space-y-2 text-[12px] text-[#59585E]">
                    <div><span className="font-semibold text-[#35353B]">产品名称:</span> M5 Wearable Breast Pump</div>
                    <div><span className="font-semibold text-[#35353B]">品牌名:</span> Momcozy</div>
                    <div><span className="font-semibold text-[#35353B]">核心卖点:</span> "免手扶穿戴式设计 · 3 秒快速佩戴 · 静音马达 &lt; 35dB · 轻量通勤可放入内衣 · APP 智能控制"</div>
                    <div><span className="font-semibold text-[#35353B]">使用场景(高级):</span> "职场妈妈通勤泵奶、夜间低噪不惊扰宝宝、出差途中单手操作"</div>
                    <div><span className="font-semibold text-[#35353B]">痛点(高级):</span> "传统吸奶器线缆杂乱、体积大不便携、噪音尴尬影响睡眠"</div>
                    <div><span className="font-semibold text-[#35353B]">品牌语气 Do:</span> "温柔、真实、像妈妈之间分享使用心得"</div>
                    <div><span className="font-semibold text-[#35353B]">品牌语气 Don't:</span> "不用'革命性'、'全球首创'等夸大词"</div>
                  </div>
                </div>
                {/* 品牌VLOG */}
                <div className="rounded-xl bg-white border border-[#EDD3D1] overflow-hidden">
                  <div className="px-5 py-3 bg-[#F8EEE8] border-b border-[#EDD3D1] text-[13px] font-semibold text-[#6A2B3A]">📹 品牌VLOG</div>
                  <div className="p-5 space-y-2 text-[12px] text-[#59585E]">
                    <div><span className="font-semibold text-[#35353B]">品牌:</span> Momcozy · 产品SKU: M5 Breast Pump（选定后自动回填六视图）</div>
                    <div><span className="font-semibold text-[#35353B]">场景:</span> 客厅</div>
                    <div><span className="font-semibold text-[#35353B]">模特:</span> 多选 — Ava(母亲) + Noah(婴儿)</div>
                    <div><span className="font-semibold text-[#35353B]">故事描述:</span> "以年轻母亲在客厅使用 M5 为核心，穿插婴儿安静入睡的镜头。开场 3 秒展示 M5 主视图建立产品认知，中段切换过肩镜头展示职场妈妈单手操作泵奶，背景婴儿在沙发安睡，突出免手扶和静音卖点。结尾品牌收尾——'为妈妈的舒适不断进化'——妈妈抱着宝宝微笑。"</div>
                    <div><span className="font-semibold text-[#35353B]">时长:</span> 30-45s（加长）</div>
                  </div>
                </div>
                {/* 网红二创 */}
                <div className="rounded-xl bg-white border border-[#EDD3D1] overflow-hidden">
                  <div className="px-5 py-3 bg-[#FCE4E2] border-b border-[#EDD3D1] text-[13px] font-semibold text-[#6A2B3A]">📱 网红二创</div>
                  <div className="p-5 space-y-2 text-[12px] text-[#59585E]">
                    <div><span className="font-semibold text-[#35353B]">视频URL:</span> 员工/KOL 原始口播视频链接</div>
                    <div><span className="font-semibold text-[#35353B]">产品:</span> M5 Wearable Breast Pump</div>
                    <div><span className="font-semibold text-[#35353B]">网红名称:</span> Sophie（可选）</div>
                    <div><span className="font-semibold text-[#35353B]">说明:</span> 上传已有员工或 KOL 的产品讲解视频 → AI 提取核心卖点 → 重混脚本 → 嵌入 Shopee/Amazon 产品链接 → 批量分发多平台</div>
                  </div>
                </div>
                {/* 快速模式 */}
                <div className="rounded-xl bg-white border border-[#EDD3D1] overflow-hidden">
                  <div className="px-5 py-3 bg-[#F8EEE8] border-b border-[#EDD3D1] text-[13px] font-semibold text-[#6A2B3A]">⚡ 快速模式</div>
                  <div className="p-5 space-y-2 text-[12px] text-[#59585E]">
                    <div><span className="font-semibold text-[#35353B]">描述:</span> "Wearable breast pump, silent motor, mom using it in living room while baby sleeps nearby, natural warm light, cozy home atmosphere"</div>
                    <div><span className="font-semibold text-[#35353B]">时长:</span> 10s · <span className="font-semibold text-[#35353B]">说明:</span> 直接测试大模型矩阵，不走完整 pipeline，10-15s 快速验证视频质量</div>
                  </div>
                </div>
              </div>
            </section>

            {/* ── Scene-specific SOP ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[#35353B] mb-2">各场景操作 SOP</h3>
              <p className="text-[12px] text-[#59585E] mb-4 leading-relaxed">不同场景的操作流程有差异，请按场景查阅对应 SOP。</p>
              <div className="space-y-4">
                {[
                  { emoji:"📦", name:"商品直拍", color:"#FCE4E2",
                    steps:[
                      "① 输入产品名称、品牌名、核心卖点（每行一个）",
                      "②（可选）展开高级设置：使用场景、用户痛点、竞品对比、品牌语气 Do/Don't",
                      "③ 选择模式：Smart Create 全自动 / Expert Studio 逐步控制",
                      "④ Smart Create：点击「开始生成」→ 等待 12 步完成 → 查看结果",
                      "⑤ Expert Studio：逐步点击「执行此步」→ 每步可查看/编辑/重做 → 4 个 Gate 关口审核 → 完成",
                    ]
                  },
                  { emoji:"🎬", name:"品牌宣传片", color:"#F8EEE8",
                    steps:[
                      "① 选择品牌规范包（从品牌资产页面预先创建）",
                      "② 输入活动主题、关键信息、目标受众",
                      "③（可选）展开高级：活动目标、品牌价值观、视觉风格、竞品活动",
                      "④ Smart Create 一键执行 / Expert Studio 逐步审核",
                      "⑤ 品牌宣传片有 4 道人工审核（策略→脚本→成片→缩略图），每道需点击「通过」继续",
                    ]
                  },
                  { emoji:"📱", name:"网红二创", color:"#FCE4E2",
                    steps:[
                      "① 输入现有视频 URL（员工/KOL 原始口播素材）",
                      "② 输入要关联的产品名称",
                      "③（可选）输入网红名称、保留原音频开关",
                      "④ AI 自动分析原视频 → 生成重混脚本 → 嵌入产品链接",
                      "⑤ 产出多平台适配版本（Shopify/Amazon/TikTok/Reddit）",
                    ]
                  },
                  { emoji:"📹", name:"品牌VLOG", color:"#F8EEE8",
                    steps:[
                      "① 选择品牌规范 + 产品 SKU（选定后六视图自动回填）",
                      "② 选择空间场景（6 选 1：职场/客厅/卧室/儿童房/户外/厨房）",
                      "③ 选择模特角色（支持多选：母亲/父亲/婴儿/孕妈/护理师/父母双人）",
                      "④ 输入故事描述（≤300字，描述人物动作+情绪+卖点节奏+结尾指令）",
                      "⑤ 选择视频时长（5-15s / 15-30s / 30-45s / 45-60s / 60-90s）",
                      "⑥ 点击「AI生成视频」→ AI 根据六视图+模特+场景+故事生成分镜脚本 → 逐镜出片",
                    ]
                  },
                  { emoji:"🎥", name:"实拍素材生成", color:"#FCE4E2",
                    steps:[
                      "① 上传实拍素材文件（视频/图片，支持拖拽）",
                      "② 输入产品信息、主题",
                      "③ AI 分析素材内容 → 自动生成旁白文案 → 同步字幕时间轴",
                      "④ 合成最终成片（含 AI 配音 + 字幕）",
                    ]
                  },
                  { emoji:"⚡", name:"快速模式", color:"#F8EEE8",
                    steps:[
                      "① 输入一段描述（中英文均可，建议包含：产品+场景+氛围）",
                      "② 选择时长（10s 或 15s）",
                      "③ 点击「快速生成」→ 直接测试大模型矩阵能力",
                      "④ 不走完整 pipeline，10-15s 快速出片验证效果",
                    ]
                  },
                ].map((s, i) => (
                  <div key={i} className="rounded-xl bg-white border border-[#EDD3D1] overflow-hidden">
                    <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: s.color, borderBottom: "1px solid #EDD3D1" }}>
                      <span>{s.emoji}</span>
                      <span className="text-[13px] font-semibold text-[#6A2B3A]">{s.name}</span>
                    </div>
                    <div className="p-4 space-y-1.5 text-[12px] text-[#59585E] leading-relaxed">
                      {s.steps.map((st, j) => <div key={j}>{st}</div>)}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── Notices ── */}
            <section>
              <h3 className="text-[18px] font-semibold text-[#35353B] mb-4">注意事项</h3>
              <div className="space-y-2">
                {NOTICES.map((n, i) => (
                  <div key={i} className="flex gap-3 p-4 rounded-xl bg-[#FFF0EF] border border-[#EDD3D1]">
                    <span className="text-[#6A2B3A] text-sm shrink-0 mt-0.5">⚠</span>
                    <div>
                      <div className="text-[13px] font-semibold text-[#35353B]">{n.title}</div>
                      <div className="text-[12px] text-[#59585E] leading-relaxed mt-0.5">{n.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── Footer CTA ── */}
            <div className="text-center pt-4">
              <button onClick={() => { setShowGuide(false); handleEnter(); }}
                className="px-10 py-3.5 rounded-xl text-[16px] font-semibold text-white bg-[#6A2B3A] hover:bg-[#4E1F2A] active:scale-[0.98] transition-all cursor-pointer shadow-lg shadow-[#6A2B3A]/20">
                {t("splash.enter")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Blueprint IFrame Modal ── */}
      {showBlueprint && (
        <div className="absolute inset-0 z-50 flex flex-col bg-[#FEF9F6]">
          <div className="flex items-center justify-between px-5 py-3 border-b border-[#EDD3D1] bg-[#FEF9F6]/90 backdrop-blur-md">
            <span className="text-[14px] font-semibold text-[#35353B]">{t("splash.blueprint")}</span>
            <button onClick={() => setShowBlueprint(false)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[13px] font-medium text-[#59585E] hover:bg-[#FCE4E2] hover:text-[#6A2B3A] transition-colors cursor-pointer">
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
        @keyframes timelinePulse { 0%,100% { opacity: 0.25; } 50% { opacity: 0.6; } }
      `}</style>
    </div>
  );
}
