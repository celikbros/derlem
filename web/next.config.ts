import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import type { NextConfig } from "next";

function appVersion(): string {
  try {
    const pkg = JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8")) as { version?: string };
    if (pkg.version) return pkg.version;
  } catch {
    // package.json okunamazsa npm ortam değişkenine düşeriz.
  }
  return process.env.npm_package_version ?? "0.0.0";
}

function appBuild(): string {
  // CI/dağıtım ortamları commit SHA'yı env ile verir; .git yoksa ona düşeriz.
  const fromEnv = process.env.DERLEM_BUILD_SHA ?? process.env.GITHUB_SHA ?? process.env.VERCEL_GIT_COMMIT_SHA;
  if (fromEnv) return fromEnv.slice(0, 7);
  try {
    return execSync("git rev-parse --short=7 HEAD", { encoding: "utf8" }).trim();
  } catch {
    return "dev";
  }
}

const nextConfig: NextConfig = {
  devIndicators: false,
  poweredByHeader: false,
  env: {
    NEXT_PUBLIC_APP_VERSION: appVersion(),
    NEXT_PUBLIC_APP_BUILD: appBuild(),
  },
};

export default nextConfig;
