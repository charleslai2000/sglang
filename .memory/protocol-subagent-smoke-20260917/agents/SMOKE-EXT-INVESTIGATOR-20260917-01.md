# Task

Retrieve ONE precise, verifiable public fact: the most recent released patch version of the CPython 3.12 series and its release date.

# Scope

PUBLIC research only. No private source, no internal paths, no hostnames, no non-public data. Only public URLs and public release information.

# Result

- **Most recent CPython 3.12 patch version:** 3.12.14
- **Release date:** 2026-08-12 (August 12, 2026)

The fact IS established with high confidence from two independent public sources.

# Evidence

## Primary Source — python.org downloads page

- **URL:** https://www.python.org/downloads/
- **Retrieved:** 2026-09-17
- **Observation:** The "All releases" table on the Python downloads page lists `Python 3.12.14` with release date `Aug. 12, 2026`. This is the topmost entry in the 3.12 series listing, confirming it is the most recent patch release.

## Independent Source — CPython GitHub repository tags

- **URL:** https://github.com/python/cpython/releases/tag/v3.12.14
- **Retrieved:** 2026-09-17
- **Observation:** The GitHub release page for tag `v3.12.14` shows the tag was applied on `12 Aug 13:57` by `Yhg1s` (T. Wouters). The release title is "Python 3.12.14". The tag is verified (GPG-signed).

## Cross-verification — python.org changelog

- **URL:** https://docs.python.org/3.12/whatsnew/changelog.html
- **Retrieved:** 2026-09-17
- **Observation:** The changelog page for Python 3.12.14 documents `Release date: 2026-08-12`, confirming the date from the downloads page.

## Agreement check

All three sources agree:
- Version: **3.12.14** (python.org downloads, GitHub tag, python.org changelog)
- Date: **2026-08-12** (python.org downloads says "Aug. 12, 2026", GitHub says "12 Aug", python.org changelog says "2026-08-12")

No disagreement found.

# Defects-blockers

None. The fact was established cleanly from multiple independent public sources.

# Remaining claims-exclusions

- The python.org downloads page was fetched as a fallback (JavaScript did not render the dynamic table), but the static HTML contained the full release table with all 3.12 entries including 3.12.14.
- The GitHub tag page was also fetched as a fallback (JavaScript did not render the full release description), but the static HTML contained the tag name, date, and author information.
- The python.org changelog page rendered fully and confirmed the release date.
- No private or non-public data was accessed or disclosed.

# Terminal state

DONE
