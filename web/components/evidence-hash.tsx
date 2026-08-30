"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export function EvidenceHash({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<number | null>(null);

  useEffect(() => () => {
    if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
  }, []);

  async function copyValue() {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const temporary = document.createElement("textarea");
      temporary.value = value;
      temporary.setAttribute("readonly", "");
      temporary.style.position = "fixed";
      temporary.style.opacity = "0";
      document.body.appendChild(temporary);
      temporary.select();
      document.execCommand("copy");
      temporary.remove();
    }
    setCopied(true);
    if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    resetTimer.current = window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <span className="evidence-hash-value">
      <code title={value} aria-label={`${label}: ${value}`}>{shortenEvidenceHash(value)}</code>
      <button
        className="evidence-copy-button"
        type="button"
        title={copied ? "Kopyalandı" : `${label} değerini kopyala`}
        aria-label={copied ? `${label} kopyalandı` : `${label} değerini kopyala`}
        onClick={() => void copyValue()}
      >
        {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
      </button>
    </span>
  );
}

export function shortenEvidenceHash(value: string) {
  return value.length > 24 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value;
}
