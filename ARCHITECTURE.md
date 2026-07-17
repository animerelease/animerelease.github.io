# Repo Map & Architecture

How this repository is laid out and how data flows through it. This file is
**hand-maintained** — unlike `README.md` and most data files, nothing
regenerates it, so it is the safe place for developer-facing notes.

> Forked from [LNRelease](https://github.com/LNRelease/lnrelease.github.io) via
> the manga tracker mangarelease. This fork retargets the same engine at
> licensed **anime physical media** (Blu-ray / DVD / 4K UHD discs). The 5-stage
> pipeline, `session.py`, and the CSV-as-database design are unchanged; the data
> model, sources, and taxonomy are anime-specific (see `SOURCES.md`).
>
> **Migration status:** MediaOCD is the only live source. Sentai Filmworks and
> AllTheAnime are next (SOURCES.md). The `lnrelease/store/*.py` modules and much
> of `lnrelease/publisher/__init__.py` are inherited manga-era code kept only as
> the generic fallback path — a later pass can prune them.

## The one thing to know

Almost every file in the repo root is **load-bearing**, for one of two reasons:

1. **The scrape hardcodes root-relative paths** — `parse.py` opens
   `Path('books.csv')`, `scrape.py` opens `Path('info.csv')`, etc. The
   pipeline runs with the repo root as its working directory.
2. **GitHub Pages / Jekyll serves the site from the root** — `index.html`,
   `data.json`, the `*.md` pages, and `year/` are the published website.

So the flat root is not disorganization you can freely tidy — moving a file
means editing the code constant that points at it **and** checking the Jekyll
site still resolves it. Treat the layout below as the contract.

## Pipeline (runs daily via GitHub Actions)

`.github/workflows/python.yml` runs `python lnrelease/lnrelease.py`, which is
five stages in order:

```
scrape → tag → parse → write → pages
```

| Stage | Module | Reads | Writes |
|-------|--------|-------|--------|
| **scrape** | `scrape.py` + `source/*.py` | source sites (MediaOCD Store API) | `series.csv`, `info.csv` |
| **tag**    | `tag.py`   | `origins.csv` (overrides) | taxonomy applied in-memory |
| **parse**  | `parse.py` + `publisher/__init__.py` | `series.csv`, `info.csv` | `books.csv` |
| **write**  | `write.py` | `books.csv` | `README.md` |
| **pages**  | `pages.py` | `books.csv`, `series.csv` | `data.json`, `html.md`, `year/*.md` |

The workflow then commits changed files as `github-actions[bot]` and, if
`books.csv` changed, calls `pages.yml` to deploy the site.

The commit step stages tracked modifications (`git add -u`) plus `year/`
explicitly, because `pages.py` can mint a brand-new `year/<n>.md` at a year
boundary that a tracked-only add would miss.

## Site pages (`pages.py`)

`pages.py` generates the interactive-site data (`data.json`, consumed by
`index.html`) and the per-format / per-year Markdown pages. It runs as the
final pipeline stage, so these outputs track the scrape day-to-day alongside
the `README.md` calendar. You can also run it standalone
(`python lnrelease/pages.py`) to regenerate the site pages from the current
`books.csv`/`series.csv` without re-scraping.

## File map by role

### Generated output — never hand-edit (rewritten by the pipeline)
| File | Written by | Notes |
|------|-----------|-------|
| `README.md` | `write.py` | GitHub landing page **and** current/upcoming calendar. Opened in `'w'` mode → fully truncated and rebuilt every run. Static prose must live in `write.py`'s header/footer constants (see [Editing the README](#editing-the-readme)). |
| `books.csv` | `parse.py` | Every disc release row (the main dataset). Columns: `serieskey,link,publisher,name,volume,format,upc,catalog,region,edition,date,origin,category`. |
| `series.csv` | `scrape.py` | Series index. |
| `info.csv` | `scrape.py` | Per-product info. Columns: `serieskey,link,source,publisher,title,index,format,upc,catalog,region,edition,date,*alts`. |

### Generated output — site pages (from `pages.py`, final pipeline stage)
| File | Notes |
|------|-------|
| `data.json` | Consumed by `index.html` for the interactive table. Data-row indices 0–7 are stable for the table script; disc fields (catalog, region, edition) are appended at 8–10. |
| `html.md` | Full non-JavaScript calendar (the `<noscript>` target). All discs are physical, so there is no per-format page split. |
| `year/*.md` | One page per calendar year. |

### Hand-maintained input — safe to edit
| File | Read by | Notes |
|------|---------|-------|
| `origins.csv` | `tag.py` | Taxonomy overrides: `slug,origin,category` (category = `TV`/`movie`/`OVA`/`ONA`/`special`). Correct a mis-classified series here (e.g. `akira,JP,movie`). **Primary human-contribution surface.** |
| `corrections.csv` | `parse.py` | Optional `code,date` date fixes (code = catalog number or UPC), for releases whose only street date is unparseable prose. |

### Per-source data/cache — owned by one source module
MediaOCD needs none: its Store API returns the whole catalogue in one paginated
JSON pull, so each run rebuilds the source's rows from the live feed. Future
per-source skip-caches (heavier stores) would live here.

### Code
| Path | Purpose |
|------|---------|
| `lnrelease/lnrelease.py` | Pipeline entry point (scrape→tag→parse→write→pages). |
| `lnrelease/scrape.py`, `parse.py`, `tag.py`, `write.py`, `pages.py` | Pipeline stages. |
| `lnrelease/source/*.py` | One module per **release source**. Currently `mediaocd.py` (WooCommerce Store API). |
| `lnrelease/publisher/__init__.py` | Generic release→Book normalizer (inherited manga volume-parser, used as the fallback for every anime distributor). |
| `lnrelease/store/*.py` | Per-storefront URL identity helpers (inherited; MediaOCD routes to `_default`). |
| `lnrelease/session.py`, `utils.py` | HTTP session (robots-aware) and shared types/helpers (incl. `extract_release_date`). |

### Site infrastructure (Jekyll)
| Path | Purpose |
|------|---------|
| `index.html` | Interactive site homepage; loads `data.json`. |
| `_layouts/`, `_sass/`, `assets/` | Jekyll theme, styles, static assets. |

### Project docs
| File | Purpose |
|------|---------|
| `ARCHITECTURE.md` | This file. |
| `AUDIT.md` | Running engineering audit / decision record. |
| `LICENSE`, `requirements.txt` | Standard. |

## Editing the README

`README.md` is regenerated top-to-bottom every scrape, so **do not edit it
directly** — changes are wiped within a day. To add or change static prose,
edit the constants in `lnrelease/write.py`:

- **Title / tagline** — the `title` string in `main()` (top of the file).
- **Taxonomy legend** — the `TAXONOMY` constant.
- **Footer** — the append block at the end of `main()` (fork note + link to
  this file).

The release tables in between are generated from `books.csv` and cannot be
hand-authored.
