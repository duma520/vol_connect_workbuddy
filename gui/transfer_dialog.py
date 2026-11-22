"""账号导出 / 导入对话框。

文件格式与 dsh-connect-workbuddy 插件**完全互通**：导出的 JSON 能直接丢给它导入，
它导出的 workbuddy-accounts-YYYY-MM-DD.json 也能直接在这里导入。
格式细节见 relay/transfer.py 顶部说明。
"""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from relay import accounts as accounts_mod
from relay import config, transfer


class ExportDialog(QDialog):
    """勾选账号 → 另存为 JSON。"""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出账号")
        self.setMinimumWidth(560)
        self.setMinimumHeight(460)
        self._records: list = []

        layout = QVBoxLayout(self)
        hint = QLabel(
            "勾选要导出的账号。导出的文件与 dsh-connect-workbuddy 插件格式完全一致，"
            "可以直接导入到插件，也可以在本程序的「导入账号」里使用。"
            "\n\n注意：文件里含明文 token，请勿随意外发，用完建议删除。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        self.btn_all = QPushButton("全选")
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        buttons.addWidget(self.btn_all)
        self.btn_none = QPushButton("全不选")
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        buttons.addWidget(self.btn_none)
        buttons.addStretch(1)
        self.summary = QLabel("")
        buttons.addWidget(self.summary)
        layout.addLayout(buttons)

        box = QDialogButtonBox()
        self.btn_export = box.addButton("导出…", QDialogButtonBox.ButtonRole.AcceptRole)
        box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_export.clicked.connect(self._do_export)
        layout.addWidget(box)

        self._load()

    def _load(self) -> None:
        pool = accounts_mod.pool()
        pool.reload()
        rows = pool.accounts()
        self._accounts = rows
        self.list.clear()
        for account in rows:
            label = account.label + "　[" + account.region + "]"
            if account.token_expired:
                label += "　（token 已过期）"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list.addItem(item)
        self._update_summary()

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.list.count()):
            self.list.item(index).setCheckState(state)
        self._update_summary()

    def _update_summary(self) -> None:
        picked = self._picked_indexes()
        self.summary.setText("已选 " + str(len(picked)) + " / " + str(self.list.count()) + " 个")

    def _picked_indexes(self) -> list:
        picked = []
        for index in range(self.list.count()):
            if self.list.item(index).checkState() == Qt.CheckState.Checked:
                picked.append(index)
        return picked

    def _do_export(self) -> None:
        picked = self._picked_indexes()
        if not picked:
            QMessageBox.warning(self, "没有选中账号", "请至少勾选一个账号。")
            return
        records = []
        for index in picked:
            account = self._accounts[index]
            try:
                records.append(transfer.transfer_record_of(account))
            except Exception as exc:
                QMessageBox.warning(self, "导出失败", account.label + "：" + repr(exc)[:200])
                return

        default_name = transfer.default_export_name()
        path, _ = QFileDialog.getSaveFileName(
            self, "保存账号文件", default_name, "JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        payload = transfer.export_payload(records)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            QMessageBox.critical(self, "写入失败", "无法写入文件：\n" + str(exc))
            return

        QMessageBox.information(
            self, "导出完成",
            "已导出 " + str(len(records)) + " 个账号到：\n" + path +
            "\n\n这个文件可以直接在 dsh-connect-workbuddy 插件里导入。"
        )
        self.accept()


class ImportDialog(QDialog):
    """选文件 → 脱敏预览 → 勾选 → 导入。"""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导入账号")
        self.setMinimumWidth(600)
        self.setMinimumHeight(520)
        self._records: list = []
        self._preview: dict = {}

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.btn_file = QPushButton("选择文件…")
        self.btn_file.clicked.connect(self._pick_file)
        row.addWidget(self.btn_file)
        self.file_label = QLabel("尚未选择文件")
        self.file_label.setWordWrap(True)
        row.addWidget(self.file_label, 1)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("导入到区域"))
        self.combo_region = QComboBox()
        self.combo_region.addItem("国内版 (cn)", "cn")
        self.combo_region.addItem("国际版 (global)", "global")
        row2.addWidget(self.combo_region)
        row2.addStretch(1)
        self.summary = QLabel("")
        row2.addWidget(self.summary)
        layout.addLayout(row2)

        note = QLabel(
            "预览里只显示账号标识，不显示 token。导入会覆盖这里已存在的同名账号；"
            "缺 token 或属于另一个区域的记录会被自动跳过。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        box = QDialogButtonBox()
        self.btn_import = box.addButton("导入选中", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_import.setEnabled(False)
        box.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_import.clicked.connect(self._do_import)
        layout.addWidget(box)

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择账号文件", "", "JSON 文件 (*.json);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                text = handle.read()
        except OSError as exc:
            QMessageBox.critical(self, "读取失败", "无法读取文件：\n" + str(exc))
            return

        try:
            preview = transfer.preview_transfer_file(text)
            self._records = transfer.parse_transfer_file(text)
        except ValueError as exc:
            QMessageBox.critical(self, "文件格式不对", str(exc))
            return

        self._preview = preview
        self.file_label.setText(path)
        self.list.clear()
        for entry in preview.get("accounts") or []:
            label = entry.get("nickname") or entry.get("uid") or "（无标识）"
            label += "　[" + str(entry.get("region") or "?") + "]"
            if not entry.get("hasToken"):
                label += "　（缺 token，会被跳过）"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if entry.get("hasToken") else Qt.CheckState.Unchecked
            )
            self.list.addItem(item)

        total = preview.get("total") or 0
        self.summary.setText("文件中共 " + str(total) + " 个账号")
        self.btn_import.setEnabled(bool(total))

        # 文件里若全是国际版账号，自动把区域切到国际版，省得用户选错被跳过。
        regions = {str(e.get("region")) for e in (preview.get("accounts") or [])}
        if regions == {"global"}:
            self.combo_region.setCurrentIndex(1)
        elif regions == {"cn"}:
            self.combo_region.setCurrentIndex(0)

    def _do_import(self) -> None:
        if not self._records:
            return
        indexes = []
        for index in range(self.list.count()):
            if self.list.item(index).checkState() == Qt.CheckState.Checked:
                indexes.append(index)
        if not indexes:
            QMessageBox.warning(self, "没有选中账号", "请至少勾选一个账号。")
            return

        region = self.combo_region.currentData() or "cn"
        settings = config.load()
        vault_dir = str(settings.get("vault_dir") or "")
        if not vault_dir:
            QMessageBox.critical(self, "没有保险库目录", "请先在设置里指定保险库目录。")
            return

        merged = transfer.merge_records(self._records, indexes, region)
        written = 0
        failures = []
        for account_id, credential in merged["changes"].items():
            try:
                accounts_mod.write_vault_account(credential, region, vault_dir)
                written += 1
            except Exception as exc:
                failures.append(account_id + "：" + repr(exc)[:160])

        accounts_mod.pool().reload()

        message = "已导入 " + str(written) + " 个账号；跳过 " + str(merged["skipped"]) + " 个。"
        reasons = merged.get("skip_reasons") or []
        if reasons:
            message += "\n\n跳过原因：\n" + "\n".join(reasons[:10])
        if failures:
            message += "\n\n写入失败 " + str(len(failures)) + " 个：\n" + "\n".join(failures[:5])
        QMessageBox.information(self, "导入完成", message)
        self.accept()