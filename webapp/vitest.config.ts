import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      reportsDirectory: "./coverage",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "**/next.config.*",
        "**/postcss.config.*",
        "**/playwright.config.*",
        "**/vitest.config.*",
        "**/.next/**",
        "**/node_modules/**",
        "**/src/app/layout.tsx",
        "**/src/app/**/page.tsx",
        "**/src/app/**/layout.tsx",
        "**/src/app/**/loading.tsx",
        "**/src/app/**/error.tsx",
        "**/src/app/**/not-found.tsx",
        "**/src/test-setup.ts",
        "**/*.d.ts",
        "**/*.stories.tsx",
        "**/index.ts",
      ],
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
