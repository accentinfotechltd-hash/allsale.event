/**
 * Privacy — public Privacy Policy page.
 *
 * Plain-English account of what we collect, why, where it's stored, who can
 * see it, and the rights NZ Privacy Act 2020 + GDPR (for EU visitors) grant.
 * Pairs with /terms — both linked from the footer and from checkout.
 */
import { usePageMeta } from "@/lib/usePageMeta";

export default function Privacy() {
  usePageMeta({
    title: "Privacy Policy",
    description:
      "How Allsale Events collects, uses and protects your personal data. NZ Privacy Act 2020 + GDPR compliant.",
  });

  return (
    <div className="max-w-3xl mx-auto px-4 py-12 lg:py-16" data-testid="privacy-page">
      <h1 className="serif text-4xl lg:text-5xl mb-2">Privacy Policy</h1>
      <p className="text-sm mb-10" style={{ color: "var(--text-dim)" }}>
        Last updated: 22 February 2026
      </p>

      <Section title="1. Who we are">
        <p>
          Allsale Events (&ldquo;we&rdquo;, &ldquo;us&rdquo;, &ldquo;the
          platform&rdquo;) is an event-ticketing service operated from New
          Zealand. We are the data controller for the personal information you
          share with us at <code>allsale.events</code>. We comply with the New
          Zealand Privacy Act 2020 and, where applicable, the EU General Data
          Protection Regulation (GDPR).
        </p>
      </Section>

      <Section title="2. What we collect">
        <p>We only collect what we need to actually run the platform:</p>
        <ul className="list-disc ml-6 space-y-1.5">
          <li>
            <strong>Account info</strong> — name, email, password hash, role
            (attendee / organizer / partner / admin), profile photo URL.
          </li>
          <li>
            <strong>Booking info</strong> — event ID, ticket tier, quantity,
            price, currency, QR code, and whether the ticket has been scanned.
          </li>
          <li>
            <strong>Payment info</strong> — handled directly by Stripe. We
            store only the booking reference, last 4 digits of the card, and
            payment status. We never see or store your full card number, CVV
            or 3DS credentials.
          </li>
          <li>
            <strong>Communications</strong> — emails we send you (booking
            confirmations, blog updates if subscribed, partner statements) and
            any reply you send back to <code>support@allsale.events</code>.
          </li>
          <li>
            <strong>Technical data</strong> — IP address, browser, device
            type, referrer URL, and pages visited. Used for security
            (brute-force detection) and aggregate analytics only.
          </li>
          <li>
            <strong>Optional data</strong> — if you choose: city for
            location-based event recommendations, favourite categories, and
            organisers you follow.
          </li>
        </ul>
      </Section>

      <Section title="3. Why we collect it">
        <ul className="list-disc ml-6 space-y-1.5">
          <li>
            <strong>To deliver tickets</strong> — without your email we can&apos;t
            send your QR code. Without a booking ID we can&apos;t let you
            through the door.
          </li>
          <li>
            <strong>To prevent fraud</strong> — IPs and device fingerprints
            help us spot card-testing attacks, scalper bot traffic, and
            duplicate QR claims.
          </li>
          <li>
            <strong>To improve the product</strong> — anonymised, aggregated
            usage data (how many people viewed an event, what % completed
            checkout) drives roadmap decisions. We do not sell this data.
          </li>
          <li>
            <strong>To comply with the law</strong> — tax obligations on
            ticket sales (NZ GST), anti-money-laundering checks on payouts,
            and lawful requests from law enforcement.
          </li>
        </ul>
      </Section>

      <Section title="4. Who we share it with">
        <p>We share data only with the third parties we strictly need to run the platform:</p>
        <ul className="list-disc ml-6 space-y-1.5">
          <li>
            <strong>Stripe</strong> — processes your card payment and runs
            organiser payouts. See{" "}
            <a
              href="https://stripe.com/privacy"
              target="_blank"
              rel="noreferrer"
              style={{ color: "var(--accent)" }}
            >
              Stripe&apos;s privacy policy
            </a>
            .
          </li>
          <li>
            <strong>Resend</strong> — delivers our transactional emails
            (booking confirmation, password reset, partner statements).
          </li>
          <li>
            <strong>MongoDB Atlas</strong> — our database host. Data resides
            in encrypted clusters with strict access controls.
          </li>
          <li>
            <strong>Google Analytics (GA4)</strong> — collects anonymised
            pageview data. We have IP anonymisation enabled. You can opt out
            via your browser&apos;s &ldquo;Do Not Track&rdquo; setting.
          </li>
          <li>
            <strong>Event organisers</strong> — for any event you book, the
            organiser sees your name, email, ticket tier and check-in status
            (so they can manage their guest list). They cannot see your
            password, payment info, or bookings on other events.
          </li>
          <li>
            <strong>Law enforcement</strong> — only with a valid court order
            or warrant.
          </li>
        </ul>
        <p>
          <strong>We do not sell your data</strong>, period. We do not run
          ad-network pixels (no Facebook Pixel, no TikTok Pixel) on this site.
        </p>
      </Section>

      <Section title="5. How long we keep it">
        <ul className="list-disc ml-6 space-y-1.5">
          <li>
            <strong>Account info</strong> — until you delete your account
            (request via <code>support@allsale.events</code>), or 5 years of
            inactivity, whichever comes first.
          </li>
          <li>
            <strong>Booking records</strong> — 7 years, to satisfy NZ tax
            record-keeping requirements.
          </li>
          <li>
            <strong>Marketing email subscribers</strong> — until you click
            &ldquo;unsubscribe&rdquo; in any email or visit{" "}
            <a href="/blog/unsubscribe" style={{ color: "var(--accent)" }}>/blog/unsubscribe</a>.
          </li>
          <li>
            <strong>Server logs</strong> — 90 days, then purged.
          </li>
        </ul>
      </Section>

      <Section title="6. Your rights">
        <p>You can, at any time:</p>
        <ul className="list-disc ml-6 space-y-1.5">
          <li>
            <strong>Access</strong> your data — email us and we&apos;ll send
            you a JSON export within 14 days.
          </li>
          <li>
            <strong>Correct</strong> inaccurate data — most fields you can
            edit in <a href="/profile" style={{ color: "var(--accent)" }}>your profile</a>.
          </li>
          <li>
            <strong>Delete</strong> your account and all personal data — email
            <code> support@allsale.events</code>. We&apos;ll keep anonymised
            booking records for the 7-year tax period but strip your name,
            email and IP.
          </li>
          <li>
            <strong>Unsubscribe</strong> from marketing emails — one click in
            any email footer.
          </li>
          <li>
            <strong>Object</strong> to a specific use of your data, or
            complain to the New Zealand Privacy Commissioner at{" "}
            <a
              href="https://www.privacy.org.nz/"
              target="_blank"
              rel="noreferrer"
              style={{ color: "var(--accent)" }}
            >
              privacy.org.nz
            </a>
            .
          </li>
        </ul>
      </Section>

      <Section title="7. Cookies &amp; local storage">
        <p>
          We use a small number of cookies / localStorage entries — all
          essential or first-party:
        </p>
        <ul className="list-disc ml-6 space-y-1.5">
          <li>
            <code>aura_token</code> &mdash; your login session JWT (deleted on
            logout).
          </li>
          <li>
            <code>welcomeSeen_*</code> &mdash; remembers if you&apos;ve
            dismissed the welcome tour.
          </li>
          <li>
            <strong>Stripe</strong> sets cookies on its iframe for fraud
            detection during checkout.
          </li>
          <li>
            <strong>Google Analytics</strong> sets a <code>_ga</code> cookie
            (24-month expiry, anonymous client ID).
          </li>
        </ul>
        <p>
          We don&apos;t use cross-site tracking cookies, retargeting pixels,
          or third-party advertising cookies.
        </p>
      </Section>

      <Section title="8. International transfers">
        <p>
          Our database is hosted in MongoDB Atlas. Stripe, Resend and Google
          Analytics may process data in the United States, EU and other
          jurisdictions. All of these providers offer Standard Contractual
          Clauses or equivalent safeguards under GDPR Article 46.
        </p>
      </Section>

      <Section title="9. Children">
        <p>
          Allsale Events is not directed at children under 16. We don&apos;t
          knowingly collect personal data from children. If you believe a
          minor has signed up, email us and we&apos;ll delete the account.
        </p>
      </Section>

      <Section title="10. Changes to this policy">
        <p>
          We&apos;ll update this page when our practices change. The
          &ldquo;Last updated&rdquo; date at the top tells you when. For
          material changes (new third-party processors, new categories of
          data), we&apos;ll email registered users at least 14 days before
          the change takes effect.
        </p>
      </Section>

      <Section title="11. Contact">
        <p>
          Questions, data access requests, or complaints:{" "}
          <a href="mailto:support@allsale.events" style={{ color: "var(--accent)" }}>
            support@allsale.events
          </a>
        </p>
      </Section>

      <div
        className="mt-16 pt-8 border-t text-sm"
        style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}
      >
        &copy; 2026 Allsale Events. All rights reserved.
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section
      className="mb-10"
      data-testid={`privacy-section-${title.split(".")[0]}`}
    >
      <h2 className="serif text-2xl lg:text-3xl mb-3">{title}</h2>
      <div
        className="space-y-3 leading-relaxed"
        style={{ color: "var(--text)" }}
      >
        {children}
      </div>
    </section>
  );
}
