import { memo } from "react";
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
    <a href={href} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-2">
      {children}
    </a>
  ),
};

function StreamingMarkdown({ content, streaming }: { content: string; streaming: boolean }) {
  return (
    <div className={clsx("ep-answer", streaming && "ep-streaming")}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
      {streaming && !content && <span className="ep-cursor" aria-hidden />}
    </div>
  );
}

export default memo(StreamingMarkdown);
