import assert from "node:assert/strict";
import test from "node:test";
import { spawn, execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  withMockOpenViking,
  readRequestBody,
  writeJson,
} from "../../memory-plugin-shared/testing/support.mjs";
const scripts = fileURLToPath(new URL(".", import.meta.url));
async function run(
  hook,
  root,
  url,
  session = "workspace-session",
  extra = {},
  payload = {},
) {
  const env = { ...process.env };
  for (const k of Object.keys(env))
    if (k.startsWith("OPENVIKING_") || k === "OV_HOOK_WORKER") delete env[k];
  Object.assign(env, {
    HOME: join(root, "home"),
    TMPDIR: root,
    OPENVIKING_MEMORY_ENABLED: "1",
    OPENVIKING_URL: url,
    OPENVIKING_API_KEY: "alice-key",
    OPENVIKING_AUTO_CAPTURE: "1",
    OPENVIKING_CAPTURE_ASSISTANT_TURNS: "1",
    OPENVIKING_WRITE_PATH_ASYNC: "0",
    OPENVIKING_RECALL_COMPRESS: "off",
    OPENVIKING_HOOK_STATE_DIR: join(root, "bindings"),
    ...extra,
  });
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [join(scripts, hook + ".mjs")], {
      cwd: tmpdir(),
      env,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let out = "",
      err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", reject);
    child.on("close", (code) =>
      code ? reject(new Error(err)) : resolve({ out, err }),
    );
    child.stdin.end(
      JSON.stringify({
        session_id: session,
        cwd: root,
        transcript_path: join(root, "transcript.jsonl"),
        prompt: "What is the order API contract?",
        source: "startup",
        ...payload,
      }),
    );
  });
}
async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), "ov-claude-workspace-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  execFileSync("git", ["init", "-q", root]);
  await mkdir(join(root, "home"));
  await mkdir(join(root, ".openviking"));
  await writeFile(
    join(root, ".openviking/config.json"),
    JSON.stringify({ version: 2, project_id: "orders" }),
  );
  await writeFile(
    join(root, "transcript.jsonl"),
    [
      JSON.stringify({
        role: "user",
        content: "Remember POST /api/orders uses sku_id and quantity.",
      }),
      JSON.stringify({
        role: "assistant",
        content: "Confirmed project order contract.",
      }),
    ].join("\n"),
  );
  return root;
}
async function server(fn, denied = false, legacySearch = false) {
  const requests = [];
  return withMockOpenViking(
    async (req, res) => {
      const body = ["POST", "PUT"].includes(req.method)
        ? await readRequestBody(req)
        : null;
      requests.push({
        url: req.url,
        project: req.headers["x-openviking-project"],
        body,
      });
      if (
        legacySearch &&
        (body?.mode === "context" || req.url === "/api/v1/search/recall")
      ) {
        writeJson(res, { status: "error" }, 404);
        return;
      }
      if (req.url === "/api/v1/workspace") {
        writeJson(
          res,
          {
            status: denied ? "error" : "ok",
            result: {
              capabilities: {
                protocol_version: 2,
                target_kinds: ["project", "peer", "user"],
              },
            },
          },
          denied ? 404 : 200,
        );
        return;
      }
      if (req.url === "/health") {
        writeJson(res, { status: "ok", result: { healthy: true } });
        return;
      }
      writeJson(res, {
        status: "ok",
        result: req.url.includes("/messages")
          ? { added: body.messages?.length || 1 }
          : req.url.includes("/search/")
            ? { memories: [], resources: [], skills: [] }
            : { message_count: 2, pending_tokens: 1, commit_count: 0 },
      });
    },
    (url) => fn(url, requests),
  );
}
test("capture and final commit use payload cwd project, including module-level HTTP helpers", async (t) => {
  const root = await fixture(t);
  await server(async (url, requests) => {
    await run("auto-capture", root, url);
    await run("session-end", root, url);
    const writes = requests.filter(
      (r) => r.url.includes("/messages") || r.url.endsWith("/commit"),
    );
    assert.ok(writes.some((r) => r.url.includes("/messages")));
    assert.ok(writes.some((r) => r.url.endsWith("/commit")));
    assert.ok(writes.every((r) => r.project === "orders"));
  });
});
test("recall searches project memories and resources without personal targets", async (t) => {
  const root = await fixture(t);
  await server(
    async (url, requests) => {
      await run("auto-recall", root, url);
      const queries = requests.filter(
        (r) => r.url.includes("/search/") && r.body.target_uri,
      );
      assert.ok(queries.length);
      assert.ok(
        queries.every(
          (r) =>
            r.project === "orders" &&
            r.body.target_uri.startsWith("viking://project/orders/"),
        ),
      );
      assert.ok(queries.some((r) => r.body.target_uri.endsWith("/resources")));
    },
    false,
    true,
  );
});
test("changing project or credential cannot reroute an existing Claude session", async (t) => {
  const root = await fixture(t);
  await server(async (url, requests) => {
    await run("auto-capture", root, url);
    requests.length = 0;
    await writeFile(
      join(root, ".openviking/config.json"),
      JSON.stringify({ version: 2, project_id: "other" }),
    );
    await run("session-end", root, url);
    assert.equal(requests.length, 0);
    await writeFile(
      join(root, ".openviking/config.json"),
      JSON.stringify({ version: 2, project_id: "orders" }),
    );
    await run("auto-capture", root, url, "workspace-session", {
      OPENVIKING_API_KEY: "bob-key",
    });
    assert.equal(requests.length, 0);
  });
});
test("unauthorized workspace fails closed without personal capture", async (t) => {
  const root = await fixture(t);
  await server(async (url, requests) => {
    await run("auto-capture", root, url);
    assert.ok(requests.some((r) => r.url === "/api/v1/workspace"));
    assert.ok(
      requests.every(
        (r) => r.url === "/health" || r.url === "/api/v1/workspace",
      ),
    );
  }, true);
});
test("offline commits queue under identity and workspace binding", async (t) => {
  const root = await fixture(t);
  await run("session-end", root, "http://127.0.0.1:1", "one");
  await writeFile(
    join(root, ".openviking/config.json"),
    JSON.stringify({ version: 2, project_id: "other" }),
  );
  await run("session-end", root, "http://127.0.0.1:1", "two");
  const dirs = await readdir(
    join(root, "home/.openviking/pending/claude-workspaces"),
  );
  assert.equal(dirs.length, 2);
  for (const d of dirs)
    assert.ok(
      (
        await readdir(
          join(root, "home/.openviking/pending/claude-workspaces", d),
        )
      ).length,
    );
});

test("context recall carries project scope", async (t) => {
  const root = await fixture(t);
  await server(async (url, requests) => {
    await run("auto-recall", root, url);
    const query = requests.find((r) => r.body?.mode === "context");
    assert.equal(query?.project, "orders");
  });
});

test("subagent capture and compaction keep the parent project", async (t) => {
  const root = await fixture(t);
  await server(async (url, requests) => {
    const payload = {
      agent_id: "worker",
      agent_transcript_path: join(root, "transcript.jsonl"),
    };
    await run("subagent-start", root, url, "parent", {}, payload);
    await run("subagent-stop", root, url, "parent", {}, payload);
    await run("pre-compact", root, url, "parent");
    const writes = requests.filter(
      (r) => r.url.includes("/messages") || r.url.endsWith("/commit"),
    );
    assert.ok(writes.some((r) => r.url.includes("__subagent-worker")));
    assert.ok(writes.every((r) => r.project === "orders"));
  });
});
test("background worker rejects changed binding", async (t) => {
  const root = await fixture(t);
  await server(async (url, requests) => {
    await run("auto-capture", root, url, "worker", {
      OV_HOOK_WORKER: "1",
      OPENVIKING_CC_WORKER_BINDING: "different",
    });
    assert.equal(requests.length, 0);
  });
});
test("MCP resolves the same explicit workspace root as hooks", async (t) => {
  const root = await fixture(t);
  const { readProxyConfig } = await import("../servers/mcp-proxy.mjs");
  const cfg = readProxyConfig({
    HOME: join(root, "home"),
    OPENVIKING_WORKSPACE_ROOT: root,
    OPENVIKING_URL: "http://localhost:8021",
    OPENVIKING_API_KEY: "test",
    OPENVIKING_CREDENTIAL_SOURCE: "env",
  });
  assert.equal(cfg.projectId, "orders");
  assert.equal(cfg.workspaceProtocol, 2);
});

test("repository binding precedes capture and carries a readable title", async (t) => {
  const root = await fixture(t);
  await writeFile(
    join(root, ".openviking/config.json"),
    JSON.stringify({ version: 2, project_id: "orders", repository_id: "api" }),
  );
  await server(async (url, requests) => {
    await run("auto-capture", root, url);
    const bind = requests.findIndex((r) => r.url.endsWith("/repository"));
    const write = requests.findIndex((r) => r.url.includes("/messages"));
    assert.ok(bind >= 0 && bind < write);
    assert.equal(requests[bind].project, "orders");
    assert.ok(requests[bind].body.title.includes("POST /api/orders"));
    assert.equal(requests[bind].body.repository_id, "api");
  });
});
