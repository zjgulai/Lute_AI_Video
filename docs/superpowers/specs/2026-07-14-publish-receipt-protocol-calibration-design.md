---
title: W1-25 发布回执、环境变量与平台协议校准设计
doc_type: architecture
module: backend-frontend
topic: publish-receipt-protocol-calibration
status: stable
created: 2026-07-14
updated: 2026-07-14
owner: self
source: human+ai
---

# W1-25 发布回执、环境变量与平台协议校准设计

## 1. 决策摘要

本规格只闭环路线图 W1-25：在不执行真实平台调用的前提下，把 TikTok 与
Shopify 发布连接器校准到当前官方协议，把 Shopify credential 环境变量收敛为
单一事实源，并让任何 `published` 状态都有可持久化、可回读、不可伪造的
平台回执。

用户已逐节批准路线 A：完整的本地协议校准。固定决策如下：

1. TikTok 使用 Content Posting API v2 的 creator preflight、Direct Post init、
   FILE_UPLOAD、status fetch 和可选 video query；`publish_id` 永远不是
   `post_id`。
2. Shopify 使用固定的 Admin GraphQL `2026-07` 版本，执行 VIDEO staged
   upload、`fileCreate`、`READY` 轮询、精确 Product GID 关联和关联回读；
   Video GID 不是 post ID。
3. 发布请求新增严格、按平台区分的 `platform_options`。TikTok 的 AI 标记由
   服务端强制为 true；Shopify 只接受精确 Product GID，不再按产品名模糊搜索。
4. 在 acceptance consume 前插入只读 preflight。确定性 preflight 拒绝和
   preflight 不可用都保持 acceptance 未消费。
5. 新增严格的 `PublishReceiptV1`，并在 `publish_logs` 增加一个可空
   `receipt` JSON 字段。新写入的 `published` 必须携带通过平台特定校验的
   receipt；历史空 receipt 不补造事实。
6. 发布连接器保持 W1-23/W1-24 的单次 service invocation、零自动重试、消费后
   不恢复 authority。平台协议内部所需的不同步骤各执行至多一次；TikTok
   分片上传是同一已初始化任务的顺序传输，不是自动重提。
7. 新增 tenant-bound attempt readback；旧 status 路由只能查询当前 tenant
   已持有的真实 TikTok post receipt，不能用于任意外部 ID 探测。
8. `SHOPIFY_ACCESS_TOKEN` 是唯一 Shopify runtime token 名称。旧 token 名称、
   可配置 provider endpoint 和用户名拼接 URL 均退出活跃运行路径。
9. `TIKTOK_PUBLISH_ENABLED` 与 `SHOPIFY_PUBLISH_ENABLED` 默认关闭。
10. 本项只允许 fake transport、fixture、SQLite 和 disposable PostgreSQL 18。
    不读取真实 credential，不调用真实平台，不部署，不执行生产 migration。

路线 B（只改 env 与 mock 字符串）无法证明当前 endpoint、异步状态与 receipt
语义，拒绝采用。路线 C（先 TikTok、后 Shopify）会让数据库和 API receipt
合同重复迁移，拒绝采用。

## 2. 背景与当前事实

### 2.1 W1-23/W1-24 已建立的边界

W1-23 已完成 acceptance-backed publish transaction：

- 两条 publish mutation 共用 `PublishAttemptService`；
- 一条 acceptance 只授权一个平台和一个 attempt；
- readiness 在 consume 前执行；
- consume 后不自动重试、不恢复 acceptance；
- attempt ledger 使用 tenant-bound CAS；
- 本地 fake connector 与 disposable PostgreSQL 18 已通过。

W1-24 已完成 connector truth 的本地实现：

- 缺 credential、模拟结果和不可信结果均 fail-closed；
- runtime publish/status 不再回退 mock success；
- `simulated` 使用精确 bool；
- 确定性失败与 ambiguous outcome 分离；
- 当前状态为
  `implementation_complete_local / independent_review_pending`，
  `independent_review=false`。

W1-25 不重建 acceptance authority，也不放宽 W1-23/W1-24 的失败边界。

### 2.2 当前实现仍存在的真实性缺口

仓库审计确认当前代码仍有以下缺口：

- TikTok publish 使用旧 `/video/upload/`、`/video/publish/`、
  `/video/query/` 路径；
- TikTok 把 upload/init 标识回退为 post ID，并用 `TIKTOK_USERNAME` 拼接 URL；
- TikTok 没有 creator-info preflight、当前 privacy/interaction 校验、官方
  FILE_UPLOAD PUT/chunk 流程或 status-fetch terminal receipt；
- Shopify 仍允许 `SHOPIFY_API_KEY` legacy fallback；
- 活跃 workflow 和 no-provider contract 使用不一致的
  `SHOPIFY_ADMIN_TOKEN`；
- Shopify GraphQL URL 默认固定在过期的 `2024-07`，且允许任意模板覆盖；
- staged upload 错误使用 `resource: FILE`，创建后不等待 `READY`；
- Shopify 用 `product_name` 模糊搜索，关联失败仍可返回 published；
- Shopify 把 Video GID 写入 `post_id`，并构造 Admin products URL 作为
  `post_url`；
- publish ledger 没有独立 receipt 字段，无法区分 provider operation、
  provider resource、目标对象、终态和公开可见性；
- status 路由只做 API-key 校验，可用任意 post ID 探测平台；
- 新旧 connector 结果只校验宽泛字符串，无法完整拒绝 `mock` ID/URL。

因此，W1-24 的绿色只证明“不制造本地模拟成功”，不证明当前平台协议或 receipt
正确。

## 3. 官方平台合同

本规格只以官方一手文档为外部行为依据。

### 3.1 TikTok

- Direct Post 要先查询 creator info，再调用
  `/v2/post/publish/video/init/`；本地文件使用 `FILE_UPLOAD`，init 返回
  `publish_id` 和 `upload_url`：
  [Direct Post](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)。
- `privacy_level` 必须来自 creator info 的 `privacy_level_options`；
  creator info 还返回 interaction 禁用状态与
  `max_video_post_duration_sec`：
  [Query Creator Info](https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info?enter_method=left_navigation)。
- 上传使用 init 返回的完整 URL 和 PUT；分片必须顺序发送，单片 5–64 MB，
  最后一片最多 128 MB，小于 5 MB 的文件整片发送，最多 1000 片：
  [Media Transfer Guide](https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide?enter_method=left_navigation)。
- 状态查询使用 `/v2/post/publish/status/fetch/` 和 `publish_id`；
  `PUBLISH_COMPLETE` 才表示 Direct Post 完成。官方响应字段拼写为
  `publicaly_available_post_id`，且只有公开并通过 moderation 时才返回真实
  post ID：
  [Get Post Status](https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status?enter_method=left_navigation)。
- 可选的 `/v2/video/query/` readback 可返回真实 video `id` 与
  `share_url`，但需要相应 scope：
  [Query Videos](https://developers.tiktok.com/doc/tiktok-api-v2-video-query/)。

### 3.2 Shopify

- 当前 stable Admin API 为 `2026-07`，请求必须显式 pin 版本：
  [API versioning](https://shopify.dev/docs/api/usage/versioning)。
- 视频 staged upload 必须使用 `resource: VIDEO` 且携带 `fileSize`：
  [stagedUploadsCreate](https://shopify.dev/docs/api/admin-graphql/latest/mutations/stagedUploadsCreate)。
- staged upload 后以 `resourceUrl` 调用
  `fileCreate(contentType: VIDEO)`：
  [fileCreate](https://shopify.dev/docs/api/admin-graphql/latest/mutations/fileCreate)。
- 文件异步处理，必须轮询 `fileStatus` 到 `READY` 后才能关联；状态包括
  `UPLOADED`、`PROCESSING`、`READY`、`FAILED`：
  [File](https://shopify.dev/docs/api/admin-graphql/latest/interfaces/File)。
- `fileUpdate(referencesToAdd: [Product GID])` 可建立精确 product reference；
  视频与产品媒体管理需要相应 files/products scopes：
  [fileUpdate](https://shopify.dev/docs/api/admin-graphql/latest/mutations/fileUpdate)、
  [Manage media](https://shopify.dev/docs/apps/build/product-merchandising/products-and-collections/manage-media)。

由这些合同得到两个关键结论：

1. TikTok `publish_id` 是异步 operation ID，不是公开 post ID；
2. Shopify Video GID 是文件资源 ID，把它关联到 product 也不等于已在某个
   storefront/sales channel 公开发布。

## 4. 目标、非目标与证据上限

### 4.1 目标

- 统一并固定 TikTok/Shopify 当前协议 endpoint、请求顺序和状态语义；
- acceptance consume 前完成 tenant-bound acceptance/artifact 读取和平台只读
  preflight；
- 引入严格平台 options 和服务端 AI disclosure；
- 引入可持久化、可回读、平台特定校验的 receipt；
- 让 receipt、attempt terminal state、post projection 在同一 CAS transaction
  中写入；
- 收敛 Shopify credential env，并阻断旧变量和 endpoint override；
- 新增 tenant-bound attempt readback，收紧 legacy status；
- 保持既有单次 acceptance、无自动 retry、无 authority restore；
- 通过 fake transport、SQLite、disposable PostgreSQL 18、OpenAPI 和前端
  regression 建立 L1/L2 证据。

### 4.2 非目标

- 不验证真实 token、scope、app audit、账户状态或平台配额；
- 不执行真实 creator info、status、GraphQL、upload 或 video query；
- 不执行 sandbox/production publish、删除、解除关联或 reconciliation；
- 不建立 publish/review UI、平台 OAuth UI 或 acceptance picker；
- 不证明 TikTok public visibility、Shopify storefront visibility、delivery 或
  active-post metrics；
- 不申请 credential，不读取 `.env`、`.env.prod` 或 secret 文件；
- 不执行生产 migration、SSH、deploy、stage、commit、push、PR 或 merge；
- 不建立 immutable artifact snapshot；现有 acceptance 后再次校验 exact bytes
  的边界保持不变；
- 不把 W1-26 live publish 或 W5 acceptance matrix 合并进本项。

### 4.3 证据上限

W1-25 实现完成后的最高状态仍是：

- `implementation_complete_local / independent_review_pending`
- `independent_review=false`
- `production unchanged`
- `provider_call=false`
- `provider_attempt_made=false`
- `real_connector_call=false`
- `external_status_call=false`
- `live_publish=false`
- `live_send=false`
- `database_write=local-test-only`

用户明确要求不使用子智能体，因此主线程可以做两遍自审，但不能把自审表述为
independent review，也不能将 W1-25 标成 `completed_local`。

## 5. 核心不变量

### 5.1 Authority 与调用顺序

规范顺序为：

`strict request -> local readiness -> prepared -> inspect acceptance/artifact ->
read-only platform preflight -> consume acceptance -> persist acceptance_consumed ->
revalidate exact artifact -> one connector invocation -> protocol mutations ->
receipt readback -> atomic terminal transition`

规则：

1. 无效请求在创建 attempt 前返回 422；
2. disabled/missing/invalid connector 在创建 attempt 前返回 503；
3. platform preflight 前必须先只读验证 acceptance 仍 available 且 exact artifact
   仍匹配；
4. preflight 失败不得 consume acceptance；
5. preflight 通过后，`consume_for_publish` 必须再次验证 exact artifact；
6. consume 后继续保留当前 artifact revalidation；
7. service 对同一个 attempt 最多调用 connector 一次；
8. 每个协议 mutation step 最多执行一次，不自动重试；
9. bounded status polling 是对同一个 provider operation 的只读观察，不是 mutation
   retry；
10. consume 后任何失败都不恢复 acceptance。

### 5.2 Receipt 真实性

- connector 成功结果必须携带一个严格 `PublishReceiptV1`；
- receipt 必须有 `simulated=false`，且类型是精确 bool；
- TikTok `publish_id` 只进入 `provider_operation_id`；
- TikTok `post_id` 只来自 status fetch 的官方
  `publicaly_available_post_id` 或与其一致的 video query；
- Shopify Video GID 只进入 `provider_resource_id`；
- Shopify Product GID 只进入 `target_id`；
- Shopify 不生成 `post_id` 或 Admin `post_url`；
- 不从 username、store host、产品名、GID 或 operation ID 推导公开 URL；
- receipt 的任何 ID/URL 出现大小写不敏感的 `mock` 标记即无效；
- receipt 缺失、类型错误、平台矛盾或字段关系不成立时不得写
  `published`。

### 5.3 隐私与日志

receipt、attempt content、日志和 HTTP 响应不得包含：

- token、credential、Authorization 或 `X-Shopify-Access-Token`；
- upload URL、signed query、staged parameters 或 resource URL；
- 原始 provider response/body/errors/log ID；
- GraphQL error 文本、TikTok fail reason 或 transport exception 文本；
- creator username/avatar/nickname、产品标题或其它 PII；唯一例外是
  `/v2/video/query/` 返回并经严格 host/path/post-ID 校验的公开
  `share_url`，它只能作为不拆解、不记录日志的 opaque platform locator；
- 绝对本地路径。

日志只允许稳定 event、platform、attempt ID、HTTP status、provider status
allowlist 值和 exception class。

## 6. 请求合同与平台 options

### 6.1 顶层请求

`PublishAttemptRequest` 保留：

- `acceptance_id`
- `platform`
- `metadata`

并新增必填 `platform_options`。options 使用 `platform` 字段作为 discriminated
union，同时与顶层 `platform` 做 exact-match 校验。这样保留现有顶层 platform
兼容性，又让 OpenAPI/前端类型能区分字段。

### 6.2 TikTok options

`TikTokPublishOptions`：

- `platform: "tiktok"`
- `privacy_level`：只允许
  `PUBLIC_TO_EVERYONE`、`MUTUAL_FOLLOW_FRIENDS`、
  `FOLLOWER_OF_CREATOR`、`SELF_ONLY`
- `disable_comment`：必填精确 bool
- `disable_duet`：必填精确 bool
- `disable_stitch`：必填精确 bool
- `brand_content_toggle`：必填精确 bool
- `brand_organic_toggle`：必填精确 bool

`is_aigc` 不暴露给调用方；服务端对本项目发布固定发送
`is_aigc=true`。调用方不能关闭 AI label。

creator preflight 必须验证：

- privacy 在最新 `privacy_level_options` 中；
- creator 已禁用的 interaction 不能由请求声明为启用；
- 视频时长不超过 `max_video_post_duration_sec`；
- title/caption 满足当前长度与控制字符约束；
- commercial toggle 为明确值，不通过缺省值替用户作商业声明。

### 6.3 Shopify options

`ShopifyPublishOptions`：

- `platform: "shopify"`
- `product_id`：必填，格式必须是
  `gid://shopify/Product/<positive-decimal-id>`

`metadata.product_name` 可继续作为显示/alt metadata，但不具备定位 authority，
不得参与搜索、匹配、目标选择或 receipt。

### 6.4 兼容性

旧请求缺少 `platform_options` 时返回安全 422，不提供静默默认。原因是 TikTok
privacy/commercial consent 与 Shopify Product GID 都不能由服务端猜测。

deprecated `POST /publish/{video_id}` 继续忽略 path video ID，并消费同一严格
request model；它不会获得宽松兼容。

## 7. Consume 前只读 preflight

### 7.1 Internal acceptance inspect

`ArtifactAcceptanceService` 新增仅供内部发布使用的只读 inspect：

- tenant 与 acceptance ID 必须精确匹配；
- record 必须是 `accepted + available + unexpired`；
- stored artifact authority 必须通过现有严格校验；
- exact artifact path、SHA-256 和 size 必须重新解析并匹配；
- 不修改 acceptance，不创建 consume evidence；
- 不新增 HTTP consume/inspect route。

平台 preflight 完成后，既有 `consume_for_publish` 仍再次执行相同 authority 与
artifact 校验，防止 preflight 与 consume 之间的 race。

### 7.2 Connector preflight contract

新增 typed preflight vocabulary：

- `ConnectorPreflightRejected`：可信只读响应证明请求当前不能发布；
- `ConnectorPreflightUnavailable`：timeout、disconnect、5xx、parse、shape 或
  无法确定的只读响应；
- `ConnectorPreflightSnapshot`：只含后续 mutation 需要的安全、结构化事实，
  不含 PII、token 或原始响应。

TikTok snapshot 只保留 options 校验结果、max duration 与 observation time；
Shopify snapshot 只保留 exact Product GID、必需 scope 通过事实和 observation
time。snapshot 仅在当前 service invocation 内传递，不持久化。

### 7.3 Preflight state

新增 attempt status：

- `preflight_failed`

新增合法 transition：

- `prepared -> preflight_failed`

新增稳定 error code：

- `publish_preflight_rejected`
- `publish_preflight_unavailable`

`preflight_failed` 必须满足：

- `acceptance_consumed=false`
- `retry_allowed=true`
- 无 post ID、URL 或 receipt
- 不调用 provider mutation

## 8. TikTok v2 协议设计

### 8.1 固定 endpoint

TikTok connector 使用固定 origin `https://open.tiktokapis.com`：

- creator info：
  `POST /v2/post/publish/creator_info/query/`
- Direct Post init：
  `POST /v2/post/publish/video/init/`
- status fetch：
  `POST /v2/post/publish/status/fetch/`
- 可选 video readback：
  `POST /v2/video/query/?fields=id,share_url`

上传只使用 init 响应中的完整 HTTPS `upload_url`，不复用 endpoint env。

### 8.2 本地媒体校验

在平台 preflight 前校验：

- 文件仍是 exact accepted artifact；
- suffix/MIME 只允许 MP4、MOV、WebM 对应组合；
- size 大于 0 且不超过官方 4 GB；
- 通过项目已有媒体探测能力取得有限、可信 duration；探测失败视为 preflight
  unavailable；
- chunk 计划满足官方 5–64 MB、final <=128 MB、1–1000 片和顺序约束；
- 小于 5 MB 时整片上传。

测试通过注入媒体 probe 和小 fixture 验证，不引入新 dependency。

### 8.3 发布顺序

1. read-only creator info；
2. 校验 privacy、interaction、duration 和 commercial options；
3. consume acceptance；
4. recheck publish flag、token 和 artifact；
5. 恰好一次 Direct Post init，固定 `source=FILE_UPLOAD`；
6. `post_info` 使用批准 options，并强制 `is_aigc=true`；
7. 按已计算 chunk plan 对同一 upload task 顺序 PUT；每片至多一次；
8. 对同一 `publish_id` 做有界 status fetch；
9. `FAILED` 为确定性 post-consume failure；
10. `PUBLISH_COMPLETE` 才可创建 published receipt；
11. 超出 poll budget、状态结构漂移或无法确认终态进入 `ambiguous`，保存安全
    partial receipt，不重提 init；
12. status 返回单个公开 numeric ID 时可设置真实 post ID；零个表示没有公开
    ID；多个互相矛盾的 ID 视为 ambiguous。

TikTok status endpoint 虽使用 POST，但语义为 read-only observation。poll 次数与
总 monotonic deadline 必须有上限；具体数值进入实施计划和测试，不通过 sleep
拉长默认测试。

### 8.4 URL 与公开性

- 不用 `TIKTOK_USERNAME` 构造 URL；
- status fetch 返回官方公开 post ID 时，
  `public_visibility_verified=true`；
- video query 返回与该 ID 精确一致且 URL host/path 合法时，可记录
  `post_url` 并令 `verified_by=video_query`；
- 可信 `share_url` 必须使用 HTTPS，规范化后的 host 只能是
  `www.tiktok.com` 或 `tiktok.com`，不得显式携带 port，path 必须精确匹配
  `/@<creator>/video/<post_id>`（允许末尾 `/`），且不得包含 query、
  fragment 或 userinfo；
- video query 因 scope 未授权而不可用时，可以保留 status-fetch receipt，
  `post_url=null`；
- video query 返回矛盾 ID、mock URL 或非法结构时，receipt 不可信，attempt
  进入 ambiguous。

## 9. Shopify 2026-07 协议设计

### 9.1 固定 endpoint 与 credential

GraphQL endpoint 只由严格 store host 构造：

`https://<shop>.myshopify.com/admin/api/2026-07/graphql.json`

store host 必须是单一、规范化的小写 `<shop>.myshopify.com`，不允许 scheme、
path、port、query、fragment、userinfo、空白、IP 或其它域名。

所有 Admin API 请求只使用 `SHOPIFY_ACCESS_TOKEN` 的
`X-Shopify-Access-Token` header。

### 9.2 Preflight

Shopify read-only preflight 必须：

- 验证 exact Product GID；
- 查询 exact product 并要求响应 ID 精确匹配；
- 查询当前 app access scopes，至少证明当前协议所需的
  `read_products`、`write_products`、`write_files`；
- 验证本地视频格式、size <=1 GB、duration <=10 分钟；
- deterministic missing product/scope 为 `publish_preflight_rejected`；
- timeout、5xx、GraphQL parse/shape uncertainty 为
  `publish_preflight_unavailable`。

### 9.3 发布顺序

consume 后执行：

1. recheck flag、canonical token、store host 和 exact artifact；
2. 一次 `stagedUploadsCreate`，输入使用 `resource: VIDEO`、
   `fileSize`、filename 和 MIME；
3. 校验 staged target，只向 provider 返回的安全 HTTPS target 发送 multipart
   upload；不发送 Shopify token，不跟随 redirect；
4. 一次 `fileCreate(contentType: VIDEO, originalSource: resourceUrl)`；
5. 验证返回的是 `gid://shopify/Video/<positive-id>`；
6. 有界轮询该 exact Video GID 的 `fileStatus`；
7. `FAILED` 为确定性 post-consume failure；poll timeout/unknown 为 ambiguous；
8. `READY` 后恰好一次
   `fileUpdate(referencesToAdd: [exact Product GID])`；
9. 查询 exact Product GID 的 media，要求 exact Video GID 出现在回读中；
10. 只有 `READY + exact association readback` 才返回 published receipt。

每个协议 mutation step 至多一次。任何 timeout/disconnect/parse uncertainty 后
不自动重放 staged upload、fileCreate 或 fileUpdate。

### 9.4 Shopify 完成语义

W1-25 的 Shopify `published` 只表示
`shopify_product_media` 完成：Video 已 READY 且与 exact product 建立引用。

它不证明：

- product 已 active；
- Online Store 或其它 sales channel 已发布；
- storefront 对公众可见；
- 产品页 URL 可访问。

因此 Shopify receipt 固定：

- `post_id=null`
- `post_url=null`
- `public_visibility_verified=false`

不得再生成 Admin products URL。

## 10. PublishReceiptV1

### 10.1 字段

`PublishReceiptV1` 是 strict、extra-forbid、size-limited 模型：

| 字段 | 语义 |
|---|---|
| `schema_version` | 固定 `publish-receipt.v1` |
| `platform` | `tiktok` 或 `shopify` |
| `protocol_version` | `tiktok-content-posting-v2` 或 `shopify-admin-2026-07` |
| `completion_scope` | `tiktok_direct_post` 或 `shopify_product_media` |
| `provider_operation_id` | TikTok `publish_id`；Shopify 可为空 |
| `provider_resource_id` | TikTok public post ID 或 Shopify Video GID；可为空 |
| `target_id` | Shopify Product GID；TikTok 为空，避免持久化 creator PII |
| `provider_status` | 可信 provider 状态；partial receipt 可为空 |
| `post_id` | 只允许真实 TikTok numeric post ID |
| `post_url` | 只允许 TikTok 官方 readback 的安全 share URL |
| `public_visibility_verified` | 精确 bool |
| `observed_at` | 服务端生成的 timezone-aware UTC timestamp |
| `verified_by` | `status_fetch`、`video_query`、`file_query_and_product_readback` 或空 |
| `simulated` | 固定精确 `false` |

canonical JSON 编码后最大 8 KiB。字段不得附加 provider 原始 payload。

`provider_status` 只允许本次固定协议路径实际可观测的官方状态：

- TikTok Direct Post + FILE_UPLOAD：`PROCESSING_UPLOAD`、
  `PUBLISH_COMPLETE`、`FAILED`；
- Shopify Video：`UPLOADED`、`PROCESSING`、`READY`、`FAILED`。

在尚未获得可信 status 前，partial receipt 使用 null，不创造
`SUBMITTED`、`UNKNOWN` 或其它本地状态冒充 provider 状态。

### 10.2 Published receipt 不变量

TikTok：

- operation ID 必填、1–64 字符、无控制字符、无 mock 标记；
- `provider_status=PUBLISH_COMPLETE`；
- `verified_by` 至少是 `status_fetch`；
- post ID 若存在，必须是 positive decimal，并与 provider resource ID 相等；
- post URL 若存在，必须与 post ID 一致并来自可信 video query；
- 没有公开 ID 时 post ID/URL/resource ID 均为空，公开可见性为 false。

Shopify：

- `provider_resource_id` 必须是 exact Video GID；
- `target_id` 必须是请求中的 exact Product GID；
- `provider_status=READY`；
- `verified_by=file_query_and_product_readback`；
- post ID/URL 必须为空；
- 公开可见性必须为 false。

### 10.3 Partial receipt

post-consume `failed` 或 `ambiguous` 可以保存已确认的安全 partial receipt，
例如 TikTok publish ID 或 Shopify Video GID。规则：

- 不完整字段使用 null，不使用 placeholder；
- 未经终态 readback 不设置 `verified_by`；
- 不把 partial receipt 投影成 post ID/URL；
- partial receipt 仍必须通过平台、格式、size、mock 和敏感信息校验；
- preflight 失败不创建 receipt。

## 11. 数据库与 repository

### 11.1 Schema

在当前 Alembic head `f9a2b3c4d5e6` 之后新增一条 migration：

- PostgreSQL：`publish_logs.receipt JSONB NULL`
- SQLite：`publish_logs.receipt TEXT NULL`
- 新增非唯一 tenant/platform/post_id partial index，只覆盖
  `status='published' AND receipt IS NOT NULL AND post_id IS NOT NULL`，用于
  受限 legacy status lookup

同步：

- `src/storage/migrations/001_init.sql`
- `src/storage/db.py` fresh SQLite schema
- SQLite compat-column backfill
- production required-column readiness contract
- backup/restore schema contracts

本项不对生产数据库执行 migration。

### 11.2 状态与 CAS

状态集合新增 `preflight_failed`。合法 transition 增加：

- `prepared -> preflight_failed`

现有 post-consume transition 保持：

- `acceptance_consumed -> published`
- `acceptance_consumed -> failed`
- `acceptance_consumed -> ambiguous`

terminal CAS 必须在同一 SQL update 中写入：

- status
- safe receipt
- legacy post ID/URL projection
- stable error code
- updated_at

新代码 transition 到 `published` 时 receipt 必填。历史 `published` 行允许
`receipt=null` 被只读投影为 legacy/unverified，但不得补造 receipt，也不得被
legacy status 路由当成可信平台 authority。

### 11.3 Projection

现有 `post_id`、`url` 列保留为兼容 projection：

- 只从已验证 receipt 写入；
- TikTok 可写真实 post ID/URL；
- Shopify 固定为空；
- failed/ambiguous/preflight_failed 固定为空。

repository 读取 receipt 时先做 canonical JSON 和 strict model validation。数据库
中存在 malformed receipt 时 fail-closed 为 store unavailable，不向调用方返回
半可信数据。

## 12. API 与 status 兼容

### 12.1 Publish response

`PublishAttemptResponse` 保留现有字段，并新增安全 `receipt`。成功仍只允许
`status=published`、`success=true`、`acceptance_consumed=true`、
`retry_allowed=false`。

### 12.2 Canonical attempt readback

新增：

`GET /distribution/publish-attempts/{attempt_id}`

要求：

- `artifact:publish|all`；
- tenant 从认证上下文取得；
- 只按 `tenant_id + attempt_id` 读取；
- 不执行任何平台/外部调用；
- 不返回 metadata、artifact path、原始 content 或 provider payload；
- 返回 attempt/acceptance ID、platform、status、stable error、post projection、
  safe receipt、acceptance-consumed/retry projection 和 timestamps；
- `retry_allowed` 只表示该 attempt 终止时 acceptance 是否已知未消费，不是新的
  authority；后续请求仍必须重新通过 readiness、preflight 与 acceptance 校验；
- 不存在或跨 tenant 都返回 404；
- store 不可用返回稳定 503。

### 12.3 Legacy status

`GET /distribution/status/{platform}/{post_id}` 标记 deprecated，并收紧为：

- 权限从普通 API key 改为 `artifact:publish|all`；
- 只支持 TikTok numeric public post ID；
- Shopify 返回 410 和稳定 `distribution_status_route_deprecated`；
- 先按当前 tenant、platform、post ID 查找带有效 receipt 的已发布
  attempt，必须精确命中一条；
- 无 exact receipt 返回 404，不调用 connector；
- 命中多条相互矛盾的有效 receipt 时 fail-closed 为稳定 503，不选择
  “最新”一条冒充唯一事实；
- 只返回已持久化 receipt 的 `provider_status`、post ID 与精确
  `simulated=false` durable snapshot，不把 public post ID 错当 publish ID；
- 不调用 connector、不执行外部 status、不写数据库；
- 任何真实 status refresh/reconciliation 仍属于 W1-26。

前端新增 canonical attempt helper/type；现有 TikTok status helper 保留 deprecated
兼容。W1-25 不增加发布表单或新视觉流程。

## 13. 错误与状态矩阵

| 观察 | HTTP | attempt | stable code | acceptance | retry |
|---|---:|---|---|---|---|
| request/options 无效 | 422 | 无 | validation detail | 未消费 | 修正请求 |
| flag 关闭/credential/config 不可用 | 503 | 无 | `publish_connector_not_ready` | 未消费 | 修复配置后允许 |
| acceptance 不可用 | 404/409/503 | `authorization_failed` 或 state unknown | 既有 acceptance code | 未消费或未知 | 按既有合同 |
| deterministic preflight 拒绝 | 409 | `preflight_failed` | `publish_preflight_rejected` | 未消费 | 允许修正后再提交 |
| preflight timeout/5xx/parse/shape | 502 | `preflight_failed` | `publish_preflight_unavailable` | 未消费 | 允许再次 preflight |
| consume 后 credential/flag 消失，零 mutation | 502 | `failed` | `publish_connector_not_ready_after_consume` | 已消费 | 禁止 |
| mutation 后明确 provider 拒绝/FAILED | 502 | `failed` | `publish_connector_failed` | 已消费 | 禁止 |
| mutation timeout/disconnect/poll timeout | 502 | `ambiguous` | `publish_outcome_ambiguous` | 已消费 | 禁止 |
| receipt missing/mock/contradictory/malformed | 502 | `ambiguous` | `publish_outcome_ambiguous` | 已消费 | 禁止 |
| terminal persistence 无法确认 | 500 | state unknown | `publish_attempt_state_unknown` | 已消费 | 禁止自动动作 |
| trusted terminal receipt | 200 | `published` | 无 | 已消费 | 禁止 |

任何 ambiguous 都禁止自动删除、自动解除关联、自动重提或新建 acceptance。

## 14. 环境变量迁移

### 14.1 Canonical active variables

只保留：

- `TIKTOK_ACCESS_TOKEN`
- `TIKTOK_PUBLISH_ENABLED`
- `SHOPIFY_ACCESS_TOKEN`
- `SHOPIFY_STORE_URL`
- `SHOPIFY_PUBLISH_ENABLED`

publish flags 默认关闭。只有显式 truthy 值才能开启；unset、blank、unknown 值都
保持关闭。

### 14.2 退出 active runtime 的变量

以下非空 legacy/override 变量不再被读取为 fallback，且使 readiness 返回稳定
invalid configuration，不记录其值：

- `SHOPIFY_API_KEY`
- `SHOPIFY_ADMIN_TOKEN`
- `SHOPIFY_API_PASSWORD`
- `SHOPIFY_GRAPHQL_URL_TEMPLATE`
- `TIKTOK_USERNAME`
- `TIKTOK_API_UPLOAD_URL`
- `TIKTOK_API_BASE_URL`

同步更新：

- `src/config.py`
- `.env.example`
- active GitHub workflows
- no-provider/remotion contracts
- hermetic scripts 与对应 tests
- 当前 runbook/reference docs

历史、archive、research 文档不改写为“当时已使用新变量”；必要时只在活跃文档
标记 superseded。

## 15. 测试策略

所有实现严格执行 RED -> 最小 GREEN -> focused regression。

### 15.1 Request/config RED

- platform/options discriminator mismatch；
- TikTok privacy/boolean/commercial 字段缺失、coercion、unknown field；
- Shopify Product GID 空、错误类型、错误 resource、非 positive ID；
- Shopify 只设置 legacy token 时 not ready；
- canonical 与 legacy 同时非空时 fail-closed；
- endpoint override/username 非空时 fail-closed；
- publish flags unset/blank/false/invalid/true；
- 活跃 workflow、config、env example 和 no-provider contract 只使用 canonical
  名称。

### 15.2 Preflight RED

- acceptance inspect tenant/expiry/status/artifact mismatch；
- TikTok creator privacy/interaction/duration allow 与 reject；
- Shopify product/scope exact allow 与 reject；
- timeout、disconnect、4xx/5xx、GraphQL/API error、parse/shape；
- preflight rejection/unavailable 均不 consume、不调用 mutation；
- prepared 到 preflight_failed 的 SQLite/PG CAS。

### 15.3 TikTok protocol RED

fake transport 严格断言：

- creator info -> init -> ordered PUT chunk(s) -> status fetch -> optional video
  query；
- 固定 official URLs 和 request bodies；
- `FILE_UPLOAD`、chunk headers、`is_aigc=true`；
- init 恰好一次、每片恰好一次、无 retry；
- PROCESSING 到 PUBLISH_COMPLETE 的 bounded poll；
- FAILED、poll timeout、malformed/multiple post IDs；
- publish ID 与 post ID 永不互换；
- 不拼 username URL、不接受 mock ID/URL。

### 15.4 Shopify protocol RED

fake transport 严格断言：

- exact 2026-07 URL 与 access-token header；
- staged `resource: VIDEO + fileSize`；
- multipart upload 不携带 Shopify token；
- fileCreate 返回 exact Video GID；
- PROCESSING -> READY bounded poll；
- fileUpdate 只关联请求中的 exact Product GID；
- product readback 包含 exact Video GID；
- 每个 mutation step 至多一次；
- FAILED、userErrors、timeout、parse、poll timeout、association mismatch；
- 无 product-name search、无 Admin URL、无 Shopify post ID。

### 15.5 Receipt/repository/API RED

- TikTok/Shopify published receipt 全字段不变量；
- safe partial receipt；
- missing/non-bool simulated；
- mock marker、provider/platform/status/ID/URL contradiction；
- canonical JSON 与 8 KiB limit；
- receipt 与 terminal state/post projection 原子 CAS；
- historical null receipt 只读兼容但不可信；
- SQLite fresh/compat、PostgreSQL fresh/upgrade/downgrade/re-upgrade；
- tenant-bound attempt readback 与跨 tenant 404；
- legacy status permission、exact receipt lookup、Shopify 410、零外部调用；
- error/log/DB 不含敏感字段。

### 15.6 回归门

由窄到宽执行：

1. 新 W1-25 request/config/preflight/connector/receipt tests；
2. W1-22 acceptance 与 W1-23/W1-24 publish regressions；
3. disposable PostgreSQL 18 migration/repository/service tests；
4. backup/restore、readiness、OpenAPI drift 和 auth contracts；
5. metrics connector/poller compatibility；
6. Ruff 与 backend `make ci`；
7. frontend Vitest、ESLint、TypeScript、OpenAPI typegen/drift、Next build；
8. hermetic HTTP-construction/socket guard；
9. docs/frontmatter/link/archive governance；
10. `git diff --check`、sensitive-pattern、placeholder/mock-ID、temporary artifact
    scan；
11. 主线程两遍自审，明确 `independent_review=false`。

不复制历史 pass count 作为本轮证据，只记录 fresh 输出。

## 16. 验收标准

### 16.1 功能

- 两个平台请求必须携带正确 platform options；
- preflight 失败不会消费 acceptance；
- TikTok/Shopify fake transport 顺序与当前官方协议一致；
- 新 `published` 必须有严格 receipt；
- TikTok operation/post ID 分离；
- Shopify Video/Product GID 分离且无 post projection；
- fake/mock/derived ID/URL 无法进入 published；
- no retry、one connector invocation、no acceptance restore 仍成立；
- attempt readback tenant-bound 且不触发外部调用；
- legacy status 不再允许任意 ID 探测。

### 16.2 数据与兼容

- Alembic、fresh PG init、SQLite fresh/compat 均有 receipt；
- terminal state/receipt/post/error 一次 CAS；
- 历史 null receipt 不被改写或冒充验证；
- W1-22/W1-23/W1-24 原有 authority/concurrency/error 不变量保持绿色；
- OpenAPI 和生成前端类型一致；
- metrics 不把 Shopify Video GID 当成已公开 post。

### 16.3 安全与边界

- 所有测试默认阻止真实 HTTP client/socket escape；
- 不读取或打印 credential；
- 不调用真实 platform/provider/status；
- 不执行 production DB、SSH、deploy、live publish、delivery、metrics pull；
- 最终报告列出 fresh commands、RED 诊断、文件 manifest、未验证项和
  W1-26 精确授权门；
- 无 independent reviewer 时状态不得超过
  `implementation_complete_local / independent_review_pending`。

## 17. 预计文件影响

业务与合同：

- `src/config.py`
- `src/connectors/base.py`
- `src/connectors/registry.py`
- `src/connectors/tiktok_connector.py`
- `src/connectors/shopify_connector.py`
- `src/models/publish_attempt.py`
- `src/services/artifact_acceptance.py`
- `src/services/publish_attempt.py`
- `src/storage/publish_attempt_repository.py`
- `src/storage/db.py`
- `src/storage/migrations/001_init.sql`
- `src/routers/distribution.py`
- 一条新的 Alembic migration

配置、生成类型与活跃治理：

- `.env.example`
- active GitHub workflows 与 hermetic/no-provider contracts
- `web/src/components/api.ts`
- `web/src/types/api.generated.ts`（生成）
- 对应 tests、runbook、reference、roadmap、Kiro/SDD/report

明确不改：

- acceptance HTTP authority/UI；
- publish/review 产品 UI；
- generation provider clients；
- production secret 文件与部署环境；
- delivery、active-post metrics、C2PA、W1-26 live harness 行为；
- archive/research 历史正文。

实施计划若发现必须扩展到上述“明确不改”范围，必须暂停并重新确认规格。

## 18. 回滚与发布安全

本轮只做本地实现，所以回滚只撤销 W1-25 manifest，不覆盖既有 Wave 1 dirty
worktree。

schema 变更是 additive nullable column；本地 downgrade 可删除 receipt column，
但不得用于已有真实 receipt 的生产库。未来若部署：

1. 先阻断 publish/status；
2. 备份并验证 PostgreSQL；
3. 先执行批准 migration，再启动要求 receipt column 的应用；
4. 保持两个 publish flag 默认关闭；
5. read-only 验证 schema/readiness 后，W1-26 仍需单 post 精确授权；
6. 回滚应用前继续阻断 route，不能回到旧 mock/derived receipt 行为；
7. 对 consumed/failed/ambiguous attempt 只做人工 reconciliation。

不自动执行 Shopify `fileDelete`、`referencesToRemove` 或 TikTok cancellation。
这些都是真实外部 mutation，必须进入 W1-26 的单独 rollback plan 与授权。

## 19. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| preflight 与 consume 之间发生 race | 使用过期 authority/bytes | inspect 后 consume 再验证，consume 后再次解析 exact artifact |
| status polling 被误当 retry | 隐性重复发布 | 只观察同一 operation ID；init/fileCreate/fileUpdate 不重放 |
| Shopify 多步骤协议与“一次调用”混淆 | 错误删减必需 mutation | one service connector invocation；每个官方 step at most once |
| provider 返回 upload URL 造成 exfiltration | 本地视频发往不可信目标 | HTTPS/public-host/no-userinfo/no-redirect 校验，绝不携带 Admin token |
| TikTok publish ID 被继续写作 post ID | 虚假公开证据 | receipt 字段分离 + strict numeric public post ID |
| Shopify GID 被继续称为 post | metrics/UX 误判 | completion scope + null post projection + product readback |
| 历史 null receipt 被误当真实 | 旧数据提升证据等级 | legacy/unverified 只读，不用于 status authority |
| endpoint env 可被篡改 | credential 外传 | 固定 official origin/version，测试靠 injected client |
| 无 independent reviewer | 路线图完成门未满足 | 保持明确状态 ceiling，不冒充 completed_local |
| 同一路径反复 patch | 根因被掩盖 | 第三次验证仍失败时停止，回到协议/状态机审查 |

## 20. 实施入口门

本规格已根据用户逐节确认写出，用户已完成对实际文件的
最后核对，当前状态为 `status: stable`。允许：

1. 使用可用的 writing-plans 指令或项目现有等价模板，编写逐文件、逐测试的
   W1-25 TDD 实施计划；
2. 对计划做机械与语义自审；
3. 再进入业务代码 RED/GREEN 实施。

本规格与后续计划都不授权 commit、stage、push、PR、production migration、
SSH、deploy、真实 preflight、真实 connector/status、live publish、delivery 或
metrics live pull。
