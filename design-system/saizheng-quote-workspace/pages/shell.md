# Shell Page Overrides

> **PROJECT:** Saizheng Quote Workspace
> **Generated:** 2026-04-11 11:02:46
> **Page Type:** General

> ⚠️ **IMPORTANT:** Rules in this file **override** the Master file (`design-system/MASTER.md`).
> Only deviations from the Master are documented here. For all other rules, refer to the Master.

---

## Page-Specific Rules

### Layout Overrides

- **Max Width:** 1200px (standard)
- **Layout:** Full-width sections, centered content
- **Sections:** 1. Intro (Vertical), 2. The Journey (Horizontal Track), 3. Detail Reveal, 4. Vertical Footer

### Spacing Overrides

- No overrides — use Master spacing

### Typography Overrides

- No overrides — use Master typography

### Color Overrides

- **Strategy:** Continuous palette transition. Chapter colors. Progress bar #000000.

### Component Overrides

- Avoid: Ignore accessibility motion settings
- Avoid: Leave UI frozen with no feedback
- Avoid: Animate everything that moves

---

## Page-Specific Components

- No unique components for this page

---

## Recommendations

- Effects: Morphing elements (SVG/CSS), fluid animations (400-600ms curves), dynamic blur (backdrop-filter), color transitions
- Animation: Check prefers-reduced-motion media query
- Animation: Use skeleton screens or spinners
- Animation: Animate 1-2 key elements per view maximum
- CTA Placement: Floating Sticky CTA or End of Horizontal Track
