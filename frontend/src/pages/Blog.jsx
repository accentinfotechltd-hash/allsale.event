import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Calendar, ArrowRight, Tag as TagIcon } from "lucide-react";
import api from "@/lib/api";

/**
 * Blog index — public-facing list of published posts.
 *
 * Why a blog matters: every published post is a permanent landing page
 * indexed by Google. Targeted "how to host a [type] event in [city]" posts
 * become long-tail traffic that converts to organizer signups over months.
 *
 * The page also injects basic SEO meta tags (title + description + canonical
 * + OG) directly into <head> via `useEffect` so we don't need react-helmet.
 */
export default function Blog() {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const { data } = await api.get("/blog?limit=24");
        if (live) setPosts(data.items || []);
      } catch (_e) {
        if (live) setPosts([]);
      } finally {
        if (live) setLoading(false);
      }
    })();
    return () => { live = false; };
  }, []);

  useEffect(() => {
    document.title = "Blog — Allsale Events";
    setMeta("description", "Guides, stories and playbooks for event organizers and ticket-buyers in New Zealand. Allsale Events blog.");
    setMeta("og:title", "Allsale Events Blog", { property: true });
    setMeta("og:description", "Guides, stories and playbooks for event organizers in New Zealand.", { property: true });
    setCanonical(`${window.location.origin}/blog`);
  }, []);

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-12" data-testid="blog-index-page">
      <header className="mb-12">
        <div className="text-xs uppercase tracking-[0.32em]" style={{ color: "var(--accent)" }}>
          The Allsale Journal
        </div>
        <h1 className="mt-3 font-serif" style={{ fontSize: "clamp(2.5rem, 5vw, 3.75rem)", lineHeight: 1.05, color: "var(--text)" }}>
          Stories, guides &amp; playbooks for the live-events world.
        </h1>
        <p className="mt-4 max-w-2xl text-base" style={{ color: "var(--text-dim)" }}>
          Tactical advice for organizers, behind-the-scenes from venues, and
          smart picks for ticket-buyers. New stories every week.
        </p>
      </header>

      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {[0,1,2,3,4,5].map((i) => (
            <div key={i} className="rounded-2xl border animate-pulse" style={{ borderColor: "var(--border)", height: 320 }} />
          ))}
        </div>
      ) : posts.length === 0 ? (
        <div className="rounded-2xl border py-16 text-center" style={{ borderColor: "var(--border)" }} data-testid="blog-empty">
          <div className="text-base" style={{ color: "var(--text)" }}>No posts yet — check back soon.</div>
          <div className="text-sm mt-2" style={{ color: "var(--text-dim)" }}>We&apos;re cooking up the first one.</div>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="blog-grid">
          {posts.map((p) => <PostCard key={p.slug} post={p} />)}
        </div>
      )}
    </div>
  );
}

function PostCard({ post }) {
  return (
    <Link
      to={`/blog/${post.slug}`}
      className="group block rounded-2xl border overflow-hidden transition hover:translate-y-[-2px]"
      style={{ borderColor: "var(--border)", background: "var(--card-bg, transparent)" }}
      data-testid={`blog-card-${post.slug}`}
    >
      <div
        className="aspect-[16/10] w-full bg-cover bg-center"
        style={{
          backgroundImage: post.cover_url ? `url("${post.cover_url}")` : "linear-gradient(135deg,#0F2A3A,#1F4459)",
        }}
      />
      <div className="p-5">
        <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-dim)" }}>
          <Calendar size={12} />
          <time dateTime={post.published_at}>{fmt(post.published_at)}</time>
          {post.tags?.[0] && (
            <span className="inline-flex items-center gap-1 ml-2">
              <TagIcon size={12} />
              {post.tags[0]}
            </span>
          )}
        </div>
        <h2 className="mt-2 font-serif group-hover:underline" style={{ fontSize: "1.5rem", lineHeight: 1.15, color: "var(--text)" }}>
          {post.title}
        </h2>
        <p className="mt-3 text-sm line-clamp-3" style={{ color: "var(--text-muted)" }}>
          {post.excerpt}
        </p>
        <div className="mt-4 inline-flex items-center gap-1 text-sm font-medium" style={{ color: "var(--accent)" }}>
          Read story <ArrowRight size={14} />
        </div>
      </div>
    </Link>
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
