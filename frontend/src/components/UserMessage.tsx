import { useEffect, useRef, useState } from "react";
import { Check, Copy, Pencil } from "lucide-react";
import type { UserMessage as UserMessageT } from "../types/types";
import { useAgent } from "../hooks/useAgentStream";
import { copyText, formatTimeShort } from "../lib/format";

export default function UserMessage({ message }: { message: UserMessageT }) {
  const { editAndResend } = useAgent();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const [copied, setCopied] = useState(false);
  const ta = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing && ta.current) {
      ta.current.focus();
      ta.current.setSelectionRange(draft.length, draft.length);
      ta.current.style.height = "auto";
      ta.current.style.height = `${ta.current.scrollHeight}px`;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  if (editing) {
    return (
      <div className="ml-auto w-full max-w-[85%] rounded-2xl border border-border bg-surface p-3 shadow-soft">
        <label htmlFor={`edit-${message.id}`} className="sr-only">
          Edit message
        </label>
        <textarea
          id={`edit-${message.id}`}
          ref={ta}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${e.target.scrollHeight}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") setEditing(false);
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              editAndResend(message.id, draft);
            }
          }}
          className="w-full resize-none bg-transparent text-[15px] leading-relaxed outline-none"
        />
        <div className="mt-2 flex justify-end gap-2">
          <button type="button" onClick={() => setEditing(false)} className="rounded-lg px-3 py-1.5 text-[13px] text-muted hover:bg-surface-2 hover:text-ink">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => editAndResend(message.id, draft)}
            className="rounded-lg bg-ink px-3 py-1.5 text-[13px] font-medium text-bg hover:opacity-90"
          >
            Save & send
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="group flex flex-col items-end">
      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-surface-2 px-4 py-2.5 text-[15px] leading-relaxed">
        {message.content}
      </div>
      <div className="mt-1 flex items-center gap-0.5 text-muted opacity-0 transition-opacity duration-150 focus-within:opacity-100 group-hover:opacity-100">
        <time className="mr-1.5 text-[11.5px]" dateTime={new Date(message.createdAt).toISOString()}>
          {formatTimeShort(message.createdAt)}
        </time>
        <button
          type="button"
          className="icon-btn h-7 w-7"
          aria-label={copied ? "Copied" : "Copy message"}
          onClick={async () => {
            if (await copyText(message.content)) {
              setCopied(true);
              setTimeout(() => setCopied(false), 1400);
            }
          }}
        >
          {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
        </button>
        <button type="button" className="icon-btn h-7 w-7" aria-label="Edit message" onClick={() => { setDraft(message.content); setEditing(true); }}>
          <Pencil size={14} />
        </button>
      </div>
    </div>
  );
}
