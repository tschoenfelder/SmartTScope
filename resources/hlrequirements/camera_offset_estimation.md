# camera offset estimation

Requirement: New Camera Bias Frame Offset Estimation

SmartTScope shall support taking bias frames for a new camera and estimating the required camera offset from those frames before final offset values are added to the configuration.

For each new camera model and relevant gain mode, SmartTScope shall capture a defined set of bias frames with the shortest possible exposure time, closed shutter or covered sensor, and the intended gain setting. The captured frames shall be analyzed to determine whether the current offset prevents pixel clipping at the lower end of the signal range.

The offset estimation shall identify the lowest offset value that keeps the bias frame histogram safely above zero while avoiding unnecessary signal pedestal. The resulting offset recommendation shall be documented per camera model and gain mode.

Acceptance Criteria

SmartTScope can capture bias frames for a new camera using the intended gain mode and shortest available exposure.
The bias frame analysis reports key statistics, including minimum value, mean, median, standard deviation, and number or percentage of zero-value pixels.
The estimated offset keeps the bias signal safely above zero with no significant clipping.
Offset recommendations are produced separately for each relevant camera model and gain mode.
The recommended offset values can be transferred into the SmartTScope configuration file and later applied automatically by camera model and gain mode.