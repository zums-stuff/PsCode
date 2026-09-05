import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    include: ["test/**/*.test.ts"],
    setupFiles: ["test/setup.ts"],
    alias: {
      "@codemirror/lang-pseint": path.resolve(__dirname, "src/lang/index.ts"),
    },
  },
  resolve: {
    alias: {
      "@codemirror/lang-pseint": path.resolve(__dirname, "src/lang/index.ts"),
    },
  },
});
