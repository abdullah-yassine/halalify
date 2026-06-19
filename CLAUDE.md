# Halalify — Project Spec

This is the source-of-truth spec for Claude Code. Read this fully before writing any code. It captures product scope, architecture decisions, and rationale so decisions already made aren't re-litigated.

---

## 1. What this app is

Halalify is an iOS app that lets users scan a product's barcode and instantly see whether it's **Halal**, **Haram**, or **Doubtful**, based on its ingredients and (where available) certification data.

**Target market:** United States and Europe (Western Muslim consumers). This matters because:
- Open Food Facts has strong data density in this market (unlike MENA/Gulf regions).
- Western packaged food labeling is dense with ambiguous/animal-adjacent additives (gelatin, mono/diglycerides, L-cysteine, natural flavors) because manufacturers aren't labeling for a halal-conscious audience. The "Doubtful" classification carries real product weight here.
- Recognized certification bodies for this market: **IFANCA, HMS (Halal Monitoring Services), HFSAA (Halal Food Standards Alliance of America), JAKIM** (for imported/international products).

This is a sibling project to the developer's other app, **Al-Hayy** (a hyperlocal MENA neighborhood app), but Halalify is a fully separate codebase, audience, and infrastructure — do not conflate the two or assume shared backend.

---

## 2. MVP scope (v1) vs later (v2+)

### v1 (build this first, end to end, before anything else)
- Camera barcode scan → ingredient lookup → Halal/Haram/Doubtful verdict
- Manual barcode entry fallback
- Verdict screen showing **which specific ingredient(s)** triggered a Haram/Doubtful flag, in plain language
- Scan history (local, per-user)
- Sign in with Apple (native auth, our own backend issues session/JWT after Apple verifies identity — see Section 6)
- One-time Open Food Facts data import (no recurring sync yet — see Section 5)
- In-app disclaimer: informational guidance only, not a substitute for verified certification; users should independently verify for strict dietary needs. Must be visible on first launch and on every "Doubtful" verdict screen.

### v2+ (do not build until v1 works end to end)
- Certification/brand database expansion (this grows over time, starts mostly empty in v1)
- Community-submitted corrections/reports + moderation
- Community voting on Doubtful items
- Photo upload for products missing from Open Food Facts
- Madhab-aware strictness settings (configurable strictness level per user)
- Personal "avoid list" for specific additives/allergens regardless of halal status
- "Halal alternatives nearby" suggestions when a scan is Haram/Doubtful
- Browse-by-category discovery (not just scan-driven)
- Recurring automated Open Food Facts sync pipeline (Celery + Celery Beat)
- Push notifications (APNs)

Do not build v2 features into the schema or API prematurely. Keep v1 lean.

---

## 3. Classification engine — the core logic

This is the most important and hardest part of the app. The algorithm:

```
for each ingredient in product.ingredients:
    if ingredient in haram_list: return HARAM (cite the specific ingredient + reason)
    if ingredient in doubtful_list: mark as doubtful_candidate

if product.brand has active certification (in certifications table): return HALAL (cite certifying body)
elif doubtful_candidates is empty: return HALAL
else: return DOUBTFUL (list which ingredient(s) triggered it, and plain-language reason for each)
```

### Three ingredient categories
1. **Clearly Haram** — pork and pork derivatives (lard, pork gelatin, pork enzymes), alcohol as a deliberate ingredient (not trace/cooked-off), blood, carnivorous animal byproducts. Finite, well-known list.
2. **Clearly Halal** — plant-based ingredients, most synthetic additives, anything explicitly certified. Default bucket once Haram/Doubtful are excluded.
3. **Doubtful (ambiguous)** — finite, documented list. Seed examples:
   - Gelatin (pork/beef/fish — source usually unstated on label)
   - Mono- and diglycerides / emulsifiers (E471 etc. — plant or animal source unstated)
   - L-cysteine (E920 — often from feathers/hair, sometimes synthetic)
   - Natural flavors / vanilla extract (often alcohol-based)
   - Enzymes / rennet (microbial, plant, or animal — relevant for cheese)
   - Carmine / cochineal (insect-derived — scholarly disagreement on permissibility)
   - Whey (depends on rennet source used)

### Data tables needed
- **Ingredient classification table**: ingredient name/E-number → category (Haram/Halal/Doubtful) → plain-language reason. Seed by hand (~30-50 entries) from published halal-ingredient guides (IFANCA, JAKIM, academic sources) before writing the classifier logic against it.
- **Certification table**: brand/product → certifying body → certified (bool) → source/verification link. Starts mostly empty in v1 — this is what resolves Doubtful cases over time, grows via v2 community contributions.

### Failure mode philosophy
When uncertain, default to **Doubtful**, never default to Halal. Over-flagging as Doubtful is the safe failure mode. Under-flagging (calling something Halal when it isn't) is the dangerous one and must be avoided even at the cost of being less "useful" early on.

---

## 4. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| iOS frontend | Swift / SwiftUI | Native iOS app, camera barcode scanning (AVFoundation / VisionKit) |
| Backend | Django (Python) + Django REST Framework | Business logic, classification engine, API |
| Database | PostgreSQL | Source of truth. Indexed barcode lookup is the core query pattern — single-digit ms at any scale we'll hit early on |
| Cache | Redis | In front of Postgres for hot/repeat product lookups. Pattern: scan → check Redis → miss → query Postgres (indexed) → backfill Redis |
| Background jobs (v2, not v1) | Celery + Celery Beat | For the eventual recurring Open Food Facts sync pipeline. Not needed for v1's one-time import |
| Image/file storage (if needed) | S3-compatible (AWS S3 or Cloudflare R2) | For any product photos, v2+ |
| Hosting | Railway | Chosen over Render and Supabase. Usage-based pricing (~$10-15/month expected at low traffic), bundles Postgres + Redis under one usage-based bill. Start here directly (no need for Render free-tier detour) |
| Auth | Sign in with Apple | See Section 6 |

### Explicitly rejected, do not revisit without a new decision
- **Supabase**: would require replacing Django entirely with Supabase's auto-generated API/client SDKs — architecture conflict with the Django decision above. Also not cheaper than Railway once past free tier (~$25/month Pro vs ~$10-15/month Railway).
- **Vercel**: irrelevant — there is no web frontend to deploy. The iOS app ships via Xcode/App Store, not Vercel. Only relevant if a companion web/marketing site is built later.
- **MongoDB**: Open Food Facts ships data in a Mongo-style dump, but that's just their *distribution* format. We transform it into our own relational schema on import; we don't need Mongo's schema flexibility since our schema is fixed and known (barcode → product → classification).

---

## 5. Open Food Facts data strategy

**Decision: Option B — self-hosted local copy**, not live API calls per scan, and not a full global mirror.

- Download Open Food Facts data dump (JSON/CSV export), filtered/scoped to relevant categories and US/Europe market relevance (not the entire global dataset).
- Transform into our own Postgres schema on import (do not keep their raw Mongo-style schema).
- **v1: one-time import only.** Get the core scan → classify flow working end to end before building any sync automation.
- **v2: recurring sync pipeline** (Celery + Celery Beat) to keep data fresh — explicitly deferred, do not build prematurely. When built, it must avoid clobbering our own enrichments (halal/haram classifications, certification data) that don't exist in OFF's source data.

---

## 6. Auth

- **Sign in with Apple**, native — required for App Store approval given we'd otherwise need it as soon as any other social login exists, and it's the natural fit for an iOS-only app.
- Our own Django backend issues and manages sessions/JWTs after verifying the Apple identity token. We are not using Supabase Auth or any third-party auth-as-a-service — auth is handled in our own Django backend, consistent with the rest of the stack decision.

---

## 7. API shape (sketch — finalize before iOS networking code is written)

Suggested REST endpoints (Django REST Framework):

- `GET /api/products/{barcode}/` → product info + ingredients + classification verdict + reason
- `POST /api/scans/` → log a scan to the authenticated user's history
- `GET /api/scans/history/` → authenticated user's scan history
- `POST /api/auth/apple/` → exchange Apple identity token for our session/JWT
- v2 (do not build yet): `POST /api/reports/`, `GET /api/products/{barcode}/alternatives/`

---

## 8. Legal / trust considerations

- This app provides automated/inferred guidance, not verified certification, for many products (especially Doubtful ones). That's a real-world risk surface for a food-classification app — not legal advice, just a product requirement:
- **Disclaimer required in-app**: visible on first launch and on every Doubtful verdict screen. Suggested language: "Halalify provides informational guidance based on available ingredient data. For products marked Doubtful or for strict dietary requirements, please verify independently with the manufacturer or a certifying body."
- Always show **which ingredient triggered a verdict** and **why** — never give an unexplained verdict. This is both a trust feature and a risk-mitigation feature.

---

## 9. Security requirements (non-negotiable, build in from day one)

Security is not a v2 concern. Build the Django backend with these in place from the first endpoint, not retrofitted later.

### SQL injection
- Use the Django ORM for all queries. Never use raw SQL with string formatting/concatenation.
- If raw SQL is ever unavoidable, use parameterized queries only (`cursor.execute(query, [params])`), never f-strings or `.format()` into SQL.

### Rate limiting
- Apply rate limiting at the API level (e.g. `django-ratelimit` or DRF throttling classes) on all endpoints, especially:
  - Auth endpoints (`/api/auth/apple/`) — protect against brute force/abuse
  - Product lookup (`/api/products/{barcode}/`) — protect against scraping the enriched classification dataset (this is our work product, not just raw Open Food Facts data)
  - Scan logging (`/api/scans/`) — protect against spam/abuse
- Consider both per-IP and per-authenticated-user rate limits.

### Auth & token handling
- JWT/session tokens must have reasonable expiration; implement refresh token rotation.
- On iOS: store tokens in Keychain, never UserDefaults or plain storage.
- Validate Apple identity tokens server-side properly (signature verification against Apple's public keys, audience/issuer checks) — never trust client-asserted identity alone.

### Input validation
- Validate barcode format strictly before it touches the DB or triggers a lookup.
- Any future user-submitted text (v2 community reports) must be validated and sanitized before storage and before rendering anywhere (XSS prevention if any web surface ever exists).

### Secrets management
- No secrets (DB credentials, Apple auth keys, API keys) hardcoded or committed to git, ever.
- Use environment variables via Railway's secret/env management.
- Add a `.env.example` (no real values) and ensure `.env` is gitignored from the first commit.

### Django production hardening
- `DEBUG = False` in production, always — this is a common and serious real-world leak (exposes stack traces, settings, internals).
- `ALLOWED_HOSTS` explicitly set to actual production domain(s), not wildcarded.
- Enable Django's security middleware: `SecurityMiddleware`, HSTS settings, `SECURE_SSL_REDIRECT = True`, secure cookie flags (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`).
- `SECRET_KEY` must be a real generated secret pulled from env, not the Django default placeholder.

### Transport security
- HTTPS only, everywhere. No endpoint should ever be reachable over plain HTTP in production (Railway provides this by default — verify it's enforced, not just available).

### CORS
- Configure CORS (`django-cors-headers`) to only accept requests from the actual iOS app context, not wildcard `*` origins.

### Database access control
- App's Postgres connection should use a least-privilege DB user/role scoped to only what the app needs, not a superuser/admin connection string.

### Dependency hygiene
- Periodically audit Python dependencies for known CVEs (`pip audit` or equivalent). Pin versions; don't float on `latest` in production requirements.

### Data minimization & privacy posture
- Store only the user data actually needed (scan history, auth identity). Avoid collecting anything extra "just in case."
- Given the Europe market target, build with GDPR-friendly posture in mind even if not formally required yet: ability to delete a user's data on request, no unnecessary retention.

### Logging
- Never log sensitive data (tokens, full auth payloads, PII) in plaintext logs.

---

## 10. Explicitly out of scope / deferred decisions

- Recurring OFF sync automation (v2)
- Certification database beyond a minimal seed (v2, grows over time)
- Community features of any kind (v2)
- Madhab-aware strictness settings (v2)
- Any web frontend (not currently planned; Vercel/Next.js would only become relevant if this changes)
- Push notifications (v2)

---

## 11. Related context (do not build into this app, just background)

The developer is also building **Al-Hayy**, a separate hyperlocal neighborhood app for Saudi Arabia/MENA (Django backend, Swift/SwiftUI iOS, PostGIS, AWS Bahrain, PDPL compliance). Halalify is unrelated in audience and infra (Railway, not AWS) — do not assume shared backend, shared region, or shared codebase unless explicitly instructed otherwise in the future.
