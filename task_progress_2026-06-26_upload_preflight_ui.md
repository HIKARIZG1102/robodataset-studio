# Task Progress - 2026-06-26 Upload / Preflight / UI

## Task Checklist

- [x] Investigate bottom status bar text overlap.
- [x] Make project/config/path labels elide long text instead of overlapping.
- [x] Investigate Upload API 500 behavior.
- [x] Convert expected upload errors to readable HTTP 400 responses.
- [x] Make frontend API errors include backend response details.
- [x] Investigate Collect topic check timeout.
- [x] Identify current ROS visibility issue as `ROS_LOCALHOST_ONLY` mismatch.
- [x] Add ROS graph/runtime context to preflight results.
- [x] Make missing topics report RMW/ROS_DOMAIN_ID/ROS_LOCALHOST_ONLY guidance.
- [x] Speed up preflight by using graph info and parallel topic probes.
- [x] Restart app with `ROS_LOCALHOST_ONLY=1` to match current mock/camera publishers.

## Completed Changes

- Status bar labels now show elided text and keep full values in tooltips.
- Upload endpoints now return readable 400 errors for common local/remote/path/auth failures.
- Frontend API client now surfaces backend error details instead of generic HTTP errors.
- Preflight now samples the ROS graph first and reports runtime details.
- Preflight topic probes run in parallel and use shorter echo/hz checks.

## Verification

- Python compile checks passed for changed modules.
- `git diff --check` passed.
- `/api/upload/manifest` with a missing local path returns `400 Bad Request` with a clear detail.
- `/api/ros/graph` now sees mock arm and USB camera topics after app restart with `ROS_LOCALHOST_ONLY=1`.
- `/api/recording/preflight` for `mock_test_v1` returns `ok: true` in about 9.5 seconds.

## Issues Encountered

- Current mock arm and USB camera publishers were running with `ROS_LOCALHOST_ONLY=1`, while the app/backend had been running with `ROS_LOCALHOST_ONLY=0`. ROS2 discovery cannot cross that boundary.

## Pending Manual Checks

- Visually confirm the bottom status bar no longer overlaps at your preferred zoom/window size.
- Try the Upload page again with the intended server/path/password and confirm any remaining failure displays a specific reason.
- Run Collect preflight from the UI and confirm the timeout warning is gone.
