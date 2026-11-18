import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// ダイアログは components/ui/dialog.tsx（Radix）だけで組む。手書きのモーダルはフォーカスの閉じ込めや
// Esc・スクロール止めが抜けやすいため。全画面ビューなど例外は理由を書いて eslint-disable する。
const UI_PARTS = [
  {
    selector: "JSXAttribute[name.name='aria-modal']",
    message: "モーダルは @/components/ui/dialog の Dialog / DialogContent / DialogFrame を使ってください。",
  },
  {
    selector: "JSXAttribute[name.name='role'][value.value=/^menu(item)?$/]",
    message: "メニューは @/components/ui/menu の Menu / MenuContent / MenuItem を使ってください。",
  },
];

// 見た目の組み合わせを手で書き写さない（1 か所で変えられるように）。色や強調を変えた特例は書いてよい。
const UI_LOOKS = [
  {
    selector: "Literal[value=/animate-spin/]",
    message: "回る輪は @/components/ui/spinner の Spinner を使ってください。",
  },
  {
    selector: "Literal[value=/uppercase tracking-[^ ]+ text-muted/]",
    message: "区切りの小見出しは class の eyebrow（globals.css の @utility）を使ってください。",
  },
  {
    selector: "Literal[value=/rounded-card border-\\[0\\.5px\\] border-divider(-strong)? bg-surface/]",
    message: "面は @/components/ui/card の Card、または class の card / card-sunken / card-raised を使ってください。",
  },
  {
    selector: "TemplateElement[value.raw=/color-mix\\(in srgb, $/]",
    message: "形式の色の札は @/components/ui/file-tile の FileTile / fileTileStyle を使ってください。",
  },
];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/**/*.tsx"],
    ignores: ["src/components/ui/**"],
    rules: { "no-restricted-syntax": ["error", ...UI_PARTS, ...UI_LOOKS] },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // pdf.js の CMap・wasm（scripts/copy-pdfjs-assets.mjs が作る生成物）
    "public/pdfjs/**",
  ]),
]);

export default eslintConfig;
