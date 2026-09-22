import {
  maybeDetach as detach,
  readHookStdin,
} from "../shared/async-writer.mjs";
import { loadConfig } from "../config.mjs";
import { bindClaudeSession } from "./workspace-stage.mjs";
export { readHookStdin };
export async function maybeDetach(cfg, options) {
  if (process.env.OV_HOOK_WORKER === "1") return false;
  const raw = await readHookStdin();
  process.env.OPENVIKING_HOOK_STDIN_CACHE = raw;
  let input;
  try {
    input = JSON.parse(raw);
  } catch {
    return false;
  }
  const cwd = input.cwd || process.cwd();
  const effective = loadConfig(cwd);
  const binding = await bindClaudeSession(effective, cwd, input.session_id);
  process.env.OPENVIKING_CC_WORKER_BINDING = binding;
  return detach(effective, options);
}
