# Requirements

**Summary**: Full requirement set for shipping the SmartTelescope application on the C8 + Raspberry Pi 5 + OnStep V4 platform, tagged MVP / MVP+ / Full. Revised after external review; see [[requirements-review]] for rationale.

**Sources**: SmartTelescope.md, requirements-review (2026-04-19)

**Last updated**: 2026-04-30

---

Requirements are derived from the [[smart-telescope]] category definition and benchmarked against [[seestar-s50]] and [[vaonis-vespera]]. The target [[hardware-platform]] is a Celestron C8 OTA, Raspberry Pi 5, and OnStep V4 mount controller.

**Goal**: A user can power on, connect with an app, choose a target, and the system autonomously aligns, points, tracks, acquires images, improves them live, and saves/shares results — with minimal astronomy knowledge required.

---

## Tag definitions

- **MVP** — minimum to honestly market the product as a smart telescope
- **MVP+** — what users will soon expect in a serious first product
- **Full** — release-2 competitive parity (current Vaonis/Seestar feature floor)

> **Quality note**: Many items below are still written as capabilities, not yet as verifiable requirements. Items marked *(needs AC)* require measurable acceptance criteria before sprint planning. See [[requirements-review]] for the full critique.

---

## 1. System startup and usability

| Requirement | Tag | Notes |
|---|---|---|
| Single guided startup flow — app connects, checks device status, leads user to "ready to observe" | MVP | |
| Health/status dashboard — devices, storage, temp, tracking, power, network | MVP | *(needs AC)* |
| One-button "Start Observation" workflow | MVP | |
| Persistent config profiles — C8 native, C8 + 0.63× reducer, C8 + 2× Barlow | **MVP** | Promoted from MVP+: profiles change FOV, pixel scale, solve profile, and framing — foundational on C8 |
| Beginner mode vs. advanced mode | MVP+ | |

## 2. Connectivity lifecycle

> **New section** — missing from v1. Device onboarding and reconnect are product-level requirements, not engineering plumbing. Current smart telescopes explicitly document first-use pairing flows. *(needs AC on all items)*

| Requirement | Tag |
|---|---|
| Wi-Fi / hotspot provisioning and first-time pairing flow | MVP |
| App reconnect after phone/network drop without losing session state | **MVP** (promoted from MVP+) |
| Defined behavior on app relaunch mid-session | MVP |
| Defined behavior after Pi reboot — safe state, no data loss | MVP |
| Clear connection-state feedback in UI (connecting / connected / lost / recovering) | MVP |

## 3. Autonomous alignment and positioning

| Requirement | Tag | Notes |
|---|---|---|
| Automatic location/time acquisition (phone, network, or GPS) | MVP | |
| Mount connection and safe initialization with OnStep — connect, detect park/unpark, enable tracking, read limits | MVP | |
| Home / park / unpark / reset state handling | MVP | *(needs AC)* — was missing from v1 |
| Automatic sky alignment / [[plate-solving]] — no manual star alignment | MVP | |
| Plate-solve timeout behavior and retry strategy | MVP | *(needs AC)* — was missing from v1 |
| Automatic GoTo + centering correction — solve and recenter to defined tolerance | MVP | *(needs AC: centering tolerance in arcmin)* |
| Wide-field assist or staged "solve wide → solve narrow" workflow | **MVP** | Promoted from MVP+: near-mandatory for C8 narrow FOV |
| Recovery from poor initial pointing (up to Y° error) | MVP+ | *(needs AC: max recoverable pointing error)* |
| Meridian-flip handling with reacquisition and continued stacking | Full | |

## 4. Focus and image readiness

| Requirement | Tag | Notes |
|---|---|---|
| Focus aid — live FWHM/HFR or Bahtinov feedback | MVP | |
| Electronic [[autofocus]] — star-size metric, backlash handling | **MVP** | Promoted from MVP+: Vaonis ships live autofocus as standard; C8 focal length is unforgiving |
| Optical train awareness — pixel scale, FOV, solve profiles per config | **MVP** | Promoted from MVP+: foundational for correct solving, framing, and warnings |
| Refocus triggers — temp drift, filter change, altitude, elapsed time | **MVP+** | Promoted from Full |

## 5. Target selection and observing workflow

| Requirement | Tag | Notes |
|---|---|---|
| Integrated target catalog — Sun/Moon/planets, Messier, NGC/IC, bright objects | MVP | See solar safety below |
| **Solar safety gate** — solar observation requires confirmed filter interlock or explicit user-validated solar mode; Sun must not be slewed to without it | **MVP** | **New — hard safety gap in v1.** Seestar docs explicitly require solar filter installation before solar observation. |
| Smart target filtering — observable now, altitude, moonlight, obstructions | MVP+ | |
| Context-aware warnings — "M51 too low", "Barlow unsuitable for this target", "plate solve may fail at current FOV" | MVP+ | |
| Target recommendation engine — "best objects tonight" | MVP+ | Lower priority than core robustness |

## 6. Live imaging and computational imaging

| Requirement | Tag | Notes |
|---|---|---|
| Live view — low-latency preview with stretch/histogram | MVP | *(needs AC: max preview latency)* |
| [[live-stacking]] for deep-sky objects | MVP | *(needs AC: stack refresh rate)* |
| Automatic stretch / color balance | MVP | |
| Frame quality rejection — bad stars, poor tracking, clouds, vibration | MVP+ | |
| Dark-frame / bad-pixel calibration support | MVP+ | |
| Planetary / lunar lucky-imaging mode (separate from DSO stacking) | MVP+ | Strong C8 differentiator; separate workflow required |
| Mosaic mode | **MVP+** | Promoted from Full: Vaonis markets live mosaic as standard differentiator |

## 7. Tracking, guiding, and acquisition robustness

| Requirement | Tag | Notes |
|---|---|---|
| Tracking state monitoring — detect loss of tracking or mount stall | MVP | |
| Safe mount limits and collision awareness | MVP | |
| Automatic recentering during long sessions — periodic solve-and-correct | **MVP** | Promoted from MVP+: long focal length makes drift more visible and harmful |
| Guiding support — external guider or OAG | MVP+ | Define unguided performance baseline first *(needs AC)* |
| Cloud interruption / temporary loss recovery | Full | |

## 8. Output and data products

| Requirement | Tag | Notes |
|---|---|---|
| Save final enhanced image automatically (JPEG/PNG) | MVP | |
| Deterministic file naming and metadata completeness | MVP | *(needs AC)* — was missing from v1 |
| Storage-full behavior — warning, graceful stop, no corruption | MVP | **New** — was missing from v1 |
| Save original data products — FITS/subframes/metadata/session logs | MVP+ | |
| Observation session summary — target, times, frames, config | MVP+ | |
| Share/export workflow — phone/tablet/NAS/PC | MVP+ | |

## 9. Smartness in the product sense

| Requirement | Tag | Notes |
|---|---|---|
| Automation-first UX — user does not manage mount sync, solving, stacking, stretch, save paths separately | MVP | |
| Self-checks with actionable guidance — "focus poor", "dew risk high", "solve profile mismatch" | MVP+ | |
| Scheduled observations — queue targets or start at given time | **MVP+** | Promoted from Full: Seestar Plan mode and Vaonis automated sessions are current market features |
| Multi-night continuation — resume target, combine results across nights | **MVP+** | Promoted from Full: Vaonis ships this; treat as release-2 competitive parity |
| Emergency stop — immediate halt of all motion and capture | **MVP** | **New** — hard safety gap in v1 |

## 10. Operational fallback

> **New section** — missing from v1. Automation will fail; the product must degrade gracefully rather than becoming a brick. *(needs AC on all items)*

| Requirement | Tag |
|---|---|
| Manual override for focus — user can drive focuser motor directly when autofocus fails | MVP |
| Manual override for slew — user can nudge mount when GoTo/solve loop fails | MVP |
| Manual exposure control — user can set gain/exposure when auto-imaging fails | MVP+ |
| Diagnostic mode — exposes raw camera feed, mount position, solve logs without the normal session flow | MVP+ |

## 11. Configuration validity

> **New section** — missing from v1. The app must prevent impossible or unsafe hardware combinations. *(needs AC)*

| Requirement | Tag |
|---|---|
| Valid optical train combinations enforced — app prevents selecting incompatible reducer/Barlow/camera combos | MVP |
| Solve profile automatically matched to active optical train config | MVP |
| Warning or block for configurations likely to fail plate solving (e.g. Barlow + faint star field) | MVP+ |

## 12. Performance targets

> **New section** — missing from v1. These make non-functional requirements testable. Values are placeholders; all need agreement before implementation. *(needs AC — all values TBD)*

| Target | Tag |
|---|---|
| Time-to-first-image after "Start Observation" — TBD seconds under nominal conditions | MVP |
| Centering accuracy after GoTo — TBD arcmin RMS | MVP |
| Plate-solve success rate — TBD % on first attempt under nominal sky | MVP |
| Live preview latency — TBD ms end-to-end | MVP |
| Live stack refresh rate — TBD seconds between displayed updates | MVP |
| Unguided tracking performance — TBD arcsec/min drift, enabling TBD-second unguided subs | MVP+ |
| Session reliability — complete a TBD-hour unattended session without operator intervention | MVP |
| Pi 5 thermal ceiling — CPU temperature stays below TBD °C during concurrent stacking and solving | MVP |

## 13. Non-functional requirements

| Requirement | Tag | Notes |
|---|---|---|
| Reliable unattended operation — no manual shell access during normal observing | MVP | *(needs AC: session length and conditions)* |
| Clear logging and diagnosability — user log, engineering log, device log, solve log | MVP | *(needs AC: scope and retention)* |
| Local-first operation — define which functions remain available offline | MVP | *(needs AC: offline function list)* |
| Power-loss handling during capture — defined safe state, file integrity after interruption | **MVP** | **New** — was missing from v1 |
| Safe remote update mechanism — versioned updates with rollback | MVP+ | |

## 14. Process requirements

> **New section (2026-04-30)** — These govern how changes are tracked and communicated. They apply to all requirement and implementation work.

| Requirement | Tag | Notes |
|---|---|---|
| **Documentation gate**: a change is not considered done until the corresponding documentation (wiki page, API contract, quickstart, or inline help) is updated | **MVP** | Applies to all sprints; documentation lag is a quality debt |
| **Release traceability**: each requirement carries a "Planned for release" field and a "Implemented in release" field; both are kept current | **MVP** | Enables stakeholder visibility and retrospective audit |

> **Immediate action**: add "Planned" and "Implemented" columns to all requirement tables in §§1–13. Until then, track release info in the sprint log.

---

## MVP core (non-negotiable minimum)

The irreducible set that earns the "smart telescope" label:

1. Guided startup + device onboarding
2. Automatic mount initialization (home/park/unpark)
3. Automatic plate solving / alignment
4. Automatic GoTo + recentering (to defined centering tolerance)
5. Live preview
6. Live stacking for DSO
7. Automatic image enhancement
8. Simple target selection (with solar safety gate)
9. Automatic save/export (with storage-full handling)
10. Emergency stop
11. Robust error/status handling

---

## C8-specific elevations

Items formally tagged MVP+ in the generic smart telescope definition that are treated as **MVP for this platform**:

| Item | Reason |
|---|---|
| Persistent optical profiles | Reducer/native/Barlow change FOV, pixel scale, solve profile — foundational, not polish |
| Wide-field / staged solve workflow | Narrow FOV makes blind solve success unreliable |
| Electronic autofocus | Long focal length is unforgiving; manual focus damages the "smart" promise |
| Optical train awareness | Correct solving, framing, and warnings depend on active config |
| Automatic recentering | Long focal length amplifies drift; periodic recentering is essential |

(source: SmartTelescope.md, requirements-review 2026-04-19)

---

## Related pages

- [[smart-telescope]]
- [[hardware-platform]]
- [[plate-solving]]
- [[live-stacking]]
- [[autofocus]]
- [[requirements-review]]
