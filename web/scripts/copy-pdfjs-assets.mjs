// 原本の対照表示（specs/030）で pdf.js が読む CMap・標準フォント・wasm を public/pdfjs/ に置く。
// 日本語 PDF の埋め込まれていないフォントを描くのに要る。生成物は git に入れない。
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = dirname(require.resolve("pdfjs-dist/package.json"));
const dest = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "pdfjs");
rmSync(dest, { recursive: true, force: true });
mkdirSync(dest, { recursive: true });
for (const dir of ["cmaps", "standard_fonts", "wasm"]) {
  if (existsSync(join(root, dir))) cpSync(join(root, dir), join(dest, dir), { recursive: true });
}
