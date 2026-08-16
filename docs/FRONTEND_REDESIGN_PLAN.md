# BCIP Frontend Redesign Plan

**Version:** 1.0
**Scope:** Visual system for the React (Vite) client — Organization Portal and Public Verification Portal
**Corresponding SRS:** §4.1 User Interfaces, §5.3 Usability, NFR-2.1

---

## 1. Why redesign

The current interface works but reads as an unstyled prototype. Three concrete problems:

| Problem | Evidence | Consequence |
|---|---|---|
| Default framework palette | `--color-primary-600: #2563eb` — Tailwind's stock blue | Looks like every bootstrapped demo; no identity |
| Font declared but never loaded | `font-family: 'Inter'` with no `@font-face` or link | Silently falls back to a system font; the intended design was never seen |
| No dark mode | Single `:root` block only | Looks broken on a dark-themed OS |
| Status is text-only | Pills carry colour but little weight | The single most important signal on the dashboard does not read at a glance |

For a project whose entire subject is **trust and authenticity**, an interface that looks provisional undermines the argument. A verification page that an employer is asked to believe should look institutional, not like a side project.

---

## 2. Design direction

**Subject world:** credentials, registries, seals, official records. Not fintech, not SaaS.

The visual language deliberately matches the project's own architecture, so the documentation and the application read as one system:

- **Teal** = off-chain, the application, the trusted-good state
- **Bronze** = on-chain, the blockchain, the immutable anchor
- **Red** = tamper and failure, used sparingly so it retains force

This is not decoration. A user who learns that bronze means "blockchain" on the certificate detail page carries that reading to the verification page.

### Colour

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` | `#F5F6F3` | `#0F1413` | Page ground — cool grey-green, biased toward the accent, not a default grey |
| `--surface` | `#FFFFFF` | `#161C1A` | Cards, table, inputs |
| `--ink` | `#161B19` | `#E9EDEA` | Primary text |
| `--muted` | `#5B6662` | `#8D9894` | Secondary text, labels |
| `--line` | `#DCE0DA` | `#2C3532` | Borders, rules |
| `--accent` | `#0B6B5F` | `#4FC9B6` | Brand, primary action, VALID |
| `--chain` | `#8A5A0B` | `#DFA53E` | Anything blockchain: hashes, tx links, anchors |
| `--danger` | `#A23829` | `#EE8A79` | REVOKED, FAILED, TAMPERED |
| `--warn` | `#8A6D3B` | `#C9A24E` | EXPIRED |

Both themes are defined at token level. The bare `:root` carries the complete light palette; `prefers-color-scheme: dark` and `[data-theme="dark"]` redefine only tokens. No component styles colour inside a media query.

### Typography

Three roles, each doing real work — and every stack resolves to a font actually present on the machine, so nothing falls back silently:

- **Display** — `"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif`
  Page titles and the brand mark. A serif signals *document* and *record*, which is what a certificate is. Deliberately not the sans-everywhere default.
- **UI** — `"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif`
  All controls, table content, body copy. Native on the target machine, so it renders as intended.
- **Mono** — `"Cascadia Mono", Consolas, ui-monospace, "SF Mono", Menlo, monospace`
  Certificate IDs, hashes, wallet addresses, status pills. These are machine identifiers that get read character by character and compared — proportional type is the wrong tool for them.

### Layout

- App shell with a fixed top bar: brand, signed-in organisation, sign out. Content capped at 1180px.
- Cards: 1px border, 6px radius, near-invisible shadow. Restraint over `rounded-2xl` and drop shadows.
- Tables: no zebra striping; a hover state and a hairline rule per row. `tabular-nums` on dates and IDs so columns align.
- Forms: label above field, 2px focus ring in the accent, errors inline beneath the field.

### One signature detail

Page titles sit above a **seal rule** — a short solid accent segment running into a full-width hairline. It echoes the engraved border of a printed certificate, costs two CSS rules, and appears nowhere else. That is the page's one flourish; everything around it stays quiet.

### Explicitly avoided

Purple/blue gradient heroes, giant centred hero blocks, emoji as section markers, `rounded-lg` on everything, Inter/Space Grotesk as the safe default, accent bars on rounded cards, and animation for its own sake.

---

## 3. Implementation strategy

**Rewrite the CSS layer; leave the components alone.**

The UI components (`Button`, `Card`, `Input`, `Table`, `StatusPill`) are thin wrappers that emit stable class names. Every class in `components.css` is already referenced by the pages. So the entire redesign lands by replacing two files:

```
src/styles/tokens.css       ← new design tokens, both themes
src/styles/components.css   ← every component restyled
```

This means:
- No page logic is touched, so no behaviour can regress
- No API calls, state, or routing change
- The diff is reviewable as "styling only"

Small `.tsx` changes are limited to structure the CSS cannot add:

| File | Change | Reason |
|---|---|---|
| `AuthLayout.tsx` | Show the signed-in organisation name in the bar | Users need to know which account they are in |
| `PublicLayout.tsx` | Restructured header, footer note | Public page needs to look independent and official |
| `StatusPill.tsx` | Add the `UNVERIFIED` case | Backend returns it; the CSS class was missing |

---

## 4. Status design

The dashboard is scanned, not read. Status must be legible in peripheral vision, so each state differs in **colour, border weight and label** — never colour alone, which fails for colour-blind users and in greyscale print.

| Status | Treatment | Meaning to the user |
|---|---|---|
| `PENDING` | Neutral, dashed border | Working on it — not final |
| `VALID` | Teal, solid | Confirmed and anchored |
| `EXPIRED` | Muted amber, solid | Genuine but out of date |
| `REVOKED` | Red, solid | Cancelled by the issuer |
| `FAILED` | Red, dashed | Something broke — action needed |
| `TAMPERED` | Red, heavy border | Do not trust |
| `NOT_FOUND` | Neutral outline | No such certificate |
| `UNVERIFIED` | Neutral outline | Could not reach the chain |

`PENDING` and `FAILED` use dashes because both are *transient* — the dash reads as "not settled". `TAMPERED` gets the heaviest border because it is the one state that must never be mistaken for anything else.

---

## 5. Accessibility

- All text meets WCAG AA contrast in both themes.
- Focus is always visible: 2px accent outline with offset, never `outline: none`.
- Status conveyed by icon + label + shape, not colour alone.
- `prefers-reduced-motion` disables transitions.
- Tables use real `<th>` elements; inputs are bound to labels via `htmlFor`.

---

## 6. Out of scope

Deliberately not part of this redesign, and tracked separately:

1. **Session persistence** — refreshing `/dashboard` logs you out, because `ProtectedRoute` checks only the in-memory token and nothing attempts a silent refresh on mount. This is a functional bug, not a styling one.
2. **Auth screens missing the `email` field** — `verify-email`, `verify-password-reset` and `reset-password` now require it server-side. Those forms will 400 until updated.
3. **Certificate detail polling** — a `PENDING` certificate does not update until the page is reloaded.

Items 1 and 2 make the application look broken regardless of how it is styled, and should be fixed next.

---

## 7. Acceptance criteria

- [ ] No page renders with an unstyled or fallback-font element
- [ ] Every screen is legible in light and dark themes
- [ ] Certificate IDs, hashes and addresses render in mono and are selectable
- [ ] The dashboard status column is scannable without reading labels
- [ ] Keyboard tab order is visible on every interactive element
- [ ] No horizontal page scroll at 360px width
- [ ] `npm run build` completes with no TypeScript errors

---

*End of plan*
