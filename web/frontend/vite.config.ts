import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@codemirror/lang-pseint": path.resolve(__dirname, "src/lang/index.ts"),
      "@": path.resolve(__dirname, "src"),
    },
  },
});