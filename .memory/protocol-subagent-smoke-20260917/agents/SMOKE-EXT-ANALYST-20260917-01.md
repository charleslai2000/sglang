# Task

Synthesize the run's already-gathered PUBLIC external evidence into ONE calibrated judgment for a long-lived production deployment that pins the CPython 3.12 series, assessed as of 2026-09. State what an operations owner should conclude.

# Scope

- PUBLIC evidence only. No private source, no internal paths, no hostnames, no non-public data.
- Two input artifacts used:
  - `agents/SMOKE-EXT-INVESTIGATOR-20260917-01.md` — establishes CPython 3.12.14 as the latest 3.12 patch, released 2026-08-12, per 3 public sources.
  - `agents/SMOKE-EXT-RESEARCHER-20260917-01.md` — CPython release-cadence model; support phases; 18-month vs 24-month bugfix divergence; source quality ratings.
- No network calls were made during synthesis; reasoning is over the supplied evidence only.

# Result

**Judgment (one paragraph with explicit confidence):** An operations owner pinning CPython 3.12 for a long-lived production deployment should conclude that the series is in its **security-only support phase** as of September 2026, with no further bugfix or feature releases expected. The latest patch (3.12.14, released 2026-08-12) is the final maintenance opportunity within the bugfix window, and the series will transition to pure source-only security fixes until end-of-life approximately 5 years after the 3.12.0 release (October 2023), placing EOL around October 2028. **Confidence level: HIGH.** This is justified because (a) the investigator artifact establishes 3.12.14 as the latest patch from three independent, cross-verified public sources with no disagreement, and (b) the researcher artifact establishes — with explicit source attribution and empirical corroboration from endoflife.date — that the 3.12 series used an 18-month bugfix phase (not 24 months), meaning active bugfix support ended around April 2025 and the series has been in the security-only phase since then. The confidence is HIGH rather than maximal only because the inputs do not explicitly state a confirmed date for the 3.12 security-only transition weekend (they triangulate it from the 18-month rule + release date), and because the researcher artifact's source quality ratings note that endoflife.date is a secondary tracker (★★★☆☆) rather than an authoritative CPython source.

**Supporting evidence (each attributed to its input artifact):**

| Element | Source artifact | What it establishes |
|---|---|---|
| CPython 3.12.14 is the latest 3.12 patch, released 2026-08-12 | SMOKE-EXT-INVESTIGATOR-20260917-01 | The most recent bugfix release in the 3.12 series at the time of assessment |
| Three independent public sources agree on version and date (python.org downloads, GitHub tag v3.12.14, python.org changelog) | SMOKE-EXT-INVESTIGATOR-20260917-01 | No disagreement among sources; high-confidence fact establishment |
| CPython 3.12 bugfix phase duration is 18 months (not 24 months) | SMOKE-EXT-RESEARCHER-20260917-01 | PEP 602 note + devguide + endoflife.date collectively confirm 18 months for versions 3.9–3.12 |
| 3.12 entered security-only mode ~April 2025 | SMOKE-EXT-RESEARCHER-20260917-01 | Derived from 18-month rule applied to 2023-10-02 release date; corroborated by endoflife.date empirical data for 3.12 |
| Total support lifecycle is 5 years (EOL ~October 2028 for 3.12) | SMOKE-EXT-RESEARCHER-20260917-01 | devguide versions page + endoflife.date: "Five years after a release, support ends" |
| PEP 602 is the authoritative specification (★★★★★); endoflife.date is secondary (★★★☆☆) | SMOKE-EXT-RESEARCHER-20260917-01 | Source quality ratings inform how much weight to give each piece of evidence |

**Strongest counterevidence (stated at full strength, not a strawman):**

The strongest alternative reading is that **an operations owner should NOT assume 3.12 is secure-even-with-source-only-fixes and should instead plan a migration to 3.13 or later.** This reading is supported by the researcher artifact's own data: (1) PEP 602 specifies 24 months of full bugfix support for versions ≥3.13, meaning 3.13+ receives more robust maintenance than 3.12 did; (2) the 18-month bugfix window for 3.12 means the series has been in the security-only phase for approximately 17 months as of September 2026, accumulating a growing backlog of unpatched security-adjacent issues that only source-only fixes address; (3) endoflife.date (secondary source, last updated 2026-08-14) may not reflect the most recent security branch activity; and (4) the investigator artifact confirms that 3.12.14 is the latest bugfix, but does not address whether any security fixes have been applied since the bugfix window closed — it only confirms the latest bugfix release date. This counterevidence does not overturn the core judgment (3.12 is in security-only phase), but it reframes the risk posture from "stable and maintained" to "stable but declining in maintenance intensity."

**Explicit conditions that would CHANGE the judgment:**

1. **If a newer 3.12.x patch (e.g., 3.12.15) is released after 2026-08-12**, the investigator's fact that 3.12.14 is the latest patch would be invalidated, and the bugfix-phase assessment would need to be revisited — though the 18-month rule would still apply to the overall phase boundary.
2. **If PEP 602 were amended or a new PEP were accepted to re-extending bugfix support for 3.9–3.12 to 24 months**, the entire 18-month vs. 24-month divergence would be resolved in favor of continued active bugfix support, fundamentally changing the risk posture.
3. **If endoflife.date or the devguide versions page were updated to show 3.12 EOL earlier than ~October 2028** (e.g., due to an accelerated end-of-life decision), the total-support-duration claim would change.
4. **If the researcher artifact's source quality ratings were revised** — for example, if endoflife.date were upgraded to a primary source or if PEP 602's note on 18-month support were found to apply only to a subset of 3.12 sub-versions — the confidence level would need to be downgraded or the judgment reframed.
5. **If an operations owner's deployment includes a distribution (e.g., Ubuntu, RHEL) that backports additional bugfix or security patches onto CPython 3.12**, the CPython-level support phase alone is insufficient to assess the actual patch posture of the deployed runtime. The researcher artifact explicitly excludes distribution-specific schedules.

**Separation of what the inputs ESTABLISH versus what is INFERENCE:**

| Category | Content | Attribution |
|---|---|---|
| **ESTABLISHED by inputs** | CPython 3.12.14 is the latest 3.12 patch release (version and date) | Investigator artifact, cross-verified by 3 public sources |
| **ESTABLISHED by inputs** | CPython 3.12 bugfix phase is 18 months (not 24), per PEP 602 note + devguide + endoflife.date | Researcher artifact, all three cited sources |
| **ESTABLISHED by inputs** | Total CPython support is 5 years from first release | Researcher artifact, devguide + endoflife.date |
| **ESTABLISHED by inputs** | PEP 602 is the authoritative specification (★★★★★); endoflife.date is secondary (★★★☆☆) | Researcher artifact, source quality table |
| **INFERENCE (my synthesis)** | As of September 2026, the 3.12 series is in the security-only phase (~17 months into it) | Derived by applying the 18-month rule to the 2023-10-02 release date; the inputs provide the rule and the date but do not explicitly state "security-only as of 2026-09" |
| **INFERENCE (my synthesis)** | The confidence level is HIGH (not maximal) | Derived from the strength of cross-verification in the investigator artifact and the secondary-source caveat in the researcher artifact |
| **INFERENCE (my synthesis)** | The risk posture is "stable but declining in maintenance intensity" | Interpretation of what security-only phase means for operations, not a direct claim from either input |
| **INFERENCE (my synthesis)** | The counterevidence reasoning about migration urgency | Synthesized from the researcher artifact's data on 3.13's 24-month bugfix window and the 18-month 3.12 window |

**Disagreements between inputs and weaker-source analysis:**

- **No direct disagreement** exists between the two input artifacts. The investigator artifact establishes a fact (latest 3.12 patch = 3.12.14, released 2026-08-12) that is consistent with and complementary to the researcher artifact's cadence model (18-month bugfix phase for 3.12). There is no conflict to resolve.
- **Relative weakness in the researcher artifact:** The source quality table rates endoflife.date as ★★★☆☆ (secondary, third-party tracker). This means any claim that depends heavily on endoflife.date's empirical dates (e.g., the precise date 3.12 entered security-only mode) carries less weight than claims that depend only on PEP 602 or the devguide. The judgment mitigates this by triangulating the 18-month rule from PEP 602's note and the devguide as well, not relying solely on endoflife.date.
- **Relative weakness in the investigator artifact:** The investigator artifact does not address the support lifecycle or phase model at all. It is limited to establishing a single release fact. Any judgment about the support phase (security-only, bugfix-closed, etc.) must come from the researcher artifact — the investigator artifact cannot independently support that inference.
- **How these weakenings affect the judgment:** The HIGH confidence level is deliberately capped because the investigator artifact alone cannot establish the support phase, and the researcher artifact's most impactful empirical date (3.12 security-only transition) relies partly on the secondary endoflife.date source. If either artifact were found to have a factual error, the confidence would need to be revised downward.

# Defects-blockers

None identified in the synthesis. Both input artifacts are in DONE terminal state, contain no internal defects, and their facts are consistent with each other.

# Remaining claims-exclusions

- The assessment does not cover distribution-level packaging (e.g., Ubuntu, Debian, RHEL) which may apply additional patches or have different support timelines for CPython 3.12. The researcher artifact explicitly excludes distribution schedules.
- The assessment does not cover pre-3.12 series or future 3.13+ series except as relevant context for the counterevidence (3.13's 24-month bugfix window).
- The assessment does not cover internal CPython governance discussions, private mailing list deliberations, or unpublished security advisories.
- The claim that the 3.12 security-only transition occurred ~April 2025 is an inference from the 18-month rule applied to the 2023-10-02 release date; the inputs do not explicitly confirm the exact transition date for 3.12 from endoflife.date (they note the site confirms the 18-month pattern empirically but the specific 3.12 transition date is shown as an example, not as a directly verified input to this synthesis).
- No private or non-public data was accessed or disclosed at any point.

# Terminal state

DONE
