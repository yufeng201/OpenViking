# 项目工作区

项目将资源、会话、记忆保存在账号拥有的 `viking://project/{project_id}` 下。用户使用自己的 API key；项目 ID 只选择资产空间，不替代认证。管理员把已有用户组绑定到项目，组成员共享项目内容。移除成员或删除用户不删除项目资产。

## 启用与升级

此功能为实验性增量能力，默认关闭。在 `ov.conf` 的 `server` 中设置 `workspace_capture_enabled: true`。先升级所有 HTTP/MCP 服务、队列消费者、自动提交进程和客户端，再打开开关。混用旧消费者可能丢失工作区语义，不支持滚动降级；关闭前应先停止新写入、处理完工作区队列。现有个人会话和 v1 仓库配置保持原行为，不自动迁移。

当前提供 HTTP 管理、Python SDK 和 Codex Hook/MCP 接入。直接运行旧 `ov` CLI 不会自动应用仓库 v2 目标；项目 Agent 的工具读写请通过已绑定工作区的 MCP，或显式设置目标的 Python SDK/HTTP 请求完成。Studio 项目管理页面和其他 Agent 的会话绑定适配尚未提供。项目不支持 skills 或持续资源 watch；通过普通资源导入上传文档。

## 数据布局

```text
viking://project/orders/
  resources/                 # 产品文档、接口文档、代码资源
  sessions/{session_id}/     # 前后端成员的独立会话、消息、归档
  memories/
    overview.md              # 项目名称和背景，由项目管理接口维护
    architecture/            # 架构约束
    conventions/             # 团队约定
    decisions/               # 已确认决策
    experiences/             # 可复用开发经验
```

物理数据位于 `/local/{account_id}/project/{project_id}`，项目注册信息位于 `/local/{account_id}/_system/projects/{project_id}.json`。成员关系复用 `_system/groups.json`，不存在第二份成员名单。一个组可关联多个项目，修改成员会影响所有关联项目；被项目引用的组不能通过管理接口删除。

成员可读取其他成员会话，但只能追加自己的会话；会话写权限不通过普通文件写入接口开放。项目记忆由抽取任务或管理员写入，成员可写项目资源。归档项目保留可读性并拒绝写入。已受理的项目后台任务不依赖贡献者继续留在项目，但仍受项目归档状态限制。项目任务使用独立的持久化 owner bucket，贡献者身份仍用于审计。

## 接口

沿用标准 `{ "status": "ok", "result": ... }` 返回结构与 API-key 身份认证。以下管理接口均作用于认证账号。项目不存在和非成员访问项目详情均返回 404；非管理员进行管理操作返回 403。

### POST /api/v1/projects

管理员创建项目。先使用账号管理接口创建组并添加用户，再创建项目：

```json
{
  "project_id": "orders",
  "group_id": "orders-team",
  "name": "订单系统",
  "description": "订单创建、支付及履约",
  "repositories": [{"id": "orders-api", "name": "服务端", "description": "订单 API"}]
}
```

`project_id` 为账号内唯一且不可修改的路径标识；`group_id` 必须存在且不可更换；`name` 必填，`description` 和 `repositories` 可选。成功返回项目记录，包括 `status`、`initialized`、创建/更新时间和创建人。初始化失败的记录不向成员开放，同一创建人、同一组可重试。已初始化的重复项目返回冲突。

### GET /api/v1/projects

返回调用者可见的项目数组。管理员可见账号内所有已初始化项目。

### GET /api/v1/projects/{project_id}

返回指定项目记录。

### PATCH /api/v1/projects/{project_id}

管理员修改 `name`、`description`、`repositories` 或 `status`（`active` / `archived`）。不接受修改项目 ID、组 ID、创建人。当前不提供项目删除接口。

### GET /api/v1/projects/{project_id}/members

管理员查询绑定组的成员 ID 数组。

### PUT /api/v1/projects/{project_id}/members/{user_id}

管理员将账号内已有用户加入项目绑定组。复用组管理语义。

### DELETE /api/v1/projects/{project_id}/members/{user_id}

管理员将用户从绑定组移除；保留其已提交资产。

### GET /api/v1/workspace

返回当前认证身份、解析后的 `target` 和 `capabilities`。打开开关后返回协议版本 2，支持 `user`、`peer`、`project`。关闭时只声明旧个人模式。客户端必须探测能力；指定项目后失败必须停止，不能降级写入个人目录。

## 请求目标

- 企业项目：`X-OpenViking-Project: orders`。
- 个人仓库：`X-OpenViking-Workspace-Peer: my-repo`，写入 `viking://user/{authenticated_user}/peers/my-repo`。
- 未设置上述请求头：保留旧个人行为。

两个工作区请求头互斥。项目目标与 `X-OpenViking-Actor-Peer` 互斥；peer 目标也不需要 actor-peer。`viking://~` 继续表示个人空间；项目请求中不要使用它作为项目目录替代。成员关系由服务器校验，客户端不能通过 user/account 请求头伪造 API key 身份。

已有会话创建、追加、读取、提交和资源导入接口复用上述目标头。省略资源目标时，使用当前工作区的 `resources`。项目召回默认查询项目记忆和资源，会话可显式读取；公共资源仍可作为显式查询目标。前端和服务端共享同一个 project ID，但应创建各自的 session ID。

## Codex 接入

先沿用现有 setup 配置个人 API key，再在业务仓库配置目标：

```bash
node /path/to/codex-memory-plugin/scripts/setup.mjs --project orders --workspace /path/to/orders-web
```

命令先检查权限和服务端能力，再更新已有 `.openviking/config.json` 格式（version 2），不会在仓库保存 API key：

```json
{"version": 2, "project_id": "orders"}
```

个人仓库使用 `--peer my-repo`；仅本机覆盖使用 `--local`，写入 `.openviking/config.local.json`。个人配置示例：

```json
{"version": 2, "project_id": null, "peer": {"id": "my-repo"}}
```

团队文件与本机覆盖合并后也不能同时存在 project 和 peer。切换前检查旧 peer 设置并移除冲突项。请将 `config.local.json` 加入仓库忽略规则。机器注册表和既有配置优先级仍然有效。

MCP 进程需在该仓库的 Agent MCP 配置环境中明确设置 `OPENVIKING_WORKSPACE_ROOT=/path/to/orders-web`，不要依赖进程启动目录推断项目。Hook 使用事件中的仓库目录。更改目标、账号、地址或 API key 后开启新 Agent 会话并重启 MCP；旧会话不会自动迁移。离线重试保留原会话绑定，切换目标后停止发送旧记录。

## Python 客户端接入

使用本分支同步版本的 `sdk/python`：

**Python SDK**

```python
from openviking_sdk import AsyncHTTPClient

client = AsyncHTTPClient(url="http://localhost:1933", api_key=user_key, project_id="orders")
await client.initialize()  # 检查工作区协议和权限
# 后续 session/resource/retrieval 请求复用固定项目目标
await client.close()
```

个人 peer 使用 `workspace_peer_id="my-repo"`，与 `project_id` 互斥。目标固定在 client 实例上，不使用全局可变项目状态；不同项目创建不同 client。

## 记忆抽取

项目采用独立的 architecture、conventions、decisions、experiences 模板，不复用用户画像、个人偏好或 Agent 技能进化。只有 `evidence_status=confirmed` 的抽取建议进入共享记忆。未确认、冲突建议和自动删除建议保存在来源归档的 `memory-candidates.jsonl`，不进入默认召回；管理员可检查后手工维护记忆，当前没有候选审批 UI。

记忆元数据保留服务器生成的项目归属、来源归档、贡献者、来源消息 ID 和抽取时间；合并时保留多个来源。项目 URI、批处理键、队列上下文和向量过滤都包含目标空间，删除贡献者不会按作者清理项目记忆。自动抽取仍有模型判断误差，应通过来源复核关键团队约定。
