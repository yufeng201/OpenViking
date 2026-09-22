import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { resolve, join } from "node:path";
import { randomUUID } from "node:crypto";
import { loadConfig } from "./config.mjs";
import { createOvHttp } from "./shared/ov-http.mjs";
import { validateWorkspaceId } from "./shared/workspace-target.mjs";

/** Extend the existing repository settings; never write credentials here. */
export async function configureWorkspace(args) {
  const value = (name) => {
    const index = args.indexOf(name);
    if (index < 0) return undefined;
    if (!args[index + 1] || args[index + 1].startsWith("--")) throw new Error(`${name} requires a value`);
    return args[index + 1];
  };
  const project = value("--project");
  const peer = value("--peer");
  if (Boolean(project) === Boolean(peer)) throw new Error("Specify exactly one of --project or --peer");
  validateWorkspaceId(project || peer, project ? "project_id" : "peer_id");
  const root = resolve(value("--workspace") || process.cwd());
  const directory = join(root, ".openviking");
  const path = join(directory, args.includes("--local") ? "config.local.json" : "config.json");
  let previous = {};
  try { previous = JSON.parse(await readFile(path, "utf8")); } catch (error) { if (error.code !== "ENOENT") throw error; }
  const next = { ...previous, version: 2, project_id: project || null };
  if (project) delete next.peer;
  else next.peer = { id: peer, source: "git" };
  const cfg = loadConfig(root, { workspaceOverride: { root, path, data: next } });
  if (cfg.workspaceError || cfg.projectId !== (project || "")
      || (!project && (cfg.peerId !== peer || cfg.peerSource === "none"))) {
    throw new Error(`Workspace configuration is overridden or conflicting: ${cfg.workspaceError || "effective target differs"}. Update the conflicting config.local.json, peer settings, or environment before retrying.`);
  }
  const fetchJSON = createOvHttp(cfg, { defaultTimeoutMs: 10000, resolveActorPeerId: () => peer || "" });
  const probe = await fetchJSON("/api/v1/workspace");
  const caps = probe.result?.capabilities;
  if (!probe.ok || caps?.protocol_version !== 2 || !caps?.target_kinds?.includes(project ? "project" : "peer")) {
    throw new Error(`Workspace unavailable: ${probe.error?.message || "upgrade/enable workspace capture on the server"}`);
  }
  await mkdir(directory, { recursive: true });
  const temporary = `${path}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(next, null, 2)}\n`, { mode: 0o600 });
  await rename(temporary, path);
  process.stdout.write(`Configured ${path}\nStart a new Agent session. Set OPENVIKING_WORKSPACE_ROOT=${root} in this repository's MCP server environment.\n`);
}
