# 一周交付计划 — S1∪S2 + S3 真视频产出

> **截止**:下周(5/4-5/8)向领导演示
> **方向**:路径 A(垂直内容工厂)+ Skills Graph 工作流
> **目标**:两个场景真实跑通,产出可播放的 mp4 视频
> **作者视角**:资深短视频专家 + 架构师,以"演示成功"为唯一指标

## 架构原则(用户明确要求)

**1. Skill,不是 prompt**:本周新增的能力全部封装为 SkillRegistry 注册的 Skill,不让 prompt 散落在 pipeline 里。

```
现有 Skills(产数据)              本周新增 Skills(产媒体)
────────────────────             ───────────────────────
product-strategy-skill           seedance-video-generate-skill   ← 真生成 mp4 片段
script-writer-skill              elevenlabs-tts-skill            ← 真生成 mp3
storyboard-skill                 gpt-image-generate-skill        ← 真生成 png  
seedance-prompt-skill            remotion-assemble-skill         ← 真拼接最终 mp4
thumbnail-prompt-skill
remix-script-skill
viral-extractor-skill
video-analysis-skill
brand-compliance-skill
```

每个新 Skill:
- 在 `src/skills/` 下独立文件
- 继承 `BaseSkill`,实现 `async def execute(input) -> SkillResult`
- 在文件末尾 `SkillRegistry().register(...)`
- 配套测试 `tests/test_<skill>.py`

**2. 自我自证(Self-verification)**:每个媒体 Skill 出口必须验证产物有效。

```python
# 模板伪码
class SeedanceVideoGenerateSkill(BaseSkill):
    name = "seedance-video-generate-skill"
    
    async def execute(self, input: dict) -> SkillResult:
        # ... call Seedance API ...
        video_path = await sd.text_to_video(prompt=...)
        
        # === Self-verification ===
        if not video_path.exists():
            return SkillResult(success=False, error="file_not_created")
        if video_path.stat().st_size < 1024:
            return SkillResult(success=False, error="file_too_small")
        if not self._is_valid_mp4(video_path):
            return SkillResult(success=False, error="invalid_mp4")
        if self._get_duration(video_path) < 3.0:
            return SkillResult(success=False, error="duration_too_short")
        
        return SkillResult(success=True, data={"video_path": str(video_path), ...})
```

**3. 审计(Audit)**:每个 pipeline 关键节点后,调 `auditor.py` 做语义层检查并产出 audit_report。

```python
# Pipeline 内
synth_result = await reg.execute("seedance-video-generate-skill", ...)

# === Audit ===
audit = await reg.execute("media-quality-audit-skill", {
    "video_path": synth_result.data["video_path"],
    "expected_product": product["name"],
    "expected_duration": script_segment["duration"],
})
result.audit_reports.append(audit.data)
```

**4. 失败兜底**:`retry.py` 已有指数退避;3 次重试后用 stub 占位(黑屏 + overlay 文本),不让整个 pipeline 挂掉。


---

## 演示场景定义(领导要看到的"故事")

### 场景 1:网红二创(S3)
**输入**:
- 一个母婴垂直网红视频 URL(如 Momcozy 爆款 TikTok)
- 你的产品信息(`name`, `usps`, `brand_name`)

**输出**(领导能看到的):
- ✅ 一段真实的 mp4 视频(15-30s,9:16 竖屏)
- ✅ 4 张缩略图(真实生成的图片,不是 prompt)
- ✅ Brief / Script / Storyboard 全程数据(透明度)

**故事线**:"我们能学习任何爆款的结构,把你的产品自然嵌入,产出风格保留的二创视频。"

### 场景 2:商品直拍(S1∪S2 合并)
**输入**:
- 产品信息(图、文、卖点)
- 品牌资产(可选,有就用,没有就用默认母婴风)

**输出**(领导能看到的):
- ✅ 一段真实的 mp4 视频(20-45s,9:16 竖屏)
- ✅ 4 张缩略图
- ✅ 平台分发计划(JSON 即可,不需真发)

**故事线**:"输入产品,输出可发布的商品视频,适配 TikTok / Shopify。"

---

## 7 天执行计划(按天细化)

### Day 1 — 周一 4/27:基础设施 + Remotion 本机跑通 ⭐ 最关键

**目标**:在你的 Mac 上跑出**第一条真实的 sample mp4 视频**(用现成 sample data)

**任务**:
1. `cd rendering && npm install`(预计 1-2 分钟)
2. `cd rendering && npm run render`(用 Root.tsx 里的 sampleData 直接出一条 mp4)
3. 如果失败:debug 字体/codec 问题,确保 ffmpeg + Remotion 协作正常
4. 改 `src/tools/remotion_renderer.py` 的 `render()` 方法,确保从 Python 调用 npx tsx 能产出 mp4
5. 写一个 `scripts/test_render.py`,加载 sample JSON → 调 RemotionRenderer.render() → 验证 mp4 文件存在

**验收**:
- [ ] `outputs/renders/sample.mp4` 存在,可在 QuickTime 打开,有声音(或留白)有画面
- [ ] Python 调用一次,5-10 分钟内能产出
- [ ] 视频满足 1080x1920、30fps、h264 编码

**如果本地 Mac 没装 Node**:`brew install node` 先装上(5 分钟)。如果出现内存/CPU 问题,降低分辨率到 720x1280。

**风险预警**:Remotion 第一次跑可能要装 Chromium(自动下载,200MB,5-10 分钟)。**先做这一步,不要拖到 Day 5**。

---

### Day 2 — 周二 4/28:S3 真实媒体生成串通

**目标**:S3 Pipeline 不只产 prompt,要产**真实的视频片段 + 真实的音频 + 真实的缩略图**

**改动文件**:
1. `src/pipeline/s3_remix_pipeline.py` — 在 step 3/4 之后,加 step 5/6/7
2. 新建 `src/pipeline/media_pipeline.py` — 通用媒体生成器,被 S1/S3 共用
3. 新建 `src/skills/media_synthesis.py` — 注册一个新 skill `media-synthesis-skill`,统一调度

**新增 Skills Graph 步骤(编号衔接现有)**:

```
S3 现有: video_analysis → remix_script → seedance_prompt → thumbnail_prompt
S3 升级: 
  + Step 5: seedance_generate (调真 Seedance API,产出 .mp4 片段们,每段 5-10s)
  + Step 6: tts_generate (调 ElevenLabs,按 remix_script 的 segments 产出 .mp3)
  + Step 7: thumbnail_generate (调 GPT-Image,按 thumbnail prompts 产出 .png)
  + Step 8: assemble_video (调 RemotionRenderer,把 mp4 片段 + mp3 + 字幕组装成最终 mp4)
```

**media_pipeline.py 骨架**:

```python
# src/pipeline/media_pipeline.py
"""Real media synthesis layer — turns prompts into actual video assets."""
from pathlib import Path
from typing import Any
from src.tools.seedance_client import SeedanceClient
from src.tools.elevenlabs_client import ElevenLabsClient
from src.tools.gpt_image_client import GPTImageClient
from src.tools.remotion_renderer import RemotionRenderer
import structlog

logger = structlog.get_logger()


class MediaSynthesisPipeline:
    """Generate real audio/video/thumbnails from prompts.
    
    Used by both S1 and S3 to produce final mp4 deliverables.
    """
    
    async def synthesize(
        self,
        video_prompts: list[dict],   # from seedance_prompt skill
        script_segments: list[dict],  # voice text per timestamp
        thumbnail_prompts: list[dict], # from thumbnail_prompt skill  
        language: str = "en",
        output_name: str = "output",
    ) -> dict:
        """Run the real synthesis: clips + audio + thumbnails + assembly.
        
        Returns:
            {
              "video_path": "outputs/renders/{name}.mp4",
              "thumbnail_paths": ["outputs/gpt_images/{name}_v1.png", ...],
              "audio_paths": ["outputs/audio/seg_0.mp3", ...],
              "clip_paths": ["outputs/seedance/clip_0.mp4", ...],
              "errors": [],
            }
        """
        errors = []
        
        # Step 1: Generate Seedance clips (parallel)
        clip_paths = []
        sd = SeedanceClient()
        for i, vp in enumerate(video_prompts[:5]):  # cap to 5 segments for demo
            try:
                result = await sd.text_to_video(
                    prompt=vp.get("prompt", ""),
                    duration=5,
                    resolution="720p",  # 720p faster for demo
                )
                clip_paths.append(result.get("local_path"))
            except Exception as e:
                errors.append(f"Seedance clip {i}: {e}")
        
        # Step 2: Generate TTS audio (parallel)
        audio_paths = []
        tts = ElevenLabsClient()
        for i, seg in enumerate(script_segments):
            try:
                p = await tts.synthesize(
                    text=seg.get("voiceover", "") or seg.get("description", ""),
                    language=language,
                )
                audio_paths.append(str(p))
            except Exception as e:
                errors.append(f"TTS seg {i}: {e}")
        
        # Step 3: Generate thumbnails (parallel)
        thumbnail_paths = []
        gpt = GPTImageClient()
        for i, tp in enumerate(thumbnail_prompts[:4]):
            try:
                result = await gpt.generate(prompt=tp.get("prompt", ""))
                thumbnail_paths.append(result.get("local_path"))
            except Exception as e:
                errors.append(f"Thumbnail {i}: {e}")
        
        # Step 4: Assemble via Remotion
        video_path = ""
        try:
            renderer = RemotionRenderer()
            input_json = self._build_render_json(
                clip_paths, audio_paths, script_segments,
            )
            video_path = str(await renderer.render_async(
                input_json=input_json,
                output_filename=f"{output_name}.mp4",
            ))
        except Exception as e:
            errors.append(f"Render: {e}")
        
        return {
            "video_path": video_path,
            "thumbnail_paths": thumbnail_paths,
            "audio_paths": audio_paths,
            "clip_paths": clip_paths,
            "errors": errors,
        }
    
    def _build_render_json(self, clips, audios, segments):
        # Build the JSON that Remotion's render.ts expects
        ...
```

**验收**:
- [ ] `await S3InfluencerRemixPipeline().run(...)` 真的能产出一个 mp4 文件
- [ ] mp4 时长 = sum(segment durations),声画对齐
- [ ] 4 张缩略图是真实的 png 文件,不是 placeholder

**风险**:
- Seedance API 单次调用 30-60s,5 个片段 = 5 分钟。可考虑并发(asyncio.gather)。
- 单条视频成本估计:Seedance ~$1 + ElevenLabs ~$0.05 + DALL-E ~$0.10 = **$1.15/视频**

---

### Day 3 — 周三 4/29:S1∪S2 合并 + 接通真实媒体

**目标**:把 S2 砍掉,S1 升级支持品牌模式;接通同一个 media_pipeline

**改动文件**:
1. `src/pipeline/s1_product_pipeline.py` — 在 step 5 之后加 step 6 (media_pipeline)
2. **删除** `src/pipeline/s2_brand_pipeline.py`(或先保留,但不再被路由)
3. `src/api.py` — `/scenario/s2` 改为转发到 `/scenario/s1`,加 `brand_mode=True`
4. `web/src/components/SceneSelector.tsx` — UI 上保留两个入口,后端合并到 S1
5. `S1ProductDirectPipeline.run()` 增加 `enable_media_synthesis: bool = True` 参数

**S1 Pipeline 的改动伪码**:

```python
# src/pipeline/s1_product_pipeline.py
class S1ProductDirectPipeline:
    async def run(self, ..., enable_media_synthesis: bool = True):
        # ... 现有 5 步保留 ...
        
        # NEW Step 6: Real media synthesis (only for the first script)
        if enable_media_synthesis and scripts_dict:
            from src.pipeline.media_pipeline import MediaSynthesisPipeline
            media = MediaSynthesisPipeline()
            
            first_script = scripts_dict[0]
            first_thumbs = thumbnails[0] if thumbnails else {}
            first_prompts = prompts[0] if prompts else {}
            
            synth = await media.synthesize(
                video_prompts=[{"prompt": first_prompts.get("prompt", {}).get("seedance_prompt", "")}],
                script_segments=first_script.get("segments", []),
                thumbnail_prompts=first_thumbs.get("variants", []),
                output_name=f"s1_{int(time.time())}",
            )
            
            return {
                ...,  # existing fields
                "video_path": synth["video_path"],
                "thumbnail_image_paths": synth["thumbnail_paths"],
                "audio_paths": synth["audio_paths"],
                "media_errors": synth["errors"],
            }
```

**验收**:
- [ ] `/scenario/s1` 调用产出真实 mp4(至少 15s)
- [ ] `/scenario/s2` 仍然工作,但底层走 S1 + brand_mode
- [ ] 至少 3 个不同产品测试通过(Wearable Pump, Bottle Warmer, Baby Monitor)

---

### Day 4 — 周四 4/30:前端集成 + 视频播放

**目标**:领导在 UI 里能直接看到生成的视频,不用打开文件夹

**改动文件**:
1. `src/api.py` — 新增 `/api/media/{filename}` 端点,从 outputs/renders/ 服务 mp4
2. `web/src/components/OneShotResultView.tsx` — 加一个 "视频" tab,放 `<video>` 标签播放
3. `web/src/components/OneShotResultView.tsx` — 缩略图改为真实 img(从 /api/media/ 加载)
4. `web/src/app/page.tsx` — 加 loading 进度条(因为真实生成 5-8 分钟)

**API 端点伪码**:

```python
# src/api.py
from fastapi.responses import FileResponse

@app.get("/api/media/{filename}")
async def serve_media(filename: str):
    """Serve generated mp4/png/mp3 files."""
    from pathlib import Path
    from src.config import OUTPUT_DIR
    safe = Path(filename).name  # prevent traversal
    candidates = [
        OUTPUT_DIR / "renders" / safe,
        OUTPUT_DIR / "gpt_images" / safe,
        OUTPUT_DIR / "audio" / safe,
        OUTPUT_DIR / "seedance" / safe,
    ]
    for path in candidates:
        if path.exists():
            return FileResponse(path)
    raise HTTPException(404)
```

**前端改动重点**:

```tsx
// OneShotResultView.tsx — 加新 tab
const TABS = [
  { id: "video", label: "🎬 最终视频", count: result.video_path ? 1 : 0 },  // NEW
  { id: "briefs", label: "策略", count: briefs.length },
  // ...其他保持不变
];

// VideoView 组件
function VideoView({ videoPath, thumbnails }: { ... }) {
  if (!videoPath) return <Empty text="视频生成中..." />;
  
  // 从 /api/media/ 转换文件名
  const filename = videoPath.split("/").pop();
  const videoUrl = `http://localhost:8001/api/media/${filename}`;
  
  return (
    <div>
      <video controls src={videoUrl} className="w-full max-w-md mx-auto" />
      <div className="grid grid-cols-2 gap-2 mt-4">
        {thumbnails.map((path, i) => {
          const tFilename = path.split("/").pop();
          return <img src={`http://localhost:8001/api/media/${tFilename}`} key={i} />;
        })}
      </div>
    </div>
  );
}
```

**验收**:
- [ ] UI 上跑一次 S3,5 分钟后能在浏览器里直接播放视频
- [ ] 缩略图是真实图片
- [ ] 加载中有清晰进度提示("正在生成视频片段 2/5...")

---

### Day 5 — 周五 5/1:Polish + 速度优化 + 错误处理

**目标**:让演示流畅,避免现场翻车

**任务**:
1. **预生成两条 demo 视频**:运行一次 S3 + 一次 S1,把 mp4 / 缩略图存到 `demos/` 目录,演示时优先用 cached 版本
2. **加缓存层**:`MediaSynthesisPipeline` 检查 `outputs/cache/{hash}.json`,相同输入不重新调 API
3. **错误恢复**:Seedance 失败时降级用 stub 占位视频(黑屏+ overlay 提示),不要让整个流程挂掉
4. **进度反馈**:每个 step 通过 WebSocket 或轮询返回 `current_step` + `progress_percent`
5. **README 更新**:写一个 5 分钟的演示流程 docs/demo/run-book.md

**Demo Run-Book 提纲**:
```markdown
# 演示流程(5 分钟)

## 0. 准备(演示前 30 分钟)
- 启动后端: `./scripts/start_api.sh`
- 启动前端: `cd web && npm run dev`
- 浏览器开 http://localhost:3001
- 准备好两个 demo 输入:
  - S3: video_url=<momcozy_url>, product=<lactfit_pump>
  - S1: product=<wearable_pump>

## 1. 开场(30 秒)
"我们做了一个 AI 短视频内容工厂,母婴垂直,目前 EN/ES/FR/DE 四语,4 个平台。
今天演示两个场景:网红二创、商品直拍。"

## 2. S3 演示(2 分钟)
点击"网红二创" → 输入 → 30 秒后看到 brief / script / 视频

## 3. S1 演示(2 分钟)
点击"商品直拍" → 输入 → 30 秒后看到产物

## 4. 收尾(30 秒)
"下一步:多语言、平台真发布、品牌资产入库 UI、Analytics 反馈。"
```

**验收**:
- [ ] 演示从开始到结束不超过 5 分钟
- [ ] 至少跑过 3 次完整流程,每次都成功
- [ ] 提前 cache 至少 2 条不同的 demo 视频

---

### 周末(5/2-5/3):备份缓冲

- 录一段视频备份(万一现场网络/API 出问题,用录像)
- 准备 Q&A 应对(预想领导可能问什么)
- 把演示稿打印出来

---

### 演示当天(5/4 周一):放手一搏

- 提前 30 分钟到场,先跑一次 cache 视频确认 OK
- 网络出问题就用 cache 视频和录像,不要慌
- 演示结束后不要被"什么时候上线"卡住,回答"我们正在做生产级化,3 周后再演示一次"

---

## 关键风险与应对

| 风险 | 概率 | 应对 |
|------|------|------|
| **Remotion 在 Mac 上跑不起来** | 中 | Day 1 解决,如果跑不通,降级用 Python ffmpeg + moviepy 拼接 |
| **Seedance API 太慢/失败** | 高 | Day 5 cache 预生成 demo 视频;现场用 cache |
| **API 费用超出预算** | 低 | 5 个 demo 视频 × $1.15 = $5.75,加测试 ~$30 总预算 |
| **演示当天网络/API 抖动** | 中 | 录视频备份 + 本地 cache 文件 |
| **领导问"什么时候多语言" "什么时候多租户"** | 高 | 答:"演示后 4-6 周第二次演示,届时多语言全闭环" |

---

## 不做的事(明确划线)

这一周**绝对不做**:
- ❌ 多语言端到端(只做 EN)
- ❌ 多租户/Auth(单租户)
- ❌ 平台真发布(只生成计划)
- ❌ Analytics 反馈回路
- ❌ 品牌资产入库 UI(下周再做)
- ❌ Postgres 持久化(用 MemorySaver,演示当天不重启)
- ❌ 抽象 LangGraph 复杂层(skills graph 直走)
- ❌ 改架构、写 RFC、开会

每一项都很重要,但**不在这一周**。这周只为一件事:**演示成功**。

---

## 我现在能帮你做什么

我手上的工具能直接改代码,我建议**现在立刻开始 Day 1**:

1. 帮你跑 `cd rendering && npm install`
2. 帮你 debug Remotion 第一次渲染
3. 帮你写 `media_pipeline.py` 的实际代码
4. 帮你改 S1/S3 pipeline 接通 media_pipeline
5. 帮你写 API 端点 + 前端集成

**你回我一句"开干"我就开始 Day 1。**

只需要你提供:
- (现在不用)Seedance / ElevenLabs / OpenAI 的 API key(等我们改完代码再填)
- (现在不用)demo 视频 URL 和产品信息
- (现在用)你的 Mac 是否有 Node.js?(如果没有,先 `brew install node`)
