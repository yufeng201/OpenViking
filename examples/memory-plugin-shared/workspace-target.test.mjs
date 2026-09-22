import test from "node:test";
import assert from "node:assert/strict";
import { assertSessionWorkspace, resolvedWorkspaceTarget, workspaceTargetSettings } from "./lib/workspace-target.mjs";
import { workspaceBinding } from "./lib/workspace-binding.mjs";
import { buildOvHeaders, createOvHttp } from "./lib/ov-http.mjs";

test("project selection ignores global peer and never sends an actor peer", () => {
  const cfg = { workspaceProtocol: 2, projectId: "orders", apiKey: "test-key" };
  assert.deepEqual(resolvedWorkspaceTarget(cfg, "global-personal-peer"), { kind: "project", id: "orders" });
  const headers = buildOvHeaders(cfg, { actorPeerId: "global-personal-peer" });
  assert.equal(headers["X-OpenViking-Project"], "orders");
  assert.equal(headers["X-OpenViking-Actor-Peer"], undefined);
  assert.equal(headers.Authorization, "Bearer test-key");
});

test("explicit conflicting config and unsafe project ids fail closed", () => {
  for (const value of [
    { project_id: "orders", peer: { id: "repo" } },
    { project_id: "../orders" }, { project_id: "" },
  ]) {
    const cfg = workspaceTargetSettings({ ...value, workspace_protocol: 2 });
    assert.throws(() => resolvedWorkspaceTarget(cfg));
  }
});

test("legacy headers and explicit personal override stay distinct", () => {
  assert.equal(buildOvHeaders({}, { actorPeerId: "repo" })["X-OpenViking-Actor-Peer"], "repo");
  const cfg = workspaceTargetSettings({ workspace_protocol: 2, project_id: null, peer: { id: "repo" } });
  assert.equal(buildOvHeaders(cfg, { actorPeerId: "repo" })["X-OpenViking-Workspace-Peer"], "repo");
});

test("sessions are pinned to target and connection identity", () => {
  const cfg = { workspaceProtocol: 2, projectId: "orders", baseUrl: "http://localhost:1933", apiKey: "key" };
  const state = { capturedTurnCount: 0 };
  assertSessionWorkspace(state, cfg, "", workspaceBinding(cfg));
  assertSessionWorkspace(state, cfg, "", workspaceBinding(cfg));
  for (const changed of [{ ...cfg, projectId: "payments" }, { ...cfg, apiKey: "different-key" }]) {
    assert.throws(() => assertSessionWorkspace(state, changed, "", workspaceBinding(changed)), /new Agent session/);
  }
  assert.throws(() => assertSessionWorkspace({ capturedTurnCount: 3 }, cfg, "", workspaceBinding(cfg)));
});

test("unsupported server never receives the capture request", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    return { ok: false, json: async () => ({}) };
  };
  try {
    const client = createOvHttp({ workspaceProtocol: 2, projectId: "orders", baseUrl: "http://local" });
    const result = await client("/api/v1/sessions/s/messages", { method: "POST", body: "{}" });
    assert.equal(result.ok, false);
    assert.equal(result.status, 409);
    assert.deepEqual(calls, ["http://local/api/v1/workspace"]);
  } finally {
    globalThis.fetch = original;
  }
});
