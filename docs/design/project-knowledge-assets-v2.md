# 项目知识资产与工作项：增量设计

状态：设计提案，尚未实现。基于 2026-09-22 当前项目工作区代码核对。

## 目标与边界

项目拥有资源、会话和知识；成员身份用于权限和贡献审计。支持前后端多仓库协作、新人接手、进度查询与经验复用。首版不建设任务排期、工时、复杂审批或外部平台双向同步。

## 目录与职责

```text
project/{id}/
  resources/                    原始资料，按需按产品、工程、会议组织
  sessions/{session_id}/         原始对话、归档、抽取来源
  memories/
    overview.md                 项目名称与范围
    architecture/               架构、模块职责和依赖
    conventions/                已采用的接口、编码、测试、发布约定
    decisions/                  已采用决策、原因和替代关系
    experiences/                可复用的方法及适用限制
    work_items/{id}.md          工作事实的可读投影，新增
```

不增加 task、issue、bug 三套平级存储。工作项统一使用 work_item_id，kind 为 feature、task、bug；外部 Issue 通过 external_refs 表达，不与服务端异步 task_id 混用。工作项投影不能交给通用 Markdown patch 合并器自由修改状态。

项目进度通过工作项汇总得到，不在 overview.md 内另存一份独立进度。当前 ProjectService.update 会重写 overview.md，不能将它当作自由编辑的知识正文。

## 工作项的事实模型

一个工作项可关联多个仓库、Session、PR 和资源；一个 Session 可以讨论多个工作项。会话关联不意味着每条消息都属于所有关联项，抽取结果必须引用对应消息范围。

最小字段：id、kind、title、repository_ids、external_refs、acceptance_criteria、state、revision、updated_at。状态为 unknown、open、in_progress、blocked、done、cancelled。没有证据时保持 unknown，不根据对话结束推断完成。

追加事实字段：event_id、work_item_id、kind、payload、source_refs、actor_id、occurred_at、recorded_at、evidence_kind。区分 proposed、declared、observed、verified：模型提出的是建议，成员声明不等于外部系统验证，工具输出也不自动等于可信 CI 结果。

测试通过、PR 合并、部署、验收分别记录事实，并绑定仓库、commit、环境和证据。done 依据明确验收条件或有权限成员的显式确认；保留确认者和来源。不同 commit 的验证不得相互覆盖。

首版只允许显式创建或关联工作项；外部记录采用 provider + repository + external_id 唯一键。模型发现疑似新工作项只产出候选，避免按标题重复建项。没有 work_item_id 的会话仍可正常抽取长期知识。

事实记录与状态投影由小型专用 Store/Service 管理，复用现有 AGFS 系统元数据、路径锁和原子写能力。内部路径建议为 /local/{account}/_system/project_work_items/{project}/，不经普通文件 API 开放。成员通过专用接口提交，服务端检查项目成员和归档状态；不扩大普通成员直接写 memories 的权限。

修改使用 revision 并发检查；事件先持久化，状态与 Markdown 投影可重建。幂等键绑定项目、工作项、来源消息和事件类型。投影失败重试时不重复事件，进度查询以权威记录为准；索引同步独立重试。跨项目关联默认禁止。

## 分类抽取

| 类型 | 主要字段 | 准入条件 |
| --- | --- | --- |
| architecture | 模块、职责、依赖、数据流、仓库及版本 | 当前事实与未来方案分开 |
| conventions | 规则、适用范围、采用依据、例外 | 一次实现不自动成为团队规范 |
| decisions | 问题、选择、原因、备选项、影响 | 提案和已采用决策分开 |
| experiences | 场景、现象、根因、步骤、验证、限制 | 提炼复用方法，不复制任务流水账 |
| work_items | 目标、事实、阻塞、关联产物、验证 | 产生结构化事实候选，由服务校验和更新 |

一次缺陷处理可同时产出工作项事实和长期经验，两者链接来源而不复制完整正文。冲突比较前必须先比仓库、模块、版本和环境；不同范围的结论可以并存。范围不明时保留候选，不凭名称相似覆盖。

长期知识补充 repository_ids、module、applicability、work_item_ids、evidence_kind、last_verified_at、status、supersedes。现有项目来源机制已经保存 archive_uri、session_id、contributor_id、message_ids、extracted_at，应扩展复用。owner、贡献者和证据链接由服务端绑定，不相信模型提供的身份。

知识状态 active、superseded、deprecated 与证据状态是两个维度。旧知识保留历史来源，默认召回过滤失效项；历史追溯请求可明确包含。旧记录缺少新字段时标记未知，不批量升级为 verified。

## 进度与召回

默认编码召回以四类长期知识和资源为主。明确关联工作项时补充该项的最新状态与阻塞；查询进度时使用结构化工作项服务，不依靠向量检索凑齐完整项目清单。首版用明确工具参数选择查询路径，无需新增意图模型。

项目进度展示活跃工作、阻塞、已确认完成、待验证、最近更新时间和覆盖范围。不输出无依据的完成百分比；标记超过可配置时间未更新的记录。外部平台作为状态来源时，只读同步，失败显示最近同步时间和错误，禁止用会话猜测覆盖。

同名 OpenViking 可以指开源服务端，也可以指 vikingdb-fe/apps/openviking 控制台应用。召回和冲突判断必须携带 repository/module，不能把前端子应用解释为整个服务端项目不存在。

## 抽取可见性：优先于新增目录

2026-09-22 实测 openviking-collab 两个 session 均完成 session_commit，耗时约 49 秒和 52 秒。一项写入 1 条 architecture 记忆，另一项产生 2 条 conflict 候选，正式写入为 0。只有目录树时，用户无法区分尚未执行、处理中、无产出和冲突拦截。

每个归档应展示：排队、抽取中、已完成、失败；完成后展示新增、更新、候选及原因。0 条写入不能统一解释为没有可抽取信息。复用现有 task_id、任务阶段、memory_diff 和 memory-candidates，先增加只读展示；候选采用与驳回随后增加专用权限入口。

目录刷新由任务完成触发，另保留手动刷新。断线或历史 task 被清理时，从归档持久化结果恢复状态；未知不显示为已完成。重试复用归档和幂等标识，不重新捕获整个会话。

## 实施顺序

1. 抽取状态与候选展示：不改变知识准入规则，先让用户知道发生了什么。
2. 仓库/模块范围与来源证据：插件提供仓库上下文，后端校验，抽取、合并、索引、召回贯通；无范围记录保留未知。
3. 工作项最小闭环：显式创建/关联、事实追加、状态投影、详情及关联会话；不做排期。
4. 知识维护：修正、候选处理、失效/替代、来源追溯。跨项目发布另行授权，不自动共享。
5. 进度汇总：基于已有工作项事实，按需接入外部平台只读同步。

实现涉及 SessionMeta 序列化及创建/更新 API、项目模板与 workspace_registry、project_candidates/provenance、memory_updater、Context 分类、context assembler 配额与索引、Studio 详情和插件会话上下文。新增 work_items 不能只添加 YAML：通用长期记忆抽取与工作项事实抽取需要明确路由。

## 验收

- 前后端各自 Session 可关联同一工作项，项目资产归属不变。
- 不同仓库同名模块不误覆盖；真正冲突保留两个来源并展示候选。
- 本地测试通过不升级为合并或部署，旧 commit 的验证不覆盖新版本。
- 重复提交/事件重放不重复建项；并发修改不静默覆盖；索引失败可修复。
- 无工作项的个人和项目捕获保持兼容；旧记忆仍可查。
- 非成员、跨项目引用、已归档写入被拒绝；退出成员不影响已持久化资产。
- 抽取新增、更新、候选、零产出、失败在 Studio 中均有可辨识状态。
- 项目进度显示事实时间和覆盖范围；知识失效后默认召回不再采用。
