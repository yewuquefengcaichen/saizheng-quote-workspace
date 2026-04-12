# Saizheng Quote System Design System

> Supersedes the previous auto-generated draft. This version is the approved visual direction for the next UI rebuild phase.

---

**Project:** Saizheng Quote System
**Updated:** 2026-04-10
**Design Direction:** Quiet Enterprise Glass
**Product Type:** B2B quotation and mall document workspace

## Why This Direction

The system should no longer feel like a repainted mall backend. It needs to feel like a calm, precise, premium workbench for quotation, matching, review, and export.

The chosen direction combines:

- Apple HIG thinking: clear hierarchy, consistent structure, depth used only when it improves clarity
- Aura-style calm spacing and product confidence
- StyleKit glassmorphism materials, but only on control layers and overlays
- MotionSites hero rhythm and staged reveal, but without turning the app into a landing page
- Design Prompts and UI Prompt style browsing ideas for the template center

## Core Product Mood

- Calm, not noisy
- Premium, not flashy
- Efficient, not cold
- Professional, not bureaucratic
- Dense enough for work, but never cramped

## Design Principles

### 1. Tool First

The interface exists to help people complete a quotation workflow quickly. Beauty must support speed, not compete with it.

### 2. Separate Control From Content

Use material, blur, shadows, and elevation to distinguish navigation, filters, inspectors, and modal layers from the working content beneath them.

### 3. Use Depth Sparingly

Depth is for shell layers, drawers, sticky inspectors, and high-priority callouts. Tables, forms, and result rows should remain solid and readable.

### 4. High Density, High Breathability

This is a work system, so it cannot become a giant marketing page. Information density is allowed, but spacing, alignment, and typography must keep scanning effortless.

### 5. Calm Chinese Readability

Large Chinese text blocks, product names, models, and supplier data must remain legible. Decorative display typography is not allowed in core workflow areas.

## References

- Apple HIG: https://developer.apple.com/design/human-interface-guidelines/
- Apple Layout: https://developer.apple.com/design/human-interface-guidelines/layout
- Apple Accessibility: https://developer.apple.com/design/human-interface-guidelines/accessibility
- StyleKit Glassmorphism: https://www.stylekit.top/zh/styles/glassmorphism
- Aura: https://www.aura.build/
- MotionSites: https://motionsites.ai/
- Design Prompts: https://www.designprompts.dev/
- UI Prompt Explorer: https://uiprompt.art/
- UI Style Prompt: https://www.uiprompt.site/zh/styles

## What We Are Deliberately Avoiding

- Mall-style red and orange promotion visuals
- Purple AI gradients
- Overuse of blur on every card
- Giant marketing hero blocks inside task-heavy views
- Thick Bootstrap tables and default modal aesthetics
- Too many status colors competing on one screen
- Hover-only affordances for important actions
- Decorative infinite motion

## Visual System

### Palette

Use a cold, bright, misty base with restrained blue emphasis.

| Token | Value | Use |
|------|------|------|
| `--bg-canvas` | `#F3F7FB` | Global page background |
| `--bg-subtle` | `#EDF3F8` | Secondary backgrounds |
| `--surface-solid` | `#FFFFFF` | Tables, cards, forms |
| `--surface-soft` | `rgba(255,255,255,0.78)` | Floating panels |
| `--surface-glass` | `rgba(255,255,255,0.62)` | Top bar, overlay shells |
| `--surface-tint` | `rgba(239,246,255,0.72)` | Accent-tinted panels |
| `--line-soft` | `rgba(148,163,184,0.18)` | Borders |
| `--line-strong` | `rgba(100,116,139,0.28)` | Active borders |
| `--text-strong` | `#0F172A` | Headlines and key values |
| `--text-default` | `#334155` | Body text |
| `--text-muted` | `#64748B` | Secondary text |
| `--accent` | `#2563EB` | Primary actions |
| `--accent-strong` | `#1D4ED8` | Hover / selected |
| `--accent-soft` | `#DBEAFE` | Chips and highlighted rows |
| `--success` | `#059669` | Positive margin, matched |
| `--warning` | `#D97706` | Needs review |
| `--danger` | `#DC2626` | Reject / risk |
| `--premium` | `#A16207` | Very sparing premium hint |

### Surface Strategy

- `canvas`: soft mist background with subtle gradient wash
- `solid`: working cards, tables, data rows
- `glass`: top navigation, command bar, inspector, modal header shell
- `tint`: selected or focused work zones

### Gradients

Gradients are allowed only for:

- top-level hero or workspace shell
- primary CTA fills
- premium section accents
- selected state highlights

Never use gradients behind dense text tables.

## Typography

### Recommended Font Stack

- Chinese UI and content: `Noto Sans SC`, `HarmonyOS Sans SC`, `Microsoft YaHei`, `sans-serif`
- Latin labels and large metric numerals: `Plus Jakarta Sans`, `Noto Sans SC`, `sans-serif`

### Typography Rules

- Headings should feel clean and firm, not editorial
- Body text should use regular to medium weights only
- Data values should use tabular numerals
- Long product names should wrap cleanly and preserve line height

### Scale

| Role | Size | Weight |
|------|------|--------|
| Display hero | 40-48px | 600 |
| Page title | 28-32px | 600 |
| Section title | 20-24px | 600 |
| Card title | 16-18px | 600 |
| Body | 14-15px | 400-500 |
| Small meta | 12-13px | 500 |
| KPI value | 28-36px | 600 |

## Spacing And Shape

### Spacing Scale

| Token | Value |
|------|------|
| `--space-2xs` | `4px` |
| `--space-xs` | `8px` |
| `--space-sm` | `12px` |
| `--space-md` | `16px` |
| `--space-lg` | `24px` |
| `--space-xl` | `32px` |
| `--space-2xl` | `48px` |

### Radius

| Token | Value | Use |
|------|------|------|
| `--radius-sm` | `12px` | Inputs, chips |
| `--radius-md` | `18px` | Cards |
| `--radius-lg` | `24px` | Panels, modal shells |
| `--radius-pill` | `999px` | Chips and segmented controls |

### Shadow Model

| Token | Value | Use |
|------|------|------|
| `--shadow-sm` | `0 8px 18px rgba(15,23,42,0.04)` | Buttons, small cards |
| `--shadow-md` | `0 18px 38px rgba(15,23,42,0.07)` | Floating cards |
| `--shadow-lg` | `0 28px 60px rgba(15,23,42,0.12)` | Modals, inspector panels |

## Motion

### Allowed Motion

- fade and translate for panel entry
- slight shadow and border emphasis on hover
- count-up only for key metrics
- staged reveal on the first screen only

### Timing

- `160ms`: hover
- `220ms`: focus and selection
- `280ms`: panel entry

### Motion Constraints

- animate `opacity` and `transform` only
- support `prefers-reduced-motion`
- no infinite decorative animation
- no bounce on productivity controls

## Application Shell

The future app shell should be consistent across all major views:

1. Top glass navigation bar
2. Secondary command bar or filter bar beneath
3. Main content region with stable max width
4. Optional right-side sticky inspector for detail and action context

### Shell Rules

- Keep top navigation shallow
- Make the current step obvious
- Keep the main action visible without requiring hover discovery
- Use sticky zones for important context instead of modal spam

## Component Rules

### Buttons

- Primary button: blue gradient or solid blue fill, white text
- Secondary button: white or glass surface, strong border
- Tertiary button: text-plus-icon only for low priority actions
- Danger button: reserved for delete or explicit rejection only

### Inputs And Filters

- All filter controls should share one height
- Search bars should be wider, softer, and more obviously primary than utility filters
- Use segmented chips for common states like matched, unresolved, OCR, with image

### Cards

- Working cards should be solid, not fully glass
- Glass is allowed only for shell cards or preview summaries
- Each card must have one clear hierarchy: title, key value, supporting text, actions

### Tables

- Replace thick Bootstrap table feel with softer row groups
- Use row hover tint, not dark row hover
- Important numeric columns should align consistently
- Sticky headers are preferred in long lists

### Badges

- Limit to 4 semantic badge families: info, success, warning, neutral
- Avoid rainbow badge noise inside dense result lists
- Badge text should stay short and meaningful

### Modals And Drawers

- Large task modals should evolve into sheet-style overlays
- Small confirmation dialogs can stay modal
- Headers should be calmer and less Bootstrap-like

### Empty States

- Empty states should feel premium and reassuring
- Use neutral illustration or icon, concise explanation, and one next action
- Never leave large blank white rectangles without guidance

## Page Hierarchy

### Primary Views

- Home workspace
- Match workbench
- Export center

### Secondary Views

- Catalog browser
- History
- Settings
- AI assistant

Primary views define the design language. Secondary views inherit from them.

## Current UI Gap

The current `templates/index.html` already contains improved hero, glass shell, and template-center ideas, but the system is still visually split:

- the home area feels redesigned
- the workflow internals still rely on heavy Bootstrap patterns
- modals and tables still look like an older admin tool
- button color language is still too scattered

The next implementation phase must unify the internals, not just polish the landing section.

## Implementation Order

1. Build global tokens and shell
2. Replace buttons, inputs, chips, tabs, cards
3. Redesign the match workbench layout
4. Redesign export center layout
5. Unify catalog, history, and modal patterns
6. Remove remaining Bootstrap-default visual leftovers

## Pre-Implementation Checklist

- [ ] Visual direction remains calm, premium, and tool-first
- [ ] No page looks like the old mall frontend
- [ ] Blur is used only on shell and overlay layers
- [ ] Data-heavy views remain easy to scan
- [ ] Chinese content stays readable at normal zoom
- [ ] Keyboard focus is visible
- [ ] Reduced motion is respected
- [ ] Desktop and mobile layouts are both considered from the start
