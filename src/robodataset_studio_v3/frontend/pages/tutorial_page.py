from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget


class TutorialPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml(
            """
            <h2>RoboDataset Studio V3 Workflow</h2>
            <ol>
              <li>Create or open a project.</li>
              <li>Open Project Config and confirm project_config.yaml plus dataset_config.yaml.</li>
              <li>Use ROS Discovery to inspect topics.</li>
              <li>Use Collect to run preflight, start recording, and stop recording.</li>
              <li>Use Review to scan sessions and check dataset quality.</li>
              <li>Use Convert to scan sessions and prepare merge/HDF5 tasks.</li>
              <li>Use Upload to check dependencies and prepare upload or repair tasks.</li>
            </ol>
            <p>V3 currently has full frontend/backend wiring. Production ROS recording, conversion, and upload
            execution will be migrated from the validated V2 logic module by module.</p>
            """
        )
        layout.addWidget(browser)
