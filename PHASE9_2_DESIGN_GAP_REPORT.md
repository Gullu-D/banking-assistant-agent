# Phase 9.2 — Visual UI Review and Design Gap Analysis

## 1. Executive Assessment

The current UI is a **Streamlit application with a CSS overlay**, not a designed
product. The glassmorphism tokens exist (`--glass-bg`, `--glass-blur`) and the
color palette is correct (navy #101D35, teal #16856B, soft gray #F5F7FA, white
#FFFFFF), but the visual result reads as "a Streamlit dashboard with a dark
sidebar and recolored cards."

**What works:**
- Color palette is cohesive — navy sidebar, teal accents, soft gray background
- Glassmorphism CSS properties are declared and applied
- Auth page has a clean centered layout
- Empty states have styled cards with clear CTAs

**What doesn't work:**
- Layout is 100% Streamlit's default grid, not a Bento Grid
- Cards are uniform white rectangles — no size variation, no visual hierarchy
- Glassmorphism is invisible (white cards on near-white background = no blur
  effect visible)
- Typography uses browser defaults — no type scale, no weight contrast
- Sidebar is a plain dark rectangle with unstyled radio buttons
- Header is a generic dark banner with no brand presence
- Charts use Plotly defaults with no theme integration
- The overall impression is "functional internal tool," not "polished financial
  SaaS product"

**Honest rating: 4/10** for visual polish against the agreed design direction.
The design system is declared in CSS but not realized in the rendered output.

---

## 2. Verification Method

**Inspection method:** Built-in browser pane (Chromium-based), 1024×768 desktop
viewport.

**Pages inspected:**
- Login/Register (auth page) — unauthenticated
- Overview — empty state (no data)
- Transactions — empty state
- AI Assistant — with query input and quick-query buttons
- Anomalies — empty state
- Insights — empty state
- Import Data — with file uploader and empty history

**Code files reviewed:**
- `app.py` lines 58–242 (complete CSS block)
- `app.py` lines 351–409 (header and sidebar rendering)
- `app.py` lines 505–580 (auth page)
- `app.py` lines 587–738 (overview page with KPIs and charts)
- `app.py` lines 740–818 (transactions page)
- `app.py` lines 839–1013 (AI assistant page)
- `app.py` lines 1015–1087 (anomalies and insights pages)
- `app.py` lines 1185–1280 (import page)
- `.streamlit/config.toml` (theme configuration)

**Limitation:** Could not import data into the new test account (sandbox
restriction), so data-populated views (KPI cards with values, charts, anomaly
cards, insight cards) were evaluated from code analysis and Phase 9.1
verification screenshots, not fresh live inspection.

---

## 3. Page-by-Page Observations

### 3.1 Login / Register Page

**Layout:** Centered card (`max-width: 420px`, `margin: 60px auto`) with
glassmorphism. Two Streamlit tabs for Login/Register. Title and tagline
duplicated — once in the header banner at top, once as a large centered heading
below it.

**Issues:**
- **Double branding:** The page shows the app name/tagline twice: in the dark
  header banner AND in a large centered `<h1>`. Looks like two different
  components fighting for attention.
- **Login form is Streamlit default:** White inputs with Streamlit's built-in
  labels, no custom styling on form fields. The `.auth-container` glass effect
  is applied via CSS but barely visible since the card sits on `#F5F7FA`
  background — `rgba(255,255,255,0.72)` on near-white is just white.
- **No visual branding beyond the emoji:** The `🏦` emoji is the entire brand
  identity. No logo, no illustration, no color accent on the auth card.
- **Tab styling is Streamlit default:** The Login/Register tabs use Streamlit's
  unstyled tab component. No custom highlighting.

### 3.2 Overview Page (Dashboard)

**Layout:** Streamlit's `st.columns(4)` for KPIs, then `st.columns(2)` for
charts. Each chart is wrapped in a `<div class="bank-card">`. No Bento Grid —
all cells are equal width.

**Issues:**
- **Not a Bento Grid:** The layout is a flat 4-column KPI row + two rows of
  2-column charts. A Bento Grid uses unequal cell sizes (1×1, 2×1, 1×2, etc.)
  to create visual hierarchy. Currently every card is the same width.
- **KPI cards lack visual hierarchy:** All four KPI cards (Income, Expenses,
  Net Cash Flow, Transactions) are identical white rectangles. No card is
  visually emphasized. No icons, no color-coded borders, no accent highlights.
- **Glassmorphism not visible:** `.kpi-card` and `.bank-card` use
  `background: rgba(255,255,255,0.72)` with `backdrop-filter: blur(12px)`,
  but since they sit on `#F5F7FA` (near-white) background with a subtle gradient
  (`linear-gradient(160deg, #F5F7FA 0%, #EDF1F7 50%, #F0F5FA 100%)`), the blur
  has nothing contrasting behind it. The glassmorphism is technically applied
  but visually invisible.
- **Charts use Plotly defaults:** `plot_bgcolor="white"` with no grid styling,
  no rounded corners on the chart container, no theming of axes/fonts to match
  the design system. The chart titles are `<h3>` with emojis (`📈`, `📊`,
  `🏪`, `💰`) — not professional iconography.
- **Period comparison expander:** Uses Streamlit's default expander style with
  `st.metric()` cards inside — completely different visual treatment from the
  custom KPI cards above.
- **No section headings or visual separation:** KPIs flow into charts with
  just `st.write("")` (an empty line) as spacing.

### 3.3 Transactions Page

**Layout:** Five-column filter row (`st.columns([2,2,2,2,3])`), then a sort
dropdown, then three KPI cards in a row, then a Streamlit dataframe.

**Issues:**
- **Filter controls are Streamlit defaults:** Five `st.selectbox` / `st.date_input`
  / `st.text_input` widgets with no custom styling. They look like standard form
  elements, not a cohesive filter bar.
- **Sort control is a standalone selectbox:** Sits alone between the filter row
  and the KPI cards, not grouped with the filters.
- **Data table is `st.dataframe`:** Streamlit's default dataframe widget with
  no custom styling. Not a glassmorphic card — just a raw table.
- **KPI cards (Filtered Transactions, Total Debits, Total Credits) use the
  same `kpi_card()` as the Overview.** Functional but no variety.
- **No pagination UX:** The `st.number_input` for page number is Streamlit's
  default number stepper — no "Previous/Next" buttons, no indication of
  which rows are visible beyond a `st.caption`.

### 3.4 AI Assistant Page

**Layout:** Conversation history in an expander, a `bank-card` div wrapping a
text area and quick-query buttons, then results area below.

**Issues:**
- **Empty `bank-card` visible at top:** The conversation history section renders
  an empty expander-like area even when there's no history. Visible as a blank
  white rectangle above the input area.
- **Quick-query buttons are Streamlit defaults:** Four equal-width buttons in
  `st.columns(4)` with no custom styling — they inherit Streamlit's button look.
  The emoji + text wrapping makes them look cramped at narrower viewports.
- **Text area is Streamlit default:** No custom input styling. The placeholder
  text is light gray inside a standard textarea.
- **Analyze button centered with flanking empty columns:** `bc1, mid, bc2 =
  st.columns([1, 1, 1])` — the center column holds the button, but the left
  column is always empty. Wastes space.
- **Results area is purely vertical:** After analysis, KPIs, charts, anomalies,
  summary, and transactions stack vertically with no visual grouping beyond
  `bank-card` dividers. No layout sophistication.
- **No chat-like conversation UI:** History is buried in an expander. The
  assistant does not feel conversational — it's a form with a results dump
  below.

### 3.5 Anomalies Page

**Layout:** Date range selector, then anomaly cards in a single `bank-card`
wrapper.

**Issues:**
- **Anomaly cards inside one card:** All anomalies render inside a single
  `bank-card` wrapper with the title "⚠️ Potential Anomalies (period) —
  N flagged". This means anomaly cards (`.anomaly-card`) are nested inside
  `.bank-card` — cards within a card.
- **No summary statistics:** No KPI showing total flagged amount, severity
  breakdown, or period comparison. Just a list.
- **Severity pills are small inline text:** The `.severity-pill` is a tiny
  `font-size: 10.5px` element. Not very scannable at a glance.

### 3.6 Insights Page

**Layout:** Title, caption, then insight cards stacking vertically.

**Issues:**
- **Purely vertical card stack:** Each insight is an `.insight-card` with a
  green left border. No grid, no visual variety — just a list of same-width
  cards.
- **No visual icons or categories:** Each card is plain text with a title and
  body. No icons or color coding to distinguish insight types (spending vs
  income vs anomaly insights).
- **Section heading uses Streamlit's `####`:** No custom styled header.

### 3.7 Import Data Page

**Layout:** Title + description text, Streamlit file uploader, divider, import
history heading, and history table.

**Issues:**
- **File uploader is Streamlit's default widget:** Cannot be styled. The "Drag
  and drop file here" area is Streamlit's built-in component.
- **Column mapping section (visible after upload) uses `st.selectbox` in
  dynamic columns** — functional but visually generic.
- **Import history uses `st.dataframe`:** Same unstyled default table as
  Transactions.
- **`st.markdown("---")` divider:** Streamlit's default horizontal rule, not a
  styled separator.
- **No progress indicator during import** beyond `st.spinner`, which is
  Streamlit's default loading overlay.

### 3.8 Header (All Pages)

**Current:** Dark navy banner (`.bank-header`, `background: var(--bank-navy)`)
with app name, tagline, and a `bank-badge` showing AI status. "Logged in as
username" in light gray.

**Issues:**
- **Generic dark stripe:** No visual depth, no gradient, no brand icon beyond
  `🏦`.
- **Badge is a simple `border-radius: 20px` pill** with tiny font. Functional
  but unremarkable.
- **No breadcrumb or page title in header.** The user's current page is only
  indicated by the sidebar radio button selection.

### 3.9 Sidebar (All Pages)

**Current:** Streamlit sidebar with `background: var(--bank-navy)` and all text
forced to `#cbd5e1 !important`.

**Issues:**
- **Navigation is `st.radio()`:** Streamlit's radio buttons with colored dots.
  Not styled as a proper nav menu. No hover states, no active page indicator
  beyond the radio dot color.
- **Section titles ("ACCOUNT", "AI STATUS", "ABOUT") are unstyled uppercase
  text:** Uses `.sidebar-section-title` CSS which only sets `font-size: 11px`,
  `text-transform: uppercase`, and color. No visual weight or spacing.
- **Logout button is Streamlit's default outline button** with no custom
  styling. The `🚪` emoji serves as the only visual indicator.
- **No logo or brand mark** in the sidebar header.
- **"What is this?" expander** uses Streamlit's default expander styling, which
  clashes with the dark sidebar background.

---

## 4. Current Design vs. Agreed Design Direction

| Design Principle     | Agreed Direction                                    | Current Reality                                      | Gap |
|----------------------|-----------------------------------------------------|------------------------------------------------------|-----|
| **Modern Minimalism**| Clean lines, generous whitespace, clear hierarchy   | Streamlit defaults with CSS color overrides, no custom spacing or hierarchy | Large |
| **Bento Grid**       | Unequal card sizes creating visual interest          | Uniform `st.columns(N)` everywhere — all equal width | Missing entirely |
| **Glassmorphism**    | Frosted-glass effect with depth and layering        | `backdrop-filter: blur(12px)` declared but invisible (white-on-white) | Technically present, visually absent |
| **Color Navy #101D35**| Primary surfaces, deep backgrounds                 | Sidebar and header only. Rest is default `#F5F7FA`   | Partial |
| **Teal #16856B**     | Accent, interactive elements, positive indicators   | Buttons and chart bars. No gradient accents, no hover effects visible | Partial |
| **Soft gray #F5F7FA**| Background canvas                                   | Applied correctly via `.stApp` and config.toml       | Done |
| **White #FFFFFF**    | Card surfaces                                       | Applied but glassmorphism makes them `rgba(255,255,255,0.72)`, indistinguishable from background | Done (but invisible) |
| **Typography**       | Systematic type scale with weight hierarchy         | Browser defaults via `font: "sans serif"` in config. No custom font loading, no type scale | Missing |
| **Iconography**      | Consistent icon set for navigation and categories   | Emoji characters (`🏦 📈 📊 🏪 💰 ⚠️ 🔍 📥`)      | Missing — emojis are not icons |
| **Component Polish** | Custom-styled inputs, buttons, tables               | Streamlit default widgets with no CSS override       | Large |
| **Data Visualization**| Charts themed to match design system               | Plotly with white background and default axes         | Large |
| **Responsive Design**| Fluid at all widths above 768px                     | Streamlit handles responsive automatically — no custom breakpoints | Default only |

---

## 5. Top 10 Visual Improvements (Ranked by Impact)

### 1. Make Glassmorphism Actually Visible
**Impact:** Transforms the entire app from "white cards on white" to the intended frosted-glass aesthetic.
**Problem:** Cards use `rgba(255,255,255,0.72)` over `#F5F7FA` — zero contrast through the blur.
**Fix:** Add colored geometric shapes or gradients to the background that the glass cards can blur over. Alternative: shift cards to `rgba(255,255,255,0.55)` and add a more dramatic background gradient with colored blobs (e.g., a navy blob and a teal blob at 10% opacity behind the content area).

### 2. Implement Genuine Bento Grid on Overview
**Impact:** The dashboard is the most-visited page. A Bento Grid creates instant visual hierarchy and makes it look like a designed product, not a template.
**Problem:** `st.columns(4)` and `st.columns(2)` produce equal-width cells.
**Fix:** Use Streamlit's `st.columns([2, 1, 1])` and `st.columns([1, 2])` for varied cell sizes. Make the Income vs Expenses chart span 2 units while Spending by Category gets 1, etc. Consider making one KPI card double-height with a sparkline inside.

### 3. Replace Emoji Icons with SVG or Font Icons
**Impact:** Emoji render differently per platform and look unprofessional. Consistent iconography is a hallmark of polished SaaS.
**Problem:** Headers use `🏦`, `📈`, `📊`, charts use `🏪`, `💰`, nav uses `📥`, etc.
**Fix:** Use inline SVG icons or a lightweight icon font (Phosphor, Lucide) loaded via CDN. Render as `st.markdown()` with `unsafe_allow_html=True`.

### 4. Style the Sidebar Navigation
**Impact:** The sidebar is visible on every page. Currently it's an unstyled radio button list.
**Problem:** `st.radio()` renders as Streamlit's default radio group with colored dots.
**Fix:** Override Streamlit's radio button CSS to look like a nav menu: remove radio dots, add left-border accent on active item, add hover backgrounds, add proper spacing. CSS target: `section[data-testid="stSidebar"] .stRadio label`.

### 5. Add Custom Typography Scale
**Impact:** Typography is the most impactful design element after color. Currently all text is browser-default sans-serif at default sizes.
**Problem:** No custom fonts loaded, no systematic size/weight scale.
**Fix:** Load Inter (already referenced in chart `font.family`) via Google Fonts `<link>` in the CSS block. Define a type scale: page titles 28px/800, section titles 18px/700, body 14px/400, captions 12px/500.

### 6. Theme Plotly Charts to Match Design System
**Impact:** Charts are the primary data visualization and currently look disconnected from the rest of the UI.
**Problem:** `plot_bgcolor="white"`, default axes, no rounded corners on container.
**Fix:** Set `paper_bgcolor="transparent"`, `plot_bgcolor="transparent"`, use `--bank-muted` for axis labels, use the teal palette for all series. Add CSS border-radius to chart containers. Reduce chart margins.

### 7. Style Form Inputs and Buttons
**Impact:** Every interaction point (filters, search, login) currently uses Streamlit defaults.
**Problem:** Streamlit widgets (`st.text_input`, `st.selectbox`, `st.date_input`) cannot be individually styled, but they can be partially overridden via CSS targeting `[data-testid]` selectors.
**Fix:** Add CSS for `input`, `select`, and `textarea` elements inside the main content area: custom border-radius (10px), border color (`--bank-border`), focus ring in teal, and consistent padding.

### 8. Redesign KPI Cards with Visual Hierarchy
**Impact:** KPI cards are the first thing users see. Currently they're identical white rectangles.
**Problem:** All cards use the same `kpi_card()` template with no differentiation.
**Fix:** Add: (a) colored top borders — teal for income, red for expenses, navy for net, gray for count; (b) small inline SVG icons next to labels; (c) make the delta indicator more prominent with background color.

### 9. Add Section Headers and Visual Rhythm
**Impact:** Currently there's no visual separation between sections — KPIs flow directly into charts.
**Problem:** `st.write("")` is the only spacing. No section headings with styled typography.
**Fix:** Add styled section dividers with titles: `<div class="section-header">Dashboard Overview</div>` and `<div class="section-header">Charts & Trends</div>`. Define consistent vertical spacing (24px between sections, 16px between cards).

### 10. Eliminate Double Branding on Auth Page
**Impact:** The login page is the first impression. Currently shows the app name twice.
**Problem:** Dark header banner + centered `<h1>` both show "Banking Assistant Agent".
**Fix:** On the auth page, either hide the header banner or remove the centered heading. Choose one brand moment, not two. The auth card itself could get a small teal accent border or gradient.

---

## 6. Proposed Overview Dashboard — Bento Grid Layout

### Current Layout (Equal-Width Grid)

```
┌─────────┬─────────┬─────────┬─────────┐
│ Income  │Expenses │Net Cash │  Txn    │
│ (1/4)   │ (1/4)   │ (1/4)   │ Count   │
│         │         │         │ (1/4)   │
└─────────┴─────────┴─────────┴─────────┘
┌───────────────────┬───────────────────┐
│ Income vs Expense │ Spending by Cat.  │
│ (1/2)             │ (1/2)             │
└───────────────────┴───────────────────┘
┌───────────────────┬───────────────────┐
│ Top Merchants     │ Monthly Cash Flow │
│ (1/2)             │ (1/2)             │
└───────────────────┴───────────────────┘
```

### Proposed Bento Grid Layout

```
┌─────────────────────────┬──────────┬──────────┐
│  NET CASH FLOW          │ Income   │ Expenses │
│  (hero card, 2×1)       │ (1×1)    │ (1×1)    │
│  Large number + delta   │          │          │
│  + sparkline            │          │          │
├─────────┬───────────────┴──────────┤──────────┤
│ Txn     │ Income vs Expenses       │ Spending │
│ Count   │ (2×1 chart)              │ by Cat.  │
│ (1×1)   │                          │ (1×2     │
│         │                          │  donut)  │
├─────────┼──────────────────────────┤          │
│ Top     │ Monthly Cash Flow        │          │
│ Merchant│ (2×1 chart)              │          │
│ (1×1)   │                          │          │
│ mini    │                          │          │
└─────────┴──────────────────────────┴──────────┘
```

**Implementation via Streamlit columns:**
```python
# Hero row: Net Cash Flow (50%) + Income (25%) + Expenses (25%)
h1, h2, h3 = st.columns([2, 1, 1])

# Middle row: Txn count (17%) + I vs E chart (50%) + Category donut (33%)
m1, m2, m3 = st.columns([1, 3, 2])

# Bottom row: Top Merchant mini (17%) + Cash Flow chart (50%) + (donut continues)
b1, b2 = st.columns([1, 3])
```

**Key changes:**
- Net Cash Flow becomes a hero card (double width, contains a sparkline)
- Category donut becomes a tall card spanning two rows (vertically via CSS min-height)
- Small KPI cards (Income, Expenses, Txn Count, Top Merchant) are compact tiles
- Charts get unequal widths, creating visual asymmetry

**Note:** True 2D Bento Grid (CSS Grid with `grid-row` spanning) is not possible
in Streamlit since `st.columns()` only creates horizontal divisions within a
single row. The best approximation is varied column widths per row + CSS
`min-height` to simulate row spanning.

---

## 7. Proposed AI Assistant Layout

### Current Layout

```
┌────────────────────────────────────────────┐
│ [Conversation history expander]            │
├────────────────────────────────────────────┤
│ 🤖 Ask your banking question               │
│ ┌────────────────────────────────────────┐ │
│ │ [textarea]                             │ │
│ └────────────────────────────────────────┘ │
│ Quick queries:                             │
│ [Btn1] [Btn2] [Btn3] [Btn4]               │
│              [Analyze]                     │
├────────────────────────────────────────────┤
│ [KPI1] [KPI2] [KPI3] [KPI4]               │
│ [Chart] [Chart]                            │
│ [Anomalies card]                           │
│ [Summary card]                             │
│ [Transaction table]                        │
│ [Category expander]                        │
└────────────────────────────────────────────┘
```

### Proposed Layout

```
┌──────────────────────────────────────────────────┐
│                    CHAT AREA                      │
│  ┌──────────────────────────────────────────────┐│
│  │ [User] Show transactions above ₹50,000       ││
│  │ [Bot]  Found 12 transactions...              ││
│  │        ┌─────────────────────┐               ││
│  │        │ Inline summary card │               ││
│  │        └─────────────────────┘               ││
│  └──────────────────────────────────────────────┘│
├──────────────────────────────────────────────────┤
│ ┌────────────────────────────────────┬──────────┐│
│ │ [query textarea]                   │[Analyze] ││
│ └────────────────────────────────────┴──────────┘│
│ Quick: [💰 High-value] [📊 Spending] [⚠️ Unusual] │
└──────────────────────────────────────────────────┘

Results expand BELOW or in a SIDE PANEL:
┌──────────────────┬─────────────────────────────┐
│ SUMMARY          │ DETAIL                       │
│ ┌──────────┐     │ ┌─────────────────────────┐ │
│ │ KPI tile │     │ │ Chart                   │ │
│ │ compact  │     │ │                         │ │
│ └──────────┘     │ └─────────────────────────┘ │
│ ┌──────────┐     │ ┌─────────────────────────┐ │
│ │ KPI tile │     │ │ Transaction table       │ │
│ └──────────┘     │ └─────────────────────────┘ │
└──────────────────┴─────────────────────────────┘
```

**Key changes:**
- **Conversation history moves from a collapsed expander to a visible chat area**
  above the input, with user/bot message styling (left/right alignment or colored
  bubbles).
- **Input area becomes more compact:** textarea + Analyze button on the same row
  (`st.columns([5, 1])`), not on separate rows.
- **Quick-query buttons move below the input** as compact pills, not full-width
  buttons.
- **Results use a two-column layout:** summary/KPIs on the left narrow column,
  charts and detail on the right wide column.

**Streamlit constraint:** A true chat interface would require `st.chat_message`
(available in Streamlit 1.26+), which provides built-in user/assistant message
bubbles. This is a better fit than the current expander approach.

---

## 8. Implementation Plan (Priority Order)

### Phase 10A — Foundation (Highest Impact, Lowest Risk)

1. **Load Inter font via Google Fonts** — add `<link>` in the CSS block
2. **Define type scale** — headings, body, captions as CSS classes
3. **Make glassmorphism visible** — add colored background blobs or increase
   background gradient contrast
4. **Style sidebar nav** — CSS overrides on `st.radio` to look like nav menu
5. **Fix auth page double branding** — remove centered heading, keep header
6. **Add section headers** — styled dividers between KPIs and charts

### Phase 10B — Component Polish

7. **Style form inputs** — border-radius, focus ring, consistent sizing via CSS
8. **Theme Plotly charts** — transparent backgrounds, teal palette, matching fonts
9. **Redesign KPI cards** — color-coded top borders, icons, prominent deltas
10. **Replace emoji with inline SVG icons** — sidebar, headers, quick queries

### Phase 10C — Layout Overhaul

11. **Implement Bento Grid on Overview** — varied column widths per row
12. **Redesign AI Assistant** — use `st.chat_message`, compact input row,
    two-column results
13. **Style data tables** — custom CSS on `st.dataframe`, styled pagination

### Phase 10D — Polish and Refinement

14. **Add micro-interactions** — hover states, transitions on card focus
15. **Add visual empty states** — illustration SVGs instead of plain text
16. **Audit responsive behavior** — test all layouts at 768px and 1440px

**Estimated effort:** ~3–4 focused sessions for Phase 10A+B, ~2 sessions for
10C, ~1 session for 10D.

---

## 9. Technical Constraints Imposed by Streamlit

### What Streamlit Controls (Cannot Override)

| Element                | Constraint                                          |
|------------------------|-----------------------------------------------------|
| **Widget rendering**   | `st.text_input`, `st.selectbox`, `st.date_input`, `st.file_uploader` render as Streamlit's React components. CSS can override some styles but not structure. |
| **Layout grid**        | `st.columns()` creates flexbox rows. No CSS Grid, no `grid-row` spanning, no true 2D Bento Grid. Column ratios are the only lever. |
| **Sidebar structure**  | `st.sidebar` is a fixed-width left panel. Cannot change its width, collapse behavior, or position. |
| **Dataframe widget**   | `st.dataframe` renders via a dedicated React component. Cannot inject custom row styles, cell formatting beyond column config, or custom pagination. |
| **Deploy button**      | The "Deploy" button + hamburger menu in the top-right are Streamlit Chrome. Can be hidden via CSS (`header[data-testid="stHeader"]`) but not styled. |
| **Toast/spinner/balloons** | System feedback uses Streamlit's built-in UI. |
| **Rerun model**        | Every interaction triggers a full page rerun. No partial updates, no SPA-like transitions. |

### What Can Be Overridden via CSS

| Element              | Technique                                            |
|----------------------|------------------------------------------------------|
| **Background**       | `.stApp` styling — gradients, colors, patterns       |
| **Cards/containers** | `st.markdown(unsafe_allow_html=True)` — full HTML/CSS control |
| **Typography**       | CSS `@import` for fonts, global `*` selectors        |
| **Buttons**          | CSS targeting `[data-testid="stButton"] button`      |
| **Radio buttons**    | CSS on `.stRadio label` — remove dots, add backgrounds|
| **Input styling**    | CSS on `input`, `select`, `textarea` within Streamlit containers |
| **Charts**           | Plotly layout parameters (not CSS) — backgrounds, fonts, margins |
| **Expanders**        | CSS on `[data-testid="stExpander"]`                  |
| **Tabs**             | CSS on `[data-testid="stTabs"]` tab buttons          |
| **Sidebar**          | Background, text colors, section spacing via CSS     |
| **Header**           | Fully custom via `st.markdown(unsafe_allow_html=True)` |

### Recommended Approach

Use `st.markdown(unsafe_allow_html=True)` for all custom layout and styled
components. Use CSS injected via the existing `<style>` block for overriding
Streamlit widget defaults. Accept that `st.dataframe`, `st.file_uploader`,
and `st.selectbox` cannot be fully restyled — wrap them in styled containers
to maintain visual consistency.

For the Bento Grid approximation: use varied `st.columns()` ratios + CSS
`min-height` on card containers to simulate row-spanning. This is the maximum
achievable within Streamlit without embedding an iframe.

---

## 10. Findings That Could Not Be Verified

| Finding                             | Reason                                          |
|-------------------------------------|-------------------------------------------------|
| KPI cards with live data (numbers, deltas, sub-text) | Could not import data into test account (sandbox restriction) |
| Plotly charts with actual data series | Same — requires populated transactions |
| Anomaly cards with severity pills and merchant data | Same |
| Insight cards with calculated values | Same |
| AI Assistant results area (KPIs + charts + table after query) | Same |
| Data table with 93 rows + pagination | Same |
| Import history table with completed imports | Same |
| Glassmorphism visibility with colored backgrounds behind cards | Would require code changes to test |
| `st.chat_message` compatibility with current Streamlit version | Would require testing `streamlit.__version__` |
| Responsive behavior at exactly 1440px viewport | Browser pane limited to 1024×768; code analysis used instead |

**Mitigation:** All findings above were evaluated via code analysis of the
rendering functions in `app.py`. The CSS declarations, HTML templates, and
Plotly layout parameters were read line-by-line. Layout structures were
determined from the `st.columns()` ratios in each page function. Color values
were cross-referenced between CSS variables and their usage in chart
`marker_color` and `color_discrete_sequence` parameters.

---

## Summary

The application has a correct color palette and the right CSS tokens declared,
but the visual execution falls short of a polished financial SaaS product.
The gap is not in the colors or the glassmorphism declaration — it's in:

1. **Layout** — equal-width grids instead of Bento Grid
2. **Visibility** — glassmorphism that can't be seen
3. **Polish** — Streamlit default widgets everywhere
4. **Typography** — no custom fonts or type scale
5. **Iconography** — emoji instead of icons

The implementation plan prioritizes high-impact, low-risk changes first
(typography, background, sidebar) before tackling layout restructuring.
