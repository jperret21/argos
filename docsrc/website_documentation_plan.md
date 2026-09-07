# Website & documentation plan — ARGOS 0.4.1

This plan keeps the public site and user documentation aligned with the field-tested
scope of ARGOS 0.4.1. It is deliberately an iteration plan: each section is written,
checked against the application, built, and reviewed before the next section starts.

## Editorial rule

Every user-facing statement must be **checkable**: a version, a file format, a
menu path, a setting name, a measured number, or a model. If a sentence contains
none of those, it is decoration — cut it. Prefer the value to the category:
"Gaia G ≤ 18" beats "catalogue depth"; "3.74″/px" beats "sensor assumptions".

Scope and validation status are stated **once, where the reader acts on them**:

1. **The quick-look boundary** — the live curve is uncalibrated and the final
   measurement belongs to Siril and `star_var_script`. Canonical location: the
   abstract of *Method & limits*, plus the scope aside on *Releases*. Everywhere
   else this is a **link**, never a restated paragraph.
2. **Validation status** — an adjective on the thing it qualifies
   ("unvalidated", "technical preview"), not a standalone disclaimer. It belongs
   in the profile table and the package table, where a reader chooses.
3. **External post-processing** — named at the hand-off step, once per page at
   most.

A caveat is written in the same register as the claim it qualifies: "Will not
accept raw files", not "may have limited support for". Do not present planned
features, illustrative curves, or synthetic examples as a scientific result.

**Why this changed (September 2026).** The previous rule required all three
categories on *every* statement. Applied per sentence rather than per site, it
produced 26 restatements of the quick-look disclaimer across six pages and 44
negative constructions — 19 on *Method & limits* alone, one every 62 words.
Past the third repetition each restatement reduces the credibility of the
others: a reader told 26 times not to trust the curve concludes the curve is
worthless. Repetition is not rigour.

## Anti-patterns

Checked against siril.org, ASTAP, PHD2, N.I.N.A., AstroImageJ, KStars,
Stellarium and INDI. None of them do any of the following:

- Headings that exhort rather than label ("Show less, learn more", "Put your
  telescope to scientific work"). Headings are noun phrases naming a task or an
  object.
- A capability described in a paragraph where a bullet would do.
- Praise adjectives on a feature ("flexible", "powerful", "seamless"). The
  capability is the claim.
- Generic nouns where a name exists — "astronomical catalogues" instead of
  Gaia DR3 / VSX / SIMBAD / VSP / NASA Exoplanet Archive.
- Caveats quarantined away from the claim they qualify.
- Mission, vision, or founding-story sections.
- A download without its version, date, architecture and size.

## What the public site must answer

| Reader question | Page / section | 0.4.1 answer |
| --- | --- | --- |
| What is ARGOS for? | Home | An observing workspace for variable-star and exoplanet time series with Seestar telescopes. |
| Is my instrument supported? | Instruments | A clear profile/validation matrix for S30 Pro, S30, S50 and absent models. |
| What do I need before observing? | Get started | Package, ASTAP, star database, observing location, telescope profile and working folder. |
| What happens during a night? | First observation | Prepare → identify field → choose target/ensemble → acquire → review. |
| What does a live curve mean? | Method & limits | A quality-control preview, not a calibrated or publishable final curve. |
| How do I recover from a problem? | Troubleshooting | ASTAP, connection, catalogue, FITS/session and support-bundle paths. |
| What is in this release? | Releases | Installers, exact changes, known limits, versioned field guide. |

## Public information architecture

### 1. Home — product overview

Keep it short and factual. It should link to the first-observation guide, the
instrument matrix, the method/limits page and the current release. It must not carry
long technical explanations or provisional scientific results.

### 2. Get started — first observation

Create a concise, task-oriented public guide from the existing 0.4.1 field guide:

1. install ARGOS;
2. install and verify ASTAP plus its star database;
3. set observer location, working directory and telescope profile;
4. connect the telescope and acquire a first frame;
5. solve and identify the field;
6. select target and comparison stars;
7. run a sequence and review it;
8. hand raw data to Siril / `star_var_script`.

This is the first documentation page to write in the next iteration.

### 3. Field identification — practical reference

Explain the user-visible layers and controls: plate solution, source types, magnitude
limit, labels, selected objects, target/comparison/check roles, catalogue/cache
behaviour and what an unresolved or unmatched source means. Include a short
troubleshooting panel for ASTAP and catalogue lookup.

### 4. Method & limits — replace the current Science results page

Retain the useful methodological content, but remove claims or charts presented as
results unless a reproducible reduction and data release support them. The page should
explain:

- raw FITS versus display data;
- green-plane measurement and differential ensemble preview;
- why target, comparison and check stars are distinct;
- what ARGOS records during acquisition;
- what must still be calibrated, registered and validated in post-processing;
- known instrumental and field-validation limits.

### 5. Instruments & prerequisites

Keep the existing profile information, but turn it into a compact support matrix:
model, sensor profile, connection path, validation status, and important caveats.
Document macOS, Debian/Ubuntu, ASTAP and external catalogue dependencies separately
from the telescope profile itself.

### 6. Review, data and support

Document what a session folder contains, how Review links curves back to FITS frames,
which files are safe to move, and how the privacy-safe local support bundle works.

### 7. Releases

Each release page needs package availability, installation caveats, field-validation
status, a linked field guide, and a human-written changelog. Generated artifacts are
not a substitute for release notes.

## Documentation split

| Audience | Location | Content |
| --- | --- | --- |
| Observer | Public site + concise guides | Installation, first observation, field identification, Review, troubleshooting. |
| Scientific user | Method & limits | Measurement semantics, data provenance, limits and hand-off to final reduction. |
| Developer | Sphinx API and technical plans | Architecture, implementation plans, API reference and tests. |

Technical plans such as `photometry_plan.md` and `release_0_4_1.md` are sources for
maintainers, not landing pages for observers.

## Language policy

The public site is English so it can serve the wider observing community. Existing
French field material remains useful during validation, but should be explicitly
labelled and translated or consolidated before it is linked as the primary public
guide. Do not silently mix languages within one navigation path.

## Iteration checklist

- [ ] **Iteration 1 — Get started:** write the first-observation page; check every
  action and setting against the 0.4.1 UI; link it from Home and Releases.
- [ ] **Iteration 2 — Field identification:** promote the practical reference and
  add ASTAP/catalogue troubleshooting.
- [ ] **Iteration 3 — Method & limits:** replace unsubstantiated public results with
  reproducible method and scope.
- [ ] **Iteration 4 — Instruments:** publish the support/validation matrix and
  prerequisites.
- [ ] **Iteration 5 — Review & support:** document session data, Review and the
  support bundle.
- [ ] **Iteration 6 — Release and maintenance:** check every link, build the site,
  add a version/update marker and publish the site branch.

## Benchmark lessons applied

Comparable tools make scope and workflow explicit: Siril separates installation,
versioned documentation and tutorials; AstroImageJ distinguishes calibrated
differential photometry from real-time workflow. ARGOS must be equally explicit about
where acquisition/preview ends and final reduction begins.
