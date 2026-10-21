import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local dev proxy: mirrors what CloudFront does in production (forwards /api to
// API Gateway and injects the x-api-key header). Set API_KEY in the environment;
// never commit it. API_TARGET overrides the API Gateway origin if needed.
const target =
  process.env.API_TARGET || "https://wlolz7mdl1.execute-api.us-east-1.amazonaws.com";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target,
        changeOrigin: true,
        headers: process.env.API_KEY ? { "x-api-key": process.env.API_KEY } : {},
      },
    },
  },
});
