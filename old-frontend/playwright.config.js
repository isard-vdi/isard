// @ts-check
const { defineConfig, devices } = require('@playwright/test')

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
// require('dotenv').config();

/**
 * @see https://playwright.dev/docs/test-configuration
 */
module.exports = defineConfig({
  testDir: './tests/e2e',
  globalSetup: require.resolve('./tests/e2e/global-setup.js'),
  globalTeardown: require.resolve('./tests/e2e/global-teardown.js'),
  /*
   * Tests inside the same file stay serial (most specs share
   * seed-state via module-level variables); different files run
   * concurrently across workers. ``fullyParallel: true`` was
   * unsafe — multiple tests hit /profile and /userstorage at the
   * same time and raced on shared apiv4 state.
   */
  fullyParallel: false,
  /* Always fail on test.only to keep the suite reproducible. */
  forbidOnly: true,
  /*
   * 2 retries by default. With the per-worker admin pool the
   * remaining flakes are stack-state timing (engine slow to
   * materialise a desktop, sessions service rate-limit, etc.)
   * — retrying classifies these as "flaky" in the html report
   * instead of failures, while a test that fails on every retry
   * is a real regression. Override with ``E2E_RETRIES=0`` to see
   * raw first-run results.
   */
  retries: Number(process.env.E2E_RETRIES ?? 2),
  /*
   * Default to 1 worker (serial) for reproducibility. This is
   * the only mode where the IsardVDI stack (single engine, single
   * apiv4, one rethinkdb writer) is fully deterministic across
   * runs.
   *
   * Opt into parallel mode for fast iteration via ``E2E_WORKERS=N``
   * — global-setup.js auto-sizes the admin pool to match. Pre-merge
   * regression gating should always run with E2E_WORKERS=1 and
   * E2E_RETRIES=0 so flakes can't mask real failures.
   */
  workers: Number(process.env.E2E_WORKERS ?? 1),
  /*
   * Reporters: ``list`` for live progress, ``html`` for the
   * post-run drill-in (flake/failure traces, screenshots,
   * timeline), ``junit`` for CI/regression-tracking systems.
   * The combination makes "what regressed" cheap to answer.
   */
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never' }], ['junit', { outputFile: 'test-results/junit.xml' }]]
    : [['list'], ['html', { open: 'never' }]],
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /*
     * Base URL to use in actions like `await page.goto('/')`.
     *
     * E2E_BASE_URL overrides the target (it was documented but never
     * implemented). On a USAGE=devel stack it MUST be the stack's real
     * DOMAIN, not https://localhost: the webpack dev server's sockjs
     * endpoint is same-origin only for that domain, and via localhost
     * every page emits CORS + "[WDS] Disconnected!" console errors that
     * fail all console-clean specs and break networkidle waits.
     */
    baseURL:
      process.env.E2E_BASE_URL ??
      (process.env.DOCKER ? 'https://host.docker.internal' : 'https://localhost'),

    ignoreHTTPSErrors: true,

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',

    /*
     * Default action timeout. Playwright's default is "no
     * timeout" which means a misbehaving locator hangs until the
     * test-level timeout (180 s). Cap at 15 s so flaky locators
     * surface fast.
     */
    actionTimeout: 15000,
    navigationTimeout: 30000
  },

  /* Configure projects for major browsers */
  projects: [
    {
      // ``chromium-headless-shell`` is the lighter Playwright build
      // (~280 MB vs ~580 MB for full chromium) optimised for headless
      // CI / server runs. Available since Playwright 1.49 and the
      // default channel for ``headless: true`` in 1.57+. Pin
      // explicitly so the project stays stable when the upstream
      // default flips.
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], channel: 'chromium-headless-shell' }
    },

    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] }
    },

    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] }
    }

    /* Test against mobile viewports. */
    // {
    //   name: 'Mobile Chrome',
    //   use: { ...devices['Pixel 5'] },
    // },
    // {
    //   name: 'Mobile Safari',
    //   use: { ...devices['iPhone 12'] },
    // },

    /* Test against branded browsers. */
    // {
    //   name: 'Microsoft Edge',
    //   use: { ...devices['Desktop Edge'], channel: 'msedge' },
    // },
    // {
    //   name: 'Google Chrome',
    //   use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    // },
  ]

  /* Run your local dev server before starting the tests */
  // webServer: {
  //   command: 'cd .. && docker compose up -d',
  //   url: 'https://localhost',
  //   reuseExistingServer: !process.env.CI,
  // },
})
