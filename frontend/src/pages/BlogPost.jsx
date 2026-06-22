import { useEffect, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { Calendar, ArrowLeft, Tag as TagIcon } from "lucide-react";
import api from "@/lib/api";
import { sanitizeRichHtml } from "@/components/RichTextEditor";

/**
 * BlogPost — a single published article.
 *
 * SEO essentials baked in:
 *  • <title>, meta description, canonical, OpenGraph + Twitter cards
 *  • JSON-LD Article schema so Google can rich-snippet it
 *  • Server-rendered HTML body sanitized through the same allowlist the
 *    event description editor uses (no XSS, no inline JS).
 */
export default function BlogPost() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [post, setPost] = useState(null);
  const [related, setRelated] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    (async () => {
      try {
        const { data } = await api.get(`/blog/${slug}`);
        if (!live) return;
        setPost(data);
      } catch (_e) {
        if (live) setPost(null);
      } finally {
        if (live) setLoading(false);
      }
      try {
        const { data } = await api.get(`/blog/${slug}/related`);
        if (live) setRelated(data || []);
      } catch (_e) { /* non-fatal */ }
    })();
    return () => { live = false; };
  }, [slug]);

  useEffect(() => {
    if (!post) return;
    const title = post.meta_title || post.title;
    document.title = `${title} — Allsale Events Blog`;
    setMeta("description", post.meta_description || post.excerpt || post.title);
    setMeta("og:title", title, { property: true });
    setMeta("og:description", post.meta_description || post.excerpt || "", { property: true });
    setMeta("og:type", "article", { property: true });
    if (post.cover_url) setMeta("og:image", post.cover_url, { property: true });
    setMeta("twitter:card", "summary_large_image");
    setCanonical(`${window.location.origin}/blog/${post.slug}`);
    // JSON-LD Article schema — boosts SERP rich results.
    injectJsonLd({
      "@context": "https://schema.org",
      "@type": "Article",
      headline: post.title,
      description: post.meta_description || post.excerpt || "",
      image: post.cover_url ? [post.cover_url] : undefined,
      datePublished: post.published_at,
      dateModified: post.updated_at,
      author: { "@type": "Person", name: post.author_name || "Allsale Events" },
      publisher: {
        "@type": "Organization",
        name: "Allsale Events",
        logo: { "@type": "ImageObject", url: `${window.location.origin}/logo192.png` },
      },
      mainEntityOfPage: `${window.location.origin}/blog/${post.slug}`,
    });
    return () => removeJsonLd();
  }, [post]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-16">
        <div className="h-6 w-32 rounded animate-pulse mb-6" style={{ background: "var(--border)" }} />
        <div className="h-10 rounded animate-pulse mb-4" style={{ background: "var(--border)" }} />
        <div className="h-64 rounded-xl animate-pulse" style={{ background: "var(--border)" }} />
      </div>
    );
  }

  if (!post) {
    return (
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-24 text-center" data-testid="blog-not-found">
        <h1 className="text-2xl font-serif mb-3" style={{ color: "var(--text)" }}>Post not found</h1>
        <p className="text-sm mb-6" style={{ color: "var(--text-dim)" }}>The link might be old or the post was unpublished.</p>
        <button onClick={() => navigate("/blog")} className="btn-primary" data-testid="blog-back-btn">
          <ArrowLeft size={14} /> Back to blog
        </button>
      </div>
    );
  }

  return (
    <article className="max-w-3xl mx-auto px-4 sm:px-6 py-12" data-testid="blog-post-page">
      <Link to="/blog" className="text-xs inline-flex items-center gap-1 mb-8" style={{ color: "var(--accent)" }} data-testid="blog-back-link">
        <ArrowLeft size={12} /> The Allsale Journal
      </Link>
      <header>
        <div className="flex items-center flex-wrap gap-3 text-xs" style={{ color: "var(--text-dim)" }}>
          <Calendar size={12} />
          <time dateTime={post.published_at}>{fmt(post.published_at)}</time>
          {post.author_name && <span>· by {post.author_name}</span>}
          {post.tags?.length > 0 && (
            <span className="inline-flex items-center gap-1">
              <TagIcon size={12} />
              {post.tags.join(", ")}
            </span>
          )}
        </div>
        <h1 className="mt-3 font-serif" style={{ fontSize: "clamp(2.25rem, 5vw, 3.25rem)", lineHeight: 1.05, color: "var(--text)" }}>
          {post.title}
        </h1>
        {post.excerpt && (
          <p className="mt-4 text-lg" style={{ color: "var(--text-muted)" }}>{post.excerpt}</p>
        )}
      </header>

      {post.cover_url && (
        <img
          src={post.cover_url}
          alt={post.title}
          loading="lazy"
          className="mt-8 w-full rounded-2xl border"
          style={{ aspectRatio: "16/9", objectFit: "cover", borderColor: "var(--border)" }}
        />
      )}

      <div
        className="prose-allsale mt-10"
        dangerouslySetInnerHTML={{ __html: sanitizeRichHtml(post.body_html || "") }}
        data-testid="blog-body"
      />

      {related.length > 0 && (
        <section className="mt-16 pt-10 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="text-xs uppercase tracking-[0.32em] mb-4" style={{ color: "var(--accent)" }}>
            Keep reading
          </div>
          <div className="grid sm:grid-cols-3 gap-4">
            {related.map((r) => (
              <Link key={r.slug} to={`/blog/${r.slug}`} className="block rounded-xl border p-4 transition hover:translate-y-[-2px]" style={{ borderColor: "var(--border)" }} data-testid={`related-${r.slug}`}>
                <div className="text-xs" style={{ color: "var(--text-dim)" }}>{fmt(r.published_at)}</div>
                <div className="mt-1 font-serif" style={{ fontSize: "1.125rem", color: "var(--text)" }}>{r.title}</div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </article>
  );
}

function fmt(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  } catch { return ""; }
}

function setMeta(name, content, opts = {}) {
  const attr = opts.property ? "property" : "name";
  let el = document.head.querySelector(`meta[${attr}="${name}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function setCanonical(href) {
  let el = document.head.querySelector('link[rel="canonical"]');
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", "canonical");
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

const JSON_LD_ID = "allsale-blog-jsonld";
function injectJsonLd(obj) {
  removeJsonLd();
  const el = document.createElement("script");
  el.type = "application/ld+json";
  el.id = JSON_LD_ID;
  el.textContent = JSON.stringify(obj);
  document.head.appendChild(el);
}
function removeJsonLd() {
  const existing = document.getElementById(JSON_LD_ID);
  if (existing) existing.remove();
}
