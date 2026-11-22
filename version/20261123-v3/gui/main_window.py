"""WorkBuddy 中继控制面板（PySide6 中文界面）。

设计约束（对应全局规则）：
- g6  中文界面 + PySide6 + 耗时操作走 QThread
- g7  每个耗时操作都有进度条
- g8  icon.ico 存在才用，不存在就不设图标
- g9  自适应分辨率：全部用布局管理器，不用绝对坐标
- g3  所有设置实时保存并落盘
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.transfer_dialog import ExportDialog, ImportDialog
from gui.workers import AccountLoader, ProbeWorker
from relay import __version__, accounts, config, server
from relay.logging_setup import log_line, recent_lines

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ICON_PATH = PROJECT_ROOT / "icon.ico"

MODEL_CHOICES = [
    ("deepseek-v4.1-flash", "DeepSeek-V4.1-Flash（0.11 倍，最省）"),
    ("glm-5.3-flash", "GLM-5.3-Flash（0.08 倍）"),
    ("space-bunny", "Space-Bunny（0.08 倍）"),
    ("minimax-m3.1-flash", "MiniMax-M3.1-Flash（0.08 倍）"),
    ("hunyuan-chat", "Hunyuan-Turbos（0.10 倍）"),
    ("glm-4.6v", "GLM-4.6V（0.11 倍，支持图片）"),
    ("mimo-v2.6-pro", "Xiaomi MiMo-V2.6-Pro（0.13 倍）"),
    ("deepseek-v4-flash", "Deepseek-V4-Flash（0.17 倍）"),
    ("deepseek-v4-pro", "DeepSeek-V4-Pro（0.51 倍，最强）"),
    ("glm-5.3", "GLM-5.3（0.69 倍）"),
    ("kimi-k3-1", "Kimi-K3（1.62 倍，最贵）"),
]


class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self, relay_server: Any = None) -> None:
        super().__init__()
        self.relay_server = relay_server
        self.settings = config.load()
        self.loader: AccountLoader | None = None
        self.prober: ProbeWorker | None = None
        self._pending_progress: tuple | None = None

        self.setWindowTitle("WorkBuddy 中继控制面板 v" + __version__)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self.resize(1080, 760)
        self.setMinimumSize(860, 600)
        self._build_ui()

        # 进度条节流：每 120ms 最多刷新一次，避免高频重绘卡界面。
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(120)
        self._progress_timer.timeout.connect(self._flush_progress)
        self._progress_timer.start()

        self._refresh_status()
        self.reload_accounts()

    # ---------- 界面 ----------

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)

        # 顶部：服务状态条
        top = QHBoxLayout()
        self.status_label = QLabel("服务状态：未启动")
        self.status_label.setFont(QFont("Microsoft YaHei UI", 10))
        top.addWidget(self.status_label, 1)
        self.btn_toggle = QPushButton("停止服务")
        self.btn_toggle.setMinimumWidth(110)
        self.btn_toggle.clicked.connect(self.toggle_server)
        top.addWidget(self.btn_toggle)
        root.addLayout(top)

        # 进度条（全局共用一条，节流刷新）
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        root.addWidget(self.progress)

        # 标签页
        tabs = QTabWidget()
        tabs.addTab(self._build_accounts_tab(), "账号池")
        tabs.addTab(self._build_settings_tab(), "设置")
        tabs.addTab(self._build_log_tab(), "运行日志")
        tabs.addTab(self._build_usage_tab(), "使用说明")
        root.addWidget(tabs, 1)

        self.setCentralWidget(central)

    def _build_accounts_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        bar = QHBoxLayout()
        self.btn_reload = QPushButton("重新载入账号")
        self.btn_reload.clicked.connect(self.reload_accounts)
        bar.addWidget(self.btn_reload)
        self.btn_probe = QPushButton("检测全部账号")
        self.btn_probe.clicked.connect(self.probe_accounts)
        bar.addWidget(self.btn_probe)
        self.btn_export = QPushButton("导出账号")
        self.btn_export.clicked.connect(self.export_accounts)
        bar.addWidget(self.btn_export)
        self.btn_import = QPushButton("导入账号")
        self.btn_import.clicked.connect(self.import_accounts)
        bar.addWidget(self.btn_import)
        self.account_summary = QLabel("账号：—")
        bar.addWidget(self.account_summary, 1)
        layout.addLayout(bar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["账号", "区域", "状态", "失败", "成功", "冷却(秒)", "最近错误"]
        )
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 190)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 80)
        layout.addWidget(self.table, 1)

        return page

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        box = QGroupBox("监听与服务")
        form = QHBoxLayout(box)
        form.addWidget(QLabel("监听地址"))
        self.edit_host = QLineEdit(str(self.settings.get("listen_host") or "127.0.0.1"))
        self.edit_host.setMaximumWidth(160)
        self.edit_host.editingFinished.connect(self.save_listen)
        form.addWidget(self.edit_host)
        form.addWidget(QLabel("端口"))
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(int(self.settings.get("listen_port") or 17583))
        self.spin_port.setMaximumWidth(120)
        self.spin_port.valueChanged.connect(self.save_listen)
        form.addWidget(self.spin_port)
        form.addStretch(1)
        layout.addWidget(box)

        box2 = QGroupBox("默认模型与换号")
        form2 = QHBoxLayout(box2)
        form2.addWidget(QLabel("默认模型"))
        self.combo_model = QComboBox()
        current = str(self.settings.get("default_model") or "deepseek-v4.1-flash")
        for model_id, label in MODEL_CHOICES:
            self.combo_model.addItem(label, model_id)
            if model_id == current:
                self.combo_model.setCurrentIndex(self.combo_model.count() - 1)
        self.combo_model.currentIndexChanged.connect(self.save_model)
        form2.addWidget(self.combo_model, 1)
        form2.addWidget(QLabel("最多换号"))
        self.spin_failover = QSpinBox()
        self.spin_failover.setRange(1, 20)
        self.spin_failover.setValue(int(self.settings.get("max_failover") or 3))
        self.spin_failover.setMaximumWidth(90)
        self.spin_failover.valueChanged.connect(self.save_failover)
        form2.addWidget(self.spin_failover)
        layout.addWidget(box2)

        box3 = QGroupBox("账号来源")
        form3 = QVBoxLayout(box3)
        row = QHBoxLayout()
        row.addWidget(QLabel("保险库目录"))
        self.edit_vault = QLineEdit(str(self.settings.get("vault_dir") or ""))
        self.edit_vault.editingFinished.connect(self.save_vault)
        row.addWidget(self.edit_vault, 1)
        form3.addLayout(row)
        row2 = QHBoxLayout()
        self.chk_cn = QCheckBox("国内版（copilot.tencent.com）")
        self.chk_cn.setChecked(bool(self.settings.get("include_cn", True)))
        self.chk_cn.stateChanged.connect(self.save_regions)
        row2.addWidget(self.chk_cn)
        self.chk_global = QCheckBox("国际版（workbuddy.ai）")
        self.chk_global.setChecked(bool(self.settings.get("include_global", False)))
        self.chk_global.stateChanged.connect(self.save_regions)
        row2.addWidget(self.chk_global)
        row2.addStretch(1)
        form3.addLayout(row2)
        layout.addWidget(box3)

        box4 = QGroupBox("上游兼容（不要随便关）")
        form4 = QVBoxLayout(box4)
        self.chk_gate = QCheckBox("启用渠道校验规避（关掉后 90% 请求会被 11128 拒绝）")
        self.chk_gate.setChecked(bool(self.settings.get("enable_channel_gate_fix", True)))
        self.chk_gate.stateChanged.connect(self.save_gate)
        form4.addWidget(self.chk_gate)
        self.chk_tools = QCheckBox("把工具调用透传给上游（Codex 执行命令必需）")
        self.chk_tools.setChecked(bool(self.settings.get("pass_tools", True)))
        self.chk_tools.stateChanged.connect(self.save_tools)
        form4.addWidget(self.chk_tools)
        layout.addWidget(box4)

        note = QLabel(
            "所有设置改完立即写入 config.json，重启不丢。"
            "改监听地址或端口后需要点「停止服务」再「启动服务」才生效。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_log_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        bar = QHBoxLayout()
        self.btn_refresh_log = QPushButton("刷新日志")
        self.btn_refresh_log.clicked.connect(self.refresh_log)
        bar.addWidget(self.btn_refresh_log)
        bar.addStretch(1)
        layout.addLayout(bar)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_view, 1)
        return page

    def _build_usage_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "三步用起来：\n"
            "\n"
            "1. 本窗口「服务状态」必须是「运行中（端口 17583）」。\n"
            "2. 打开火山软件开发平台 → 模型配置 → 选「WorkBuddy（多账号中继）」→ 导入。\n"
            "3. 服务地址填 http://127.0.0.1:17583/v1 ，密钥随便填（中继自己管账号）。\n"
            "\n"
            "本面板能看什么：\n"
            "- 账号池：每个账号的可用状态、失败次数、冷却剩余秒数、最近一次错误。\n"
            "- 导出账号：「账号池」页的「导出账号」按钮，勾选后另存为 JSON。\n"
            "- 导入账号：「账号池」页的「导入账号」按钮，选文件 → 脱敏预览 → 勾选 → 导入。\n"
            "\n"
            "账号文件与 DSH 插件 dsh-connect-workbuddy 完全互通：\n"
            "  · 本程序导出的 workbuddy-accounts-日期.json 可以直接丢给插件导入；\n"
            "  · 插件导出的同名文件也可以直接在这里导入。\n"
            "  导入会覆盖已存在的同名账号；缺 token、或 domain 判定不出区域的记录会跳过。\n"
            "  文件里是明文 token，请勿随意外发。\n"
            "- 设置：默认模型、最多换号次数、账号来源，改完立即保存。\n"
            "- 运行日志：上游到底回了什么，出问题先看这里。\n"
            "\n"
            "换号是怎么发生的：\n"
            "积分不足 / 登录失效 / 账号被限制 / 限流 / 模型繁忙 → 自动换下一个账号，\n"
            "并让这个账号冷却一段时间。渠道校验失败（11128）和内容策略拒绝（11140）\n"
            "换号没用，会直接把原因告诉你。\n"
        )
        layout.addWidget(text, 1)
        return page

    # ---------- 行为 ----------

    def _flush_progress(self) -> None:
        if self._pending_progress is None:
            return
        value, text = self._pending_progress
        self._pending_progress = None
        self.progress.setValue(max(0, min(100, value)))
        if text:
            self.status_label.setText("服务状态：" + text)

    def _on_progress(self, value: int, text: str) -> None:
        self._pending_progress = (value, text)

    def _refresh_status(self) -> None:
        if self.relay_server is not None and self.relay_server.running:
            self.status_label.setText(
                "服务状态：运行中（http://" + self.relay_server.host + ":" +
                str(self.relay_server.port) + "）"
            )
            self.btn_toggle.setText("停止服务")
        else:
            self.status_label.setText("服务状态：未启动")
            self.btn_toggle.setText("启动服务")

    def toggle_server(self) -> None:
        if self.relay_server is None:
            QMessageBox.warning(self, "提示", "没有可用服务实例。")
            return
        if self.relay_server.running:
            self.relay_server.stop()
        else:
            try:
                self.relay_server.start()
            except OSError as exc:
                QMessageBox.critical(self, "启动失败", "端口可能被占用：\n" + str(exc))
                return
        self._refresh_status()

    def reload_accounts(self) -> None:
        if self.loader is not None and self.loader.isRunning():
            return
        self.progress.setValue(0)
        self.loader = AccountLoader(self)
        self.loader.progress.connect(self._on_progress)
        self.loader.finished_ok.connect(self._on_accounts_loaded)
        self.loader.failed.connect(self._on_failed)
        self.loader.start()

    def _on_accounts_loaded(self, payload: dict) -> None:
        rows = payload.get("accounts") or []
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            state = "可用" if row.get("available") else "冷却中"
            if row.get("token_expired"):
                state += "（token 已过期）"
            values = [
                str(row.get("label") or ""),
                str(row.get("region") or ""),
                state,
                str(row.get("failures") or 0),
                str(row.get("success_count") or 0),
                str(row.get("cooldown_seconds") or 0),
                str(row.get("last_error") or ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(index, column, item)
        self.account_summary.setText(
            "账号：" + str(payload.get("count") or 0) + " 个，可用 " +
            str(payload.get("available") or 0) + " 个"
        )
        self.progress.setValue(100)
        self._refresh_status()

    def export_accounts(self) -> None:
        """导出账号到兼容 dsh-connect-workbuddy 的 JSON 文件。"""
        dialog = ExportDialog(self)
        if dialog.exec():
            self.reload_accounts()

    def import_accounts(self) -> None:
        """从文件导入账号（可直接用插件导出的文件）。"""
        dialog = ImportDialog(self)
        if dialog.exec():
            self.reload_accounts()

    def probe_accounts(self) -> None:
        if self.prober is not None and self.prober.isRunning():
            return
        self.prober = ProbeWorker(str(self.settings.get("default_model") or ""), self)
        self.prober.progress.connect(self._on_progress)
        self.prober.one_done.connect(self._on_probe_one)
        self.prober.finished_ok.connect(self._on_probe_done)
        self.prober.failed.connect(self._on_failed)
        self.prober.start()

    def _on_probe_one(self, label: str, state: str, message: str) -> None:
        log_line("INFO", "probe", label + " -> " + state + (" " + message if message else ""))

    def _on_probe_done(self, payload: dict) -> None:
        self.progress.setValue(100)
        QMessageBox.information(
            self, "检测完成",
            "可用：" + str(payload.get("ok") or 0) + " 个\n失败：" + str(payload.get("fail") or 0) + " 个",
        )
        self.reload_accounts()

    def _on_failed(self, message: str) -> None:
        log_line("ERROR", "gui", message)
        QMessageBox.critical(self, "出错了", message)

    def refresh_log(self) -> None:
        self.log_view.setPlainText("\n".join(recent_lines(300)))

    # ---------- 设置实时保存 ----------

    def save_listen(self) -> None:
        config.save({
            "listen_host": self.edit_host.text().strip() or "127.0.0.1",
            "listen_port": int(self.spin_port.value()),
        })
        self.settings = config.load(force=True)

    def save_model(self) -> None:
        model = self.combo_model.currentData()
        if model:
            config.save({"default_model": str(model)})
            self.settings = config.load(force=True)

    def save_failover(self) -> None:
        config.save({"max_failover": int(self.spin_failover.value())})
        self.settings = config.load(force=True)

    def save_vault(self) -> None:
        config.save({"vault_dir": self.edit_vault.text().strip()})
        self.settings = config.load(force=True)

    def save_regions(self) -> None:
        config.save({
            "include_cn": bool(self.chk_cn.isChecked()),
            "include_global": bool(self.chk_global.isChecked()),
        })
        self.settings = config.load(force=True)

    def save_gate(self) -> None:
        config.save({"enable_channel_gate_fix": bool(self.chk_gate.isChecked())})
        self.settings = config.load(force=True)

    def save_tools(self) -> None:
        config.save({"pass_tools": bool(self.chk_tools.isChecked())})
        self.settings = config.load(force=True)


def run_gui(relay_server: Any = None) -> int:
    """启动 GUI。"""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(relay_server)
    window.show()
    return app.exec()