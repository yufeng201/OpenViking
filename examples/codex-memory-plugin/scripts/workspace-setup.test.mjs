import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { configureWorkspace } from "./workspace-setup.mjs";
import { loadConfig } from "./config.mjs";

async function fixture(t, shared, local) {
  const root = await mkdtemp(join(tmpdir(), "ov-setup-review-"));
  await mkdir(join(root, ".openviking"));
  for (const [name, value] of [["config.json", shared], ["config.local.json", local]]) {
    if (value) await writeFile(join(root, ".openviking", name), JSON.stringify(value));
  }
  const oldFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, headers: options.headers });
    return { ok: true, status: 200, json: async () => ({ status: "ok", result: { capabilities: { protocol_version: 2, target_kinds: ["user", "peer", "project"] } } }) };
  };
  t.after(async () => { globalThis.fetch = oldFetch; await rm(root, { recursive: true, force: true }); });
  return { root, calls };
}

test("local project refuses inherited peer conflict without changing files or probing", async (t) => {
  const { root, calls } = await fixture(t, { version: 2, peer: { id: "personal" } });
  await assert.rejects(configureWorkspace(["--workspace", root, "--local", "--project", "team"]), /conflict/);
  await assert.rejects(readFile(join(root, ".openviking/config.local.json")), { code: "ENOENT" });
  assert.equal(calls.length, 0);
});

test("shared target refuses a different local target before probing or writing", async (t) => {
  const shared = { version: 2, project_id: "old" };
  const { root, calls } = await fixture(t, shared, { version: 2, project_id: "local" });
  await assert.rejects(configureWorkspace(["--workspace", root, "--project", "team"]), /overridden/);
  assert.deepEqual(JSON.parse(await readFile(join(root, ".openviking/config.json"))), shared);
  assert.equal(calls.length, 0);
});

test("same-layer personal to project switch probes and loads the chosen project", async (t) => {
  const { root, calls } = await fixture(t, { version: 2, peer: { id: "personal" }, capture: { enabled: false } });
  await configureWorkspace(["--workspace", root, "--project", "team"]);
  const cfg = loadConfig(root);
  assert.equal(cfg.workspaceError, "");
  assert.equal(cfg.projectId, "team");
  assert.equal(calls[0].headers["X-OpenViking-Project"], "team");
  const saved = JSON.parse(await readFile(join(root, ".openviking/config.json")));
  assert.equal(saved.peer, undefined);
  assert.equal(saved.capture.enabled, false);
});

test("local personal override clears project and disabled peer source", async (t) => {
  const { root, calls } = await fixture(t, { version: 2, project_id: "team" }, { version: 2, peer: { source: "none" } });
  await configureWorkspace(["--workspace", root, "--local", "--peer", "personal"]);
  const cfg = loadConfig(root);
  assert.equal(cfg.workspaceError, "");
  assert.equal(cfg.projectId, "");
  assert.equal(cfg.peerId, "personal");
  assert.equal(calls[0].headers["X-OpenViking-Workspace-Peer"], "personal");
});
