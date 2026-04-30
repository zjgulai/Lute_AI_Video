# 管道执行中止 / 取消功能 — 设计规格

**日期**: 2026-04-30  
**方案**: A — AbortController + State Recovery（纯前端）  
**源起**: Expert Studio 策略生成等待时间过长且无法取消

---

## 一、问题定义

当前平台中 4 类长等待操作全部无可中断机制：

| 场景 | 等待时长 | 当前行为 |
|------|---------|---------|
| Smart Create 自动模式 | 30s–5min | Loading overlay 覆盖全屏，必须等完 |
| Expert Studio 逐步执行 | 每步 5s–6min | 步骤按钮 disabled，无法中断 |
| StageProgress 轮询 | 2–10min | 进度条一直跑，无关闭按钮 |
| 审核提交后轮询 | 5s | 无中止，但时长较短可接受 |

唯一「取消」方式 `resetAll()` 会暴力清空所有状态并丢弃整个管道运行——已完成的步骤也丢失。

---

## 二、设计目标

1. **中止当前操作**：用户在任何长等待中都能中断，不被卡住
2. **保留已完成步骤**：中止后不丢失已完成步骤的结果
3. **不弹错误提示**：用户主动取消不是错误，不弹 toast
4. **改动最小化**：仅前端改动，不碰后端和管道代码
5. **覆盖所有场景**：Smart Create、Expert Studio、StageProgress、审核轮询

---

## 三、架构设计

### 3.1 三层注入模型

```
┌──────────────────────────────────────────────┐
│  层级 3: 取消后处理                           │
│  page.tsx / VideoWorkflow / StepByStepView   │
│  ├─ 关闭 loading overlay                     │
│  ├─ fetchState 拿部分结果                     │
│  └─ 展示已完成步骤                            │
├──────────────────────────────────────────────┤
│  层级 2: 全局 AbortController                 │
│  page.tsx: abortRef = useRef<AbortController>│
│  ├─ 每次异步开始前 new AbortController()      │
│  ├─ 传递给 api.ts 函数的 signal              │
│  └─ 取消时 abortRef.current.abort()          │
├──────────────────────────────────────────────┤
│  层级 1: api.ts 底层 fetch 支持 signal        │
│  18 个函数加可选 signal 参数                   │
│  fetch(url, { signal })                      │
└──────────────────────────────────────────────┘
```

### 3.2 数据流

```
用户点击取消
    │
    ▼
abortRef.current.abort()        ← 层级 2
    │
    ├──→ fetch 立即 reject AbortError   ← 层级 1
    │       │
    │       ▼
    │    catch 中检测: AbortError? → return  ← 层级 3
    │    (不弹 toast)
    │
    └──→ setLoading(false)           ← 关闭 overlay
         fetchS1State(label)          ← 拿后端已完成步骤
         │
         ▼
         setStepByStepState(partial)  ← 展示部分结果
```

---

## 四、逐层详细设计

### 4.1 层级 1: api.ts — 18 个函数加 signal 参数

**改动模式**（以 `runS1ProductDirect` 为例）:

```typescript
// 修改前
export async function runS1ProductDirect(config: any): Promise<any> {
  const res = await fetch(getApiBase() + "/scenario/s1", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(config),
  });

// 修改后
export async function runS1ProductDirect(
  config: any,
  options?: { signal?: AbortSignal }
): Promise<any> {
  const res = await fetch(getApiBase() + "/scenario/s1", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(config),
    signal: options?.signal,
  });
```

**需要改动的 18 个函数**:

| 函数 | 调用方 |
|------|--------|
| `runS1ProductDirect` | Smart Create auto 模式 |
| `runS2BrandCampaign` | S2 场景 |
| `runS3InfluencerRemix` | S3 场景 |
| `runS4LiveShoot` | S4 场景 |
| `runS5BrandVlog` | 品牌VLOG 场景 |
| `startPipeline` | Expert Studio |
| `submitReview` | 审核面板 |
| `fetchState` | 审核后轮询 · 通用 |
| `fetchS1State` | S1 状态轮询 |
| `runS1Step` | Expert Studio 逐步 |
| `regenerateS1Step` | Expert Studio 重生成 |
| `resumeS1` | Expert Studio 一键执行 |
| `updateS1State` | 编辑保存 |
| `startS1StepByStep` | 逐步初始化 |
| `fetchOutput` | 结果导出 |
| `fetchDistribution` | 分发视图 |
| `fetchPlatforms` | 平台列表 |
| `publishContent` | 发布 |

### 4.2 层级 2: page.tsx — 全局 AbortController

**新增 state**:

```typescript
const abortRef = useRef<AbortController | null>(null);
```

**每次异步开始前创建**:

```typescript
abortRef.current?.abort();      // 确保上一次的 controller 已失效
const controller = new AbortController();
abortRef.current = controller;
```

**Loading overlay 加取消按钮**:

```tsx
{loading && (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
    <div className="apple-card px-8 py-8 flex flex-col items-center gap-5 w-full max-w-md mx-4">
      <Spinner />
      <p>{loadingText}</p>
      <ProgressBar />
      <button
        onClick={handleCancel}
        className="mt-2 px-4 py-2 rounded-xl text-xs font-medium
                   text-[var(--ink-tertiary)] border border-[var(--border-default)]
                   hover:text-[var(--status-error)] hover:border-[var(--status-error)]/30
                   hover:bg-[var(--status-error-light)]
                   transition-colors duration-200 cursor-pointer"
      >
        {t("common.cancel")}
      </button>
    </div>
  </div>
)}
```

**handleCancel 实现**:

```typescript
const handleCancel = async () => {
  abortRef.current?.abort();
  setLoading(false);
  setShowStageProgress(false);

  // Smart Create auto 模式 → 尝试拿部分结果
  if (stepByStepLabel) {
    try {
      const partial = await fetchS1State(stepByStepLabel);
      if (partial) {
        setStepByStepState(partial);
        setShowStepByStep(true);
      }
    } catch {
      showToast(t("toast.cancelNoPartial"), "info");
    }
  }
};
```

### 4.3 层级 3: 四种场景的取消后处理

#### 场景 A: Smart Create 自动模式

```typescript
const startSmartCreate = async (config: any) => {
  if (loading) return;
  abortRef.current?.abort();
  abortRef.current = new AbortController();
  setLoading(true);
  // ...
  try {
    const result = await runS1ProductDirect(..., { signal: abortRef.current.signal });
    // ...
  } catch (e: any) {
    if (e instanceof DOMException && e.name === "AbortError") return; // ← 静默
    // 正常错误处理...
  } finally {
    setLoading(false);
  }
};
```

#### 场景 B: Expert Studio 逐步执行

```typescript
// VideoWorkflow.tsx: handleRunStep, handleRegenerate, handleResume
const handleRunStep = async (stepName: string) => {
  abortRef.current?.abort();
  abortRef.current = new AbortController();
  setLoading(true);
  try {
    const result = await runS1Step(label, stepName);
    // 传递 signal 给 api 层 (api.ts 层注入)
    onStateChange?.(result);
  } catch (e: any) {
    if (e instanceof DOMException && e.name === "AbortError") return;
    // ...
  }
  // ...
};
```

#### 场景 C: StageProgress 轮询

```typescript
const handleCancelPoll = () => {
  pollingRef.current && clearInterval(pollingRef.current);
  timerRef.current && clearInterval(timerRef.current);
  onCancel?.(); // 关闭 StageProgress 视图
};
```

按钮放在 StageProgress 卡片底部，与现有的 `elapsed time` 同行。无需 AbortController——轮询是前端 setInterval，直接 clearInterval 即可。

#### 场景 D: 审核提交后轮询

```typescript
// handleReview 中的 5 次重试轮询
for (let i = 0; i < 5; i++) {
  if (abortRef.current?.signal.aborted) break; // ← 检测中止
  await new Promise((r) => setTimeout(r, 1000));
  const data = await fetchState(threadId, { signal: abortRef.current.signal });
  // ...
}
```

### 4.4 AbortError 统一处理

所有 catch 块加同一行：

```typescript
} catch (e: any) {
  if (e instanceof DOMException && e.name === "AbortError") return;
  // 原有错误处理...
}
```

涉及的 catch 块: `page.tsx` 4 处、`VideoWorkflow.tsx` 3 处、`StepByStepView.tsx` 4 处。

### 4.5 新增翻译 key

```typescript
// zh
"toast.cancelNoPartial": "已取消，无法获取部分结果",

// en
"toast.cancelNoPartial": "Cancelled, unable to retrieve partial results",
```

---

## 五、改动文件清单

| 文件 | 改动 | 预估行数 |
|------|------|---------|
| `api.ts` | 18 个函数加 `signal` 参数 | +36 行 |
| `page.tsx` | `abortRef` + `handleCancel` + 取消按钮 + 4 处 AbortError | +35 行 |
| `VideoWorkflow.tsx` | `abortRef` + 3 处 AbortError | +12 行 |
| `StepByStepView.tsx` | `abortRef` + 4 处 AbortError | +12 行 |
| `StageProgress.tsx` | 取消按钮 + `onCancel` prop + `handleCancelPoll` | +15 行 |
| `translations.ts` | 2 个新 key | +4 行 |
| **合计** | | ~114 行 |

---

## 六、测试验证清单

- [ ] Smart Create → 点「开始生成」→ 立即点「取消」→ overlay 关闭，不弹 toast
- [ ] Expert Studio → 执行 strategy 步骤 → 等待 2s → 点取消 → 步骤回到 pending，不弹 toast
- [ ] StageProgress → 轮询中 → 点取消 → 回到逐步视图，已完成步骤保留
- [ ] 审核提交 → 提交中 → 点取消 → 回到审核面板
- [ ] 取消后→ 点「开始生成」→ 正常执行（AbortController 被正确 new 覆盖）
- [ ] 不点取消 → 正常执行完 → 结果页正常展示（无 AbortError 侵入）
- [ ] 网络真实错误时 → 仍然正常弹 toast（AbortError 不影响正常错误处理）

---

## 七、自审

- **占位符检查**: 无 TBD/TODO，所有参数名和函数名已明确
- **内部一致性**: 三级注入逐层对应，数据流无环
- **范围控制**: 仅前端，不碰后端管道和 StepRunner
- **歧义检查**: `AbortError === DOMException.name === "AbortError"` 是 Web 标准，跨浏览器一致
