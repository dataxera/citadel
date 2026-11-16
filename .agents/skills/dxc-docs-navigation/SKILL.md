---
name: Citadel Documentation & MkDocs Navigation
description: Rules and checklist for adding, renaming, or removing documentation pages and ADRs under docs/, keeping mkdocs.yml and section index.md files synchronized for Read the Docs.
---
# Citadel Documentation & MkDocs Navigation

Use this skill whenever you:
- Add a new documentation page under `docs/` (e.g., `docs/user/`, `docs/developer/`, `docs/installation/`)
- Add a new Architecture Decision Record (ADR) under `docs/architecture-decisions/`
- Rename, move, or delete an existing documentation file in `docs/`

---

## 1. Update `mkdocs.yml` Navigation (`nav:`)

Because `mkdocs.yml` defines an explicit `nav:` tree, any new `.md` file under `docs/` **will not appear in the Read the Docs site navigation** unless it is added to `mkdocs.yml`.

1. Open `mkdocs.yml` at the repository root.
2. Add the new page under the appropriate section in `nav:` using a path relative to `docs/`:
   ```yaml
   nav:
     - User Guide:
         - user/index.md
         - Getting Started: user/getting-started.md
         - My New Guide: user/my-new-guide.md
   ```
3. If introducing a **new top-level section** under `docs/<section>/`:
   - Create `docs/<section>/index.md` as the section landing page (do **not** name it `README.md`, as MkDocs uses `index.md` for directory URLs with `navigation.indexes`).
   - Add the section and its `index.md` to `nav:` in `mkdocs.yml`.
   - Link the new section from `docs/index.md`.
4. If renaming or deleting a page, update or remove its entry in `mkdocs.yml` and check for any internal links referencing the old path.

---

## 2. Update Section `index.md`

Keep the parent section's `index.md` synchronized with `mkdocs.yml`:

- **Installation**: `docs/installation/index.md`
- **User Guide**: `docs/user/index.md`
- **Developer Guide**: `docs/developer/index.md`
- **Architecture Decisions**: `docs/architecture-decisions/index.md` (add a row to the Decisions table with the ADR ID, title, and relative link)

---

## 3. Read the Docs & MkDocs Link Rules

- **Never use local `file://` URLs** (e.g., `file:///home/...`). They break on Read the Docs and fail `mkdocs build --strict`.
- **Links between docs pages**: Use relative paths (e.g., `[Core Concepts](core-concepts.md)` or `[Getting Started](../user/getting-started.md)`).
- **References to repo files outside `docs/`** (e.g., `.agents/rules/constitution.md`, `backend/src/...`): Write them as inline code paths (`` `.agents/rules/constitution.md` ``) rather than Markdown links, since files outside `docs/` are not published by MkDocs.
- **Mermaid diagrams**: Use standard ```` ```mermaid ```` fenced code blocks (supported via `pymdownx.superfences` in `mkdocs.yml`).

---

## 4. SPDX Header

Include the project SPDX tag in newly created documentation files (typically as an HTML comment at the bottom of `.md` files, or `#` comment in YAML):

```markdown
<!--
SPDX-FileCopyrightText: Copyright © <year> Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
-->
```

---

## 5. Verification Checklist

Before finishing any documentation change:
1. Verify the new/updated page is listed in `mkdocs.yml` under `nav:`.
2. Verify the corresponding section `index.md` links to the new page.
3. Run a strict MkDocs build (if `mkdocs` is available in your environment) to catch broken links or missing nav entries:
   ```bash
   mkdocs build --strict -d /tmp/mkdocs-site
   ```

<!--
SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
SPDX-License-Identifier: AGPLv3+
-->
