# Task Progress - 2026-06-26 Upload / Preflight / UI

## Task Checklist

- [x] Fix status bar project/config/path values being over-elided to `..`.
- [x] Reduce Inspector dock minimum width so it can be compressed further.
- [x] Shorten Inspector button labels and keep full descriptions in tooltips.
- [x] Fix bottom-left text overlap by replacing Qt statusBar temporary messages with a dedicated message label.
- [x] Restore Inspector button text readability and use scrollbars for narrow dock widths instead of hiding labels.
- [x] Shorten Image Monitor control labels enough to leave room for image type.
- [x] Add session-level AI review prompt generation based on compact quality metrics and sampled NPZ statistics.
- [x] Keep AI session prompt short by sending stats/field summaries, not raw arrays or full metadata.
- [x] Add batch episode marking for selected rows.
- [x] Show saved `ai_session_report.md` in Overview when selecting a session folder.
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

- Status bar elision now uses the configured maximum width instead of transient startup widget width.
- Normal project/config labels display fully when they fit.
- Inspector image preview minimum size was reduced.
- Inspector controls use shorter labels and split image controls into two rows.
- Status messages now render in `message_label`, separate from project/config/path widgets.
- Inspector controls now keep full button text; narrow widths use scrollbars instead of squeezed invisible labels.
- Image Monitor buttons now use shorter labels such as `Sync from project`, `Start monitor`, and `Stop monitor`.
- Review now builds AI prompts from the selected session, including overview, issue counts, mark counts, metrics, and sampled episode stats.
- AI replies are composed into a session report with a short overview header before saving.
- `Mark Selected` now applies to all selected episode rows.
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
