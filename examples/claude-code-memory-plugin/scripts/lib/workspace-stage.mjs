/** Pin each Claude conversation to its original identity and asset workspace. */
import { AsyncLocalStorage } from "node:async_hooks";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir, tmpdir } from "node:os";
import {
  runHookStage as runStage,
  withAgentHookLock,
  readHookState,
  writeHookState,
} from "../shared/agent-hook-runtime.mjs";
import { resolvedWorkspaceTarget } from "../shared/workspace-target.mjs";
import { resolveEffectivePeerId } from "../shared/workspace-peer.mjs";
export const workspaceContext = new AsyncLocalStorage();
export function claudeBinding(cfg, cwd) {
  const peer = resolveEffectivePeerId({ cfg, cwd }).peerId;
  const target = resolvedWorkspaceTarget(cfg, peer);
  return createHash("sha256")
    .update(
      JSON.stringify([
        cfg.baseUrl,
        cfg.account,
        cfg.user,
        cfg.apiKey,
        ...(cfg.repositoryId ? [cfg.repositoryId] : []),
        target || { kind: "legacy" },
      ]),
    )
    .digest("hex");
}
export async function bindClaudeSession(cfg, cwd, sessionId) {
  try {
    return await bindSession(cfg, cwd, sessionId);
  } catch (error) {
    process.stderr.write(`[OpenViking] Workspace binding failed: ${error.message}\n`);
    throw error;
  }
}

async function bindSession(cfg, cwd, sessionId) {
  const binding = claudeBinding(cfg, cwd);
  if (
    process.env.OPENVIKING_CC_WORKER_BINDING &&
    process.env.OPENVIKING_CC_WORKER_BINDING !== binding
  )
    throw new Error(
      "Workspace changed before background capture; start a new Claude session",
    );
  if (!sessionId) {
    if (cfg.workspaceProtocol === 2)
      throw new Error("Workspace hook requires a Claude session ID");
    return binding;
  }
  const result = await withAgentHookLock(
    "claude-workspace",
    sessionId,
    async () => {
      const state = await readHookState("claude-workspace", sessionId);
      if (state.binding && state.binding !== binding)
        throw new Error(
          "Workspace or identity changed; start a new Claude session",
        );
      if (!state.binding && cfg.workspaceProtocol === 2) {
        const safe = String(sessionId).replace(/[^a-zA-Z0-9_-]/g, "_");
        let old;
        try {
          old = JSON.parse(
            await readFile(
              join(tmpdir(), "openviking-cc-capture-state", `${safe}.json`),
              "utf8",
            ),
          );
        } catch (error) {
          if (error.code !== "ENOENT") throw error;
        }
        if (old?.capturedTurnCount > 0)
          throw new Error(
            "Existing personal conversation cannot be moved into a project; start a new Claude session",
          );
      }
      await writeHookState("claude-workspace", sessionId, { binding });
      return binding;
    },
  );
  if (!result) throw new Error("Could not lock Claude workspace binding");
  return result;
}
export function runHookStage(options, handler) {
  return runStage(options, async (stage) => {
    const binding = await bindClaudeSession(
      stage.cfg,
      stage.cwd,
      stage.sessionId,
    );
    const previous = process.env.OPENVIKING_PENDING_DIR;
    if (stage.cfg.workspaceProtocol === 2)
      process.env.OPENVIKING_PENDING_DIR = join(
        previous || join(homedir(), ".openviking", "pending"),
        "claude-workspaces",
        binding,
      );
    try {
      return await workspaceContext.run(
        { cfg: stage.cfg, cwd: stage.cwd, binding },
        () => handler(stage),
      );
    } finally {
      if (previous === undefined) delete process.env.OPENVIKING_PENDING_DIR;
      else process.env.OPENVIKING_PENDING_DIR = previous;
    }
  });
}
