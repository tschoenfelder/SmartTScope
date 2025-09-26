export SMARTTSCOPE_PROFILE=rpi
export SMARTTSCOPE_CAMERA=picamera2
export SMARTTSCOPE_CAMERA_B=picamera2
export SMARTTSCOPE_CAMERA_INDEX=0
export SMARTTSCOPE_CAMERA_B_INDEX=1
# (vorerst GPS/Teleskop als Mock, bis reale Adapter da sind)
export SMARTTSCOPE_GPS=mock
export SMARTTSCOPE_TELESCOPE=mock

python examples/dual_camera.py
