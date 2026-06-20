/**
 * Terms — public Terms of Service page.
 *
 * Intentionally NOT a wall of legal text. Plain English, with the IP /
 * copyright section called out so it's enforceable: if a competitor scrapes
 * the site or rebuilds it visually, the explicit prohibition here gives us
 * grounds to send a takedown notice to their host / Cloudflare / Vercel.
 */
import { usePageMeta } from "@/lib/usePageMeta";

export default function Terms() {
  usePageMeta({
    title: "Terms of Service",
    description: "Terms governing the use of Allsale Events — the event-ticketing platform.",
  });

  return (
    <div className="max-w-3xl mx-auto px-4 py-12 lg:py-16" data-testid="terms-page">
      <h1 className="serif text-4xl lg:text-5xl mb-2">Terms of Service</h1>
      <p className="text-sm mb-10" style={{ color: "var(--text-dim)" }}>
        Last updated: 19 February 2026
      </p>

      <Section title="1. The basics">
        <p>
          Allsale Events (&ldquo;we&rdquo;, &ldquo;us&rdquo;, &ldquo;the
          platform&rdquo;) is an event-ticketing service operated from New
          Zealand. By using the site at <code>allsale.events</code> &mdash;
          whether to browse, buy tickets, or list events &mdash; you agree to
          these Terms. If you don&apos;t agree, please don&apos;t use the
          service.
        </p>
      </Section>

      <Section title="2. Accounts">
        <p>
          You&apos;re responsible for keeping your password secure. Don&apos;t
          share it. Notify us immediately if you suspect unauthorized use of
          your account at <a href="mailto:support@allsale.events">support@allsale.events</a>.
        </p>
      </Section>

      <Section title="3. Buying tickets">
        <p>
          All sales are between you (the buyer) and the event organizer.
          Allsale Events facilitates the transaction and provides the e-ticket
          + QR code, but the organizer is responsible for the event itself.
          Refund eligibility depends on the organizer&apos;s refund policy
          shown on each event page.
        </p>
      </Section>

      <Section title="4. Listing events (organizers)">
        <p>
          You may list events on Allsale only for legal, real events you have
          the right to sell tickets to. We reserve the right to remove any
          event or account that violates these terms, NZ law, or applicable
          local law in the event&apos;s country. Platform fees are disclosed
          at checkout and on your organizer dashboard.
        </p>
      </Section>

      <Section title="5. Intellectual property — important">
        <p className="mb-3">
          All content on <code>allsale.events</code> &mdash; including but not
          limited to: source code, design, layout, copy, illustrations, logos,
          icons, the brand name &ldquo;Allsale Events&rdquo;, the seat-map
          interaction system, ticket-protection mechanism, organizer-chat
          workflow, and any compiled JavaScript bundles &mdash; is the
          exclusive property of Allsale Events and is protected by copyright
          and trademark law.
        </p>
        <p className="mb-3">
          You may NOT:
        </p>
        <ul className="list-disc pl-6 space-y-1.5 mb-3">
          <li>
            Reproduce, clone, mirror, or rebuild the site or any substantial
            portion of it &mdash; whether visually, structurally, or in code.
          </li>
          <li>
            Scrape, crawl, or extract content for AI training, dataset
            building, or any other automated purpose. This site&apos;s{" "}
            <code>robots.txt</code> explicitly disallows GPTBot, ClaudeBot,
            PerplexityBot, CCBot and similar agents; respecting it is a
            condition of use.
          </li>
          <li>
            Use the Allsale Events name, brand, or domain in any way that
            implies affiliation without prior written permission.
          </li>
          <li>
            Reverse-engineer the minified production JavaScript bundles to
            rebuild proprietary features (seat-hold atomicity logic, fee
            calculation, ticket protection, boost ranking, etc.) for use in
            a competing service.
          </li>
        </ul>
        <p>
          Violations will result in immediate account termination and may be
          referred to hosting providers (Cloudflare, Vercel, etc.) for
          takedown, and to legal counsel.
        </p>
      </Section>

      <Section title="6. Refunds and cancellations">
        <p>
          Refund policy is set by each organizer and shown on the event page.
          Where the organizer offers Allsale Ticket Protection at checkout
          (DIY markup), buyers may file a claim through their profile and
          claims are reviewed by Allsale admins.
        </p>
      </Section>

      <Section title="7. Privacy">
        <p>
          We collect only what we need to operate the service: your name,
          email, ticket purchases, and basic device info for fraud prevention.
          We don&apos;t sell your data. Payment data is handled by Stripe; we
          never see your card number.
        </p>
      </Section>

      <Section title="8. Limitation of liability">
        <p>
          The platform is provided &ldquo;as is&rdquo;. To the maximum extent
          allowed by law, Allsale Events isn&apos;t liable for damages caused
          by event cancellations, organizer fraud, or third-party service
          outages (Stripe, email delivery, etc.).
        </p>
      </Section>

      <Section title="9. Changes to these terms">
        <p>
          We may update these terms occasionally. Material changes will be
          announced via email and/or a banner on the site. Continued use after
          changes means you accept the updated terms.
        </p>
      </Section>

      <Section title="10. Contact">
        <p>
          Questions, complaints, or takedown requests:{" "}
          <a href="mailto:support@allsale.events" style={{ color: "var(--accent)" }}>
            support@allsale.events
          </a>
        </p>
      </Section>

      <div className="mt-16 pt-8 border-t text-sm" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
        &copy; 2026 Allsale Events. All rights reserved. Unauthorized
        reproduction prohibited.
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="mb-10" data-testid={`terms-section-${title.split(".")[0]}`}>
      <h2 className="serif text-2xl lg:text-3xl mb-3">{title}</h2>
      <div className="space-y-3 leading-relaxed" style={{ color: "var(--text)" }}>
        {children}
      </div>
    </section>
  );
}
