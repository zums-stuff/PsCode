import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    include: ["test/**/*.test.{ts,tsx}"],
    setupFiles: ["test/setup.ts"],
    alias: {
      "@codemirror/lang-pseint": path.resolve(__dirname, "src/lang/index.ts"),
      "@": path.resolve(__dirname, "src"),
    },
  },
  resolve: {
    alias: {
      "@codemirror/lang-pseint": path.resolve(__dirname, "src/lang/index.ts"),
      "@": path.resolve(__dirname, "src"),
    },
  },
});