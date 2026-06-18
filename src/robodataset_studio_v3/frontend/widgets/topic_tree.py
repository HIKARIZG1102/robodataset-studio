from __future__ import annotations

from collections import defaultdict
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTreeWidget, QTreeWidgetItem


class TopicTreeWidget(QTreeWidget):
    selectionChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setColumnCount(3)
        self.setHeaderLabels(["Use", "Topic", "Type"])
        self.setUniformRowHeights(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTextElideMode(Qt.ElideNone)
        self.setWordWrap(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.header().setStretchLastSection(True)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.header().setSectionResizeMode(1, QHeaderView.Interactive)
        self.header().setSectionResizeMode(2, QHeaderView.Interactive)
        self.header().setMinimumSectionSize(48)
        self.itemChanged.connect(self._handle_item_changed)

    def populate(self, topics: list[dict[str, Any]], selected_names: set[str] | None = None) -> None:
        selected_names = selected_names or {row["topic"] for row in self.selected_topics()}
        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for topic in topics:
            name = str(topic.get("name") or topic.get("topic") or "")
            msg_type = str(topic.get("type") or topic.get("message_type") or "")
            if not name:
                continue
            groups[self.group_name(name)].append({"name": name, "topic": name, "type": msg_type, "message_type": msg_type})

        self.blockSignals(True)
        self.clear()
        for group in sorted(groups):
            children = sorted(groups[group], key=lambda item: item["topic"])
            parent = QTreeWidgetItem(["", f"{group} ({len(children)})", ""])
            parent.setFlags(parent.flags() | Qt.ItemIsUserCheckable)
            parent.setCheckState(0, Qt.Unchecked)
            parent.setData(0, Qt.UserRole, {"group": group})
            parent.setToolTip(1, f"{group} ({len(children)} topics)")
            self.addTopLevelItem(parent)
            checked_count = 0
            for topic in children:
                child = QTreeWidgetItem(["", topic["topic"], topic["type"]])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                checked = topic["topic"] in selected_names
                child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                child.setData(0, Qt.UserRole, topic)
                child.setToolTip(1, topic["topic"])
                child.setToolTip(2, topic["type"])
                parent.addChild(child)
                checked_count += int(checked)
            if checked_count == len(children) and children:
                parent.setCheckState(0, Qt.Checked)
            elif checked_count:
                parent.setCheckState(0, Qt.PartiallyChecked)
            parent.setExpanded(checked_count > 0)
        self._fit_topic_column(groups)
        self.resizeColumnToContents(0)
        self.setColumnWidth(2, 260)
        self.blockSignals(False)
        self.selectionChanged.emit()

    def selected_topics(self) -> list[dict[str, str]]:
        selected: list[dict[str, str]] = []
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) != Qt.Checked:
                    continue
                data = child.data(0, Qt.UserRole)
                if isinstance(data, dict):
                    selected.append(
                        {
                            "name": str(data.get("name") or data.get("topic") or ""),
                            "topic": str(data.get("topic") or data.get("name") or ""),
                            "type": str(data.get("type") or data.get("message_type") or ""),
                            "message_type": str(data.get("message_type") or data.get("type") or ""),
                        }
                    )
        return [row for row in selected if row["topic"]]

    def _handle_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        data = item.data(0, Qt.UserRole)
        if isinstance(data, dict) and "group" in data:
            self.blockSignals(True)
            state = item.checkState(0)
            for idx in range(item.childCount()):
                item.child(idx).setCheckState(0, state)
            self.blockSignals(False)
        else:
            parent = item.parent()
            if parent is not None:
                self._sync_parent_state(parent)
        self.selectionChanged.emit()

    def _sync_parent_state(self, parent: QTreeWidgetItem) -> None:
        checked = 0
        partial = 0
        for idx in range(parent.childCount()):
            state = parent.child(idx).checkState(0)
            checked += int(state == Qt.Checked)
            partial += int(state == Qt.PartiallyChecked)
        self.blockSignals(True)
        if checked == parent.childCount() and parent.childCount():
            parent.setCheckState(0, Qt.Checked)
        elif checked or partial:
            parent.setCheckState(0, Qt.PartiallyChecked)
        else:
            parent.setCheckState(0, Qt.Unchecked)
        self.blockSignals(False)

    @staticmethod
    def group_name(topic: str) -> str:
        parts = [part for part in topic.split("/") if part]
        if not parts:
            return "root"
        return parts[0]

    def _fit_topic_column(self, groups: dict[str, list[dict[str, str]]]) -> None:
        longest = ""
        for topics in groups.values():
            for topic in topics:
                if len(topic["topic"]) > len(longest):
                    longest = topic["topic"]
        if not longest:
            self.setColumnWidth(1, 320)
            return
        metrics = QFontMetrics(self.font())
        desired = metrics.horizontalAdvance(longest) + 52
        viewport_width = max(self.viewport().width(), 320)
        self.setColumnWidth(1, max(280, min(desired, int(viewport_width * 0.72))))
