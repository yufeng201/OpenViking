# Project workspaces

Projects own resources, sessions and shared memory independently of individual contributors. Authenticate using each user's API key. An account administrator binds an existing group to a project; group membership is authoritative. Removing a contributor does not remove project assets.

Enable experimental `server.workspace_capture_enabled` only after upgrading every HTTP/MCP server, queue consumer and client. It defaults to false. Legacy personal requests remain unchanged. Drain workspace jobs before downgrading. This version supports HTTP administration, the Python SDK, Studio project management and Codex/Claude Code hooks/MCP; other Agent v2 session bindings are not yet included. Skills and recurring resource watches are unsupported in workspaces. The existing `ov` CLI does not automatically apply repository v2 targets; use workspace-bound MCP, the scoped Python SDK, or HTTP target headers for project operations.

## Ownership and authorization

Data lives under `viking://project/{project_id}/{resources,sessions,memories}`. Project metadata is stored in `/local/{account_id}/_system/projects`, and membership reuses the existing group store. Members can read shared sessions and resources, write resources, and append only their own sessions through the session API. Shared memory is written by extraction workers or administrators. Archived projects remain readable and reject writes. Accepted background work retains project ownership when a contributor leaves. Referenced groups cannot be deleted through the administration API.

Responses use the standard `{"status":"ok","result":...}` envelope. Management operations require an account administrator. Hidden or missing projects return 404; unauthorized management returns 403.

### POST /api/v1/projects

Create project.

### GET /api/v1/projects

List visible projects.

### GET /api/v1/projects/{project_id}

Get project.

### PATCH /api/v1/projects/{project_id}

Update/archive project.

### GET /api/v1/projects/{project_id}/members

List members.

### PUT /api/v1/projects/{project_id}/members/{user_id}

Add member.

### DELETE /api/v1/projects/{project_id}/members/{user_id}

Remove member.

### GET /api/v1/workspace

Resolve workspace and capabilities.

Create requires `project_id`, an existing `group_id`, and `name`. Optional fields are `description` and `repositories` (objects containing `id`, `name`, `description`). IDs and group binding are immutable. PATCH accepts name, description, repositories and status (`active`/`archived`). GET projects returns visible initialized records; GET members returns user IDs. Membership PUT/DELETE operates on existing account users through the bound group, affecting every project that shares the group. Project deletion is not offered. The workspace endpoint returns authenticated account/user, resolved target and capability flags.

## Agent connection

Send `X-OpenViking-Project: orders`, or `X-OpenViking-Workspace-Peer: my-repo` for `viking://user/{user_id}/peers/my-repo`. The headers are mutually exclusive. Do not combine a project with actor-peer. Without either header, existing personal behavior remains. Session/resource/retrieval APIs reuse the target. Default resource ingestion uses the workspace resources directory. Default project recall includes project memory and resources; read sessions explicitly. Explicit public resource queries remain supported. `viking://~` remains personal.

Run the existing Codex setup for credentials, then:

```bash
node /path/to/codex-memory-plugin/scripts/setup.mjs --project orders --workspace /path/to/repo
```

This probes capabilities/permissions before writing `{"version":2,"project_id":"orders"}` into the existing `.openviking/config.json`. Use `--peer my-repo` for a personal workspace, or `--local` for `config.local.json`. Ignore local settings in Git. Remove conflicting peer entries from the merged repository/local configuration before selecting a project. Credentials remain outside repository settings.

Set `OPENVIKING_WORKSPACE_ROOT=/path/to/repo` in that repository's MCP environment. Hooks resolve the event's directory; MCP must receive an explicit root. Start a new Agent session and restart MCP after changing target or connection identity. Unsupported servers stop capture instead of falling back to personal storage. Old captured sessions are not migrated.

The Python SDK adds immutable `project_id` and `workspace_peer_id` constructor options to AsyncHTTPClient (and the sync wrapper). Use one client per workspace, call initialize to validate capabilities, and retain the user's own API key. Install the matching SDK from this branch.

## Extraction

Project memory has four schemas: architecture, conventions, decisions and experiences. It excludes personal profiles/preferences and skill evolution. Only confirmed proposals become searchable memory; uncertain/conflicting proposals and automatic deletes go into the source archive's `memory-candidates.jsonl`. Candidate approval has no UI yet. Server-owned provenance records source archives, contributor IDs, message IDs and timestamps; merging retains multiple sources. Model confirmation is not a guarantee of factual correctness—review source evidence for critical conventions.

See the [Chinese reference](../../zh/api/26-project-workspaces.md) for full configuration examples.

## Claude Code

Plugin 0.6.0+ supports repository `.openviking/config.json` with `{"version":2,"project_id":"your-project-id"}`. Authenticate with a member's own API key in a private `ovcli.conf`; `OPENVIKING_CLI_CONFIG_FILE` can select a separate connection file. Start a new Claude conversation from the repository. If MCP starts elsewhere, set `OPENVIKING_WORKSPACE_ROOT` to that same repository.

Recall, main/subagent capture, compaction and final commits share the project target. Project mode does not inject personal profiles. Conversations are pinned to identity and target, and offline queues are isolated by that binding. Changing either requires a new conversation; denied access never falls back to personal storage. Without v2 configuration the existing personal mode remains available.
