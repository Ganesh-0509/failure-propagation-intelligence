import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
  },
  build: {
    rollupOptions: {
      output: {
        // Split the heavy charting library into its own chunk so the main
        // app bundle stays small and cacheable.
        manualChunks: {
          recharts: ["recharts"],
          react: ["react", "react-dom"],
        },
      },
    },
  },
});
