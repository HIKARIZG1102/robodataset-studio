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
            <p><b>Scope:</b> V3 is primarily a ROS2 listener-based dataset
            tool. It discovers existing ROS2 nodes/topics, subscribes to
            selected data streams, records datasets, reviews sessions, converts
            outputs, and uploads results. It does not send robot control
            commands by default.</p>
            <ol>
              <li>Create or open a project.</li>
              <li>Open Project Config and confirm project_config.yaml plus dataset_config.yaml.</li>
              <li>Use ROS Discovery to inspect topics.</li>
              <li>Use Collect to run preflight, start recording, and stop recording.</li>
              <li>Use Review to scan sessions and check dataset quality.</li>
              <li>Use Convert to scan sessions and prepare merge/HDF5 tasks.</li>
              <li>Use Upload to check dependencies and prepare upload or repair tasks.</li>
            </ol>
            <h3>ROS2 Communication Layers</h3>
            <p>ROS2 traffic flows through several layers: ROS setup/workspace,
            rclpy/rclcpp, RMW, DDS, transport, QoS, message type conversion,
            and dataset storage. DDS/RMW is part of the ROS2 runtime installed
            on the robot workstation, not a normal pip dependency of this app.</p>
            <ul>
              <li><b>RMW/DDS:</b> FastDDS and CycloneDDS may both appear on ROS2 systems.
              V3 auto-detects installed RMW implementations and avoids known FastDDS
              shared-memory failures where possible.</li>
              <li><b>Discovery/network:</b> ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY, multicast,
              VPNs, and LAN routing can decide whether nodes see each other.</li>
              <li><b>QoS:</b> Image and sensor topics usually need sensor-data QoS.</li>
              <li><b>Messages:</b> V3 supports Image, CompressedImage, JointState,
              IMU, Odometry, geometry messages, and common std_msgs arrays/scalars.
              Unsupported custom messages should fail or warn explicitly.</li>
              <li><b>Image encodings:</b> rgb8, bgr8, mono/depth, float depth, and
              compressed image streams require separate decode handling.</li>
            </ul>
            """
        )
        layout.addWidget(browser)
