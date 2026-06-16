# camera id mapping

Requirement: Keep a mapping of serial numbers and camera names in config

Add mapping to config file and allow usage of camera names in app instead serial ids.

Starting config is:
GPCMOS02000KPA  tp-3-4-23-0547-1367
ATR585M         tp-4-1-10-0547-157c
G3M678M         tp-4-2-11-0547-14bc

For post final release keep as additional requirement to check for new cameras and to update the config. If names are identical, use an index '_a´' to distingish
