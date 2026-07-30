import js from '@eslint/js'
import { globalIgnores } from 'eslint/config'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['src/**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  {
    // Componentes shadcn/ui exportam a variante (cva) junto do componente
    // por convencao da lib; regra de fast-refresh vira aviso, nao erro.
    files: ['src/components/ui/**/*.{ts,tsx}'],
    rules: {
      'react-refresh/only-export-components': 'warn',
    },
  },
  {
    // Badges de ticket exportam mapas de estilo (STATUS_ACCENTS etc.) junto
    // dos componentes por design; regra de fast-refresh vira aviso, nao erro.
    files: ['src/components/tickets/**/*.{ts,tsx}'],
    rules: {
      'react-refresh/only-export-components': 'warn',
    },
  },
  {
    // Componentes de reporting exportam mapas de estilo (STATUS_CHART_FILL etc.)
    // junto dos componentes por design; regra de fast-refresh vira aviso, nao erro.
    files: ['src/components/reporting/**/*.{ts,tsx}'],
    rules: {
      'react-refresh/only-export-components': 'warn',
    },
  },
])
