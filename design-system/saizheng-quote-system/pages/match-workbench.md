# Match Workbench Override

Use this file before rebuilding the quotation matching view.

## Mission

Make the matching workflow feel like a professional review desk, not a pile of cards and modals.

## Primary User Goal

Scan unresolved items fast, compare candidates with confidence, confirm the right product, then move straight to export.

## Target Layout

Use a three-zone desktop layout:

### 1. Left Process Rail

- current step
- filter states
- counts: matched, unresolved, no match, OCR
- lightweight history or recent actions

This rail should stay narrow and stable.

### 2. Main Result Stream

- quotation items as vertically stacked result cards or structured rows
- dense but breathable
- row grouping by status is preferred over one endless undifferentiated list

### 3. Right Sticky Inspector

For the selected item, show:

- chosen product summary
- price and margin panel
- product image
- supplier info
- manual search
- quick confirm or swap actions

This inspector should reduce modal dependence.

## Result Card Structure

Every quote item should follow the same information order:

1. Quote item identity
2. Current status
3. Best match summary
4. Supporting signals
5. Actions

### Supporting Signals

Allowed:

- OCR source
- template hit
- image available
- historical feedback count
- confidence band

Not allowed:

- too many colorful badges in one row
- noisy secondary actions competing with confirm

## Price Presentation

Price is core to trust. It needs stronger hierarchy.

- show market price as primary commercial value
- show cost price as secondary internal value
- show margin delta with clean semantic color
- show warnings only when meaningful

## Candidate Comparison

Candidate lists should look more like ranked recommendations than raw search results.

Each candidate needs:

- name
- supplier
- key spec
- image state
- price block
- reason snippet
- choose action

## Interaction Rules

- selecting a row updates the right inspector
- expanding all candidates should not visually explode the layout
- manual search should happen inline in the inspector or under the active row
- modals remain only for genuinely separate tasks

## Modal Reduction Plan

Move these toward embedded or side-sheet patterns:

- price comparison
- product detail
- quote catalog search

Keep these as modal or sheet:

- mapping confirmation
- export confirm
- destructive history delete

## Success Criteria

- unresolved work is easy to spot
- one selected row always has clear context
- confirming a match feels fast and deliberate
- the page no longer feels like old Bootstrap admin UI
