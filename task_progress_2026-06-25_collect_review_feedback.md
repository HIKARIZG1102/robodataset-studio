# Task Progress - 2026-06-25 Collect / Review Feedback

## Task Checklist

- [x] Merge Episode Review scan and local check into one visible button.
- [x] Run scan before local checks so the UI has a current session index.
- [x] Show a warning dialog when no session is selected.
- [x] Show a warning dialog when the selected session path does not exist.
- [x] Show a warning dialog when the session has no `episode_*.npz` files.
- [x] Make Collect recording state visually obvious while a task is running.
- [x] Refresh the Collect output panel with task status, elapsed time, progress, session path, and live logs.
- [x] Add backend recording heartbeat logs while a recorder subprocess is running.
- [x] Stream recorder subprocess stdout/stderr into the task log before the process exits.
- [x] Run Python compile checks on touched files.

## Completed Changes

- Episode Review now exposes `Scan + Run Local Checks` as the main validation button.
- The combined flow scans first, updates the episode table, then runs local checks only when episode data exists.
- Collect now shows an active recording label and a continuously refreshed `RECORDING MONITOR` in the lower output panel.
- Recording tasks now log configured streams, state keys, sample rate, stop mode, and periodic file-count heartbeat lines.
- Recorder stdout/stderr is appended to task logs as it arrives instead of only after completion.

## Issues Encountered

- The shell environment does not provide a `python` command. Validation was run with `python3`.

## Pending Manual Checks

- Start a real ROS2 recording from the Collect page and confirm the lower output panel refreshes during collection.
- Stop the recording and confirm the final session path is shown.
- Open Episode Review and use `Scan + Run Local Checks` on the new session.
- Try an empty session directory and confirm the warning dialog appears.
