# Daily Dev Activity

> A quiet little bridge between **Notion** and **GitHub**.

I use Notion to manage my day.
This repository turns the technical work I choose to share into a simple, daily development log — automatically.

---

## How it works

```text
Notion
  ↓
Done + Publish to GitHub
  ↓
GitHub Actions · 11:00 PM IST
  ↓
Privacy filter
  ↓
Daily activity log
  ↓
GitHub
```

No manual commits. No copy-pasting. No GPT in the execution loop.

## The rule

Only tasks that are:

- completed
- explicitly marked **Publish to GitHub**
- recognised as technical / development work
- not flagged as personal

make it through.

The final checkbox in Notion is the privacy gate.

## What gets published

Each day gets a small Markdown log:

```text
2026/
└── 08/
    └── 12.md
```

Example:

```md
# 2026-08-12

## Development & Learning
- Revise python
- Research on Apple Developer Academy
- Work on projects
```

## Stack

**Notion API** · **Python** · **GitHub Actions** · **GitHub**

## Why I built this

I wanted my GitHub activity to reflect the work I'm actually doing without turning GitHub into another productivity system I have to maintain.

Notion stays the source of truth.
GitHub simply records the work worth showing.

---

<sub>Automated daily. Kept intentionally simple.</sub>
