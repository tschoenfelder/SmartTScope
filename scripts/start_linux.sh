export SMARTTSCOPE_PROFILE=rpi
export SMARTTSCOPE_CAMERA=picamera2
export SMARTTSCOPE_CAMERA_B=picamera2
export SMARTTSCOPE_CAMERA_INDEX=0
export SMARTTSCOPE_CAMERA_B_INDEX=1
# (vorerst GPS/Teleskop als Mock, bis reale Adapter da sind)
export SMARTTSCOPE_GPS=mock
export SMARTTSCOPE_TELESCOPE=mock

systemd-run --user --scope -p CPUQuota=60% -p MemoryMax=800M -p Nice=10 -p IOSchedulingClass=idle \
  taskset -c 1-3 env SMARTTSCOPE_PREVIEW_STREAM=lores SMARTTSCOPE_MAX_FPS=0 SMARTTSCOPE_UI_FPS=15 \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  python examples/dual_camera.py

