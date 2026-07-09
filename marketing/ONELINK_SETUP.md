# International earnings — Amazon OneLink (Canada + UK)

**Goal:** earn on Canadian & UK clicks, which currently pay **$0**. Our deal
links are already native `amazon.com/dp/ASIN?tag=` URLs — exactly what OneLink
rewrites automatically — and the site already has the injection slot
(`ONELINK_ONETAG` in `src/render_site.py`). So the remaining work is almost
entirely on Amazon's side.

**The one rule that matters:** OneLink will *route* a Canadian/Brit to their
local store regardless, but you **earn nothing from a store until you're
enrolled in that store's Associates program** and it's linked in OneLink.

---

## Checklist

### 1. Enroll in Amazon.ca Associates  (easiest — do first)
- [ ] Go to **associates.amazon.ca**, sign in with your Amazon account, apply.
- [ ] Enter the site (`boardgameblackmarket.com`) and tax info (W-8BEN, same as
      the US one).
- [ ] Record the CA tracking ID once approved.

### 2. Enroll in Amazon.co.uk Associates
- [ ] Go to **affiliate-program.amazon.co.uk**, apply the same way.
- [ ] Record the UK tracking ID once approved.

### 3. Set up OneLink  (from your **US** Associates Central)
- [ ] Associates Central (US) → **Tools → OneLink**.
- [ ] Connect/link your **CA** and **UK** accounts (enter those tracking IDs).
- [ ] If offered, grab the **OneTag script** (Tools → OneLink → "Get OneTag
      Script").

### 4. Hand off to the site
- [ ] Send the OneTag `<script>` snippet to Claude → it drops into
      `ONELINK_ONETAG` and deploys on the next push.
- [ ] If OneLink says routing is **automatic / no script needed**, just say so —
      nothing more to do on the site; it already works on our native links.

---

## Notes
- Approvals can take ~a day per region. Each regional program has an initial
  qualifying-sales window to stay active (check the terms at signup).
- OneLink only routes **native** `amazon.com` / `amzn.to` links — ours qualify;
  never wrap deal links in a third-party shortener or routing breaks.
- Supported stores if you expand later: UK, DE, JP, CA, AU, FR, IT, ES, NL, PL,
  SA, SG, SE.
- The US tag (`carnivalgam06-20`) and US earnings are unaffected — this only
  adds income from non-US visitors who were earning nothing before.
