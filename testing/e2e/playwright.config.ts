// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

const env = (key: string, fallback: string) => process.env[key] ?? fallback;
const envInt = (key: string, fallback: number) =>
  parseInt(process.env[key] ?? "") || fallback;

const isCI = !!process.env.CI;
const browser = env("E2E_BROWSER", "chromium");

const projects = [];
if (browser === "chromium" || browser === "all") {
  projects.push({
    name: "chromium",
    use: { ...devices["Desktop Chrome"] },
  });
}
if (browser === "firefox" || browser === "all") {
  projects.push({
    name: "firefox",
    use: { ...devices["Desktop Firefox"] },
  });
}

const baseURL =
  process.env.E2E_BASE_URL ??
  (process.env.DOCKER ? "https://host.docker.internal" : "https://localhost");

export default defineConfig({
  testDir: "./tests",
  globalSetup: "./global-setup.js",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: envInt("E2E_RETRIES", isCI ? 2 : 1),
  workers: envInt("E2E_WORKERS", isCI ? 2 : 16),
  reporter: env("E2E_REPORTER", "html"),
  timeout: envInt("E2E_TIMEOUT", 30000),
  use: {
    baseURL,
    ignoreHTTPSErrors: true,
    trace: env("E2E_TRACE", "on-first-retry") as
      | "on"
      | "off"
      | "on-first-retry"
      | "retain-on-failure",
    screenshot: env("E2E_SCREENSHOT", "only-on-failure") as
      | "on"
      | "only-on-failure"
      | "off",
    video: env("E2E_VIDEO", "off") as
      | "on"
      | "off"
      | "on-first-retry"
      | "retain-on-failure",
  },
  projects,
});
