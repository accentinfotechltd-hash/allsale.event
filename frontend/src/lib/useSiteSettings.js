/**
 * useSiteSettings — fetches /api/site-settings once, caches in localStorage
 * so the About / Contact / Footer pages render their last-known content
 * instantly, then revalidate in the background.
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";

const STORAGE_KEY = "allsale_site_settings_v1";

const FALLBACK = {
  about: {
    hero_eyebrow: "About us",
    hero_title: "Live experiences,\nsold the human way.",
    hero_subtitle: "Allsale Events is a tickets & events platform built in Auckland.",
    story_title: "Why we built it",
    story_body: "",
  },
  contact: {
    hero_eyebrow: "Contact us",
    hero_title: "Let's talk.",
    hero_subtitle: "Drop us a note — a real human will reply within 24 hours.",
    email: "support@allsale.events",
    phone: "+64 9 555 0100",
    address: "Auckland, New Zealand",
    organizer_note: "",
  },
};

export default function useSiteSettings() {
  const [data, setData] = useState(() => {
    try {
      const cached = localStorage.getItem(STORAGE_KEY);
      return cached ? JSON.parse(cached) : FALLBACK;
    } catch {
      return FALLBACK;
    }
  });

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const { data: fresh } = await api.get("/site-settings");
        if (!active) return;
        setData(fresh);
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(fresh)); } catch { /* noop */ }
      } catch { /* keep cached / fallback */ }
    })();
    return () => { active = false; };
  }, []);

  return data;
}
