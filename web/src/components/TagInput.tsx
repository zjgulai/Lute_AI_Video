"use client";

import { useState, useRef, useCallback, type KeyboardEvent } from "react";
import { X } from "@phosphor-icons/react";

interface Props {
  id: string;
  name?: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  ariaLabel?: string;
  ariaDescribedBy?: string;
  maxTags?: number;
  separator?: RegExp;
  className?: string;
}

const DEFAULT_SEPARATOR = /[,，\s\n]/;

export default function TagInput({
  id,
  name,
  value,
  onChange,
  placeholder,
  ariaLabel,
  ariaDescribedBy,
  maxTags,
  separator = DEFAULT_SEPARATOR,
  className = "",
}: Props) {
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const commit = useCallback(
    (raw: string) => {
      const tokens = raw
        .split(separator)
        .map((s) => s.trim())
        .filter(Boolean);
      if (tokens.length === 0) return;
      const merged = [...value];
      for (const token of tokens) {
        if (!merged.includes(token)) merged.push(token);
        if (maxTags && merged.length >= maxTags) break;
      }
      onChange(merged);
      setDraft("");
    },
    [value, separator, maxTags, onChange],
  );

  const handleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      if (draft.trim()) commit(draft);
    } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
      e.preventDefault();
      onChange(value.slice(0, -1));
    }
  };

  const removeTag = (i: number) => {
    const next = value.filter((_, idx) => idx !== i);
    onChange(next);
    inputRef.current?.focus();
  };

  return (
    <div
      onClick={() => inputRef.current?.focus()}
      className={`apple-input flex flex-wrap items-center gap-1.5 px-2.5 py-2 cursor-text min-h-[42px] ${className}`}
      data-tag-input={id}
    >
      {value.map((tag, i) => (
        <span
          key={`${tag}-${i}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] text-[12px] font-medium"
        >
          {tag}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              removeTag(i);
            }}
            aria-label={`Remove ${tag}`}
            className="hover:text-[var(--crimson-mist)] transition-colors cursor-pointer leading-none"
          >
            <X size={10} weight="bold" />
          </button>
        </span>
      ))}
      <input
        ref={inputRef}
        id={id}
        name={name || id}
        type="text"
        value={draft}
        onChange={(e) => {
          const v = e.target.value;
          if (separator.test(v)) {
            commit(v);
          } else {
            setDraft(v);
          }
        }}
        onKeyDown={handleKey}
        onBlur={() => draft.trim() && commit(draft)}
        placeholder={value.length === 0 ? placeholder : ""}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedBy}
        className="flex-1 min-w-[80px] bg-transparent border-0 outline-none text-sm placeholder:text-[var(--text-placeholder)] py-0.5"
      />
    </div>
  );
}
