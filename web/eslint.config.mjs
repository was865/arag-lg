import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // ダイアログは components/ui/dialog.tsx（Radix）だけで組む。手書きのモーダルはフォーカスの閉じ込めや
  // Esc・スクロール止めが抜けやすいため。全画面ビューなど例外は理由を書いて eslint-disable する。
  {
    files: ["src/**/*.tsx"],
    ignores: ["src/components/ui/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='aria-modal']",
          message: "モーダルは @/components/ui/dialog の Dialog / DialogContent / DialogFrame を使ってください。",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
