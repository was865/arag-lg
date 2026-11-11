import type { Metadata, Viewport } from "next";
import { THEME_COLOR_DARK, THEME_COLOR_LIGHT, THEME_STORAGE_KEY } from "@/lib/constants";
import { LEGACY_DEFAULT_ACCENT, TWEAKS_VERSION } from "@/lib/tweaks-migrate";
import { getDictionary } from "@/i18n/dictionary";
import { LocaleProvider } from "@/i18n/context";
import { ToastProvider } from "@/components/feedback/toast-provider";
import { MotionProvider } from "@/components/motion-provider";
// 自前ホストの書体（Latin/数字 = Inter、日本語 = Noto Sans JP）。実ウェイトのみ読み込む。
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/inter/latin-700.css";
import "@fontsource/noto-sans-jp/400.css";
import "@fontsource/noto-sans-jp/500.css";
import "@fontsource/noto-sans-jp/600.css";
import "@fontsource/noto-sans-jp/700.css";
import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "ARag",
  description: "社内文書に根拠を持って答えるナレッジアシスタント",
  appleWebApp: { capable: true, statusBarStyle: "default", title: "ARag" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
};

/* 保存済みのテーマとアクセント色を初回描画の前に当てる（ちらつき防止）。 */
const themeBootstrap = `
(function () {
  var dark = false;
  try {
    var raw = localStorage.getItem('${THEME_STORAGE_KEY}');
    var t = raw ? JSON.parse(raw) : {};
    dark = !!t.dark;
    var el = document.documentElement;
    el.classList.add(dark ? 'theme-dark' : 'theme-light');
    // 版の印が無い保存値の旧既定（橙）は使わず、CSS の既定（朱）に任せる（lib/tweaks-migrate と同じ判定）
    var legacy = !(t.v >= ${TWEAKS_VERSION}) && String(t.accent).toLowerCase() === '${LEGACY_DEFAULT_ACCENT}';
    if (t.accent && !legacy) el.style.setProperty('--accent', t.accent);
  } catch (e) {
    document.documentElement.classList.add('theme-light');
  }
  var meta = document.createElement('meta');
  meta.name = 'theme-color';
  meta.content = dark ? '${THEME_COLOR_DARK}' : '${THEME_COLOR_LIGHT}';
  document.head.appendChild(meta);
})();
`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ja" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body>
        <LocaleProvider locale="ja" dict={getDictionary()}>
          <MotionProvider>
            <ToastProvider>{children}</ToastProvider>
          </MotionProvider>
        </LocaleProvider>
      </body>
    </html>
  );
}
