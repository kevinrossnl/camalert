// End-to-end tests of the web player and the extension (#92, #127): Chromium against the fake Home Assistant.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60000,
  workers: 1,
  reporter: [["list"], ["junit", { outputFile: "../../junit-web.xml" }]],
  use: { headless: true, viewport: { width: 1280, height: 720 } },
});
