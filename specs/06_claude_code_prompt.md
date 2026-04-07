# Claude Code Prompt — Spec 06 Implementation

Paste this into Claude Code:

---

Read `specs/06_user_manual_tooltips.md` and implement it end to end. Do not deviate from the spec — ask me before making any changes.

## Rules
1. Follow the spec exactly. If you think something should be different, ASK ME first.
2. Every single metric, label, title, chart, filter, toggle, table column, and number in the dashboard must have a `help=` tooltip or explanatory caption. No exceptions.
3. Talk to me like I am not technical. Short sentences.
4. The audience for these tooltips is a non-scientist, non-coder. Every tooltip must use plain English. No jargon without an immediate definition in the same tooltip.

## Step-by-step execution

### Step 1: Add tooltips to the sidebar
Follow spec section 2. Every widget in the sidebar needs `help=`.

### Step 2: Add tooltips to each tab (sections 3-11)
Go through tabs 1-10 in order. For each tab:
- Add `help=` to every `st.metric()`
- Add subtitles/captions to every chart
- Add `help=` to every filter/selectbox/toggle
- For data tables: add column descriptions via tooltips or a legend above the table

### Step 3: Expand Sources & Methods
Follow spec section 12. Add the full "How to Read This Dashboard" guide.

### Step 4: Add the User Manual tab
Follow spec section 13. Add a new "User Manual" tab as the last tab with:
- Getting Started
- Tab-by-Tab Guide
- Glossary (every term defined)
- FAQ (all 7 questions from the spec)

### Step 5: Verify
- Run `streamlit run app.py`
- Click through every tab and verify every element has a tooltip
- Read each tooltip — does it make sense to a non-technical person?
- Confirm all Done Criteria from spec section 14
- Commit and push

## Important
- Do NOT change any data processing, classification, or linkage logic
- Only add help text, tooltips, captions, and the manual tab
- Keep all existing functionality working
- The tooltips are defined in the spec — use those exact texts (you may improve wording if needed, but keep the meaning and plain-English tone)
- Commit after each major step
