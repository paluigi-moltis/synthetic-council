# ECB "foedb" publications database

## What it is

The ECB website's "All news & publications" pages (e.g.
<https://www.ecb.europa.eu/press/pr/activities/mopo/html/index.en.html>) are not
server-rendered lists. Since the 2024 site redesign they are driven by a
client-side database called **foedb**, downloaded as static JSON chunks from
`www.ecb.europa.eu`. The full corpus contains **every ECB publication since 1992**
(20,028 records as of August 2026): press releases, speeches, working papers,
Economic Bulletin issues, accounts, etc.

For this project it is the authoritative single source for **Governing Council
monetary policy decision announcement dates** (press release title
"Monetary policy decisions", 317 records covering March 1999 – July 2026), with
direct URLs to the press-release documents.

## How the endpoint was discovered

1. The visible page contains only an empty `<div class="foedb-plugin" ...>`.
2. Loading the page in a headless browser (Chromium via CDP, `Network.enable` +
   `Page.navigate`) and recording `Network.requestWillBeSent` events shows the
   JSON URLs the plugin fetches.
3. Reading `foedb.min.js` (`/shared/dist/plugins/foedb/foedb.min.js`) confirms the
   URL scheme (see below) and the chunk math.

Replication snippet (no browser needed once the scheme is known):

```python
# list of tabs → headless chrome --remote-debugging-port=9222 --remote-allow-origins=*
# then attach a WebSocket to the page target and record network requests while
# navigating to any "All news & publications" page.
```

## URL scheme

Base: `https://www.ecb.europa.eu/foedb/dbs/foedb/publications.en/{version}/{hash}/`

- `{version}` and `{hash}` are discovered from `versions.json` (the first entry
  is the current one):

  ```
  https://www.ecb.europa.eu/foedb/dbs/foedb/publications.en/versions.json
  → [{"version":"1787316230","hash":"6GzEKP5S"}]
  ```

| File | Content |
|---|---|
| `metadata.json` | record count, chunk size (250), column header, index list |
| `data/0/chunk_{i}.json` | flat array; every 13 consecutive elements = one record |
| `indexes/{field}/index.json` | facet values (e.g. `year`, `type`) with record counts |
| `indexes/{field}/{value_id}/chunk_{i}.json` | sorted record ids per facet value |

**Pitfall:** the JS builds chunk URLs as `data/{group}/chunk_{id}` where the
*group* directory (`chunk_group_size=1000`) is **always 0** in practice — chunk ids
run 0..80 sequentially under `data/0/`. A naive implementation that varies the
group directory only gets the first ~2,500 records.

## Record schema (13 columns, in order)

| # | Field | Type | Notes |
|---|---|---|---|
| 0 | `id` | int | stable publication id |
| 1 | `pub_timestamp` | int | Unix epoch seconds (CET-based, 14:15 CET for decisions) |
| 2 | `year` | int | publication year |
| 3 | `issue_number` | int | per-year sequence |
| 4 | `type` | str | facet id (see `indexes/type/index.json`) |
| 5 | `JEL_Code` | str/None | pipe-separated JEL codes (research outputs) |
| 6 | `Taxonomy` | str/None | topic tag |
| 7 | `boardmember` | str/None | pipe-separated ECB board member names |
| 8 | `Authors` | str/None | pipe-separated authors (research outputs) |
| 9 | `documentTypes` | list[str] | relative URLs of the documents (all languages) |
| 10 | `publicationProperties` | dict | `Title`, `Subtitle`, `Abstract` where present |
| 11 | `childrenPublication` | list | related child items |
| 12 | `relatedPublications` | list | related items |

Records are **sorted by `pub_timestamp` descending** (newest = chunk 0, id 0).

## Verified counts (2026-08-21)

- Total records: 20,028 (chunks 0–80, 81 returns 404)
- "Monetary policy decisions" (exact title): **317**, first 1999-03-03, last 2026-07-23
- Per-year decision counts match the GC's known cadence exactly:
  - 1999–2001: 20–24/yr (the GC set rates at twice-monthly meetings until
    November 2001)
  - 2002–2014: 12/yr
  - 2015–2025: 8/yr (six-weekly cycle)
  - 2026: 5 through July

## Politeness / stability

- ~81 requests of ~1 MB total fetch the whole database; the collector sleeps
  0.25 s between chunks and sends a descriptive `User-Agent`.
- `{version}/{hash}` change on site rebuilds — **always resolve them via
  `versions.json` at run time**, never hardcode.
