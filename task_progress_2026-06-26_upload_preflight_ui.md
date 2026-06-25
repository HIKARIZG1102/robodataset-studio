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
- [x] Confirm AI prompt text box sends the full prompt, not just visible text.
- [x] Rework AI prompt into compact column-style field statistics.
- [x] Remove Markdown-style output instructions from AI report prompt.
- [x] Normalize Review page box heights and splitter proportions.
- [x] Clean Markdown-like markers from AI review responses before displaying/saving.
- [x] Align Review page prompt/result panels with consistent titled boxes.
- [x] Reduce Inspector dock minimum width so it can collapse to about one third of the previous minimum.
- [x] Align Review right-side NPZ details, AI report, and AI response panel widths.
- [x] Add Select All Episodes control for batch Review marking/deleting.
- [x] Fix HDF5 conversion for string/Unicode NPZ fields such as ROS `std_msgs/String` data.
- [x] Add basic merge/HDF5 conversion task logs so failures are visible in task details.
- [x] Add Review action to delete an entire session by moving it into `.delete/sessions`.
- [x] Add Settings Maintenance tab with recycle-bin cleanup and log-cache cleanup.
- [x] Archive completed/failed/cancelled task records to disk with logs, results, and errors.
- [x] Make Clear Log Cache also clear task archive counts, including failed records.
- [x] Refresh Logs page/sidebar immediately after maintenance log cleanup.
- [x] Increase Inspector minimum width back to 144px, three times the previous 48px narrow setting.
- [x] Set Inspector default dock width around 320px and keep minimum at 260px so controls are visible without being overly wide.
- [x] Split Inspector node/topic/image controls across rows so the right dock no longer opens with half-clipped controls.
- [x] Persist Inspector dock width and left/right dock area in local settings.
- [x] Pull latest `v3-fastapi-pyside` from GitHub and verify local/remote are synchronized.
- [x] Test new Docker packaging and identify runtime Qt dependency gaps.
- [x] Add missing Docker runtime libraries required by PySide6/Qt.
- [x] Make Docker run script work in non-interactive terminals by only adding `-it` for real TTY sessions.
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
- Session AI prompt now groups repeated field information by field name and lists sampled episode values under each field.
- AI report prompt asks for plain text section labels, avoiding Markdown syntax that renders poorly in the app.
- Re-saving an AI report replaces the existing `ai_session_report.md`.
- AI review responses are sanitized to plain text before being shown and composed into `ai_session_report.md`.
- Review page text panels now use consistent titled left/right boxes for summary/report and prompt/response.
- Inspector can now collapse to a much narrower dock width while keeping scrollbars for content access.
- Review episode controls now include `Select All Episodes` for batch marking/deletion.
- HDF5 conversion now writes string, bytes, object, scalar, numeric, and image NPZ fields through explicit dtype handling.
- Convert tasks now log selected session counts, output paths, converted/merged episode counts, and failure types.
- Review now has `Delete Session`, guarded by a confirmation dialog, and active sessions are moved into `.delete`.
- Settings now has a Maintenance tab for cleaning project `.delete`/`review_deleted` files and temporary runtime log cache.
- Task completion/failure/cancellation now appends a full JSONL record to `~/.config/robodataset-studio-v3/task_archive.jsonl`.
- Clear Log Cache now removes the task archive file as well as runtime task cache, so `failed` archive counts reset.
- Settings emits a maintenance refresh event that refreshes the Logs tab and sidebar after cleanup.
- Logs page now shows an explicit empty-state message after task/log cleanup.
- Inspector now receives a default right-dock width via `resizeDocks`, and its controls wrap into separate rows instead of relying on a very wide dock.
- Inspector now restores the previous dock side and width on startup instead of always using the default layout.
- Docker image now installs `libdbus-1-3`, `libfontconfig1`, and `libfreetype6`, which PySide6/Qt needs at runtime.
- `scripts/docker_run.sh` now supports non-interactive launches without Docker failing on `the input device is not a TTY`.
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
- HDF5 conversion was reproduced against mock session data containing `mock_widowx_task_phase` with Unicode dtype and now succeeds.
- `git fetch` against `origin/v3-fastapi-pyside` succeeded; local and remote commit counts are even.
- Original Docker image reproduced `ImportError: libfontconfig.so.1` on startup.
- Patched Docker image passed backend/frontend import smoke tests.

## Issues Encountered

- Current mock arm and USB camera publishers were running with `ROS_LOCALHOST_ONLY=1`, while the app/backend had been running with `ROS_LOCALHOST_ONLY=0`. ROS2 discovery cannot cross that boundary.
- HDF5 conversion previously failed on `dtype('<U5')` because h5py cannot directly create a compressed dataset from numpy Unicode arrays. This came from string/generic ROS fields, not from merge itself.
- Docker default DNS in this environment could not resolve Ubuntu package hosts during build; building with `docker build --network host ...` works here.
- The newly added Docker packaging depended on Qt libraries that were not included in the first image version.

## Pending Manual Checks

- Visually confirm the bottom status bar no longer overlaps at your preferred zoom/window size.
- Try the Upload page again with the intended server/path/password and confirm any remaining failure displays a specific reason.
- Run Collect preflight from the UI and confirm the timeout warning is gone.
