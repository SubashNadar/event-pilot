import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import clsx from "clsx";
import { ArrowUp, FileText, Paperclip, Square, X } from "lucide-react";

const MAX_CHARS = 4000;

export interface ComposerHandle {
  focus: () => void;
}

export interface InvitationAttachment {
  name: string;
  text: string;
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: (v: string, attachments: InvitationAttachment[]) => void;
  onStop: () => void;
  streaming: boolean;
}

const SAMPLE_INVITATION = `WEDDING RECEPTION OF MEERA AND KARTHIK

Together with their families, Meera and Karthik invite you to celebrate their wedding reception.

Saturday, 20 March 2027 | 6:30 PM onwards
Whitefield Garden Pavilion, Whitefield, Bengaluru

Dinner and music to follow. RSVP by 5 March 2027.

Planning note: approximately 350 guests. Event planning budget: INR 12 lakh.
Objective: create a warm family celebration with a smooth guest welcome, ceremony timing, photography and dinner flow.`;

const Composer = forwardRef<ComposerHandle, Props>(function Composer({ value, onChange, onSend, onStop, streaming }, ref) {
  const ta = useRef<HTMLTextAreaElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<File[]>([]);

  useImperativeHandle(ref, () => ({ focus: () => ta.current?.focus() }));

  // Auto-grow up to ~10 lines.
  useEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
  }, [value]);

  const over = value.length > MAX_CHARS;
  const canSend = (value.trim().length > 0 || attachments.length > 0) && !over && !streaming;

  const submit = async () => {
    if (!canSend) return;
    const readable = await Promise.all(attachments.map(async (attachment) => ({ name: attachment.name, text: await attachment.text() })));
    onSend(value, readable);
    setAttachments([]);
  };

  return (
    <div className="rounded-3xl border border-border bg-surface shadow-lift transition-shadow duration-200 focus-within:border-muted/50">
      {attachments.length > 0 && (
        <ul className="flex flex-wrap gap-2 px-4 pt-3" aria-label="Attachments">
          {attachments.map((f, i) => (
            <li key={f.name + i} className="flex items-center gap-2 rounded-xl border border-border bg-surface-2 py-1.5 pl-2.5 pr-1.5 text-[12.5px]">
              <FileText size={14} className="text-accent" aria-hidden />
              <span className="max-w-[180px] truncate">{f.name}</span>
          <span className="text-muted">Invitation text</span>
              <button type="button" className="icon-btn h-6 w-6" aria-label={`Remove ${f.name}`} onClick={() => setAttachments((a) => a.filter((_, j) => j !== i))}>
                <X size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <label htmlFor="composer" className="sr-only">
        Describe the event you want to plan
      </label>
      <textarea
        id="composer"
        ref={ta}
        rows={1}
        value={value}
        placeholder="Describe your event — who, where, when, budget…"
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        className="scroll-thin block max-h-[260px] w-full resize-none bg-transparent px-4 pb-1 pt-3.5 text-[15px] leading-relaxed placeholder:text-muted/80 focus:outline-none"
      />

      <div className="flex items-center gap-2 px-2.5 pb-2.5 pt-1">
        <input
          ref={file}
          type="file"
          accept=".txt,.md"
          multiple
          className="hidden"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            setAttachments((a) => [...a, ...files]);
            e.target.value = "";
          }}
        />
        <button type="button" className="icon-btn h-9 w-9" aria-label="Attach an invitation text file" title="Attach an invitation text file" onClick={() => file.current?.click()}>
          <Paperclip size={17} />
        </button>

        {!attachments.length && (
          <button
            type="button"
            onClick={() => setAttachments([new File([SAMPLE_INVITATION], "Meera-and-Karthik-Wedding-Invitation.txt", { type: "text/plain" })])}
            className="hidden rounded-lg border border-border px-2.5 py-1.5 text-[11.5px] font-medium text-accent transition-colors hover:border-accent/45 hover:bg-accent/5 sm:inline-flex"
          >
            Try wedding invitation
          </button>
        )}

        <span className="hidden text-[11.5px] text-muted sm:inline">
          <kbd className="font-sans">Enter</kbd> to send · <kbd className="font-sans">Shift + Enter</kbd> for a new line
        </span>

        <span className={clsx("ml-auto text-[11.5px] tabular-nums", over ? "font-medium text-danger" : "text-muted", value.length < 200 && !over && "invisible")} aria-live="polite">
          {value.length.toLocaleString("en-IN")} / {MAX_CHARS.toLocaleString("en-IN")}
        </span>

        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            title="Stop"
            className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-ink text-bg transition-opacity duration-150 hover:opacity-90"
          >
            <Square size={13} className="fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!canSend}
            aria-label="Send"
            title="Send"
            className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-accent text-accent-ink transition-[opacity,transform] duration-150 hover:opacity-90 active:scale-95 disabled:cursor-not-allowed disabled:opacity-35"
          >
            <ArrowUp size={18} strokeWidth={2.25} />
          </button>
        )}
      </div>
    </div>
  );
});

export default Composer;
