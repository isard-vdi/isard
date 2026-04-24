import { defineConfig } from "@hey-api/openapi-ts";

const service = process.env.CODEGEN;

export default defineConfig({
  client: "@hey-api/client-fetch",
  input: `pkg/oas/${service}/${service}.json`,
  output: `component/frontend/src/gen/oas/${service}`,
  plugins: [
    "@tanstack/vue-query",
    {
      name: "@hey-api/typescript",
      enums: "javascript",
    },
  ],
});
