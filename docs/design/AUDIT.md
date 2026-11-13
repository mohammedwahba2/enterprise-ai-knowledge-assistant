# Design reference audit

Superseded for design purposes by `docs/design/final/` (approved direction A refined). Conducted 2026-11-13 by browsing the live sites in the in-app browser and reading computed styles from the rendered pages. "Observed" = measured or seen in this session. "Interpretation" = my reading of it.

## What was actually accessible

| Source | Result |
|---|---|
| linear.app | Loaded. Observed: dark `#08090A` page, text `#F7F8F8`, **Inter Variable**, H1 56 px at weight **510**. Features page: icon-grid hero with very low-contrast chrome. |
| stripe.com | Loaded. Observed: **sohne-var**, H1 46 px at weight **300** with **−0.92 px** tracking (≈ −2 %). |
| docs.stripe.com | Loaded. Observed: 14 px base size with **26 px line-height** for body paragraphs (a roomy 1.86). |
| raycast.com | Loaded. Observed: `#07080A` background, **Inter**, H1 64 px at weight 600. |
| notion.com | Loaded. Observed: white page, text `rgba(0,0,0,.95)`, Inter-based custom face, H1 ≈ 90 px at weight 600. |
| perplexity.ai (logged out) | Loaded. Observed: left sidebar (New, Computer, Projects, Recents), centered prompt box with a model picker, a teal/graphite dark theme. Logged-out only, so no answer/citation view was seen. |
| glean.com/ai-assistant | Marketing page only (no live product). Observed: large serif-free headline, an **orange/amber gradient hero** and pastel chat screenshots. |
| mobbin.com | Landing page only; the screen library is behind a login. Not usable. |
| dribbble.com search | Rendered blank (bot protection). Not usable. |

Limits: I could not inspect logged-in product UIs (Linear app, Notion app, Perplexity answers, Glean). Findings about those are interpretation, not observation. No Arabic enterprise product was audited; RTL decisions rely on first principles and the mockups.

## Findings

1. **Restraint is the shared trait.** Linear, Raycast and Stripe all use one neutral palette with accent used sparingly; weight and size carry hierarchy. Weight 510 and −2 % tracking are tuning, not decoration.
2. **Light-weight display type reads premium** (Stripe 300). Heavy 700 headlines read "template".
3. **Roomy body leading** (Stripe docs 1.86) makes long text pleasant; relevant because our answers are long-form reading, and Arabic needs even more (≥ 1.9).
4. **Command-first UIs** (Raycast, Linear) make speed visible through keyboard hints; useful for a power-user knowledge tool.
5. **Perplexity's pattern**: centered prompt, minimal sidebar. Familiar, which is both an advantage (zero learning) and the generic baseline we should deliberately move beyond.
6. **Glean's marketing look** (gradient hero, pastel screenshots) is the "generic enterprise AI" aesthetic the brief asks us to avoid.
7. **No reference solves verification well.** Citations are links or chips; none shows the actual source page next to the claim. That is the opening for this product.

## Three directions explored (static mockups, EN + AR/RTL, Home + Chat)

Open with: `cd docs/design/mockups && python3 -m http.server 8765`, then `http://localhost:8765/<file>?screen=chat&lang=ar`. The floating dark bar toggles Home/Chat and EN/عربي. (Opening the files directly renders a static snapshot without the toggles.) Mockups are throwaway HTML, not product code; all names and documents are synthetic.

| | **A — The Reading Room** | **B — Instrument** | **C — Chancery** |
|---|---|---|---|
| File | `a-reading-room.html` | `b-instrument.html` | `c-chancery.html` |
| Mood | Warm paper, editorial, calm | Dark graphite, dense, fast | Crisp white, document-forward, formal |
| Type | Geist UI; **Newsreader** answers; Plex Arabic + Noto Naskh | Inter Tight; JetBrains Mono; Plex Arabic | Instrument Sans; **Source Serif 4**; Noto Sans Arabic |
| Accent | Verdigris `#1F6F63` + highlighter amber | Amber `#E8A33D` | Oxblood `#8A2C3B` |
| Navigation | Left rail | Slim icon rail + command bar | Top bar (no sidebar) |
| Home | Prompt, then two ruled lists (recent, library) + one attention note | Raycast-style command bar with suggestions, dense table, activity log | Large headline, prompt, three big numbers, two lists |
| Chat | Prose with **margin-note citations** + **evidence pane** showing the real page | Answer with inline citation chips, source table, **drawer** showing the page | Single column, **footnote sources with page thumbnails** under the answer |
| Verification | Click → page highlighted beside the answer | Click chip → drawer | Thumbnails inline; open for full page |
| Strengths | Most distinctive; best reading; side-by-side verification | Fastest-feeling; best for power users; very dense | Most "enterprise formal"; works on narrow screens; easy RTL |
| Risks | Margin lane needs ≥ ~1200 px (stacks below); more layout work | Dark-first is the most Linear/Raycast-like (least original); long Arabic prose on dark needs care | Home stats are the closest to "dashboard cards"; thumbnails are small evidence |

RTL checked by screenshot in A, B and C (Home/Chat, Arabic): the rail/evidence pane/nav mirror correctly using logical properties; Arabic text uses a different font stack and looser leading; mono is not used for Arabic labels.

### Recommendation
**A** as the base, borrowing from **B** the ⌘K command palette and the dense library table, and from **C** the "Needs attention" row and the explicit support-state pill. A is the only one that makes verification a side-by-side act, which is the product's reason to exist. Decision is yours.
