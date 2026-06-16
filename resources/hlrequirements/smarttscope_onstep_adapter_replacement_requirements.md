# SmartTScope OnStep Adapter Replacement Requirements

## 1. Purpose

Replace the existing SmartTScope OnStep mount adapter with a safer, more explicit, testable adapter for **direct USB serial control of an OnStep V4 controller**.

The adapter shall support normal mount control, startup safety validation, OnStep limit readback where possible, limit-hit detection, and controlled recovery workflows.

The adapter is intended for a Celestron C8 / EQ mount / OnStep V4 setup where the Raspberry Pi controls the mount through a USB serial connection defined in the SmartTScope configuration file.

## 2. MVP scope decision

### In MVP scope

The MVP shall use **direct USB serial control** of the OnStep controller.

The USB device path, serial parameters, and expected safety policy shall be defined in the SmartTScope YAML configuration.

Example:

```yaml
mount:
  type: onstep_direct_usb
  name: OnStep V4 Terrans
  device: /dev/serial/by-id/usb-OnStep_Controller-if00
  baudrate: 9600
  timeout_seconds: 2.0

  safety:
    require_home_confirmation: true
    require_direction_test: true
    require_limit_readback: true
    allow_unattended_without_limit_readback: false

    expected_horizon_limit_deg: 10.0
    expected_overhead_limit_deg: 85.0
    expected_auto_meridian_flip: false
    expected_preferred_pier_side: east

    expected_meridian_east_limit_min: 12.0
    expected_meridian_west_limit_min: 12.0

    return_home_after_limit_hit: user_confirmed
    allow_auto_return_home: false
```

### Explicitly out of MVP scope

The MVP shall not require an INDI server.

The MVP shall not control OnStep through `pyindi-client` as the primary path.

The MVP shall not share the same serial device concurrently with INDI, KStars/EKOS, or another application.

The MVP shall not assume that OnStep firmware `Config.h` can be changed.

The MVP shall not assume that every safety setting can be modified at runtime.

### Future / optional scope

INDI support may be implemented later as a separate adapter:

```text
MountPort
  ├── OnStepDirectUsbAdapter       # MVP
  ├── OnStepIndiAdapter            # later option
  └── MockMountAdapter             # tests / Windows development
```

The direct USB adapter and future INDI adapter shall expose the same domain-level mount interface.

## 3. Key design principles

1. **Single owner of the OnStep USB connection**

   SmartTScope shall be the only process opening the configured OnStep USB serial device during MVP operation.

2. **Mechanical safety state is separate from astronomical validity**

   SmartTScope shall distinguish between:

   - mechanical mount state: `SAFE`, `UNKNOWN`, `LIMIT_HIT`, `UNSAFE`
   - astronomical coordinate state: `VALID`, `INVALID`, `UNKNOWN`

3. **HOME/PARK confirmation is the safety anchor**

   Time/location correctness is important for GoTo, horizon checks, target planning, and meridian timing, but the primary accident-prevention anchor is that OnStep knows the real mechanical mount position.

4. **Do not continue automation after a limit event**

   If OnStep reports or implies that a limit has been hit, SmartTScope shall stop automated activities and enter a dedicated recovery state.

5. **Read back before trusting**

   SmartTScope shall read back all available safety-relevant settings and status values before enabling unattended automation.

6. **Unsupported readback shall be explicit**

   If a setting cannot be read from the detected OnStep firmware, SmartTScope shall mark it as unsupported instead of silently assuming it is correct.

## 4. Architecture requirements

### REQ-ARCH-001: Adapter replacement boundary

SmartTScope shall replace the existing OnStep adapter with a new direct USB OnStep adapter implementing the existing mount domain port.

The adapter shall not leak OnStep serial protocol details into UI, workflow, or domain logic.

### REQ-ARCH-002: Layered implementation

The adapter shall be split internally into at least these layers:

```text
OnStepDirectUsbAdapter
  ├── SerialTransport
  ├── OnStepProtocolClient
  ├── OnStepStatusParser
  ├── OnStepSafetyReader
  └── OnStepRecoveryController
```

Suggested responsibilities:

| Layer | Responsibility |
|---|---|
| `SerialTransport` | Open, close, read, write, timeout handling |
| `OnStepProtocolClient` | Send OnStep protocol commands and return raw replies |
| `OnStepStatusParser` | Parse status strings and classify mount state |
| `OnStepSafetyReader` | Read limits, pier side, tracking state, HOME/PARK state |
| `OnStepRecoveryController` | Handle limit-hit recovery workflows |

### REQ-ARCH-003: Mockability

Every layer that communicates with hardware shall be mockable.

Unit tests shall be possible without a physical OnStep controller.

### REQ-ARCH-004: No concurrent serial ownership

Before opening the configured USB serial device, SmartTScope shall detect or at least fail clearly if the device is already in use.

If the serial device cannot be opened, SmartTScope shall report a user-facing error such as:

```text
OnStep USB device is not available or is already used by another process.
Close KStars/EKOS/INDI or configure SmartTScope to use another mount adapter.
```

## 5. Configuration requirements

### REQ-CONFIG-001: Direct USB configuration

The mount configuration shall support the following MVP fields:

```yaml
mount:
  type: onstep_direct_usb
  device: /dev/serial/by-id/...
  baudrate: 9600
  timeout_seconds: 2.0
```

### REQ-CONFIG-002: Stable device path required

SmartTScope shall recommend and support `/dev/serial/by-id/...` paths instead of unstable `/dev/ttyUSB0` or `/dev/ttyACM0` paths.

If the configured path looks unstable, SmartTScope should warn the user.

### REQ-CONFIG-003: Safety policy configuration

The configuration shall include an expected OnStep safety policy:

```yaml
mount:
  safety:
    require_home_confirmation: true
    require_direction_test: true
    require_limit_readback: true
    allow_unattended_without_limit_readback: false

    expected_horizon_limit_deg: 10.0
    expected_overhead_limit_deg: 85.0
    expected_auto_meridian_flip: false
    expected_preferred_pier_side: east

    expected_meridian_east_limit_min: 12.0
    expected_meridian_west_limit_min: 12.0
```

### REQ-CONFIG-004: Capability overrides

The configuration shall allow known firmware capability overrides if a Terrans OnStep V4 firmware does not support a specific readback command.

Example:

```yaml
mount:
  capabilities:
    read_horizon_limit: true
    read_overhead_limit: true
    read_axis_limits: true
    read_meridian_limits: false
    read_auto_meridian_flip: true
    read_preferred_pier_side: true
```

If not configured, SmartTScope shall auto-detect capabilities by probing commands safely.

## 6. Connection and protocol requirements

### REQ-CONN-001: Connect

SmartTScope shall open the configured serial device with the configured baud rate and timeout.

If connection fails, SmartTScope shall not offer mount automation.

### REQ-CONN-002: Command logging

The adapter shall support optional debug logging of sent commands and received replies.

Sensitive or excessive logging shall be disabled by default.

### REQ-CONN-003: Timeout handling

If an OnStep command times out, the adapter shall:

1. retry only where safe and configured,
2. mark the specific command as failed,
3. keep the mount state as `UNKNOWN` if the failed command is safety-relevant,
4. block unattended automation if required information is missing.

### REQ-CONN-004: Raw command diagnostic mode

SmartTScope shall provide a diagnostic mode that queries known OnStep commands and writes a capability/readback report.

The report shall include:

- command sent,
- raw reply,
- parsed value,
- parse success/failure,
- whether the value was accepted for safety validation.

## 7. Startup safety requirements

### REQ-START-001: Startup state classification

After connecting to OnStep, SmartTScope shall classify the startup state into one of:

```text
DISCONNECTED
CONNECTED_UNKNOWN
PARKED_CONFIRMED
HOME_CONFIRMED
READY_MANUAL_ONLY
READY_GOTO
READY_UNATTENDED
LIMIT_HIT
ERROR
```

### REQ-START-002: HOME/PARK confirmation

If OnStep reports HOME or PARK, SmartTScope shall ask the user to confirm that the mount is physically in the corresponding HOME/PARK position.

If the user does not confirm, SmartTScope shall block:

- GoTo,
- tracking automation,
- plate-solve correction slews,
- autofocus slews,
- unattended imaging sequences.

Manual slow movement may remain available for recovery.

### REQ-START-003: Direction test

Before enabling unattended automation after a new setup, changed configuration, firmware change, or unknown previous shutdown, SmartTScope shall provide a low-speed direction test.

The user shall confirm that movement directions match SmartTScope’s expectation.

The test should cover:

- RA/AZ positive movement,
- RA/AZ negative movement,
- DEC/ALT positive movement,
- DEC/ALT negative movement.

### REQ-START-004: Tracking disabled until validation

SmartTScope shall not enable tracking automatically until mechanical state and safety settings have been validated.

### REQ-START-005: Astronomical state validation

Before GoTo, target visibility checks, horizon checks, or software-managed meridian planning, SmartTScope shall validate:

- OnStep date/time plausibility,
- OnStep location plausibility,
- local sidereal time plausibility if readable,
- SmartTScope configured site versus OnStep site.

Failure of this check shall be reported as `ASTRONOMICAL_STATE_INVALID`, not as `UNKNOWN_MECHANICAL_STATE`.

## 8. OnStep settings readback requirements

### REQ-READBACK-001: Mandatory readback attempt

Before enabling unattended automation, SmartTScope shall attempt to read back all safety-relevant OnStep settings supported by the firmware.

At minimum, the adapter shall attempt to read:

| Setting / state | Purpose |
|---|---|
| HOME/PARK state | confirm mechanical origin |
| tracking state | know whether mount is moving with sky |
| slewing state | avoid conflicting commands |
| error/status flags | detect faults and limits |
| pier side | verify GEM state |
| horizon limit | lower altitude protection |
| overhead limit | near-zenith protection |
| auto meridian flip state | verify configured safety policy |
| preferred pier side | verify expected behavior |
| axis min/max limits | mechanical travel limits if available |
| meridian East/West limits | hard meridian safety policy if readable |

### REQ-READBACK-002: Known OnStep protocol commands

The direct USB adapter shall support a command map for known OnStep commands.

Minimum command map candidates:

| Purpose | Candidate command |
|---|---|
| get horizon limit | `:Gh#` |
| get overhead limit | `:Go#` |
| get pier side | `:Gm#` or extended status command |
| get general status | `:GU#` / `:Gu#` |
| get local time | `:GL#` |
| get longitude | `:Gg#` |
| get latitude | `:Gt#` |
| get local sidereal time | `:GS#` |
| move to HOME | `:hC#` |
| set current position as HOME | `:hF#` only with strong user confirmation |

The exact supported command set shall be verified against the Terrans OnStep V4 controller in diagnostic mode.

### REQ-READBACK-003: Meridian limit uncertainty

SmartTScope shall not assume that Meridian East/West limits are directly readable on every OnStep V4 firmware.

If direct meridian limit readback is unavailable, SmartTScope shall:

1. mark the values as `UNSUPPORTED_READBACK`,
2. display the configured expected values,
3. warn that direct verification is unavailable,
4. optionally block unattended automation depending on configuration.

### REQ-READBACK-004: Compare readback against policy

For every readable safety value, SmartTScope shall compare the OnStep value against the configured expected policy.

If a value differs beyond tolerance, SmartTScope shall block unattended automation.

Example:

```text
Expected horizon limit: +10.0°
OnStep horizon limit:    +0.0°
Result: FAIL — unattended automation blocked
```

### REQ-READBACK-005: Unsupported fields list

The adapter shall expose a list of unsupported or unreadable fields to the UI.

Example:

```text
Unsupported OnStep readback fields:
- meridian_east_limit_min
- meridian_west_limit_min
```

## 9. Limit-hit detection requirements

### REQ-LIMIT-001: Detect OnStep limit event

SmartTScope shall detect a possible OnStep limit event if one or more of the following occurs:

- OnStep reports a limit or error state,
- tracking unexpectedly stops while automation expected tracking,
- a GoTo/slew command is rejected,
- status indicates stopped/parked/error after a movement command,
- OnStep reports a general error flag after movement or tracking.

### REQ-LIMIT-002: Dedicated LIMIT_HIT state

If a limit event is suspected, SmartTScope shall enter `LIMIT_HIT` state instead of treating it as a generic connection or command failure.

### REQ-LIMIT-003: Stop dependent automation

In `LIMIT_HIT` state, SmartTScope shall stop or suspend:

- imaging sequence execution,
- guiding,
- autofocus movement,
- plate-solve correction slews,
- target re-centering,
- automated filter/exposure workflows that assume a valid mount state.

### REQ-LIMIT-004: Preserve diagnostics

When entering `LIMIT_HIT`, SmartTScope shall capture a diagnostic snapshot:

- timestamp,
- last command sent,
- last raw OnStep reply,
- parsed OnStep status,
- current RA/DEC if readable,
- current pier side if readable,
- tracking state,
- slewing state,
- HOME/PARK state,
- configured safety policy,
- readable OnStep limits.

## 10. Recovery requirements

### REQ-RECOVERY-001: Recovery actions

In `LIMIT_HIT` state, SmartTScope shall offer only controlled recovery actions:

- stop tracking,
- return to HOME,
- park,
- manual slow movement,
- re-read OnStep status,
- re-run HOME/PARK confirmation,
- re-run direction test.

### REQ-RECOVERY-002: No automatic continuation

SmartTScope shall not resume the interrupted imaging sequence automatically after a limit event.

The user shall explicitly revalidate the mount state before automation can continue.

### REQ-RECOVERY-003: Return to HOME

SmartTScope shall provide `Return to HOME` as the preferred recovery action if OnStep accepts the HOME command.

The adapter shall use the OnStep command intended to move to HOME, for example candidate command:

```text
:hC#
```

This command shall be verified against the actual controller.

### REQ-RECOVERY-004: Set HOME protection

SmartTScope shall not send a command to redefine the current position as HOME unless:

1. the user explicitly selects a recovery function for setting HOME,
2. the UI explains the consequence,
3. the user confirms that the mount is physically in the correct HOME position.

Candidate OnStep command:

```text
:hF#
```

This shall be treated as a potentially dangerous operation.

### REQ-RECOVERY-005: Manual recovery mode

Manual recovery movement shall be limited to low speed by default.

SmartTScope shall clearly indicate that the mount is not considered safe for unattended operation until validation is repeated.

### REQ-RECOVERY-006: Recovery success criteria

After recovery, SmartTScope shall require:

- OnStep reachable,
- status readable,
- HOME/PARK state known or user-confirmed,
- safety settings re-read or explicitly accepted,
- astronomical state revalidated if GoTo/automation is required.

Only then may the state change from `LIMIT_HIT` to `READY_GOTO` or `READY_UNATTENDED`.

## 11. Movement command requirements

### REQ-MOVE-001: Pre-command safety gate

Before sending any GoTo, slew, sync, tracking, autofocus-related movement, or plate-solve correction command, SmartTScope shall check the current safety state.

### REQ-MOVE-002: Manual movement exception

Manual low-speed movement may be allowed in `UNKNOWN` or `LIMIT_HIT` state only as a recovery action.

### REQ-MOVE-003: No conflicting commands

SmartTScope shall not send a new motion command while OnStep reports slewing unless the command is an explicit stop/abort command.

### REQ-MOVE-004: Tracking enable policy

SmartTScope shall only enable tracking if:

- mechanical state is confirmed,
- OnStep reports not in error/limit state,
- the mount is not parked,
- safety settings are acceptable,
- astronomical state is valid when target-based tracking is required.

## 12. Meridian safety requirements

### REQ-MERIDIAN-001: Hard limit belongs to OnStep

OnStep meridian limits shall be treated as the hard safety boundary.

SmartTScope shall not plan normal operation up to the OnStep hard limit.

### REQ-MERIDIAN-002: Software margin

SmartTScope shall keep a software margin before the OnStep hard meridian limit.

Before starting an exposure, SmartTScope shall verify:

```text
remaining_time_to_onstep_limit
  > exposure_time
  + camera_download_time
  + guiding_stop_time
  + flip_or_recovery_margin
```

### REQ-MERIDIAN-003: Auto meridian flip policy

For MVP safety, the preferred default policy shall be:

```text
OnStep auto meridian flip: OFF
SmartTScope/KStars-like software flip: future feature or explicitly controlled workflow
OnStep meridian limit: hard stop safety boundary
```

If OnStep auto-meridian-flip is enabled, SmartTScope shall display this clearly and require the setting to match the configured expected policy.

### REQ-MERIDIAN-004: User-visible warning

If meridian limit readback is unavailable, SmartTScope shall warn:

```text
SmartTScope cannot directly verify the OnStep meridian East/West limits on this firmware.
The configured values will be used for planning, but OnStep hard-limit verification is unavailable.
```

## 13. UI requirements

### REQ-UI-001: Separate safety indicators

The UI shall show at least two separate indicators:

```text
Mechanical mount state: SAFE / UNKNOWN / LIMIT HIT / UNSAFE
Astronomical state:     VALID / INVALID / UNKNOWN
```

### REQ-UI-002: OnStep safety panel

The UI shall provide an OnStep safety panel showing:

- connection status,
- HOME/PARK confirmation state,
- direction test state,
- tracking state,
- slewing state,
- pier side,
- horizon limit,
- overhead limit,
- meridian East/West limits if available,
- auto-meridian-flip state,
- preferred pier side,
- unsupported readback fields,
- last safety validation time.

### REQ-UI-003: Startup checklist

The UI shall guide the user through:

1. connect to OnStep,
2. confirm physical HOME/PARK,
3. run direction test if required,
4. read safety limits,
5. validate time/location,
6. enable manual movement,
7. enable GoTo,
8. enable unattended automation.

### REQ-UI-004: Limit-hit recovery screen

When a limit event is detected, the UI shall switch to a recovery screen or prominent recovery mode.

It shall show:

- likely cause,
- last command,
- OnStep status,
- available recovery actions,
- actions that are blocked and why.

## 14. Logging and diagnostics requirements

### REQ-LOG-001: Safety event logging

SmartTScope shall log safety-relevant events at warning or error level:

- connection failure,
- unknown HOME/PARK state,
- failed direction test,
- failed safety readback,
- mismatching safety settings,
- limit-hit event,
- recovery command,
- automation blocked due to safety state.

### REQ-LOG-002: Diagnostic report

SmartTScope shall be able to generate a diagnostic report for OnStep support and debugging.

The report should include:

- SmartTScope version,
- Git hash,
- platform,
- configured mount device,
- serial parameters,
- OnStep command capability results,
- safety policy,
- readback values,
- unsupported fields,
- last status snapshot.

### REQ-LOG-003: Raw protocol trace

A raw protocol trace may be enabled for troubleshooting.

It shall be disabled by default.

## 15. Test requirements

### REQ-TEST-001: Protocol unit tests

The protocol parser shall be tested with recorded raw OnStep replies.

### REQ-TEST-002: No-hardware tests

The adapter shall support tests using a fake serial transport.

### REQ-TEST-003: Startup state tests

Tests shall cover:

- disconnected controller,
- connected but unknown state,
- parked and user confirms,
- parked and user rejects,
- HOME and user confirms,
- unsupported readback field,
- safety mismatch,
- valid state enabling automation.

### REQ-TEST-004: Limit-hit tests

Tests shall cover:

- OnStep status indicates error,
- tracking unexpectedly stops,
- GoTo rejected,
- adapter enters `LIMIT_HIT`,
- dependent automation is stopped,
- recovery actions are limited.

### REQ-TEST-005: Recovery tests

Tests shall cover:

- return HOME command accepted,
- return HOME command rejected,
- park command accepted,
- manual recovery only,
- revalidation required before automation resumes.

### REQ-TEST-006: Configuration tests

Tests shall cover:

- valid direct USB config,
- missing device path,
- unstable `/dev/ttyUSB0` path warning,
- invalid safety policy,
- unsupported capability override.

## 16. Acceptance criteria for MVP

The MVP replacement is accepted when:

1. SmartTScope can connect to OnStep directly via the USB device specified in YAML.
2. SmartTScope can read and display OnStep status.
3. SmartTScope asks the user to confirm HOME/PARK when required.
4. SmartTScope supports a low-speed direction test workflow.
5. SmartTScope attempts safety readback and clearly reports unsupported fields.
6. SmartTScope blocks unattended automation if mandatory safety validation fails.
7. SmartTScope detects likely limit-hit events and enters `LIMIT_HIT` state.
8. SmartTScope offers controlled recovery actions, including return to HOME if supported.
9. SmartTScope never resumes automation automatically after a limit event.
10. Unit tests cover protocol parsing, startup safety, readback failures, limit-hit handling, and recovery transitions.

## 17. Open questions to clarify

These questions should be answered before coding the final adapter behavior.

### Q1. Exact USB serial settings

What baud rate does the Terrans OnStep V4 USB serial interface use in your setup?

Candidate values:

```text
9600
19200
57600
115200
```

The MVP config can support all of them, but the default should match your controller.

### Q2. Exact stable device path

What is the actual path under `/dev/serial/by-id/` on the Raspberry Pi?

Command:

```bash
ls -l /dev/serial/by-id/
```

### Q3. HOME command behavior

Does your Terrans OnStep V4 firmware accept the expected HOME commands?

Commands to verify in diagnostic mode:

```text
:hC#    move to HOME
:hF#    set current position as HOME
```

### Q4. Limit readback support

Which of these commands work on your controller and what do they return?

```text
:Gh#    horizon limit
:Go#    overhead limit
:Gm#    pier side
:GU#    general status
:Gu#    alternate/general status
:GL#    local time
:Gg#    longitude
:Gt#    latitude
:GS#    sidereal time
```

### Q5. Meridian East/West readback

Can Meridian East/West limits be read directly from your firmware?

If not, MVP behavior should be one of:

```text
A. Block unattended automation if meridian readback is unavailable.
B. Allow unattended automation if configured expected values exist, but show warning.
C. Allow only manual/GoTo, block long unattended sequences.
```

Recommended MVP default: **C**.

### Q6. Auto return HOME after limit hit

Should SmartTScope ever return HOME automatically after a limit event, or always require user confirmation?

Recommended MVP default:

```text
Always require user confirmation.
```

### Q7. Manual recovery movement

Should manual movement be possible after a limit event?

Recommended:

```text
Yes, but only low-speed manual movement and with clear warning.
```

### Q8. Direction test frequency

When should SmartTScope require a direction test?

Candidate policy:

```text
- first setup
- after mount config change
- after firmware update
- after serial device change
- after user explicitly resets safety validation
```

### Q9. Interaction with KStars/EKOS

For MVP direct USB mode, should SmartTScope simply block if KStars/EKOS/INDI owns the same serial device?

Recommended:

```text
Yes. MVP direct USB mode shall be single-owner only.
```

### Q10. UI severity

Should a failed limit readback be:

```text
A. warning only
B. blocks unattended automation
C. blocks all movement except manual recovery
```

Recommended default:

```text
B for most missing safety fields.
C for unknown HOME/PARK state.
```

## 18. Implementation note

The first implementation step should be a small standalone OnStep diagnostic script using the same serial transport layer planned for the adapter.

The script should:

1. open the configured USB serial device,
2. send the candidate readback commands,
3. record raw replies,
4. parse known values,
5. generate a capability report,
6. save the report as JSON or Markdown.

This avoids implementing UI behavior before the exact Terrans OnStep V4 command support is known.

