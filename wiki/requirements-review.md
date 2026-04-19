# Requirements Review

**Summary**: External review of the v1 requirements document — verdict, quality critique, retagging rationale, and list of missing requirement areas.

**Sources**: requirements-review (2026-04-19)

**Last updated**: 2026-04-19

---

## Overall verdict

As a **product capability map**, the v1 requirements list is good: right pillars, clear goal, sensible MVP/MVP+/Full structure. As a **real requirements specification**, it is medium quality — many entries are not yet testable, some tags are inconsistent for a C8 system, and critical operational and safety requirements were missing.

The strongest part is that it captured the core "smart telescope" promise: guided startup, automatic alignment, GoTo and centering, live view, [[live-stacking]], target selection, automatic saving, and automation-first UX — matching what current smart telescopes present as baseline user value.

---

## Main quality issues

### 1. Capabilities, not verifiable requirements
Many items were written as topics or intentions rather than testable conditions. Examples: "Health/status dashboard," "Recovery from poor initial pointing," "Smart target filtering," "Thermal and resource stability." These are valid topics but need measurable success criteria (acceptance criteria) before they can be used for sprint planning or acceptance testing.

### 2. Requirements mixed with implementation choices
Several entries described a solution rather than a requirement. Example: "Wide-field assist or staged solve workflow" is an engineering idea — the actual requirement is that the system shall center the target within X arcminutes even when initial pointing error is up to Y degrees. The staged-solve approach is a design decision that satisfies that requirement. This distinction matters: locking implementation into the requirement forecloses better solutions.

The same applies partly to "electronic autofocus — star-size metric, backlash handling."

### 3. Tagging inconsistency for the C8
The v1 document itself noted that wide-field/staged solving, autofocus, recentering, and optical profiles are "near-mandatory" for the C8, but still kept them at MVP+. That is internally inconsistent. Requirements that are near-mandatory for the target hardware belong in MVP.

---

## Retagging decisions

### Promoted to MVP (were MVP+)

| Item | Rationale |
|---|---|
| Persistent optical profiles | Reducer/native/Barlow change FOV, pixel scale, solve profile, and framing — not polish, foundational |
| Wide-field / staged solve workflow | C8 narrow FOV makes blind first-solve success unreliable; near-mandatory in practice |
| Electronic autofocus | Vaonis ships live autofocus as standard; C8 focal length is unforgiving; manual focus damages the "smart" promise |
| Optical train awareness | Correct solving, framing, pixel scale, and warnings all depend on which config is active |
| Automatic recentering | Long focal length amplifies drift; periodic solve-and-correct is essential for long sessions |
| App reconnect / session persistence | Phone disconnects are normal in the field; losing session state would be a critical UX failure |

### Promoted to MVP+ (were Full)

| Item | Rationale |
|---|---|
| Mosaic mode | Vaonis markets live mosaic as a standard differentiating feature; treat as release-2 parity, not distant stretch |
| Scheduled observations | Seestar Plan mode and Vaonis automated sessions are current market features |
| Multi-night continuation | Vaonis ships this; competitive parity, not speculative |
| Refocus triggers | Closer to "expected in a serious product" than to "distant polish" |

### Promoted to MVP (new — were missing)

| Item | Rationale |
|---|---|
| Emergency stop | Hard safety requirement; missing from v1 entirely |
| Solar safety gate | Catalog includes Sun; Seestar explicitly requires filter confirmation before solar observation — legal and safety risk |
| Home/park/unpark/reset state | OnStep detail but a real product requirement, not engineering internals |
| Plate-solve timeout and retry strategy | Part of the alignment product requirement |
| Deterministic file naming and metadata | Needed for usable output |
| Storage-full behavior | Data loss from full storage is a user-visible failure |
| Power-loss handling | File integrity and safe state after power interruption |

---

## Missing sections added to requirements

Six categories were entirely absent from v1:

1. **Connectivity lifecycle** (§2) — Wi-Fi provisioning, first-time pairing, reconnect rules, reboot behavior
2. **Solar safety gate** (§5) — hard requirement inside target catalog section
3. **Operational fallback** (§10) — manual override for focus, slew, and exposure when automation fails; diagnostic mode
4. **Configuration validity** (§11) — app enforces valid optical train combinations; solve profile matched to active config
5. **Performance targets** (§12) — measurable targets for centering accuracy, solve success rate, preview latency, stack refresh, tracking drift, thermal ceiling (all values TBD, need agreement)
6. **Power/storage fault handling** — distributed across §8 and §13

---

## Section-by-section notes

### §1 Startup and usability
Good scope. Profiles promoted to MVP. Missing: explicit device onboarding (Wi-Fi provisioning, first-time pairing) — moved to new §2.

### §3 Alignment and positioning
Strongest section in v1. Wide-field solve promoted to MVP. Added: home/park/unpark handling, solve timeout/retry, centering tolerance (needs AC).

### §4 Focus
Tags too soft for a C8 product. Autofocus and optical-train awareness promoted to MVP. Refocus triggers promoted from Full to MVP+.

### §5 Target selection
Good overall. Critical gap: **solar safety**. Target recommendation engine is nice-to-have; not worth early engineering spend ahead of core robustness.

### §6 Live imaging
Mostly right. Mosaic promoted from Full to MVP+. Planetary mode stays MVP+ as a C8 differentiator.

### §7 Tracking and robustness
Recentering promoted to MVP. Guiding stays MVP+ — but the base unguided performance requirement must be defined first.

### §8 Output
Added: file naming, metadata, storage-full behavior.

### §9 Smartness
Emergency stop added as MVP. Scheduled and multi-night promoted from Full to MVP+ (current market features).

### §13 Non-functional
Weakest section in v1 — nearly nothing is measurable. Most items carry *(needs AC)* flags. Power-loss handling added. Performance targets extracted to dedicated §12.

---

## Bottom line

The v1 list was a **good product roadmap draft** but **not yet an engineering requirements baseline**. The revised [[requirements]] document addresses the major structural issues. Outstanding work before sprint planning:

- Assign concrete values to all items marked *(needs AC)*
- Separate remaining implementation-choice entries from the requirements they serve
- Agree on performance targets in §12

---

## Related pages

- [[requirements]]
- [[smart-telescope]]
- [[hardware-platform]]
- [[plate-solving]]
- [[autofocus]]
- [[live-stacking]]
