param(
  [ValidateSet("mock","opencv","picamera2")] [string]$Camera = "mock",
  [switch]$Dual
)

# venv aktivieren
$venv = ".\.venv\Scripts\Activate.ps1"
if (Test-Path $venv) { . $venv } else {
  python -m venv .venv; . .\.venv\Scripts\Activate.ps1
  pip install -e .[dev,win]
}

if ($Dual) {
  $Env:SMARTTSCOPE_CAMERA  = $Camera
  $Env:SMARTTSCOPE_CAMERA_B = "mock"
  python examples/dual_camera.py
} else {
  $Env:SMARTTSCOPE_CAMERA = $Camera
  smarttscope
}
