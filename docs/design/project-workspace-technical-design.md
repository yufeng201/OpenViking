# 项目工作区与 Agent 接入技术方案

状态：待实现，可用于开发拆解和评审。

代码基线：`a0141a96ebe3c5b75405e68c3de0fa036742d170`。核对日期：2026-09-22。

本文中的新增字段、接口、目录能力均为设计，不代表当前服务已经支持。现状依据来自本地源码静态核对，尚未通过实现原型验证。开发前若基线变化，应重新核对涉及模块。

## 1. 背景与目标

公司中的一个项目通常由产品、前端、服务端等多人共同开发。当前 OpenViking 的用户记忆与 Session 主要归属 user；account 内共享 resources 已有能力，但不能完整表达项目对会话和记忆的所有权。

目标是让项目成为稳定的资产归属单元：成员使用自己的 User API Key，工作区配置选择个人空间或项目空间。项目工作中产生的资源、会话和记忆属于项目；成员退出不删除资产，新成员加入后可以复用历史知识。

典型场景：服务端成员开发订单接口，保存接口资料、编码 Session 并提取接口约定与排障经验。前端成员在同一项目中开发页面，可以召回这些知识并查看原始会话。服务端成员离职后，资料和记忆继续保留。

### 1.1 必须实现

- 项目属于 account；用户通过项目成员关系获得权限。
- 一个项目可以关联多个仓库，一个用户可以加入多个项目。
- 项目具有自己的概况、架构、约定、决策和经验，不套用个人画像与偏好模板。
- 仓库配置个人 peer 或 project；连接与凭证继续保存在本机配置中。
- 文件访问、搜索、Session、异步任务、抽取和来源跳转使用一致的归属。
- 未启用新模式的客户端保持现有行为。
- 用户删除、离职和 Key 轮换不影响项目资产的归属。

### 1.2 控制首版成本

- 复用现有用户组，项目管理暂由 account 管理员负责。
- 成员互相查看 Session，但不支持多人同时写同一个 Session。
- 复用现有抽取、合并、路径锁、索引和目录摘要机制。
- 不做跨 account 项目、邀请审批、细粒度项目目录 ACL、项目技能抽取。
- 不做自动判断代码已合并或已部署，不建设复杂分支记忆库。
- 不自动迁移个人历史，不做回收站和项目物理删除产品流程。
- 先打通 Codex 记忆插件的一条完整接入链路，再推广其他 Agent。

## 2. 当前实现与改造边界

| 链路 | 当前事实 | 需要调整 |
| --- | --- | --- |
| 身份 | `RequestContext` 有 user、role、group_ids、actor_peer_id，无项目上下文 | 增加经过校验的工作区目标，保留真实 user |
| 用户组 | API Key manager 已有组和成员管理，认证层解析 group_ids | 项目关联现有组，复用成员存储 |
| URI | `VikingURI` 有 scope 白名单；namespace 识别 user、agent 等 | 新增 project，支持 peer 下 sessions |
| ACL | `storage/acl.py` 仅将顶层 resources 视为 ACL 对象 | 项目使用独立成员权限边界，不依赖 ACL 开关 |
| Session | 默认 URI 为 user 下 sessions；允许内部显式传 session_uri | 将创建、列表、加载、删除统一为归属解析 |
| Session meta | 已有 created_by_user_id，但无独立项目归属 | 新增目标字段，创建后不可变 |
| 队列 | SessionCommitMsg 有 session_uri、user；worker 重建用户上下文 | 持久化归属并恢复受限任务上下文 |
| 自动提交 | 扫描 user 下 sessions | 扩展为支持三类 Session 的枚举器 |
| 抽取 | schema 渲染、隔离和合并阶段均依赖 user/peer | 独立解析 memory root 与项目模板 |
| 召回 | 默认 targets、向量过滤、context assembler 分别依赖现有根目录 | 三处同步增加项目与新 peer 范围 |
| 删除 | 用户删除调用 delete_user_data 并删除用户目录 | 项目索引不能以贡献者作为 owner_user_id |
| 仓库配置 | 已有 config.json/config.local.json、workspace registry、schema 和加载器 | 扩展现有文件，不增加另一套配置格式 |

已有仓库配置实现不等于用户当前安装的插件已经升级。上线必须验证实际插件版本和服务端能力，不能仅依据仓库文件存在。

## 3. 领域模型

### 3.1 用户、所有者与目标空间

`User API Key` 只解决 actor 身份。项目配置不能伪造 account/user，也不能授予成员权限。

建议新增小型不可变类型 `WorkspaceTarget`：

```python
@dataclass(frozen=True)
class WorkspaceTarget:
    kind: Literal["user", "peer", "project"]
    owner_id: str       # user/peer 为真实 user_id；project 为 project_id
    peer_id: str | None = None
```

account_id 由 RequestContext 提供。peer 是用户拥有的子空间，不是独立所有者。完整目标键为 `(account_id, kind, owner_id, peer_id)`，用于缓存、任务、合并批次和幂等键。

`RequestContext.user` 始终保留真实调用者。增加 optional workspace target，并由认证后的服务层解析器构建；客户端不能直接提交“已校验”的角色或组信息。

保持 `canonical_user_root()`、`viking://~` 原义。新增 `workspace_root()`、`session_root()`、`memory_root()` 等集中函数，不在几十个调用点手工拼路径，也不全局把 user root 改成 project root。

### 3.2 项目元数据

```text
Project
  account_id
  project_id               account 内唯一、稳定、不可改名
  name
  description              项目目标、业务范围
  repositories[]           可选的仓库标识、显示名、模块说明
  group_id                 绑定现有用户组
  status                   active | archived
  schema_version
  created_by
  created_at / updated_at
```

建议以现有 AGFS 系统元数据存储方式新增 ProjectStore，置于 `/local/{account_id}/_system/projects/`，复用现有元数据读写和锁模式。不得通过普通文件 API 暴露或允许成员编辑系统元数据。无需引入新数据库。

项目与成员分离：ProjectStore 不重复保存用户名单，以绑定 group 的成员列表为唯一事实来源。项目创建先验证组存在；首版不自动建组，减少跨两个存储对象的事务。项目绑定的组不得被直接删除，服务端组删除入口增加引用检查。

项目创建失败不能留下可访问的半成品：先持久化项目元数据，再初始化可幂等重试的目录；未初始化完成时不允许写入。不存在的项目即使手工创建同名文件夹也不能通过鉴权。

### 3.3 权限

首版只有 account 管理员与项目成员两层，不引入项目角色表。

| 操作 | 成员 | Account 管理员 |
| --- | --- | --- |
| 查看、检索项目资料、记忆、Session | 允许 | 允许 |
| 上传和更新项目资料 | 允许 | 允许 |
| 创建项目 Session | 允许 | 允许 |
| 追加/commit 自己创建的 Session | 允许 | 允许 |
| 追加其他成员的 Session | 不允许 | 首版也不代写 |
| 人工修订共享记忆、删除共享资源/Session | 不允许 | 允许 |
| 通过已受理 commit 自动更新项目记忆 | 由受限 worker 执行 | 由受限 worker 执行 |
| 创建项目、编辑概况、管理成员、归档 | 不允许 | 允许 |

管理员可删除和检查会话，但不能绕过会话作者约束制造新的作者消息；后续接力采用新会话并关联来源。

管理员权限限定当前 account。ROOT 延续现有特权规则，但正常验收必须使用普通 User Key，不能用 ROOT 测试代替隔离测试。

成员鉴权始终启用，与 account 资源 ACL 开关无关。源项目目录的读取不能通过 copy/move、grep/glob、摘要、关系链接、工具结果下载、导出等替代接口绕过。

## 4. Agent 接入与仓库配置

### 4.1 用户操作

1. 管理员建立项目、关联成员组，将员工加入组。
2. 员工配置服务地址与自己的 User API Key。
3. 在现有插件安装/配置入口选择个人空间或项目空间。
4. 向导写入现有 `.openviking/config.json`，或只写本机 workspace registry。
5. 插件验证服务端能力与目标权限，显示当前用户、目标空间、配置来源。
6. Hook 捕获、MCP 召回、Session 同步使用同一解析结果。

不新增独立配置文件。API Key 和服务地址仍放现有本机连接配置/环境变量，不允许从仓库配置覆盖。

### 4.2 版本化启用

现有 workspace v1 的 peer 是消息隔离/召回配置，不改变 Session 根。为避免悄悄改变老用户的数据路径，建议新增 workspace schema v2；文件名仍为 `.openviking/config.json`。

个人仓库：

```json
{
  "version": 2,
  "peer": { "id": "my-side-project" }
}
```

公司项目仓库：

```json
{
  "version": 2,
  "project_id": "order-platform"
}
```

v2 未指定 project，peer 按现有来源规则解析：有有效 peer 则选择 peer 工作区；显式 `peer.source: "none"` 或无有效来源则选择 user。无配置/v1 完整保持旧行为，包括旧的 peer 消息归属。

不要新增独立 `mode` 字段，避免 mode 与 project_id 相互矛盾。project_id 为空字符串是错误；本地覆盖使用 `project_id: null` 明确选择个人，并由向导提示目标变化。

### 4.3 配置合并与目标切换

- 沿用已有配置分层顺序，在现有 loader 中统一处理，不在每个 harness 重写一套。
- project 选择后，自动推导的 Git peer 和全局个人 peer 默认值不参与目标构造。
- 同一有效仓库配置显式指定 project_id 和 peer.id/source 时拒绝；向导切换时原子清理当前文件的互斥字段，并在写入前验证完整配置。其他配置层仍有冲突或覆盖了所选目标时，拒绝写入并提示修正对应配置，不自动修改团队配置或个人覆盖文件。
- 本地层明确切回个人时，应明确给出 peer 配置或 source，不依赖残留值。
- 仓库目标、Key、服务地址变化后，丢弃旧的权限探测缓存；历史会话不能被重新路由。
- 目标变化从新 Agent 会话起生效。当前会话继续旧目标或提示重开，不搬运已有缓存和消息。
- 项目 Key 无权限、服务端不支持新协议时停止该目标的 capture/recall，明确提示；不回退到个人写入。
- 新插件检测 v2，不支持的旧插件无法可靠理解该语义。发布文档必须要求升级接入端，并对发布支持的插件版本验证未知版本拒绝行为，不能声称任意旧插件都能安全读取 v2。

### 4.4 传输协议

建议在 HTTP/MCP 客户端统一新增两种可选目标头（待实现）：

```text
X-OpenViking-Project: order-platform
X-OpenViking-Workspace-Peer: my-side-project
```

二者互斥；无目标头沿用旧模式。peer ID 对应认证用户自己的 peer，不能指定另一个 user。

不要复用 `X-OpenViking-Actor-Peer` 表示会话所有权：它当前只是 peer 视图过滤。新旧头同时出现且语义冲突时返回 400。

Session 创建由头确定目标，持久化后目标不可变。后续操作要求目标与已存 meta/URI 相符。已有明确 URI 的 API 不改写 URI；项目模式显式访问另一个空间默认拒绝，切换目标后重新请求，防止误操作。

长期 MCP 进程必须绑定一个工作区目标，或在每次工具调用取得可靠工作区信息。无法确定目标时不能使用其启动 cwd 猜测；首版允许为每个工作区生成独立 MCP 配置/实例。HTTP SDK 使用不可变 scoped client 或请求参数，避免修改共享客户端的全局 headers。

客户端本地队列、会话映射、去重键至少包含服务端身份、account、user、完整 target、Agent session ID。重试回放使用入队时目标，不重新读取当前仓库配置。

## 5. 数据目录

```text
viking://user/{user_id}/
  sessions/                            旧 Session 与 user 模式
  memories/
  resources/
  peers/{peer_id}/
    sessions/                          v2 个人工作区新增
    memories/
    resources/

viking://project/{project_id}/
  resources/                           用户自行组织原始资料
    product/
    api/
    repositories/
  sessions/{session_id}/
    .meta.json
    messages.jsonl
    history/
    tool-results/
  memories/
    overview.md                        从项目概况生成的导航
    architecture/                      模块职责、依赖、数据流
    conventions/                       接口、开发、测试与发布约定
    decisions/                         已确认选择、原因、影响范围
    experiences/                       问题、方法、验证结果
```

真实存储统一加 `/local/{account_id}/`。project_id 不跨 account 寻址。

resources 子目录是推荐，不强制初始化空树。Session 内部布局继续复用现有实现。overview.md 由项目元数据确定性生成起步，不增加每次 commit 的全项目 LLM 汇总；它是可重建导航，不是唯一事实来源。

项目 memory 分类是新增模板类别。它们仍属于 `context_type=memory`，不是新向量集合。必须同步模板注册、schema、初始化、抽取结果统计及 context assembler 的类别映射，不能假设新增 YAML 就全部生效。

`skills` 暂不启用项目写入；请求应明确报不支持，避免无意写入个人 skills。项目根不承载 credential、成员名单等可编辑系统配置。

## 6. 服务端入口与 API

以下均为拟新增契约。新接口注册时同步中英文 API 索引与 SDK 类型。

| 方法与路径 | 用途 |
| --- | --- |
| POST `/api/v1/projects` | 管理员创建项目，指定已有 group_id |
| GET `/api/v1/projects` | 成员列自己加入的项目；管理员列 account 内项目 |
| GET `/api/v1/projects/{id}` | 获取可访问项目概况 |
| PATCH `/api/v1/projects/{id}` | 管理员修改名称、描述、仓库、状态 |
| GET `/api/v1/projects/{id}/members` | 管理员读取绑定组成员 |
| PUT `/api/v1/projects/{id}/members/{user_id}` | 管理员添加已有 account 用户，幂等 |
| DELETE `/api/v1/projects/{id}/members/{user_id}` | 管理员移除成员，保留资产 |
| GET `/api/v1/workspace` | 校验目标并返回 resolved target、能力版本、读写权限 |

Session、资源、搜索继续复用原接口，通过目标上下文选定范围，不复制成另一套 project Session API。Session 返回结果增加 canonical URI 和 owner 信息，不能只返回 session_id。

错误约定：冲突或非法目标 400；未认证沿用现有错误；非成员访问项目统一返回不暴露详情的 404；已确认可见但禁止的操作返回 403；归档项目写入返回 409。对外隐藏不影响服务端审计记录真实原因。

`GET /workspace` 探测只是接入提示，每次实际请求仍需鉴权。返回 capability 包括协议版本和支持的 target kinds；不能通过“接口返回 200”推断全部能力。

新增 ProjectService/ProjectStore，在统一服务生命周期中初始化；认证层只解析原始目标选择，成员解析在依赖可用的上下文构建层完成，避免 auth 与全局 service 循环依赖。

## 7. Session 生命周期

### 7.1 持久化

SessionMeta 新增 `workspace_target`、可选 `repository/branch/commit`、可选 `parent_session_uri`。created_by_user_id 继续表示贡献者。旧 meta 无 target 时仅按经过验证的旧 canonical 路径推断，不能依据当前调用者的目标猜测。

SessionService 的 create/get/list/delete/commit/config/history/工具结果访问都使用统一 resolver。同名 session_id 可存在于不同目标，不全局扫描猜测所属空间。

v2 peer 是仓库容器；消息中的 peer_id 仍可能是既有参与者语义。首版 v2 仓库会话不混用多参与者提取：只按 Session 固定 memory root 抽取，禁止生成嵌套 peers。legacy 会话继续旧 isolation 逻辑。

### 7.2 后台任务

SessionCommitMsg 增加版本与 workspace_target；恢复后交叉检查 account、session_uri、archive_uri、meta target 一致性。旧队列消息走旧路径。处理 rolling upgrade 时先升级全部消费者，再启用新生产者；现有 from_dict 会忽略未知字段，不能假设老 worker 理解项目消息。

已接受的项目 commit 可以在贡献者离职后完成：任务使用内部受限的资产处理上下文，权限只覆盖该项目/会话允许的派生数据，不以 ROOT 或仅 bypass_acl 代替。触发者仅用于审计；任务权限不能由外部请求头构造。

project 已归档时停止新写入，后台任务暂停/取消并进入可查询状态；不得静默继续更新。项目物理删除不在首版，account 删除则清理全部项目与队列引用。

任务状态查看按所属空间鉴权，不能仍只允许触发用户查看，也不能凭 task_id 公开。移除用户时不得取消/清理其触发但属于项目的全部任务。

自动提交扫描统一枚举 user、peer、project 三类 Session。锁/claim 键包含完整 target 或 canonical Session URI；验证两名成员的同项目写入、两个项目相同 Session ID 不冲突。

## 8. 项目记忆抽取

### 8.1 模板与策略

新增项目专用 registry 与模板，不修改共享个人默认 registry。第一版项目采用服务默认的固定项目策略，不继承触发者个人 memory_policy，不开放复杂的项目策略编辑器。

| 类别 | 抽取要求 | 不应当作有效结论 |
| --- | --- | --- |
| architecture | 模块职责、数据流、依赖关系及来源 | Agent 未验证的架构猜测 |
| conventions | 明确的项目约定、接口约束 | 某位成员的个人表达偏好 |
| decisions | 已明确选择的方案、原因、影响 | “准备考虑”或未采纳的建议 |
| experiences | 触发条件、处理方式、验证结果 | 未运行却声称成功的修复 |

不提取个人画像、私人偏好和凭证。过滤规则不保证识别所有敏感信息，接入说明应明确项目会话对成员可见。

### 8.2 流程

```text
Session commit 固化 archive
→ worker 加载固定 target
→ 选择个人/项目 registry
→ 读取当前目标已有记忆
→ 抽取结构化候选及来源
→ 校验目标、来源、类别
→ 同目标内去重/合并
→ 加锁更新文件及版本
→ 语义摘要/向量索引
→ 返回任务结果与记忆来源链接
```

memory root 必须由服务端生成。模板只在允许根内组织类别与文件，模型不能选择其他 user/project。不要将完整 URI 直接塞进当前 `user_space` 变量：现有 URI 模板有路径段安全处理，应该增加可信 root 渲染参数并保留转义校验。

抽取上下文、隔离 handler、patch merge provider、streaming updater、URI 生成和最终写入必须共同使用目标。仅替换模板目录会被合并阶段的 user 路径重算覆盖。

个人 peer v2 使用现有个人内容模板、固定到当前 peer 根；项目使用项目模板。user 模式与 legacy policy 保持现状。项目首版禁用不支持的个人技能进化/提取分支，不能静默产生个人输出。

### 8.3 来源与冲突的最小实现

每条项目记忆保存贡献者、source Session/archive URI、可用的 source message IDs、创建/更新时间、可选 repository/branch/commit。来源 ID 由服务端验证确实存在于本次 archive，不能盲信模型生成的引用。

证据不足的提议不进入有效记忆。明显冲突采用保守策略：保留旧结论，新候选写入 Session 归档下独立的 `memory-candidates.jsonl`，记录冲突原因，不进入默认 memory 索引。管理员可通过后续人工修订处理，首版不做审批页面。

未检测出的语义冲突仍是模型质量风险，首版不承诺自动发现所有冲突。对已识别候选，使用 `(archive_uri, candidate_id)` 保证重试不重复写入。

同项目、同类别的更新复用已有合并与文件锁；批次键由 account/user 改为完整 target。写入时读取最新版本，冲突后重新合并或保留候选，不能以先前读取的全文直接覆盖。

首版资源导入正常做解析、摘要和索引，不自动触发资源到项目记忆抽取，避免建立第二套更新流程。接口正式文档与会话经验都能召回，后者保留来源与适用范围。

## 9. 检索、索引与上下文组装

### 9.1 默认范围

| 请求模式 | 默认范围 |
| --- | --- |
| legacy | 保持现有逻辑 |
| v2 user | 当前用户资料/记忆及获授权公共资源 |
| v2 peer | 当前 peer 资料/记忆及获授权公共资源；个人通用偏好按明确白名单补充 |
| project | 当前 project resources/memories 及获授权 account 公共 resources |

项目不自动读个人记忆，不扫描该用户加入的全部项目。权限可访问集合与默认检索集合分开；没有目标的旧请求不能因为用户加入项目就自动扩大范围。

原始 Session 首版提供列表、查看和来源跳转，不必将全部 messages 作为知识向量召回。Session 摘要若被索引，也要携带同一 owner 及权限，不得绕过项目边界。

### 9.2 索引字段

新增可选 `owner_project_id`；个人/peer 延续 owner_user_id。项目记录的 owner_user_id 不保存贡献者，贡献者另用元数据字段记录。project_id 与 account_id 一起构成隔离边界。

所有索引生产路径，包括 resource ingest、memory update、embedding converter、reindex，都从 canonical URI/已验证 target 推导归属，禁止从触发者 user_id 默认补成项目 owner。

升级前验证各支持向量后端的增量字段更新能力。已有个人记录无需迁移；若后端不能在线增加字段，需要在启用项目能力前完成版本化 schema 升级/重建。不能只修改 Python schema 声明。

检索过滤增加 account + 授权项目条件，并保持路径范围限制；不要只把 project 根放进 visible_roots 就认为安全。ACL 关闭、空 target、显式 URI、多 target、ROOT/ADMIN 特例都需测试。

新增 memory 分类同步进入 context assembler：项目按 architecture/conventions/decisions/experiences 组装，不沿用个人类别列表。branch/commit 在首版作为适用信息展示和可选过滤；未知版本不能标记为最新，正式文档与会话记忆不一致时保留来源差异。

### 9.3 删除与撤权

用户删除继续删除其个人目录及 owner_user_id 索引；项目文件与 owner_project_id 索引保留。task tracker、work index、usage cleanup 和后台恢复一并检查，避免文件保留但任务/来源索引被删除。

组成员移除后，新请求重新解析权限；多进程下需复用并验证组配置刷新机制，无法保证即时刷新时不得上线宣称即时撤权。最小兜底是项目授权在刷新完成前直接读取权威成员数据，不接受陈旧授权缓存。

## 10. 代码改造清单

以下现有路径已在基线中核对；“新增”是建议文件，可按实际组织调整。新增业务模块尽量保持单文件不超过 800 行，不继续向超大 Session 文件堆叠项目管理逻辑。

| 目录/文件 | 实现内容 |
| --- | --- |
| `openviking/core/workspace.py`（新增） | WorkspaceTarget、目标校验、根路径、序列化与兼容解析 |
| `openviking/core/namespace.py` | project URI、内容分类、peer Session 形状、owner 推导 |
| `openviking_cli/utils/uri.py` | scope 白名单与构造器 |
| `openviking/core/directories.py` | 项目/peer 目录初始化及显示 |
| `openviking/server/identity.py`、`auth/__init__.py` | 请求目标解析、真实 actor 保留 |
| `openviking/server/project_store.py`（新增） | 项目元数据、幂等初始化与组引用 |
| `openviking/service/project_service.py`（新增） | 生命周期、成员包装、权限解析 |
| `openviking/server/routers/projects.py`（新增） | 项目与 workspace 能力 API |
| `openviking/server/api_keys/legacy.py`、`new.py`、`routers/admin.py` | 复用成员逻辑、组删除引用保护、删除用户联动 |
| `openviking/storage/viking_fs/_access.py` 与写操作入口 | 项目/peer 文件权限、操作类型约束、禁止直接改 Session 内部文件 |
| `openviking/service/session_service.py` | 目标 Session resolver、策略选择、任务查看权限 |
| `openviking/session/session.py` | Meta、固定归属、commit target 传递 |
| `openviking/service/session_auto_commit.py` | 三类 Session 枚举和 claim |
| `openviking/storage/queuefs/session_commit_msg.py`、`session_commit_processor.py` | 队列版本、目标恢复和受限任务权限 |
| `openviking/storage/queuefs/semantic_msg.py`、相关 ingest/embedding 消息与 processor | 目标、owner 和任务去重键传播，避免只修 Session 队列 |
| `openviking/session/memory/` | registry、isolation、context provider、merge、updater、URI 生成支持目标 |
| `openviking/prompts/templates/memory/project/`（新增） | 项目四类抽取模板及可信度约束 |
| `openviking/core/retrieval_targets.py` | 新模式默认搜索范围 |
| `openviking/retrieve/context_assembler/gather.py` | 项目类别与 peer 根组装 |
| `openviking/storage/collection_schemas.py`、`viking_vector_index_backend.py` | owner_project_id、schema 更新、权限过滤、用户删除保护 |
| `openviking/storage/queuefs/embedding_msg_converter.py` | 索引 owner 统一来源 |
| `openviking/service/deletion.py`、`task_work_index.py`、`reindex_executor.py` | 删除、任务归属、重建覆盖 |
| `openviking/service/resource_memory_link_service.py` | 项目记忆与资源来源关系 |
| `openviking/server/routers/content.py`、`resources.py`、`sessions.py` | 现有 user-only 校验与目标入口适配 |
| `openviking/server/mcp_endpoint.py` | MCP 目标透传与校验 |
| `openviking_cli/client/`、配置和 CLI 实际入口 | scoped client、目标头和错误展示；检查 Rust CLI 对应入口 |
| `examples/memory-plugin-shared/lib/` | config-schema、workspace-config、plugin-config、session-model、doctor、异步写入目标 |
| `examples/schemas/workspace-config-v2.json`（新增） | 新协议 Schema；v1 保留 |
| `examples/memory-plugin-shared/sync.mjs` 及生成的 harness 副本 | 修改共享源后同步，不分别手改所有副本 |
| `agent-plugins/servers/shared/` | MCP 配置、凭证分离、目标头、实例缓存 |
| `web-studio/src/routes/` 及请求/查询层 | 项目选择、成员入口、资源与会话页面目标化、缓存隔离 |
| `docs/` | 中英文 API 索引、Agent 接入、兼容与升级说明 |

实施时补做入口清单审计：搜索所有 user root/session URI 拼接、RequestContext 重建、owner_user_id 回填、队列序列化、FS bypass 和导出入口。上表是主要修改面，不保证替代完整调用链审计。

## 11. Studio 与交付入口

不新增一套独立项目控制台。顶部增加个人/项目空间选择；个人模式可选 peer。项目列表仅显示可访问项目。

管理员使用简洁表单创建项目、选择已有组、维护概况和仓库。成员复用现有目录浏览和 Session 页面；共享会话输入框只对作者开放。项目记忆展示分类与来源链接，贡献者为已删除用户时显示保留的贡献标识。

所有 query key、页面 URL 和 mutation 参数携带完整 target；切换空间时取消旧请求、清理编辑草稿与错误状态，不能让迟到响应覆盖新空间。会话深链接携带 canonical 归属，不依赖访问者当前选择。

CLI/API 管理入口在第一阶段可用；Studio 和 Agent 配置向导在第二阶段完成。只有代码配置示例而没有可用接入流程，不算用户交付完成。

## 12. 开发顺序与验收门槛

### PR 1：基础类型与项目管理

- 新增 WorkspaceTarget、ProjectStore/Service/API，绑定现有组。
- 支持 URI 解析及内容类型识别，保持旧路径不变。
- 默认关闭新写入，能力探测只声明已完成能力。
- 测试 account 隔离、组成员变更、项目初始化失败重试。

### PR 2：文件与检索隔离

- 项目所有读写入口、向量 owner/schema、默认 target、context assembler。
- 支持项目资源导入和检索。
- 验证 ACL 开/关均隔离，用户删除不删除项目向量。
- 在这一阶段通过安全验收后，才允许启用项目数据写入。

### PR 3：Session 与异步生命周期

- 项目/peer Session Meta、列表、详情、作者写入约束、队列与自动提交。
- 覆盖任务状态授权、重启恢复、撤权、归档、多目标同 ID。
- 旧 Session 与旧队列兼容测试通过。

### PR 4：项目抽取与来源

- 项目 registry、四类模板、固定目标、合并批次与来源校验。
- 自动产生的记忆能被另一个成员检索，冲突候选不默认召回。
- 项目模式不写个人记忆/skills；peer v2 不产生嵌套 peers。

### PR 5：Codex 接入与配置

- v2 配置、workspace 探测、Hook/MCP/写入同目标、本地队列与缓存迁移。
- 向导/doctor 明确显示目标和来源；不支持协议时停止同步。
- 两个仓库对应同项目、同一 Agent 对应两个项目分别验证。

### PR 6：Studio 与文档

- 项目入口、成员维护、现有资源/会话/记忆页面复用。
- 中英文 API 与用户升级说明；其他 Agent 的适配矩阵。
- API 变更在 docs 下执行 `npm run check:api`。

这些 PR 是依赖顺序，不是可分别发布的完整功能。项目模式对外启用前至少完成前五阶段的端到端验证；Studio 可后续交付。

## 13. 测试矩阵

| 测试 | 预期 |
| --- | --- |
| Alice/Bob 在 A，Charlie 不在 | Alice 写入后 Bob 可读/召回，Charlie 列表、文件、搜索、下载均不可见 |
| Alice 同时在 A/B，实体同名 | 批处理、文件、索引、缓存、默认召回互不混用 |
| 不同 account 存在同名 project | 无法跨 account 读写 |
| project 与 peer 头同时出现 | 400，无落盘 |
| 项目无权限/不存在 | 不回退 user，不回放到其他空间 |
| peer v2 Session commit | 会话和记忆位于同一 peer；无嵌套 peers |
| 旧 v1、旧 API 无新头 | 原 Session 路径和 peer 抽取行为不变 |
| Bob 追加 Alice Session | 拒绝；Bob 可创建带 parent_session_uri 的新会话 |
| 绕过 Session API 直接写 messages.jsonl | 拒绝 |
| commit 入队后服务重启 | 恢复目标、幂等完成，不写入触发者个人目录 |
| 接受 commit 后移除/删除 Alice | 项目任务按既定策略完成，资产保留；Alice 不再读结果 |
| 两个 worker 修改同一项目记忆 | 不丢更新，重复任务不产生重复记忆/候选 |
| 模型输出跨项目 URI 或假来源 | 服务端拒绝越界和无效来源 |
| 项目归档时任务在运行 | 停止新的更新并记录可查询状态 |
| 向量重建、用户删除、account 删除 | 项目 owner 不变；用户删除保留项目；account 删除全部清理 |
| 老 worker/老插件遇到新协议 | 升级闸门阻止错误处理，不能忽略目标后继续工作 |
| Studio 切空间时旧请求返回 | 不覆盖新空间数据与草稿 |
| 资源含其他项目链接 | 展示引用不授予目标权限，读取再次校验 |

复用并扩展现有 `tests/unit/test_namespace_uri_classification.py`、`tests/session/memory/test_memory_isolation_handler.py`、`tests/storage/test_session_commit_processor_identity.py`、`tests/unit/service/test_session_auto_commit.py`、`tests/session/test_session_commit_race.py` 等回归；新增项目 API/FS/向量 E2E。JS 配置测试放共享库并执行其同步一致性检查。

测试分两层：确定性的权限/路径/任务测试使用固定抽取结果；真实模型小样本验证项目分类、偏好排除、提议排除与跨端召回。不能用真实模型偶然通过代替权限回归，也不能用 mock 证明抽取质量。

## 14. 完成交付的定义

用两名真实普通用户、一名非成员和一个新成员运行以下流程：创建项目并加入成员；前后端仓库配置同一 project；服务端 Agent 同步编码 Session 并生成项目记忆；前端 Agent 召回并打开来源；移除服务端用户后资产保留且其访问失败；新成员加入后继续复用；重启服务后后台任务和新会话仍归属正确。

个人 peer 路径另做相同的存储/召回一致性验证。最终报告分别说明源码测试、真实服务端验证、实际 Agent 插件验证和 Studio 验证，不能将某一层通过替代整条链路完成。

## 15. 首版实现状态

实现分支：`feat/project-workspace`。接入与接口细节见 [项目工作区 API](../zh/api/26-project-workspaces.md)。

已实现项目管理和成员组绑定、项目/peer 目标解析、文件访问控制、Session 归属和异步恢复、项目抽取模板与来源、向量所有权及检索范围、Codex Hook/MCP、配置命令和 Python SDK。`server.workspace_capture_enabled` 默认关闭；所有服务与消费者升级到本分支后再开启。未设置工作区头的有效旧配置继续使用个人模式，损坏的仓库配置会阻止同步，避免静默选择个人目标。

首版复用现有任务存储的 owner 列：项目任务使用 `~project~{project_id}`，peer 任务使用 `~peer~{user_id}~{peer_id}`，账号维度保持独立。`~` 不允许出现在真实用户 ID 中。认证身份、会话贡献者和用量审计仍使用真实 user。用户删除清理自己的 peer 任务，但不清理项目任务；项目任务取消暂限管理员。

资源队列从服务端生成的规范目标 URI 恢复所属空间；Session 队列额外持久化协议版本和完整 target，并校验 Session/归档路径一致性。Session 初始化与追加/提交共用目录级互斥锁，子文件沿用现有独立锁，避免同时初始化时覆盖作者。

Studio 工作台已支持 project 上下文树、项目资源/会话文件/记忆浏览、按 URI 绑定项目请求、项目资源导入，以及管理员创建/修改/归档/恢复项目和成员管理。成员管理复用已有用户组，修改会影响共用该组的其他项目；新建项目需要提供账号内已有成员组 ID。独立会话页面和 Agent 对话面板暂未提供项目切换。

暂不包含其他 Agent 自动同步适配、候选审批界面、工作区持续资源 watch、历史自动迁移和项目物理删除。项目候选可从归档读取并由管理员手工维护。非 Codex Hook 遇到 v2 配置会明确停止同步。

本地验证覆盖：原生 AGFS 中多人读取/作者写入、真实归档和任务持久化、移除贡献者后受理任务继续写入项目记忆、可信来源保存；API 能力和成员校验；SDK 与 Codex 配置/目标绑定；旧个人模式、记忆合并、自动提交、检索和任务回归。已在独立部署实例通过 HTTP 接口完成真实模型文档解析、索引、项目记忆抽取和跨成员召回，验证贡献者删除完成后资产保留、新成员加入后复用历史知识。84 项接口检查全部通过。归档后创建会话、追加消息、提交和资源写入返回 409；拒绝的操作不改变原消息、不生成新会话、归档或资源。真正的越权操作仍返回 403，非成员项目访问仍返回 404。Studio 已在独立测试实例验证项目目录展开、真实共享记忆读取、项目创建和成员展示。实际多 Agent 插件端到端质量验收及完整 CI 尚未完成。
