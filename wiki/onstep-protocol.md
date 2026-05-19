# OnStep Command Protocol

**Summary**: The complete LX200-based serial command protocol used by the OnStep V4 mount controller, covering mount slewing, tracking, parking, and focuser control.

**Sources**: https://onstep.groups.io/g/main/wiki/23755 (retrieved 2026-04-24)

**Last updated**: 2026-05-02

---

## Protocol basics

- Commands are framed as `:CC[PPP...]#` — colon, two-character code, optional parameter, hash.
- Maximum command length: 40 chars (2 frame + 2 code + ≤36 parameter).
- CR/LF are accepted but ignored.
- Return values are generally `0` (failure) or `1` (success) unless stated otherwise.
- `[none]` means no reply is sent — do not read after sending.

---

## Mount state — `:GU#`

```
Reply: sss#
```

Returns a status string. Flags confirmed in spec:

| Char | Meaning |
|---|---|
| `N` | Not slewing |
| `H` | At Home position |
| `P` | Parked |
| `p` | Not parked |
| `F` | Park failed |
| `I` | Park in progress |
| `R` | PEC recorded |
| `G` | Guiding in progress |
| `S` | GPS PPS synced |

> **Note for implementation**: The firmware returns a richer pipe-delimited string (`"n|T|0|0|..."`) that includes tracking (`T`) and limit (`E`/`W`) flags not shown in this simplified spec. The `OnStepMount` adapter's flag parsing was written against the observed wire format, not this summary, and should be trusted over the table above.

---

## Slewing / movement commands

| Description | Command | Reply |
|---|---|---|
| Set target RA | `:SrHH:MM:SS#` | 0 or 1 |
| Get target RA | `:Gr#` | `HH:MM:SS#` |
| Set target Dec | `:SdsDD:MM:SS#` | 0 or 1 |
| Get target Dec | `:Gd#` | `sDD*MM'SS#` |
| Set target Azm | `:SzDDD:MM:SS#` | 0 or 1 |
| Set target Alt | `:SasDD:MM:SS#` | 0 or 1 |
| Get telescope RA | `:GR#` | `HH:MM:SS#` |
| Get telescope Dec | `:GD#` | `sDD*MM'SS#` |
| Get telescope Azm | `:GZ#` | `DDD*MM'SS#` |
| Get telescope Alt | `:GA#` | `sDD*MM'SS#` |
| GoTo equatorial target | `:MS#` | `e` (see below) |
| GoTo horizon target | `:MA#` | `e` (see below) |
| Stop all motion | `:Q#` | none |
| Move East | `:Me#` | none |
| Move West | `:Mw#` | none |
| Move North | `:Mn#` | none |
| Move South | `:Ms#` | none |
| Stop East | `:Qe#` | none |
| Stop West | `:Qw#` | none |
| Stop North | `:Qn#` | none |
| Stop South | `:Qs#` | none |
| Pulse guide (d=n/s/e/w, nnnn=ms) | `:Mgdnnnn#` | none |
| Slewing indicator | `:D#` | `0x7F#` while slewing |
| Pier side | `:Gm#` | `N#`, `E#` or `W#` |

**GoTo error codes** (`:MS#` / `:MA#`):

| Code | Meaning |
|---|---|
| 0 | No error |
| 1 | Below horizon limit |
| 2 | No object selected |
| 4 | Position unreachable |
| 5 | Not aligned |
| 6 | Outside limits |

> **Slewing indicator note**: The spec gives reply `0x7F` (DEL, ASCII 127). The current `OnStepMount` adapter checks for `|` (ASCII 124). Verify against the connected firmware version before changing either.

**Slew rates** (`:Rn#`, n=0–9):

| Code | Rate |
|---|---|
| `:RG#` / R2 | 1× sidereal (guide) |
| `:RC#` / R4 | 4× sidereal (center) |
| `:RM#` / R5 | 8× sidereal (move) |
| `:RS#` / R7 | 24× sidereal (slew) |
| R0 | 0.25× |
| R9 | 60× |

---

## Tracking commands

| Description | Command | Reply |
|---|---|---|
| Enable tracking | `:Te#` | 0 or 1 |
| Disable tracking | `:Td#` | 0 or 1 |
| Sidereal rate (default) | `:TQ#` | none |
| Reset sidereal rate | `:TR#` | none |
| Rate +0.02 Hz | `:T+#` | none |
| Rate −0.02 Hz | `:T-#` | none |
| Solar rate | `:TS#` | none |
| Lunar rate | `:TL#` | none |
| King rate | `:TK#` | none |
| Enable refraction compensation | `:Tr#` | 0 or 1 |
| Disable refraction compensation | `:Tn#` | 0 or 1 |
| Set sidereal rate RA | `:STdd.ddddd#` | 0 or 1 |
| Get sidereal rate RA | `:GT#` | `dd.ddddd#` |

---

## Sync command

| Description | Command | Reply |
|---|---|---|
| Sync to current target RA/Dec | `:CS#` | none |
| Sync to current target RA/Dec (LX200) | `:CM#` | `N/A#` |

Syncs that are not allowed (during slew, while parked, limits exceeded) fail silently.

---

## Park commands

| Description | Command | Reply |
|---|---|---|
| Set park position | `:hQ#` | 0 or 1 |
| Move to park position | `:hP#` | 0 or 1 |
| **Restore parked telescope (unpark)** | **`:hR#`** | 0 or 1 |
| Set home (counterweight-down) | `:hF#` | none |
| Move to home | `:hC#` | none |

> **Unpark discrepancy**: The spec defines `:hR#` as the unpark command. The current `OnStepMount` adapter uses `:hU#`. OnStep V4 firmware pre-dates OnStepX and used `:hU#`; `:hR#` was introduced later. **Verify against your firmware version** before changing the adapter. If unpark stops working after a firmware upgrade, switch to `:hR#`.

---

## Focuser commands

Units are **microns or steps** depending on firmware configuration. All positions are integers unless noted.

### Status and configuration

| Description | Command | Reply |
|---|---|---|
| Is Focuser 1 active? | `:FA#` | 0 or 1 |
| Is Focuser 2 active? | `:fA#` | 0 or 1 |
| Select primary focuser (n=1 or 2) | `:FA[n]#` | 0 or 1 |
| Get which focuser is primary | `:Fa#` | 0 or 1 |
| Get motion status | `:FT#` | `M#` (moving) or `S#` (stopped) |
| Get mode (0=absolute, 1=pseudo-absolute) | `:FI#` | 0 or 1 |
| Get max position | `:FM#` | `n#` |
| Get current position | `:FG#` | `n#` |
| Get microns per step | `:Fu#` | `n.n#` |
| Get focuser temperature | `:Ft#` | `n#` |
| Get focuser temperature differential | `:Fe#` | `n#` |

### Movement

| Description | Command | Reply |
|---|---|---|
| Move in (toward objective) | `:F+#` | none |
| Move out (away from objective) | `:F-#` | none |
| Stop focuser | `:FQ#` | none |
| **Move to absolute position n** | **`:FS[n]#`** | **0 or 1** |
| Move by relative amount ±n | `:FR[±n]#` | none |
| Set position as zero | `:FZ#` | none |
| Set position as half-travel | `:FH#` | none |
| Move to half-travel | `:Fh#` | none |

> **Absolute position command confirmed**: `:FS[n]#` (e.g. `:FS1000#` moves to step 1000). This is what `OnStepFocuser.move(position)` must use.  
> Note that `:FS#` with no argument means "set slow speed" — the `[n]` is mandatory when targeting a position.

### Speed control

| Description | Command | Reply |
|---|---|---|
| Set fast speed (1 mm/s) | `:FF#` | none |
| Set slow speed (0.01 mm/s) | `:FS#` | none |
| Set speed rate (n=1 finest … 4=1mm/s) | `:F[n]#` | none |

### Temperature compensation

| Description | Command | Reply |
|---|---|---|
| Get compensation coefficient (µm/°C) | `:FC#` | `n.n#` |
| Set compensation coefficient | `:FC[±n.n]#` | 0 or 1 |
| Get compensation enable status | `:Fc#` | 0 or 1 |
| Enable/disable compensation (n=0 or 1) | `:Fc[n]#` | 0 or 1 |
| Get deadband amount | `:FD#` | `n#` |
| Set deadband amount | `:FD[n]#` | 0 or 1 |

Positive coefficient → focuser moves out as temperature falls.

### Backlash and motor power

| Description | Command | Reply |
|---|---|---|
| Get backlash amount | `:FB#` | `n#` |
| Set backlash amount | `:FB[n]#` | 0 or 1 |
| Get DC motor power level (%) | `:FP#` | `n#` |
| Set DC motor power level (%) | `:FP[n]#` | 0 or 1 |

---

## Date and time

| Description | Command | Reply |
|---|---|---|
| Set date | `:SCMM/DD/YY#` | 0 or 1 |
| Get date | `:GC#` | `MM/DD/YY#` |
| Set local time | `:SLHH:MM:SS#` | 0 or 1 |
| Get local time (24h) | `:GL#` | `HH:MM:SS#` |
| Get sidereal time | `:GS#` | `HH:MM:SS#` |
| Set UTC offset | `:SGsHH#` | 0 or 1 |
| Get UTC offset | `:GG#` | `sHH#` |

---

## Site / location

| Description | Command | Reply |
|---|---|---|
| Set latitude | `:StsDD*MM#` | 0 or 1 |
| Get latitude | `:Gt#` | `sDD*MM#` |
| Set longitude | `:SgDDD*MM#` | 0 or 1 |
| Get longitude | `:Gg#` | `DDD*MM#` |
| Select site n (0–3) | `:Wn#` | none |
| Set/get site n name | `:SM#`–`:SP#` / `:GM#`–`:GP#` | 0 or 1 / name# |

---

## Firmware / misc.

| Description | Command | Reply |
|---|---|---|
| Get firmware name | `:GVP#` | `On-Step#` |
| Get firmware version | `:GVN#` | `3.16o#` |
| Get firmware date | `:GVD#` | `MM DD YY#` |
| Get firmware time | `:GVT#` | `HH:MM:SS#` |
| Set baud rate (6=9600, 7=4800…) | `:SBn#` | 0 or 1 |
| Precision toggle (high/low) | `:U#` | none |
| Reset controller | `:ERESET#` | none |

---

## Adapter implementation notes

### Threading safety (added 2026-05-02)

`OnStepMount` uses a single `pyserial` port shared across all mount methods. Concurrent HTTP requests can race on the port. As of Sprint 37 bugfix, every `_raw_send()` call acquires a `threading.Lock` before the `serial.write()` / `serial.readline()` pair. This prevents byte-interleaving that caused HTTP 500 errors during hardware testing. See [[requirements-addon-20260501]] for the bug report.

**Rule**: never call `serial.write()` outside `_raw_send()` in the mount adapter. All new commands must go through `_raw_send()` or `_send()` to inherit the lock.

### readline() and the `#` terminator

OnStep terminates replies with `#`, not `\n`. `pyserial`'s `readline()` reads until `\n` or timeout. A missing or unexpected reply consumes the full `timeout` (default 2 s). Commands marked `[none]` (no reply) must use `_raw_send()` without reading back — or use a very short per-command timeout if polling frequency matters.

### Commands currently used by `OnStepMount`

| Port method | LX200 command | Notes |
|---|---|---|
| `connect()` | opens serial, then `:Td#` | 9600 baud; sends disable-tracking immediately on connect |
| `get_state()` | `:GU#` | parses P/T/S/E/W flags from wire format |
| `unpark()` | `:hU#` | ⚠ spec says `:hR#` — firmware-version dependent |
| `enable_tracking()` | `:Te#` | returns `1` on success |
| `disable_tracking()` | `:Td#` | called on connect and via API endpoint |
| `get_position()` | `:GR#` + `:GD#` | parses RA hours + Dec degrees |
| `goto()` | `:Sr#` + `:Sd#` + `:MS#` | `MS#` returns `0` for success |
| `sync()` | `:Sr#` + `:Sd#` + `:CM#` | |
| `is_slewing()` | `:D#` | checks for `\|` char in response |
| `stop()` | `:Q#` | no reply |
| `park()` | `:hP#` | no reply — always returns True |
| `guide(d, ms)` | `:Mgdnnnn#` | d=n/s/e/w, nnnn=ms (1–9999); no reply |
| `start_alignment(n)` | `:An#` | n=1–9 stars; returns `1` on success |
| `accept_alignment_star()` | `:A+#` | returns `1` on success |
| `save_alignment()` | `:AW#` | returns `1` on success |

### Safe movement rule (hardware test finding 2026-05-01)

Use **only** `:Mgdnnnn#` (pulse guide) for manual nudge movements — not the continuous move commands (`:Me#`, `:Mw#`, `:Mn#`, `:Ms#`). If a stop command is lost (network drop, UI crash), a continuous move becomes a "mad mount." Pulse-guide commands are self-terminating after `nnnn` milliseconds. See [[requirements-addon-20260501]] for the original requirement.

The guide pads in Stages 3 and 4 of the UI already use pulse guide. Do not introduce continuous-move controls in new UI features.

### Commands needed for `OnStepFocuser` (not yet implemented)

| Port method | LX200 command | Notes |
|---|---|---|
| `connect()` | `:FA#` | returns 1 if focuser active |
| `get_position()` | `:FG#` | returns integer + `#` |
| `move(position)` | `:FS[n]#` | absolute positioning, returns 0 or 1 |
| `is_moving()` | `:FT#` | returns `M#` or `S#` |
| `stop()` | `:FQ#` | no reply |
| `disconnect()` | close serial | |

---

## Related pages

- [[hardware-platform]]
- [[autofocus]]
- [[requirements]]
- [[touptek-sdk]]
