# camera offset

Requirement: SmartTScope Camera Offset Configuration

SmartTScope shall support configurable sensor offset values in the configuration file and apply them automatically based on the selected camera model and gain mode.

The configuration shall include the following default offset settings:

G3M678M
LCG: offset 150
HCG: offset 150
CMOS02000KPA
LCG: offset 10
HCG: offset 10
ATR585M
LCG: offset 150
HCG: offset 150

When a camera is initialized or its gain mode is changed, SmartTScope shall read the corresponding offset value from the configuration and apply it to the camera settings. If no matching offset is configured, SmartTScope shall keep the current/default camera offset behavior and log that no configured offset was found.

Acceptance Criteria

The config file contains offset entries for 678M in LCG and HCG, both set to 150.
The config file contains an offset entry for CMOS02000KPA set to 10.
SmartTScope applies the configured offset automatically based on camera model and gain mode.
Offset values can be changed in the config file without modifying application code.
Missing or unknown config entries do not break camera initialization.