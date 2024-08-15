import { defineConfig } from '@hey-api/openapi-ts'

const service = process.env.CODEGEN

export default defineConfig({
  client: {
    name: '@hey-api/client-fetch',
    bundle: true
  },
  input: `../pkg/oas/${service}/${service}.json`,
  output: `src/gen/oas/${service}`,
  plugins: ['@tanstack/vue-query']
})
