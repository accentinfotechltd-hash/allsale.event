/**
 * RichTextEditor — tiny WYSIWYG built on `contenteditable` + execCommand.
 *
 * Why hand-rolled instead of TipTap / Quill / Slate?
 * - React 19 broke several popular editors (react-quill notably).
 * - We only need a small set of formatting controls (bold, italic, underline,
 *   headings, lists, font-size, link) — not a full word processor.
 * - Zero external dependency keeps the bundle small and the upgrade path
 *   simple.
 *
 * Output: HTML string in `value`, written back via `onChange(html)`. The
 * caller is responsible for sanitization on render — see `sanitizeRichHtml`
 * below (re-exported for use in `EventDetail.jsx`).
 */
import { useEffect, useRef } from "react";
import { Bold, Italic, Underline as U, List, ListOrdered, Heading2, Link as LinkIcon, Type } from "lucide-react";

// Allowed tags + attributes for safe re-render. Anything else is stripped.
const ALLOWED_TAGS = new Set([
  "P","BR","B","STRONG","I","EM","U","H2","H3","UL","OL","LI","SPAN","A","DIV",
]);
const ALLOWED_ATTRS = {
  A: new Set(["href","target","rel"]),
  SPAN: new Set(["style"]),
};
// Only allow `font-size` and `font-weight` in inline styles — block anything
// that could execute JS (background-image:url, etc.).
const SAFE_STYLE = /^(font-size|font-weight)\s*:\s*[a-zA-Z0-9.%#-]+\s*;?\s*$/;

export function sanitizeRichHtml(raw) {
  if (!raw) return "";
  if (typeof window === "undefined" || !window.DOMParser) return raw;
  const doc = new window.DOMParser().parseFromString(`<div>${raw}</div>`, "text/html");
  const walk = (node) => {
    [...node.childNodes].forEach((c) => {
      if (c.nodeType !== 1) return; // keep text + comments
      if (!ALLOWED_TAGS.has(c.tagName)) {
        // Unwrap the tag — keep its text content
        const text = doc.createTextNode(c.textContent || "");
        c.replaceWith(text);
        return;
      }
      // Strip disallowed attributes
      const allowed = ALLOWED_ATTRS[c.tagName] || new Set();
      [...c.attributes].forEach((a) => {
        if (!allowed.has(a.name.toLowerCase())) c.removeAttribute(a.name);
      });
      // For <a>: enforce safe rel + nofollow on external links
      if (c.tagName === "A") {
        const href = c.getAttribute("href") || "";
        if (!/^(https?:|mailto:|tel:|\/)/i.test(href)) c.removeAttribute("href");
        c.setAttribute("target", "_blank");
        c.setAttribute("rel", "noopener noreferrer nofollow");
      }
      // For <span>: filter inline style
      if (c.tagName === "SPAN") {
        const style = (c.getAttribute("style") || "").split(";").map((s) => s.trim()).filter(Boolean);
        const safe = style.filter((s) => SAFE_STYLE.test(s + ";"));
        if (safe.length) c.setAttribute("style", safe.join("; ") + ";");
        else c.removeAttribute("style");
      }
      walk(c);
    });
  };
  walk(doc.body.firstChild);
  return doc.body.firstChild.innerHTML;
}

function ToolbarBtn({ onClick, title, children, active, testid }) {
  return (
    <button
      type="button"
      onMouseDown={(e) => { e.preventDefault(); onClick(); }}
      title={title}
      data-testid={testid}
      className="px-2 py-1.5 rounded text-sm inline-flex items-center"
      style={{
        background: active ? "rgba(255,79,0,0.12)" : "transparent",
        color: active ? "var(--accent)" : "var(--text-muted)",
        border: "1px solid var(--border)",
      }}
    >
      {children}
    </button>
  );
}

export default function RichTextEditor({ value, onChange, placeholder, testid = "rich-text-editor" }) {
  const ref = useRef(null);

  // Only push `value` into the DOM when it changes externally (e.g. when
  // we hydrate from the API in edit mode). Mirroring on every keystroke
  // moves the caret to the start of the field.
  useEffect(() => {
    if (!ref.current) return;
    if (ref.current.innerHTML !== (value || "")) {
      ref.current.innerHTML = value || "";
    }
  }, [value]);

  const exec = (cmd, arg) => {
    document.execCommand(cmd, false, arg);
    // Push the resulting HTML up to the parent.
    if (ref.current) onChange(ref.current.innerHTML);
  };

  const handleInput = () => {
    if (ref.current) onChange(ref.current.innerHTML);
  };

  const setFontSize = (size) => {
    // execCommand("fontSize", value) only accepts 1-7 (legacy HTML4 sizes)
    // → wrap selection in a span with a CSS font-size so we get full control.
    document.execCommand("fontSize", false, "7"); // marker we replace below
    if (!ref.current) return;
    ref.current.querySelectorAll('font[size="7"]').forEach((f) => {
      const span = document.createElement("span");
      span.style.fontSize = size;
      span.innerHTML = f.innerHTML;
      f.replaceWith(span);
    });
    onChange(ref.current.innerHTML);
  };

  const insertLink = () => {
    const url = window.prompt("Link URL (https://…):", "https://");
    if (url) exec("createLink", url);
  };

  return (
    <div data-testid={testid}>
      <div className="flex flex-wrap gap-1 mb-2">
        <ToolbarBtn onClick={() => exec("bold")} title="Bold (Ctrl+B)" testid="rt-bold"><Bold className="w-3.5 h-3.5" /></ToolbarBtn>
        <ToolbarBtn onClick={() => exec("italic")} title="Italic (Ctrl+I)" testid="rt-italic"><Italic className="w-3.5 h-3.5" /></ToolbarBtn>
        <ToolbarBtn onClick={() => exec("underline")} title="Underline (Ctrl+U)" testid="rt-underline"><U className="w-3.5 h-3.5" /></ToolbarBtn>
        <ToolbarBtn onClick={() => exec("formatBlock", "<h2>")} title="Heading" testid="rt-h2"><Heading2 className="w-3.5 h-3.5" /></ToolbarBtn>
        <ToolbarBtn onClick={() => exec("insertUnorderedList")} title="Bullet list" testid="rt-ul"><List className="w-3.5 h-3.5" /></ToolbarBtn>
        <ToolbarBtn onClick={() => exec("insertOrderedList")} title="Numbered list" testid="rt-ol"><ListOrdered className="w-3.5 h-3.5" /></ToolbarBtn>
        <ToolbarBtn onClick={insertLink} title="Insert link" testid="rt-link"><LinkIcon className="w-3.5 h-3.5" /></ToolbarBtn>
        <span className="inline-flex items-center gap-1 ml-1 px-2 rounded text-xs" style={{ border: "1px solid var(--border)" }}>
          <Type className="w-3 h-3 opacity-60" />
          <select
            onChange={(e) => { if (e.target.value) { setFontSize(e.target.value); e.target.value = ""; } }}
            defaultValue=""
            className="!py-1 !px-1 !text-xs !border-0 !bg-transparent"
            data-testid="rt-fontsize"
          >
            <option value="">Size</option>
            <option value="12px">Small</option>
            <option value="16px">Normal</option>
            <option value="20px">Large</option>
            <option value="24px">XL</option>
            <option value="32px">XXL</option>
          </select>
        </span>
      </div>
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        onInput={handleInput}
        onBlur={handleInput}
        data-placeholder={placeholder || "Describe the event…"}
        className="rich-editor min-h-[140px] p-3 rounded-lg border outline-none"
        style={{
          borderColor: "var(--border)",
          background: "var(--bg)",
          color: "var(--text)",
          lineHeight: 1.6,
        }}
      />
      <style>{`
        .rich-editor:empty::before {
          content: attr(data-placeholder);
          color: var(--text-dim);
          pointer-events: none;
        }
        .rich-editor h2 { font-size: 1.5rem; font-weight: 600; margin: 0.5em 0; }
        .rich-editor ul, .rich-editor ol { padding-left: 1.5rem; margin: 0.5em 0; }
        .rich-editor ul { list-style: disc; }
        .rich-editor ol { list-style: decimal; }
        .rich-editor a { color: var(--accent); text-decoration: underline; }
      `}</style>
    </div>
  );
}
