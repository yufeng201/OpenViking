import { createHash } from "node:crypto";
import { resolvedWorkspaceTarget } from "./workspace-target.mjs";

export function workspaceBinding(cfg, peerId = "") {
  const target = resolvedWorkspaceTarget(cfg, peerId);
  if (!target) return "";
  // A one-way credential fingerprint detects identity changes before a probe;
  // keys themselves are never persisted alongside captured transcripts.
  return createHash("sha256").update(JSON.stringify([
    cfg.baseUrl || cfg.endpoint, cfg.account, cfg.user, cfg.apiKey, target,
  ])).digest("hex");
}
