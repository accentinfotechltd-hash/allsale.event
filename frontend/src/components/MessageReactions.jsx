import { useState } from "react";
import { Smile } from "lucide-react";
import api from "@/lib/api";

const QUICK_EMOJIS = ["👍", "❤️", "😂", "🎉", "😮", "😢", "🔥"];

/**
 * MessageReactions — toolbar + display for emoji reactions on a single
 * support-chat message. Used on both the visitor widget and the admin
 * panel; identity is the session_id for anon visitors and the auth'd
 * user_id for admins (backend prefers the latter when available).
 *
 * Props:
 *   message      — the message doc, must have message_id, session_id, reactions
 *   onReact      — callback called after a successful toggle, given the
 *                  updated reactions map so the parent can re-render.
 *   align        — "left" or "right" so the toolbar floats outside the bubble
 *                  in the natural reading direction.
 */
export default function MessageReactions({ message, onReact, align = "left" }) {
  const [hover, setHover] = useState(false);

  const toggle = async (emoji) => {
    try {
      const { data } = await api.post("/support/chat/reactions", {
        session_id: message.session_id,
        message_id: message.message_id,
        emoji,
      });
      onReact?.(data.reactions || {});
    } catch { /* silent — bad-request would be a 4xx; ignore */ }
  };

  const reactions = message.reactions || {};
  const reactionEntries = Object.entries(reactions).filter(([, list]) => Array.isArray(list) && list.length > 0);

  return (
    <div
      className="relative inline-block"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {/* Floating emoji picker — visible on hover */}
      <div
        className={`absolute -top-9 ${align === "right" ? "right-0" : "left-0"} flex items-center gap-0.5 rounded-full px-1.5 py-1 shadow-lg transition-opacity ${hover ? "opacity-100" : "opacity-0 pointer-events-none"}`}
        style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
        data-testid={`reaction-picker-${message.message_id}`}
      >
        {QUICK_EMOJIS.map((emoji) => (
          <button
            key={emoji}
            type="button"
            onClick={() => toggle(emoji)}
            className="w-6 h-6 grid place-items-center text-sm rounded-full hover:bg-[color:var(--bg-elev)] transition"
            aria-label={`React with ${emoji}`}
            data-testid={`react-btn-${emoji}-${message.message_id}`}
          >
            {emoji}
          </button>
        ))}
      </div>

      {/* Trigger — small smiley that triggers the picker hover area */}
      <button
        type="button"
        className="opacity-50 hover:opacity-100 transition"
        data-testid={`reaction-trigger-${message.message_id}`}
        aria-label="React"
      >
        <Smile size={12} />
      </button>

      {/* Existing reaction pills */}
      {reactionEntries.length > 0 && (
        <div className={`flex gap-1 mt-1 flex-wrap ${align === "right" ? "justify-end" : ""}`}>
          {reactionEntries.map(([emoji, list]) => (
            <button
              key={emoji}
              type="button"
              onClick={() => toggle(emoji)}
              className="text-xs px-1.5 py-0.5 rounded-full border"
              style={{
                background: "var(--bg-card)",
                borderColor: "var(--border)",
                color: "var(--text)",
              }}
              data-testid={`reaction-chip-${emoji}-${message.message_id}`}
            >
              {emoji} {list.length}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
