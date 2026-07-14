/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            "@": path.resolve(__dirname, "./src"),
        },
    },
    server: {
        host: "0.0.0.0",
        port: 5174,
        proxy: {
            "/api": {
                target: process.env.VITE_API_BASE || "http://localhost:8010",
                changeOrigin: true,
                rewrite: function (path) { return path.replace(/^\/api/, ""); },
            },
        },
    },
    test: {
        environment: "jsdom",
        setupFiles: "./src/test/setup.ts",
        clearMocks: true,
    },
});
