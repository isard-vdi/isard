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
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /*
   * With per-worker admin pool (``global-setup.js`` +
   * ``api-fixture.js``), each worker holds its own session — no
   * JWT shadowing across siblings. Parallelism is now bound only
   * by hardware (CPU + RAM for chromium-headless-shell processes
   * and the local IsardVDI stack).
   *
   * Default to ``undefined`` so Playwright picks
   * ``Math.ceil(os.cpus().length / 2)``; tune via
   * ``--workers=N`` or ``E2E_WORKERS``. Beefy CI runners can set
   * E2E_WORKERS=8+.
   */
  workers: process.env.CI
    ? Number(process.env.E2E_WORKERS ?? 2)
    : process.env.E2E_WORKERS ? Number(process.env.E2E_WORKERS) : undefined,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: process.env.CI ? [['html'], ['list']] : 'list',
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.DOCKER ? 'https://host.docker.internal' : 'https://localhost',

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
