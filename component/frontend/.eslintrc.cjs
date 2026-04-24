/* eslint-env node */
require('@rushstack/eslint-patch/modern-module-resolution')

module.exports = {
  root: true,
  extends: [
    'plugin:vue/vue3-recommended',
    'eslint:recommended',
    '@vue/eslint-config-typescript/recommended',
    'plugin:@typescript-eslint/strict',
    'plugin:@typescript-eslint/stylistic',
    '@vue/eslint-config-prettier/skip-formatting'
  ],
  rules: {
    'vue/multi-word-component-names': ['off'],
    // The strict ruleset flags these heavily across the existing codebase.
    // Keep them visible as warnings (so CI still passes) until we clean up
    // the remaining cases in follow-up commits.
    '@typescript-eslint/no-unused-vars': [
      'warn',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }
    ],
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-non-null-assertion': 'warn',
    '@typescript-eslint/no-non-null-asserted-optional-chain': 'warn'
  },
  overrides: [
    {
      files: ['e2e/**/*.{test,spec}.{js,ts,jsx,tsx}'],
      extends: ['plugin:playwright/recommended']
    },
  ],
  // The ts-eslint strict/stylistic configs set parser to @typescript-eslint/parser at the
  // top level; override it back to vue-eslint-parser so .vue SFCs can still be parsed.
  // vue-eslint-parser delegates <script lang="ts"> blocks to the ts parser via parserOptions.parser.
  parser: require.resolve('vue-eslint-parser'),
  parserOptions: {
    ecmaVersion: 'latest',
    parser: require.resolve('@typescript-eslint/parser'),
    extraFileExtensions: ['.vue']
  }
}
