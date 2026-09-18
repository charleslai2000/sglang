# CPython Release Cadence — Public Research Synthesis

## Task

Conduct a bounded public research synthesis comparing how the CPython project defines and communicates its RELEASE CADENCE, and report the conflicts between sources.

## Scope

- Public research only. No private or local project data was accessed.
- Three public sources were consulted: two primary/authoritative and one secondary.
- The research question: How does CPython publicly define its release cadence (feature, bugfix, security releases, and their support durations), and where do public sources disagree or diverge?

## Result

### Cadence Model (synthesized from sources)

CPython's release cadence is defined across two dimensions: (1) the **development cycle** for a new feature version, and (2) the **support lifecycle** after a feature version is released.

#### Development Cycle (per feature version)

| Phase | Duration | Description | Source |
|-------|----------|-------------|--------|
| Pre-alpha / Overlap | ~5 months | Development overlaps with previous version's beta/RC; unversioned | PEP 602 |
| Alpha | ~7 months | Versioned alpha releases; new features + bug fixes accepted | PEP 602 |
| Beta | ~3 months | Four versioned beta releases; no new features, bug fixes only | PEP 602 |
| Release Candidate | ~2 months | Two RCs (or more); stability focus | PEP 602 |
| Final | — | Release of 3.X.0 | PEP 602 |

Total development: ~17 months. Feature versions are released annually in October (PEP 602, "Annual Release Cadence").

#### Support Lifecycle (per released 3.X series)

| Phase | Duration | What is accepted | Binaries? | Source |
|-------|----------|-----------------|-----------|--------|
| Bugfix (maintenance/stable) | 18 months for ≤3.12; 24 months for ≥3.13 | Bug fixes + security fixes | Yes, ~every 2 months | PEP 602 (note), devguide versions page, endoflife.date |
| Security | Remaining ~3–3.5 years | Security fixes only | Source-only, as needed | PEP 602, devguide versions page, endoflife.date |
| End-of-life | 5 years after first release | No further changes | Frozen | devguide versions page, endoflife.date |

**Per-element source attribution:**

- "Feature release" = a new minor version (3.X.0) released annually: PEP 602, devguide development-cycle page.
- "Bugfix release" = a micro version >0 produced from a maintenance branch: devguide development-cycle page ("new micro versions are bugfix releases; they get released roughly every 2 months").
- "Security release" = a source-only micro version produced from a security branch after the bugfix phase ends: devguide development-cycle page ("only changes fixing issues exploitable by attackers are backported").
- "5 years total support" = devguide versions page ("end-of-life" status key: "Five years after a release, support ends") and endoflife.date ("The end-of-life is scheduled 5 years after the first release").

### Conflicts and Divergences

#### Conflict 1: Duration of the bugfix (full support) phase — 18 months vs. 24 months

This is the most significant divergence and is **explicitly acknowledged by PEP 602 itself**:

- **PEP 602** (§ "2 years of full support, 3 more years of security fixes") states the bugfix phase is "twenty four months (2 years)" and the security phase is "thirty six months (3 years)."
- **However**, PEP 602 includes a note: "2 years of full support start with Python 3.13. Python versions 3.9 - 3.12 operate on a calendar with 1½ year of full support, followed by 3½ more years of security fixes."
- **The devguide versions page** states the security phase begins "After two years (18 months for versions before 3.13)."
- **endoflife.date** confirms this empirically: Python 3.12 (released 2023-10-02) entered security-only mode on 2025-04-02 (~18 months), and Python 3.13 (released 2024-10-07) has active support until 2026-10-01 (~24 months).

**Interpretation:** PEP 602 originally specified 24 months of bugfix support, but the actual implementation for versions 3.9–3.12 used 18 months. PEP 602 was amended via a note to reflect this historical reality, and 3.13+ finally implements the originally specified 24 months. The devguide and endoflife.date reflect the actual/operational cadence, not the originally proposed one.

#### Conflict 2: "Feature release" — development phase vs. support status

- **PEP 602** uses "feature release" to mean the 3.X.0 release event and the ~17-month development cycle leading to it. It does not define "feature release" as a support status.
- **The devguide versions page** defines "feature" as a support status meaning "Before the first beta, the next full release can accept new features, bug fixes, and security fixes." This is the active development window, not a post-release support phase.
- **The devguide development-cycle page** defines "feature release" as a minor version release ("new minor versions are feature releases; they get released annually").

**Interpretation:** The term "feature release" is used in two different senses: (a) the annual 3.X.0 event and its development cycle (PEP 602), and (b) the pre-beta development phase of a branch (devguide). These are not contradictory but can confuse readers who expect a single consistent definition.

#### Conflict 3: "Security release" cadence — "as-needed" vs. no explicit schedule

- **PEP 602** says security updates are "source-only releases are made on an as-needed basis (no fixed cadence)."
- **The devguide** says security branch releases are "source-only and done only when actual security fixes have been applied" and are "coordinated with the release manager."
- **endoflife.date** does not attempt to model the security release cadence; it only tracks the start/end of the security support window.

**Interpretation:** No real conflict here — all three sources agree there is no fixed cadence for security releases. The divergence is only in the level of specificity.

#### Conflict 4: endoflife.date "Active Support" end dates vs. PEP 602's "2 years"

- **endoflife.date** shows Python 3.13 "Active Support" ending 2026-10-01 (exactly 2 years after 2024-10-07 release) and Python 3.12 "Active Support" ending 2025-04-02 (~18 months after 2023-10-02 release).
- **PEP 602** states 24 months of full support starting with 3.13.
- **PEP 602** has a note that 3.9–3.12 used 18 months.

**Interpretation:** endoflife.date's data is consistent with both PEP 602's note and the devguide's "18 months for versions before 3.13" rule. No conflict with the sources, but the site does not explicitly call out the 18-month vs. 24-month distinction in its UI — it simply shows dates.

### Source Quality Ratings

| Source | Type | URL | Retrieved | Quality Rating | Rationale |
|--------|------|-----|-----------|----------------|-----------|
| PEP 602 | Primary (authoritative specification) | https://peps.python.org/pep-0602/ | 2026-09-17 | ★★★★★ | The formal PEP that defines the annual release cycle. Authoritative, versioned, reviewed by the Steering Council. Contains its own note acknowledging the 18-month vs. 24-month divergence. |
| Python Developer's Guide — Status of Python versions | Primary (official operational reference) | https://devguide.python.org/versions/ | 2026-09-17 | ★★★★★ | Maintained by the CPython project. Defines the five support phases with explicit descriptions and links to PEP 602. Reflects the current operational state including branch statuses and EOL dates. |
| endoflife.date — Python | Secondary (third-party tracker) | https://endoflife.date/python | 2026-09-17 | ★★★☆☆ | Useful for empirical verification of release dates and support windows. Not an official CPython source. Last updated 2026-08-14. Does not define the cadence model itself — it tracks it. Data is consistent with primary sources but provides no original analysis. |

## Evidence

- PEP 602, § "2 years of full support, 3 more years of security fixes": https://peps.python.org/pep-0602/#years-of-full-support-3-more-years-of-security-fixes
- PEP 602, § "Annual release cadence": https://peps.python.org/pep-0602/#annual-release-cadence
- PEP 602, note on 18-month support for 3.9–3.12: same section as above
- devguide versions page, Status key: https://devguide.python.org/versions/#status-key
- devguide versions page, Supported versions table: https://devguide.python.org/versions/#supported-versions
- devguide development-cycle page, Branches and Stages: https://devguide.python.org/developer-workflow/development-cycle/
- endoflife.date/python: https://endoflife.date/python

## Defects-blockers

- None. The research was completed without blockers. All three sources were accessible and returned valid content.

## Remaining claims-exclusions

- This synthesis covers CPython's public-facing release cadence documentation only. It does not cover:
  - Internal CPython governance discussions or private mailing list deliberations.
  - The release schedules of individual distributions (e.g., Fedora, Ubuntu) which may deviate from CPython's cadence.
  - Pre-3.9 release cadence (PEP 602 applies from 3.9 onward; older versions followed an 18-month cadence with less formal documentation).
  - PEP 719 (3.13 release schedule) and later PEPs that may refine the model further — these were not consulted but are referenced by the devguide versions page.
- The claim that "no genuine conflict was found" in some areas (e.g., security release cadence) is based on the absence of contradictory statements across sources, not on a systematic search for conflicts in every possible dimension.

## Terminal state

DONE
