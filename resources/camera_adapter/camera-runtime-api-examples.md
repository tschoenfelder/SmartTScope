# Camera Runtime API Examples

Maintained curl examples for the native multi-camera MVP.

## Headless Pi Load Test

Run this from the SmartTScope virtual environment on Raspberry Pi 5 / Trixie 64.

```bash
python -m smart_telescope.tools.camera_loadtest \
  --duration 600 \
  --role main:60:60 \
  --role guide:0.5:0.5 \
  --role oag:0.5:0.5 \
  --json-out ~/smarttscope_3cam_60s_stress.json
```

## Measure-Only Guide/OAG Test

Runs guide and OAG streams, measures centroids, selects one active source, and
emits would-be guide pulses in JSON without moving the mount.

```bash
python -m smart_telescope.tools.guide_measuretest \
  --duration 300 \
  --primary-role guide \
  --allow-fallback \
  --role guide:0.5:0.5 \
  --role oag:0.5:0.5 \
  --json-out ~/smarttscope_measure_only_guiding.json
```

Use this before real guide pulses are enabled. The JSON contains per-role
measurements, source-selection decisions, stale-frame drops, and would-be pulse
commands.

## Cooling

Read cooling status for the main camera:

```bash
curl "http://127.0.0.1:8000/api/cooling/status?camera_role=main"
```

Enable cooling using the configured default target, normally `-10 C`:

```bash
curl -X POST "http://127.0.0.1:8000/api/cooling/set_target" \
  -H "Content-Type: application/json" \
  -d '{"camera_role":"main","enabled":true}'
```

Enable cooling with an explicit target:

```bash
curl -X POST "http://127.0.0.1:8000/api/cooling/set_target" \
  -H "Content-Type: application/json" \
  -d '{"camera_role":"main","target_c":-10,"enabled":true}'
```

Disable cooling:

```bash
curl -X POST "http://127.0.0.1:8000/api/cooling/set_target" \
  -H "Content-Type: application/json" \
  -d '{"camera_role":"main","enabled":false}'
```

## Filter Wheel

Read filter wheel status:

```bash
curl "http://127.0.0.1:8000/api/filters/status?camera_role=main"
```

Select a filter by configured filter id:

```bash
curl -X POST "http://127.0.0.1:8000/api/filters/select" \
  -H "Content-Type: application/json" \
  -d '{"camera_role":"main","filter_id":"ha"}'
```

Select a 1-based wheel position directly:

```bash
curl -X POST "http://127.0.0.1:8000/api/filters/select" \
  -H "Content-Type: application/json" \
  -d '{"camera_role":"main","position":5}'
```

## Guide Monitor

Start guide monitoring on the guide-scope camera:

```bash
curl -X POST "http://127.0.0.1:8000/api/guide_monitor/start" \
  -H "Content-Type: application/json" \
  -d '{
    "camera_role": "guide",
    "camera_model": "GPCMOS02000KPA",
    "check_interval_s": 0.5,
    "stream_cadence_s": 0.5
  }'
```

Start guide monitoring on the OAG / G3M678M camera:

```bash
curl -X POST "http://127.0.0.1:8000/api/guide_monitor/start" \
  -H "Content-Type: application/json" \
  -d '{
    "camera_role": "oag",
    "camera_model": "G3M678M",
    "check_interval_s": 0.5,
    "stream_cadence_s": 0.5
  }'
```

Read guide monitor status:

```bash
curl "http://127.0.0.1:8000/api/guide_monitor/status"
```

Stop guide monitoring:

```bash
curl -X POST "http://127.0.0.1:8000/api/guide_monitor/stop"
```
