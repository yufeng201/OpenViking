#!/usr/bin/env node

/**
 * Standalone ovcli.conf setup for marketplace installs of the Codex plugin:
 *
 *   node scripts/setup.mjs
 */

import { runSetupWizard } from "./shared/setup-wizard.mjs";

import { configureWorkspace } from "./workspace-setup.mjs";

const args = process.argv.slice(2);
(args.includes("--project") || args.includes("--peer")
  ? configureWorkspace(args)
  : runSetupWizard()).catch((err) => {
  process.stderr.write(`${err?.stack || err}\n`);
  process.exit(1);
});
