import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.ts"],
    exclude: ["**/node_modules/**", "**/.next/**", "**/e2e/**"],
    // Explicit rather than relied-on-implicitly: Vitest 5 defaults this to
    // true (unlike Jest), which is what keeps module-scoped mocks (e.g. a
    // `vi.mock("next/navigation")` router spy) from leaking call history
    // between `it` blocks in the same file.
    clearMocks: true,
  },
});
