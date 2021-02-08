module.exports = {
  parser: 'vue-eslint-parser',
  parserOptions: {
    parser: '@typescript-eslint/parser',
    ecmaVersion: 2020,
    sourceType: 'module'
  },
  plugins: ['vue', '@typescript-eslint'],
  extends: ['plugin:vue/vue3-recommended', 'prettier', 'prettier/vue'],
  rules: {
    // semi: ['error', 'never'],
    quotes: [2, 'single', { avoidEscape: true }]
  }
};
