/** Asset target validation. This module never reads connection credentials. */
const SEGMENT = /^[a-zA-Z0-9_.@-]+$/;
export function validateWorkspaceId(value, name) {
  if (typeof value !== "string" || !value || value.length > 128 || !SEGMENT.test(value)
      || value === "." || value === ".." || value.split("@").length > 2) {
    throw new Error(`Invalid ${name}`);
  }
  return value;
}

export function workspaceTargetSettings(value) {
  if (!value || value.workspace_protocol !== 2) return {};
  try {
    if (value.workspace_error) throw new Error(value.workspace_error);
    const project = value.project_id;
    if (project !== undefined && project !== null) {
      validateWorkspaceId(project, "project_id");
      if (value.peer?.id !== undefined || value.peer?.source !== undefined) {
        throw new Error("project_id and peer configuration are mutually exclusive");
      }
    }
    return { workspaceProtocol: 2, projectId: project || "", workspaceError: "" };
  } catch (error) {
    return { workspaceProtocol: 2, workspaceError: error.message };
  }
}

export function resolvedWorkspaceTarget(cfg, peerId = "") {
  if (cfg.workspaceError) throw new Error(cfg.workspaceError);
  if (cfg.workspaceProtocol !== 2) return null;
  if (cfg.projectId) return Object.freeze({ kind: "project", id: validateWorkspaceId(cfg.projectId, "project_id") });
  if (cfg.peerSource === "none") return Object.freeze({ kind: "user" });
  if (peerId) return Object.freeze({ kind: "peer", id: validateWorkspaceId(peerId, "peer_id") });
  return Object.freeze({ kind: "user" });
}

export function workspaceTargetHeaders(target) {
  if (target?.kind === "project") return { "X-OpenViking-Project": target.id };
  if (target?.kind === "peer") return { "X-OpenViking-Workspace-Peer": target.id };
  return {};
}

export function assertSessionWorkspace(state, cfg, peerId, binding) {
  const target = resolvedWorkspaceTarget(cfg, peerId);
  if (!target && !state.workspaceBinding) return;
  if (state.workspaceBinding && state.workspaceBinding !== binding) {
    throw new Error("Workspace or identity changed; start a new Agent session");
  }
  if (!state.workspaceBinding && state.capturedTurnCount > 0) {
    throw new Error("An existing personal session cannot be moved into a workspace; start a new Agent session");
  }
  state.workspaceBinding = binding;
  state.workspaceTarget = target;
}
