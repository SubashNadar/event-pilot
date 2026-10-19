import { memo, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  table: ({ children }) => (
    <div className="table-wrap">
      <table>{children}</table>
    </div>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
};

/**
 * Shows text as it types out. The model can deliver a whole paragraph in a
 * second, so the text is revealed at a steady, readable pace and catches up
 * faster the further behind it gets. Text that is already complete is shown
 * at once.
 */
function useReveal(content: string, animate: boolean): number {
  const target = content.length;
  const [shown, setShown] = useState(() => (animate ? 0 : target));
  const shownRef = useRef(shown);

  useEffect(() => {
    if (shownRef.current >= target) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const current = shownRef.current;
      if (current >= target) return;
      const elapsed = now - last;
      last = now;
      const behind = target - current;
      const charsPerSecond = Math.max(70, behind * 3);
      const next = Math.min(target, current + Math.max(1, Math.round((charsPerSecond * elapsed) / 1000)));
      shownRef.current = next;
      setShown(next);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target]);

  return Math.min(shown, target);
}

function StreamingMarkdown({ content, streaming, reveal = false }: { content: string; streaming: boolean; reveal?: boolean }) {
  const visible = useReveal(content, streaming || reveal);
  const typing = streaming || visible < content.length;
  return (
    <div className={clsx("answer", typing && "streaming")}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content.slice(0, visible)}
      </ReactMarkdown>
      {typing && <span className="cursor-blink" aria-hidden />}
    </div>
  );
}

export default memo(StreamingMarkdown);
