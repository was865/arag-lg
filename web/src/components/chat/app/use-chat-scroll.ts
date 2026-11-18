"use client";

/** 会話のスクロール。生成中は下に追従し、利用者が上へ送ったら止めて「最新へ」を出す。 */
import { useEffect, useRef, useState } from "react";

export function useChatScroll(turns: unknown) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const [awayFromBottom, setAwayFromBottom] = useState(false);
  // 会話を少しでも下へ送ったか（上部バーの区切り線は、送ったときだけ出す）
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [turns]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    setAwayFromBottom(!stickToBottom.current);
    setScrolled(el.scrollTop > 4);
  };

  const jumpToLatest = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = true;
    setAwayFromBottom(false);
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  };

  /** 次の描画から下に追従させる（送信したとき） */
  const stick = () => {
    stickToBottom.current = true;
  };

  /** スレッドを切り替えたとき */
  const reset = () => {
    stickToBottom.current = true;
    setAwayFromBottom(false);
    setScrolled(false);
  };

  return { scrollRef, onScroll, awayFromBottom, scrolled, jumpToLatest, stick, reset };
}
