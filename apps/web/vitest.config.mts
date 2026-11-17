import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  // Unit tests only: e2e/*.spec.ts is Playwright's.
  test: { include: ["**/*.test.ts?(x)"] },
});
