"use client";

/** アプリ全体のトースト基盤。
 *
 * root layout（LocaleProvider の内側）に一度だけ置き、Context で push を配って
 * ToastViewport を全画面で 1 つだけ描画する。ToastViewport は useT() を使うため
 * 必ず LocaleProvider の内側に配置すること。
 *
 * children は Server Component から props として渡るため、本 Provider が
 * トースト state の変化で再レンダリングしても children のサブツリーは再描画されない。 */

import { createContext, useContext } from "react";
import { useToasts, type PushToast } from "@/hooks/use-toasts";
import { ToastViewport } from "@/components/feedback/toast-viewport";

const noop: PushToast = () => {};

const ToastContext = createContext<PushToast>(noop);

/** トースト発火関数 push を返す。Provider 外では no-op。 */
export function useToast(): PushToast {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const { toasts, push, dismiss, pause, resume } = useToasts();
  return (
    <ToastContext.Provider value={push}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} onPause={pause} onResume={resume} />
    </ToastContext.Provider>
  );
}
