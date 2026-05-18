import { defineConfig } from "@hey-api/openapi-ts";

const service = process.env.CODEGEN;
// CODEGEN_TARGET=e2e re-emits the same spec under testing/e2e/src/gen
// without the @tanstack/vue-query plugin — the Playwright fixtures use
// the plain SDK with @hey-api/client-fetch.
const isE2E = process.env.CODEGEN_TARGET === "e2e";

const typescriptPlugin = {
  name: "@hey-api/typescript",
  enums: "javascript",
} as const;

export default defineConfig({
  client: "@hey-api/client-fetch",
  input: `pkg/oas/${service}/${service}.json`,
  output: isE2E
    ? `testing/e2e/src/gen/${service}`
    : `component/frontend/src/gen/oas/${service}`,
  // @tanstack/vue-query (frontend) implicitly pulls in @hey-api/sdk; the
  // e2e branch has to list it explicitly or `sdk.gen.ts` and `client/` are
  // not emitted.
  plugins: isE2E
    ? ["@hey-api/sdk", typescriptPlugin]
    : ["@tanstack/vue-query", typescriptPlugin],
});
