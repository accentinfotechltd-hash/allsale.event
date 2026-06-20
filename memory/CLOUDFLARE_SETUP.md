# Cloudflare in front of Railway — setup playbook

**Why bother:** Railway's free tier doesn't include WAF / DDoS protection / bot mitigation. Putting Cloudflare in front gives you all three for free, plus aggressive caching for your static-ish endpoints (like `/api/events`).

**Total time:** ~25-30 minutes (most of it waiting for DNS propagation).

---

## Step 1 — Sign up for Cloudflare (5 min)

1. Go to https://dash.cloudflare.com/sign-up — free tier is enough.
2. Verify your email.

## Step 2 — Add `allsale.events` to Cloudflare (5 min)

1. Dashboard → **+ Add site**.
2. Enter `allsale.events` → choose **Free** plan → Continue.
3. Cloudflare scans your existing DNS records (Vercel + Railway). Review them — most should auto-import.
4. **Critical**: for the Railway record (likely `api` or whatever subdomain you use to point at `allsaleevent-production.up.railway.app`), set the **proxy status to "Proxied"** (orange cloud ⛅). For Vercel records, you can also set them to Proxied — Vercel is Cloudflare-compatible.

## Step 3 — Change nameservers at your domain registrar (10 min + DNS propagation)

1. Cloudflare gives you 2 nameservers (e.g. `dora.ns.cloudflare.com`, `kirk.ns.cloudflare.com`).
2. Log in to your domain registrar (GoDaddy / Namecheap / Cloudflare Registrar / wherever you bought `allsale.events`).
3. Find the DNS / Nameservers section → change from your current ones to the two Cloudflare-supplied ones.
4. Save. DNS propagation takes 5-60 minutes globally (usually < 10 min).
5. Cloudflare will email you when activation is complete.

## Step 4 — Add Railway custom domain (5 min)

If you don't already have a custom domain pointing at Railway (currently using `allsaleevent-production.up.railway.app` directly), do this:

1. **Railway** → service → **Settings → Networking → Custom Domain** → enter `api.allsale.events`.
2. Railway gives you a `CNAME` value (something like `xxx.up.railway.app`).
3. **Cloudflare** → DNS → Add Record:
   - Type: `CNAME`
   - Name: `api`
   - Target: the value Railway gave you
   - Proxy status: **Proxied** (orange cloud)
4. Update your **Vercel env var** `REACT_APP_BACKEND_URL` → `https://api.allsale.events` (instead of the Railway URL directly).
5. Redeploy frontend on Vercel.

**Why route through `api.allsale.events` instead of the Railway URL directly?** So you can later swap Railway for another host (Fly.io, Render, etc.) without redeploying your frontend or updating any other env. It also keeps requests inside the Cloudflare proxy.

## Step 5 — Turn on the security features (5 min)

In the Cloudflare dashboard for `allsale.events`:

1. **Security → Bots** → enable **Bot Fight Mode** (free) or upgrade to Super Bot Fight Mode if you start getting hammered.
2. **Security → WAF → Tools → Rate limiting rules** → Add a free rate-limit rule:
   - Path: `/api/auth/login`
   - Limit: 5 requests per minute per IP
   - Action: Block for 10 minutes
   - This stops brute-force login attempts cold.
3. **Speed → Optimization → Auto Minify** → enable HTML, CSS, JS (just a small extra bandwidth save).
4. **Caching → Configuration → Browser Cache TTL** → set to `Respect Existing Headers` (don't override what Vercel/Railway already send).
5. **SSL/TLS → Overview** → set to **Full (strict)**. Critical — anything less can break your HTTPS or open MITM risk.

## Step 6 — Verify (2 min)

```bash
# Should now see CF-RAY header (Cloudflare cache identifier)
curl -sI https://allsale.events/ | grep -iE "cf-ray|server"
# Expected: server: cloudflare, cf-ray: ...
```

If you see `server: cloudflare`, you're proxied. 🎉

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| 521 / 522 errors after switching DNS | Origin (Railway) blocking Cloudflare's IPs | Railway → Settings → Networking → confirm no IP restrictions. Free tier doesn't have any by default. |
| HTTPS broken / "too many redirects" | SSL mode set to "Flexible" | Switch to **Full (strict)** in SSL/TLS → Overview. |
| WebSocket chat broken (admin↔organizer) | Cloudflare not forwarding WS by default for some plans | Free plan DOES support WS. If broken: Cloudflare → Network → WebSockets → ON. |
| Vercel SSL warning | Vercel has its own SSL and conflicts with proxy | Either: (a) leave Vercel records "DNS only" (grey cloud), or (b) follow Cloudflare's "Proxy Vercel" guide. |

## Test after setup

1. Visit `https://allsale.events/` — should look identical, just feel faster.
2. Test admin login — should work.
3. Open admin → Organizer chat → send a message → confirm WS still delivers live (this is the key test; if WS breaks here, do the "WebSockets ON" toggle in Cloudflare).
4. Try to brute-force login (run `for i in {1..10}; do curl -X POST .../api/auth/login -d '{...}'; done`) — should get blocked after 5 attempts.

---

**Total cost: $0** for everything above on Cloudflare's Free plan.
