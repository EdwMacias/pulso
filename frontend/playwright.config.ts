import { defineConfig } from '@playwright/test'
export default defineConfig({ testDir: './e2e', use: { baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173' }, webServer: process.env.E2E_BASE_URL ? undefined : { command: 'npm run dev -- --port 5173', url: 'http://127.0.0.1:5173', reuseExistingServer: true } })
