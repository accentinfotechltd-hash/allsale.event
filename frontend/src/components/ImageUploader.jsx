import { useRef, useState } from "react";
import api from "@/lib/api";
import { Upload, X, Loader2 } from "lucide-react";
import { toast } from "sonner";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

/**
 * ImageUploader — drag/click to upload an image; returns absolute URL via onUploaded.
 * Stores URL in `value`. Shows preview.
 */
export default function ImageUploader({ value, onUploaded, label = "Upload image", aspect = "16/9", testid = "image-uploader" }) {
  const inputRef = useRef();
  const [uploading, setUploading] = useState(false);

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/uploads", fd, { headers: { "Content-Type": "multipart/form-data" } });
      // API returns relative path /api/uploads/xxx — make absolute
      const absUrl = data.url.startsWith("http") ? data.url : `${BACKEND}${data.url}`;
      onUploaded(absUrl);
      toast.success("Uploaded");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally { setUploading(false); }
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
          <img src={value} alt="" className="w-full h-full object-cover" />
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
      ) : (
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
      )}
    </div>
  );
}
