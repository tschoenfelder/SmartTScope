# SmartTScope — Architecture Diagrams

**Last updated**: 2026-04-21

---

## 1. System context (C4 level 1)

Who uses the system and what it touches externally.

```mermaid
C4Context
    title SmartTScope — System Context

    Person(user, "Observer", "Amateur astronomer. Uses mobile or web app to start and monitor sessions.")

    System(smarttscope, "SmartTScope", "Autonomous telescope control. Aligns, slews, captures, stacks, and saves without manual astronomy steps.")

    System_Ext(astap, "ASTAP", "Local plate-solver CLI with star catalog (G17). Runs on the Pi.")
    System_Ext(onstep, "OnStep V4", "Open-source GoTo mount controller. Serial protocol over USB/UART.")
    System_Ext(touptek, "ToupTek Camera", "Imaging sensor. INDI or ToupTek SDK over USB.")
    System_Ext(focuser, "Motorised Focuser", "Electronic focuser. INDI or direct USB.")

    Rel(user, smarttscope, "Selects target, monitors session, receives stacked image", "Wi-Fi / REST + WebSocket")
    Rel(smarttscope, astap, "Submits FITS frame, receives RA/Dec solution", "subprocess / CLI")
    Rel(smarttscope, onstep, "Connect, unpark, track, sync, GoTo, stop", "LX200 serial")
    Rel(smarttscope, touptek, "Connect, capture frame (FITS)", "ToupTek SDK / INDI")
    Rel(smarttscope, focuser, "Connect, move, read position", "INDI / USB")
```

---

## 2. Container architecture (C4 level 2)

The internal runtime components and how they communicate.

```mermaid
C4Container
    title SmartTScope — Container Architecture

    Person(user, "Observer", "Mobile or web browser")

    Container(api, "Session API", "FastAPI (Python)", "REST endpoints for session control. WebSocket for live frame push.")
    Container(runner, "Workflow Engine", "Python — VerticalSliceRunner", "Executes the 9-stage pipeline. Manages state machine. Owns session log.")
    Container(domain, "Domain Model", "Python dataclasses", "SessionLog, SessionState, OpticalProfile, StageTimestamp.")
    ContainerDb(storage, "Local Storage", "Filesystem (ext4 / SD card)", "Stacked PNG, JSON session log, FITS sub-frames (MVP+).")

    System_Ext(astap, "ASTAP CLI", "Local plate-solver")
    System_Ext(mount, "OnStep V4", "Mount controller")
    System_Ext(camera, "ToupTek Camera", "Imaging sensor")

    Rel(user, api, "POST /session/start, GET /session/status, WS /session/frames", "HTTPS / WSS")
    Rel(api, runner, "Start session (target, optical profile)", "Function call / async task")
    Rel(runner, domain, "Reads and writes session state", "")
    Rel(runner, storage, "Saves PNG and session log", "StoragePort")
    Rel(runner, astap, "Submits FITS, reads INI result", "SolverPort → AstapSolver")
    Rel(runner, mount, "Connect, GoTo, sync, stop", "MountPort → OnStepAdapter (planned)")
    Rel(runner, camera, "Connect, capture FITS", "CameraPort → ToupTekAdapter (planned)")
    Rel(runner, api, "State change callbacks, frame push", "StateCallback / WebSocket")
```

---

## 3. Module / hexagonal architecture

The internal code structure showing the Ports & Adapters pattern.

```mermaid
graph TD
    subgraph Client["Client Layer (planned)"]
        APP["Mobile / Web App"]
        FASTAPI["FastAPI — Session API"]
    end

    subgraph Workflow["Workflow Layer"]
        RUNNER["VerticalSliceRunner\nrunner.py"]
    end

    subgraph Domain["Domain Layer"]
        STATES["SessionState\nstates.py"]
        SESSIONLOG["SessionLog\nsession.py"]
        OPTPROFILE["OpticalProfile\nrunner.py"]
    end

    subgraph Ports["Port Interfaces (ABCs)"]
        CAMPORT["CameraPort"]
        MNTPORT["MountPort"]
        SLVPORT["SolverPort"]
        STKPORT["StackerPort"]
        STRPORT["StoragePort"]
    end

    subgraph Adapters["Adapter Layer"]
        subgraph Mock["mock/"]
            MCAM["MockCamera"]
            MMNT["MockMount"]
            MSLV["MockSolver"]
            MSTK["MockStacker"]
            MSTR["MockStorage"]
        end
        subgraph ASTAP["astap/"]
            ASLV["AstapSolver"]
        end
        subgraph Replay["replay/"]
            RCAM["ReplayCamera"]
        end
        subgraph Planned["planned"]
            TCAM["ToupTekCamera"]
            OMNT["OnStepMount"]
            CSTK["CcdprocStacker"]
        end
    end

    APP -->|"REST / WS"| FASTAPI
    FASTAPI -->|"async task"| RUNNER
    RUNNER --> STATES
    RUNNER --> SESSIONLOG
    RUNNER --> OPTPROFILE
    RUNNER -->|"inject"| CAMPORT
    RUNNER -->|"inject"| MNTPORT
    RUNNER -->|"inject"| SLVPORT
    RUNNER -->|"inject"| STKPORT
    RUNNER -->|"inject"| STRPORT

    CAMPORT --> MCAM
    CAMPORT --> RCAM
    CAMPORT -.->|"planned"| TCAM
    MNTPORT --> MMNT
    MNTPORT -.->|"planned"| OMNT
    SLVPORT --> MSLV
    SLVPORT --> ASLV
    STKPORT --> MSTK
    STKPORT -.->|"planned"| CSTK
    STRPORT --> MSTR

    style Planned fill:#f5f5f5,stroke:#aaa,stroke-dasharray:4
    style Client fill:#e8f4f8,stroke:#5b9bd5
    style Domain fill:#e8f8e8,stroke:#5ba55b
    style Ports fill:#fff8e8,stroke:#c8a020
    style Workflow fill:#f8e8f8,stroke:#a055a0
```

---

## 4. Session state machine

Complete state machine including degraded and failure paths.

```mermaid
stateDiagram-v2
    [*] --> IDLE : runner.run()

    IDLE --> CONNECTED : camera + mount connect OK
    CONNECTED --> MOUNT_READY : unpark + tracking enabled
    MOUNT_READY --> ALIGNED : plate solve + mount sync OK
    ALIGNED --> SLEWED : GoTo M42 complete
    SLEWED --> CENTERED : offset ≤ 2 arcmin
    SLEWED --> CENTERING_DEGRADED : offset > 2 arcmin after 3 iterations
    CENTERED --> PREVIEWING : preview loop starts
    CENTERING_DEGRADED --> PREVIEWING : session continues with warning
    PREVIEWING --> STACKING : stacking loop starts
    STACKING --> STACK_COMPLETE : 10 frames integrated
    STACK_COMPLETE --> SAVED : PNG + JSON log written

    IDLE --> FAILED : any unrecoverable WorkflowError
    CONNECTED --> FAILED
    MOUNT_READY --> FAILED
    ALIGNED --> FAILED
    SLEWED --> FAILED
    CENTERED --> FAILED
    CENTERING_DEGRADED --> FAILED
    PREVIEWING --> FAILED
    STACKING --> FAILED
    STACK_COMPLETE --> FAILED

    SAVED --> [*]
    FAILED --> [*]

    note right of CENTERING_DEGRADED
        Non-fatal. Session logged with
        warning. Final offset recorded.
    end note

    note right of FAILED
        failure_stage and failure_reason
        recorded in SessionLog.
    end note
```

---

## 5. Deployment on Raspberry Pi 5

Physical and logical deployment of all components.

```mermaid
graph TB
    subgraph Field["Field environment"]
        subgraph OTA["Celestron C8 OTA"]
            SCOPE["Schmidt-Cassegrain\n2032mm f/10"]
            FOCUSER["Motorised focuser"]
        end

        subgraph Pi5["Raspberry Pi 5 (4–8 GB RAM, 4× Cortex-A76)"]
            subgraph OS["Raspberry Pi OS 64-bit"]
                SYSTEMD["systemd unit\nsmarttelescope.service"]
                FASTAPI_SVC["FastAPI process\n(session API + WS)"]
                RUNNER_TASK["VerticalSliceRunner\n(background task / thread)"]
                ASTAP_PROC["ASTAP process\n(subprocess per solve)"]
                subgraph Storage["SD Card / SSD"]
                    IMG["stacked PNGs"]
                    LOGS["session JSON logs"]
                    CATALOG["G17 star catalog\n(ASTAP index files)"]
                end
            end
        end

        subgraph Mount["EQ Mount"]
            ONSTEP["OnStep V4\nGoTo controller"]
            MOTORS["RA + Dec motors"]
        end

        CAM["ToupTek Camera\n(USB 3.0)"]
        POWER["12V power supply\nor battery pack"]
    end

    subgraph Observer["Observer's device"]
        APP2["Mobile / Web App\n(Wi-Fi)"]
    end

    SYSTEMD --> FASTAPI_SVC
    FASTAPI_SVC --> RUNNER_TASK
    RUNNER_TASK --> ASTAP_PROC
    ASTAP_PROC --> CATALOG

    Pi5 -->|"USB 3.0"| CAM
    Pi5 -->|"USB / UART serial"| ONSTEP
    Pi5 -->|"USB"| FOCUSER
    ONSTEP --> MOTORS
    CAM --> SCOPE
    FOCUSER --> SCOPE

    APP2 -->|"Wi-Fi\nREST + WebSocket"| Pi5
    POWER -->|"5V USB-C"| Pi5
    POWER -->|"12V"| Mount

    style Pi5 fill:#e8f0fe,stroke:#4a86e8
    style OTA fill:#fce8e6,stroke:#e06c6c
    style Mount fill:#e6f4ea,stroke:#4caf50
    style Observer fill:#fff3e0,stroke:#ff9800
    style Storage fill:#f3e5f5,stroke:#9c27b0
```

---

## 6. Pipeline timing budget (nominal session on Pi 5)

End-to-end time estimate under nominal field conditions. All values are estimates pending real hardware measurement.

```mermaid
gantt
    title Nominal session timeline (Pi 5, C8 native, M42)
    dateFormat mm:ss
    axisFormat %M:%S

    section Boot & connect
    systemd start + service ready   : 00:00, 30s
    Device connect (camera + mount) : 00:30, 15s

    section Alignment
    Mount unpark + tracking         : 00:45, 20s
    Capture alignment frame (5s)    : 01:05, 5s
    ASTAP plate solve               : 01:10, 30s
    Mount sync                      : 01:40, 5s

    section GoTo
    Slew to M42                     : 01:45, 90s

    section Recentering
    Capture recenter frame (10s)    : 03:15, 10s
    ASTAP solve                     : 03:25, 30s
    Correction slew (if needed)     : 03:55, 30s
    Confirm centred (10s + solve)   : 04:25, 40s

    section Previewing
    3 × 5s preview frames           : 05:05, 15s

    section Stacking
    10 × 30s exposures + stack      : 05:20, 310s

    section Save
    Write PNG + session log         : 10:30, 10s
```

**Total nominal session time: ~10–11 minutes** from power-on to saved stack. Plate solving dominates uncertainty; ASTAP on Pi 5 can range from 15 s to 90 s depending on star density and cold-start catalog loading.

---

## Related documents

- [`architecture-review.md`](architecture-review.md) — full critical review with issues and risk register
- [`../wiki/vertical-slice-mvp.md`](../wiki/vertical-slice-mvp.md) — stage-by-stage specification
- [`../wiki/requirements.md`](../wiki/requirements.md) — full requirement set
- [`../wiki/hardware-platform.md`](../wiki/hardware-platform.md) — hardware context
