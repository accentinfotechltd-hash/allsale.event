import { useRef, useState } from "react";
import api from "@/lib/api";
import { Upload, X, Loader2, Link as LinkIcon } from "lucide-react";
import { toast } from "sonner";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

/**
 * ImageUploader — drag/click to upload an image OR paste an external URL.
 * Returns absolute URL via onUploaded. Stores URL in `value`. Shows preview.
 */
export default function ImageUploader({ value, onUploaded, label = "Upload image", aspect = "16/9", testid = "image-uploader" }) {
  const inputRef = useRef();
  const [uploading, setUploading] = useState(false);
  const [showUrlInput, setShowUrlInput] = useState(false);
  const [urlDraft, setUrlDraft] = useState("");

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/uploads", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const absUrl = data.url.startsWith("http") ? data.url : `${BACKEND}${data.url}`;
      onUploaded(absUrl, data.file_id);
      toast.success("Uploaded");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed — try pasting an image URL instead");
      setShowUrlInput(true);
    } finally { setUploading(false); }
  };

  const submitUrl = () => {
    const url = urlDraft.trim();
    if (!url) return;
    if (!/^https?:\/\//i.test(url)) {
      toast.error("URL must start with http(s)://");
      return;
    }
    onUploaded(url);
    toast.success("Image set");
    setShowUrlInput(false);
    setUrlDraft("");
  };

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={(e) => upload(e.target.files?.[0])}
        data-testid={`${testid}-input`}
      />
      {value ? (
        <div className="relative rounded-xl overflow-hidden border" style={{ borderColor: "var(--border)", aspectRatio: aspect }}>
          <img
            src={value}
            alt=""
            className="w-full h-full object-cover"
            onError={(e) => {
              // Image URL is unreachable — show a helpful overlay instead of a silent broken icon
              e.currentTarget.style.display = "none";
              const wrap = e.currentTarget.parentElement;
              if (wrap && !wrap.querySelector(".img-fail")) {
                const div = document.createElement("div");
                div.className = "img-fail absolute inset-0 flex items-center justify-center text-xs text-center p-4";
                div.style.color = "var(--danger)";
                div.style.background = "rgba(220, 38, 38, 0.05)";
                div.innerText = "Image saved but preview can't load. URL: " + value;
                wrap.appendChild(div);
              }
            }}
          />
          <button
            type="button"
            onClick={() => onUploaded("")}
            className="absolute top-2 right-2 w-8 h-8 rounded-full flex items-center justify-center"
            style={{ background: "rgba(0,0,0,0.7)" }}
            data-testid={`${testid}-clear`}
          ><X className="w-4 h-4" /></button>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="absolute bottom-2 right-2 px-3 py-1.5 rounded-full text-xs"
            style={{ background: "rgba(0,0,0,0.7)" }}
            data-testid={`${testid}-replace`}
          >Replace</button>
        </div>
      ) : showUrlInput ? (
        <div className="rounded-xl border-2 border-dashed p-4 space-y-3" style={{ borderColor: "var(--border-strong)", background: "var(--bg-elev)", aspectRatio: aspect }}>
          <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Paste image URL</div>
          <input
            type="url"
            value={urlDraft}
            onChange={(e) => setUrlDraft(e.target.value)}
            placeholder="https://images.unsplash.com/..."
            className="w-full px-3 py-2 rounded-lg border outline-none text-sm"
            style={{ borderColor: "var(--border)", background: "var(--bg)", color: "var(--text)" }}
            data-testid={`${testid}-url-input`}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submitUrl(); } }}
          />
          <div className="flex gap-2">
            <button type="button" onClick={submitUrl} className="btn-primary text-sm py-1.5 px-3" data-testid={`${testid}-url-submit`}>Use this image</button>
            <button type="button" onClick={() => { setShowUrlInput(false); setUrlDraft(""); }} className="btn-ghost text-sm py-1.5 px-3" data-testid={`${testid}-url-cancel`}>Cancel</button>
          </div>
          <div className="text-xs" style={{ color: "var(--text-dim)" }}>
            Tip: Find a free image on{" "}
            <a href="https://unsplash.com" target="_blank" rel="noreferrer" className="underline">unsplash.com</a>
            {" "}— right-click → "Copy image address".
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="w-full rounded-xl border-2 border-dashed flex flex-col items-center justify-center gap-2 transition hover:border-[color:var(--accent)]"
            style={{ borderColor: "var(--border-strong)", color: "var(--text-muted)", aspectRatio: aspect, background: "var(--bg-elev)" }}
            data-testid={`${testid}-btn`}
          >
            {uploading ? <Loader2 className="w-6 h-6 animate-spin" style={{ color: "var(--accent)" }} /> : <Upload className="w-6 h-6" />}
            <span className="text-sm">{uploading ? "Uploading..." : label}</span>
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>JPG, PNG, WEBP — max 5MB</span>
          </button>
          <button
            type="button"
            onClick={() => setShowUrlInput(true)}
            className="w-full text-xs flex items-center justify-center gap-1.5 py-2 rounded-lg hover:opacity-80 transition"
            style={{ color: "var(--text-muted)" }}
            data-testid={`${testid}-paste-url`}
          >
            <LinkIcon className="w-3.5 h-3.5" />
            …or paste an image URL instead
          </button>
        </div>
      )}
    </div>
  );
}
