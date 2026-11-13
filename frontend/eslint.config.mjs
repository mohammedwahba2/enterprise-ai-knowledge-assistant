import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

import { rtlGuard } from "./eslint.rtl-guard.mjs";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  { files: ["src/**/*.{ts,tsx}"], rules: rtlGuard },
  globalIgnores([".next/**", "out/**", "node_modules/**", "next-env.d.ts"]),
]);
