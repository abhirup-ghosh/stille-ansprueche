# Data Attribution

## ifo Institute — Sozialleistungen inventory

- **Repository:** https://github.com/ifo-institute/sozialleistungen
- **License:** Creative Commons Attribution-ShareAlike 4.0 International (CC-BY-SA-4.0), per the
  repository's GitHub metadata and LICENSE file.
- **Access date:** 2026-07-21
- **Citation:** ifo Institut (2025), *Eine Inventur im Haus der sozialen Hilfe und Unterstützung*,
  https://www.ifo.de/publikationen/2025/monographie-autorenschaft/eine-inventur-im-haus-der-sozialen-hilfe-und
  Methodology article: https://www.ifo.de/publikationen/2025/aufsatz-zeitschrift/auf-der-suche-nach-passierschein-a38

LICENSE file excerpt:

```
Attribution-ShareAlike 4.0 International

=======================================================================

Creative Commons Corporation ("Creative Commons") is not a law firm and
does not provide legal services or legal advice. Distribution of
Creative Commons public licenses does not create a lawyer-client or
other relationship. Creative Commons makes its licenses and related
information available on an "as-is" basis. Creative Commons gives no
warranties regarding its licenses, any mate
```

## Portal enrichment (Phase 1b)

- **sozialplattform.de** (federal social services portal, operated on behalf of the BMAS):
  plain-language benefit description pages, discovered via `/sitemap.xml` and filtered to
  benefit-name-token candidates. Fetched with a custom User-Agent and crawl-delay 10s per its
  robots.txt.
- **familienportal.de** (federal family portal, BMFSFJ): plain-language benefit description
  pages, discovered via the sitemap index referenced in its robots.txt.
- Both accessed under `robots.txt` permission, cached under `data/raw_html/` (git-ignored),
  content used only as short excerpts appended to the corresponding benefit's corpus text.
- **Result:** 49 / 502 benefits enriched with plain-language text.
