import { existsSync, readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { resolve } from "node:path";

const localFiles = [".env.local", ".env", ".env.dev"];
const localMarker = "LOCAL_ENV_OWNER_KEY";
const ownerMarkerFile = ".ai-lead-owner.local";
const mode = process.argv[2] ?? "auto";

function hasLocalMarker(file) {
  if (!existsSync(resolve(file))) return false;
  const expression = new RegExp(`^\\s*${localMarker}\\s*=\\s*(?!\\s*(?:#|$))` , "m");
  return expression.test(readFileSync(resolve(file), "utf8"));
}

function getEnvValue(file, key) {
  if (!existsSync(resolve(file))) return undefined;
  const match = readFileSync(resolve(file), "utf8").match(
    new RegExp(`^\\s*${key}\\s*=\\s*(.+?)\\s*$`, "m")
  );
  return match?.[1]?.replace(/^['\"]|['\"]$/g, "").trim() || undefined;
}

const localFile = localFiles.find(hasLocalMarker);
const ownerMarkerEnabled = hasLocalMarker(ownerMarkerFile);
const ownerConfiguredFile = getEnvValue(ownerMarkerFile, "LOCAL_ENV_FILE");
const ownerLocalFile = ownerMarkerEnabled
  ? ownerConfiguredFile && existsSync(resolve(ownerConfiguredFile))
    ? ownerConfiguredFile
    : localFiles.find((file) => existsSync(resolve(file)))
  : undefined;
const selectedLocalFile = localFile ?? ownerLocalFile;
const useLocal = mode === "local" || (mode === "auto" && Boolean(selectedLocalFile));

if (mode !== "auto" && mode !== "local" && mode !== "infisical") {
  console.error("Usage: node scripts/run-dev.mjs [--local|--infisical]");
  process.exit(1);
}

if (mode === "local" && !selectedLocalFile) {
  console.error(
    `Local mode requires a non-empty ${localMarker} in .env.local, .env, .env.dev, or ${ownerMarkerFile}.`
  );
  process.exit(1);
}

const python = process.platform === "win32" ? "py" : "python3";
const command = useLocal ? python : "infisical";
const args = useLocal
  ? ["-3.10", "run_api.py"]
  : ["run", "--env=dev", "--", python, "-3.10", "run_api.py"];
const env = { ...process.env };

if (useLocal) {
  env.ENV_FILE = selectedLocalFile;
  console.log(`Starting with local configuration from ${selectedLocalFile}.`);
} else {
  console.log("Starting with ai-lead-pipeline-dev secrets from Infisical.");
}

const child = spawn(command, args, { cwd: process.cwd(), env, stdio: "inherit" });
child.on("error", (error) => {
  console.error(`Could not start ${command}: ${error.message}`);
  process.exit(1);
});
child.on("exit", (code, signal) => process.exitCode = code ?? (signal ? 1 : 0));
