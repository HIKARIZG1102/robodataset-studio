from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget


class TutorialPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml(
            """
            <h2>RoboDataset Studio Workflow</h2>
            <p><b>Scope:</b> RoboDataset Studio is a ROS2 listener-based dataset
            tool. It discovers existing ROS2 nodes/topics, subscribes to selected
            data streams, records datasets, reviews sessions, converts outputs,
            and uploads results. It does not send robot control commands by default.</p>

            <h3>1. Prepare External Data Sources</h3>
            <ol>
              <li>Start the external systems that publish the ROS2 topics you want to record.</li>
              <li>Confirm the app can discover those topics with the top-right <b>Refresh Nodes/Topics</b> button.</li>
              <li>If another process produces motion or task execution, start that process outside Studio. Studio only records existing topics.</li>
            </ol>

            <h3>2. Create Project And Config</h3>
            <ol>
              <li>Open <b>File</b>, then create or open a project from the Projects sidebar.</li>
              <li>Open <b>Config</b>, then create or open a reusable config from the Configs sidebar.</li>
              <li>In <b>Config Library -> ROS Topics</b>, select image, depth, state, sensor, or task topics.</li>
              <li>Click <b>Refresh config from selected topics</b> to build streams/state/action from selected topics.</li>
              <li>Click <b>Apply form to YAML</b>, then <b>Save</b>.</li>
              <li>Bind the config to the current project if it is not already bound.</li>
            </ol>

            <h3>3. Run Collection After Config</h3>
            <ol>
              <li>Open the <b>Collect</b> tab in the same project.</li>
              <li>Click <b>Reload Dataset Config</b> so Collect reads the latest dataset_config.yaml.</li>
              <li>Check the stream table. It should list the exact topics and roles that will be recorded.</li>
              <li>Click <b>Check Configured Topics</b> to run topic info, echo once, and hz checks.</li>
              <li>Choose <b>Manual</b>, <b>Duration</b>, or <b>Sample count</b>.</li>
              <li>Start the external task/data-producing process if needed.</li>
              <li>Click <b>Start Recording</b>. Studio creates a timestamped session under raw_sessions.</li>
              <li>Execute the task while configured topics publish data.</li>
              <li>Click <b>Stop Recording</b> for manual capture. Duration and sample-count captures can still be stopped early.</li>
              <li>Use <b>Simulate Test Episode</b> only to test project/review/convert structure without real data.</li>
            </ol>

            <h3>4. Review, Convert, Upload</h3>
            <ol>
              <li>Open <b>Review</b>, use <b>Use Current Session</b>, then run <b>Scan Session</b> and <b>Run Local Checks</b>.</li>
              <li>Use marks and delete actions to curate episodes.</li>
              <li>Use <b>Convert</b> to scan sessions, select sessions, merge them, or export HDF5.</li>
              <li>Use <b>HDF5 Review</b> to show HDF5 structure or validate HDF5 data.</li>
              <li>Use <b>Upload</b> to reload server fields from project config, build/verify manifest, upload, resume, and verify remote files.</li>
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

            <h3>Docker Packaging</h3>
            <p>The repository includes Docker helper scripts for a generic image
            named <code>robodataset-studio</code>. The image packages the GUI,
            FastAPI backend, application source, Python dependencies, and
            upload tools in a container-local virtual environment at
            <code>/opt/robodataset-studio/venv</code>. It does not install ROS
            inside the image. The run wrapper passes through the
            host ROS environment with host networking, <code>/opt/ros</code>,
            <code>ROS_SETUP</code>, Python/library paths, and ROS domain variables
            so the container can match the current machine. By default only
            <code>./robodataset</code> is mounted as persistent data; the app
            code runs from the image. Use <code>PROJECT_MOUNTS</code> for
            external project disks and <code>ROS_WORKSPACE_MOUNTS</code> for
            additional ROS overlays.</p>
            """
        )
        layout.addWidget(browser)
