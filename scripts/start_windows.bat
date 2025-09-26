REM im Repo
set SMARTTSCOPE_PROFILE = "win-mock"
set SMARTTSCOPE_CAMERA = "mock"
set SMARTTSCOPE_CAMERA_B = "mock"

REM optional GPS/Teleskop Mock explizit (ist per Profil schon default):
set SMARTTSCOPE_GPS = "mock"
set SMARTTSCOPE_TELESCOPE = "mock"

python examples/dual_camera.py
