import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // mesma origem que em produção (a Vercel repassa /api ao Render): cookie de refresh e sem CORS
    proxy: { "/api": { target: process.env.API_PROXY ?? "http://localhost:8000", changeOrigin: false } },
  },
});
