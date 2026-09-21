import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import jsxA11y from 'eslint-plugin-jsx-a11y'

export default [
  { ignores: ['dist/**', 'node_modules/**', '.vercel/**'] },
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.es2021 },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: 'detect' } },
    plugins: { react, 'react-hooks': reactHooks, 'jsx-a11y': jsxA11y },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs['jsx-runtime'].rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.flatConfigs.recommended.rules,
      // The kit takes props straight from API envelopes; prop-types would be a second,
      // weaker copy of contracts/openapi.json.
      'react/prop-types': 'off',
      // Typographic apostrophes and quotes in copy are correct HTML and read correctly in
      // a screen reader; escaping them would make the prose unreviewable.
      'react/no-unescaped-entities': 'off',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // axe's `scrollable-region-focusable` (serious) requires a scrolling container that
      // holds no focusable content to be focusable itself, so a keyboard user can scroll
      // it. `role="region"` with an accessible name is the ARIA pattern for that, and it
      // is exactly what this rule's `roles` option exists to allow.
      'jsx-a11y/no-noninteractive-tabindex': ['error', { tags: [], roles: ['tabpanel', 'region'], allowExpressionValues: true }],
    },
  },
  {
    files: ['**/*.test.{js,jsx}', 'src/test/**/*.js'],
    languageOptions: { globals: { ...globals.browser, ...globals.node, ...globals.vitest } },
  },
  {
    files: ['vite.config.js', 'tailwind.config.js', 'postcss.config.js', 'eslint.config.js', 'playwright.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    // Playwright specs run in node and get their globals from @playwright/test's imports,
    // not from a global injection — but they do read process.env for the seeded password.
    files: ['e2e/**/*.js'],
    languageOptions: { globals: { ...globals.node } },
  },
]
