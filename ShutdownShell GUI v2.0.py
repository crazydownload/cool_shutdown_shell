#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ShutdownShell GUI v2.0 - Графическая версия
Основана на оригинальной консольной версии 1.4.0
"""

import os
import sys
import json
import time
import threading
import subprocess
import ctypes
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit,
    QListWidget, QMessageBox, QProgressBar, QGroupBox, QFormLayout,
    QCheckBox, QDialog, QDialogButtonBox, QInputDialog, QFileDialog,
    QListWidgetItem, QSpacerItem, QSizePolicy, QFrame
)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal, QEventLoop
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut

import pyqtgraph as pg

import psutil

# Для Windows-специфичных функций
try:
    import win32api
    import win32con
    _HAS_PYWIN32 = True
except ImportError:
    _HAS_PYWIN32 = False

try:
    import winsound
except ImportError:
    winsound = None

# ============================================================================
# Константы и перечисления
# ============================================================================

__version__ = "2.0 GUI"
__author__ = "Grok (переписано с оригинала Crazydownload)"

ES_CONTINUOUS = 0x80000000
ES_DISPLAY_REQUIRED = 0x00000002

class ActionType(Enum):
    SHUTDOWN = 's'
    RESTART = 'r'
    HIBERNATE = 'h'
    BEEP = 'b'

    @property
    def description(self) -> str:
        return {'s': 'Выключение', 'r': 'Перезагрузка', 'h': 'Спящий режим', 'b': 'Звуковой сигнал'}[self.value]

# ============================================================================
# Утилиты
# ============================================================================

class PathManager:
    @staticmethod
    def get_application_path() -> str:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    @staticmethod
    def get_config_path() -> str:
        return os.path.join(PathManager.get_application_path(), "Settings.json")

    @staticmethod
    def ensure_config():
        path = PathManager.get_config_path()
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=4, ensure_ascii=False)

class SystemActions:
    @staticmethod
    def perform(action: ActionType):
        try:
            if action == ActionType.SHUTDOWN:
                subprocess.run(['shutdown', '/s', '/t', '0'], shell=False)
            elif action == ActionType.RESTART:
                subprocess.run(['shutdown', '/r', '/t', '0'], shell=False)
            elif action == ActionType.HIBERNATE:
                ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
            elif action == ActionType.BEEP and winsound:
                for _ in range(3):
                    winsound.Beep(1000, 500)
                    time.sleep(0.3)
        except Exception as e:
            QMessageBox.critical(None, "Ошибка", f"Не удалось выполнить действие: {e}")

    @staticmethod
    def cancel_shutdown():
        try:
            subprocess.run(['shutdown', '/a'], shell=False)
        except:
            pass

class DisplayManager:
    @staticmethod
    def turn_off():
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED)
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        except:
            pass

    @staticmethod
    def turn_on():
        try:
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)
        except:
            pass

# ============================================================================
# Поток мониторинга
# ============================================================================

class MonitorThread(QThread):
    update_signal = pyqtSignal(float, int, str)  # value, fails, status
    finished_signal = pyqtSignal(bool)  # success (True если не выключилось)

    def __init__(self, config: Dict):
        super().__init__()
        self.config = config
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()

    def run(self):
        config = self.config
        threshold = config['threshold_mb']
        allowed_fails = config['allowed_failures']
        interval = config['interval']
        delay = config['shutdown_delay']
        action = ActionType(config['action_mode'])

        fails = 0

        while not self.cancel_event.is_set():
            if self.pause_event.is_set():
                time.sleep(0.1)
                continue

            time.sleep(interval)

            # Проверка активности
            active = False
            if config['type'] == 'disk':
                if config.get('disk_letter'):
                    active = self._check_disk_single(config['disk_letter'], threshold)
                else:
                    active = self._check_disk_all(threshold)
            elif config['type'] == 'network':
                active = self._check_network(config, threshold)

            if active:
                fails = 0
                self.update_signal.emit(0, 0, "Активность обнаружена")
            else:
                fails += 1
                remaining = allowed_fails - fails
                self.update_signal.emit(0, fails, f"Пропусков: {remaining}")
                if fails >= allowed_fails:
                    self._countdown(delay, action)
                    if self.cancel_event.is_set():
                        self.finished_signal.emit(True)
                    else:
                        self.finished_signal.emit(False)
                    return

        self.finished_signal.emit(True)

    def _check_disk_single(self, letter: str, threshold_mb: float) -> bool:
        try:
            io1 = psutil.disk_io_counters(perdisk=True)
            key = self._find_disk_key(letter, io1)
            if not key:
                return self._check_disk_all(threshold_mb)
            time.sleep(0.5)
            io2 = psutil.disk_io_counters(perdisk=True)
            if key not in io2:
                return False
            diff = (io2[key].read_bytes + io2[key].write_bytes) - (io1[key].read_bytes + io1[key].write_bytes)
            mbps = diff / (1024*1024) / 0.5
            self.update_signal.emit(mbps, 0, f"Диск {letter}: {mbps:.2f} МБ/с")
            return mbps >= threshold_mb
        except:
            return False

    def _check_disk_all(self, threshold_mb: float) -> bool:
        try:
            io1 = psutil.disk_io_counters()
            time.sleep(0.5)
            io2 = psutil.disk_io_counters()
            diff = (io2.read_bytes + io2.write_bytes) - (io1.read_bytes + io1.write_bytes)
            mbps = diff / (1024*1024) / 0.5
            self.update_signal.emit(mbps, 0, f"Общая активность: {mbps:.2f} МБ/с")
            return mbps >= threshold_mb
        except:
            return False

    def _check_network(self, config: Dict, threshold_mb: float) -> bool:
        try:
            iface = config['interface']
            direction = 'bytes_sent' if config['traffic_type'] == 'u' else 'bytes_recv'
            counters1 = psutil.net_io_counters(pernic=True)
            if iface not in counters1:
                return False
            old = getattr(counters1[iface], direction)
            time.sleep(config['interval'])
            counters2 = psutil.net_io_counters(pernic=True)
            new = getattr(counters2[iface], direction)
            speed = (new - old) / config['interval'] / (1024*1024)
            dir_text = "Upload" if config['traffic_type'] == 'u' else "Download"
            self.update_signal.emit(speed, 0, f"{dir_text}: {speed:.2f} МБ/с")
            return speed >= threshold_mb
        except:
            return False

    def _find_disk_key(self, letter: str, io_dict: Dict) -> Optional[str]:
        letter = letter.rstrip(':\\').upper()
        for k in io_dict.keys():
            if letter in k.upper() or f"PHYSICALDRIVE" in k.upper():
                return k
        return None

    def _countdown(self, seconds: int, action: ActionType):
        for i in range(seconds, 0, -1):
            if self.cancel_event.is_set():
                return
            self.update_signal.emit(0, 0, f"{action.description} через {i} сек...")
            time.sleep(1)
        if not self.cancel_event.is_set():
            SystemActions.perform(action)

    def stop(self):
        self.cancel_event.set()

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
        else:
            self.pause_event.set()

# ============================================================================
# Основное окно
# ============================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ShutdownShell GUI v{__version__}")
        self.resize(900, 600)

        PathManager.ensure_config()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tabs.addTab(self.create_profiles_tab(), "Профили")
        self.tabs.addTab(self.create_quick_timer_tab(), "Быстрый таймер")
        self.tabs.addTab(self.create_disk_monitor_tab(), "Мониторинг дисков")
        self.tabs.addTab(self.create_display_tab(), "Дисплей")

        # Глобальные горячие клавиши
        QShortcut(QKeySequence("Ctrl+D"), self, DisplayManager.turn_off)

    # ======================= Вкладки =======================

    def create_profiles_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout()

        # Список профилей
        left = QVBoxLayout()
        self.profile_list = QListWidget()
        left.addWidget(QLabel("Сохранённые профили:"))
        left.addWidget(self.profile_list)

        buttons = QHBoxLayout()
        btn_new = QPushButton("Создать")
        btn_edit = QPushButton("Редактировать")
        btn_del = QPushButton("Удалить")
        btn_start = QPushButton("Запустить")
        for b in (btn_new, btn_edit, btn_del, btn_start):
            buttons.addWidget(b)

        left.addLayout(buttons)
        layout.addLayout(left, 1)

        # Предпросмотр
        right = QVBoxLayout()
        right.addWidget(QLabel("Описание профиля:"))
        self.profile_desc = QLabel("Выберите профиль")
        self.profile_desc.setWordWrap(True)
        self.profile_desc.setAlignment(Qt.AlignmentFlag.AlignTop)
        right.addWidget(self.profile_desc)
        layout.addLayout(right, 2)

        widget.setLayout(layout)

        # Подключение
        btn_new.clicked.connect(self.create_new_profile)
        btn_edit.clicked.connect(self.edit_profile)
        btn_del.clicked.connect(self.delete_profile)
        btn_start.clicked.connect(self.start_selected_profile)
        self.profile_list.itemSelectionChanged.connect(self.show_profile_info)

        self.refresh_profiles()
        return widget

    def create_quick_timer_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        form = QFormLayout()
        self.timer_hours = QSpinBox()
        self.timer_hours.setRange(0, 23)
        self.timer_mins = QSpinBox()
        self.timer_mins.setRange(0, 59)
        self.timer_secs = QSpinBox()
        self.timer_secs.setRange(0, 59)
        self.timer_mins.setValue(30)

        time_layout = QHBoxLayout()
        time_layout.addWidget(self.timer_hours)
        time_layout.addWidget(QLabel("ч"))
        time_layout.addWidget(self.timer_mins)
        time_layout.addWidget(QLabel("м"))
        time_layout.addWidget(self.timer_secs)
        time_layout.addWidget(QLabel("с"))

        self.timer_action = QComboBox()
        self.timer_action.addItems(["Выключение", "Перезагрузка", "Спящий режим", "Звуковой сигнал"])

        form.addRow("Время до действия:", time_layout)
        form.addRow("Действие:", self.timer_action)

        layout.addLayout(form)

        self.timer_start_btn = QPushButton("Запустить таймер")
        self.timer_start_btn.clicked.connect(self.start_quick_timer)
        layout.addWidget(self.timer_start_btn)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_disk_monitor_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        # Настройки
        group = QGroupBox("Настройки мониторинга дисков")
        form = QFormLayout()

        self.disk_combo = QComboBox()
        self.disk_combo.addItem("Все диски", None)
        for p in psutil.disk_partitions():
            if 'cdrom' not in p.opts:
                try:
                    usage = psutil.disk_usage(p.mountpoint)
                    self.disk_combo.addItem(f"{p.device} ({usage.free//(1024**3)} GB свободно)", p.device.rstrip('\\'))
                except:
                    pass

        self.disk_threshold = QDoubleSpinBox()
        self.disk_threshold.setValue(1.0)
        self.disk_threshold.setSuffix(" МБ/с")

        self.disk_fails = QSpinBox()
        self.disk_fails.setValue(3)
        self.disk_interval = QSpinBox()
        self.disk_interval.setValue(5)
        self.disk_delay = QSpinBox()
        self.disk_delay.setValue(30)
        self.disk_action = QComboBox()
        self.disk_action.addItems(["Выключение", "Перезагрузка", "Спящий режим", "Звуковой сигнал"])

        form.addRow("Диск:", self.disk_combo)
        form.addRow("Порог активности:", self.disk_threshold)
        form.addRow("Допустимых пропусков:", self.disk_fails)
        form.addRow("Интервал проверки (сек):", self.disk_interval)
        form.addRow("Задержка перед действием (сек):", self.disk_delay)
        form.addRow("Действие:", self.disk_action)

        group.setLayout(form)
        layout.addWidget(group)

        # Кнопки управления
        ctrl_layout = QHBoxLayout()
        self.disk_start_btn = QPushButton("Начать мониторинг")
        self.disk_stop_btn = QPushButton("Остановить")
        self.disk_stop_btn.setEnabled(False)
        self.disk_pause_btn = QPushButton("Пауза")
        self.disk_pause_btn.setEnabled(False)
        for b in (self.disk_start_btn, self.disk_stop_btn, self.disk_pause_btn):
            ctrl_layout.addWidget(b)
        layout.addLayout(ctrl_layout)

        # График
        self.disk_plot = pg.PlotWidget(title="Активность диска (МБ/с)")
        self.disk_curve = self.disk_plot.plot(pen='y')
        self.disk_data = []
        layout.addWidget(self.disk_plot)

        # Статус
        self.disk_status = QLabel("Готов к запуску")
        layout.addWidget(self.disk_status)

        # Подключение
        self.disk_start_btn.clicked.connect(self.start_disk_monitoring)
        self.disk_stop_btn.clicked.connect(self.stop_monitoring)
        self.disk_pause_btn.clicked.connect(self.pause_monitoring)

        widget.setLayout(layout)
        return widget

    def create_display_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        btn_off = QPushButton("Выключить дисплей")
        btn_on = QPushButton("Включить дисплей")
        btn_toggle = QPushButton("Переключить")

        btn_off.clicked.connect(DisplayManager.turn_off)
        btn_on.clicked.connect(DisplayManager.turn_on)
        btn_toggle.clicked.connect(lambda: DisplayManager.turn_off() or DisplayManager.turn_on())

        for b in (btn_off, btn_on, btn_toggle):
            layout.addWidget(b)
            b.setMinimumHeight(50)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ======================= Профили =======================

    def refresh_profiles(self):
        self.profile_list.clear()
        profiles = self.load_profiles()
        for name in profiles:
            item = QListWidgetItem(name)
            self.profile_list.addItem(item)
        if self.profile_list.count() > 0:
            self.profile_list.setCurrentRow(0)

    def load_profiles(self) -> Dict:
        try:
            with open(PathManager.get_config_path(), 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}

    def save_profiles(self, profiles: Dict):
        try:
            with open(PathManager.get_config_path(), 'w', encoding='utf-8') as f:
                json.dump(profiles, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")

    def show_profile_info(self):
        item = self.profile_list.currentItem()
        if not item:
            self.profile_desc.setText("Выберите профиль")
            return
        name = item.text()
        profiles = self.load_profiles()
        p = profiles.get(name, {})
        text = f"<b>{name}</b><br><br>"
        text += f"Тип: { {'timer':'Таймер', 'disk':'Диски', 'network':'Сеть'}.get(p.get('type','?')) }<br>"
        if p.get('type') == 'timer':
            text += f"Действие: {ActionType(p.get('action_mode','s')).description}<br>"
            text += f"Задержка: {p.get('shutdown_delay')} сек"
        elif p.get('type') == 'disk':
            disk = p.get('disk_letter') or "Все диски"
            text += f"Диск: {disk}<br>Порог: {p.get('disk_threshold',1.0)} МБ/с<br>"
            text += f"Пропусков: {p.get('allowed_failures',3)}"
        elif p.get('type') == 'network':
            text += f"Интерфейс: {p.get('interface','?')}<br>"
            text += f"Трафик: {'Upload' if p.get('traffic_type')=='u' else 'Download'}<br>"
            text += f"Порог: {p.get('threshold',0.5)} МБ/с"
        self.profile_desc.setText(text)

    def create_new_profile(self):
        name, ok = QInputDialog.getText(self, "Новый профиль", "Имя профиля:")
        if not ok or not name.strip():
            return
        profiles = self.load_profiles()
        if name in profiles:
            QMessageBox.warning(self, "Ошибка", "Профиль с таким именем уже существует")
            return

        dialog = ProfileDialog(self)
        if dialog.exec():
            settings = dialog.get_settings()
            settings['name'] = name
            profiles[name] = settings
            self.save_profiles(profiles)
            self.refresh_profiles()

    def edit_profile(self):
        item = self.profile_list.currentItem()
        if not item:
            return
        name = item.text()
        profiles = self.load_profiles()
        settings = profiles.get(name)
        if not settings:
            return

        dialog = ProfileDialog(self, settings)
        if dialog.exec():
            new_settings = dialog.get_settings()
            profiles[name] = new_settings
            self.save_profiles(profiles)
            self.refresh_profiles()

    def delete_profile(self):
        item = self.profile_list.currentItem()
        if not item:
            return
        name = item.text()
        reply = QMessageBox.question(self, "Удалить", f"Удалить профиль '{name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            profiles = self.load_profiles()
            if name in profiles:
                del profiles[name]
                self.save_profiles(profiles)
                self.refresh_profiles()

    def start_selected_profile(self):
        item = self.profile_list.currentItem()
        if not item:
            return
        name = item.text()
        profiles = self.load_profiles()
        config = profiles.get(name)
        if not config:
            return
        self.start_monitoring(config)

    # ======================= Мониторинг =======================

    def start_monitoring(self, config: Dict):
        self.monitor_thread = MonitorThread(config)
        self.monitor_thread.update_signal.connect(self.update_monitor_ui)
        self.monitor_thread.finished_signal.connect(self.monitoring_finished)

        # Открываем окно мониторинга
        self.monitor_window = MonitorWindow(config, self.monitor_thread)
        self.monitor_window.show()

        self.monitor_thread.start()

    def update_monitor_ui(self, value: float, fails: int, status: str):
        if hasattr(self, 'monitor_window'):
            self.monitor_window.update_plot(value)
            self.monitor_window.status_label.setText(status)

    def monitoring_finished(self, restart: bool):
        if hasattr(self, 'monitor_window'):
            self.monitor_window.close()
        if not restart:
            QMessageBox.information(self, "Выполнено", "Действие выполнено (или система выключена)")

    def start_disk_monitoring(self):
        config = {
            'type': 'disk',
            'disk_letter': self.disk_combo.currentData(),
            'threshold_mb': self.disk_threshold.value(),
            'allowed_failures': self.disk_fails.value(),
            'interval': self.disk_interval.value(),
            'shutdown_delay': self.disk_delay.value(),
            'action_mode': ['s','r','h','b'][self.disk_action.currentIndex()]
        }
        self.start_monitoring(config)

        self.disk_start_btn.setEnabled(False)
        self.disk_stop_btn.setEnabled(True)
        self.disk_pause_btn.setEnabled(True)

    def stop_monitoring(self):
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.stop()
        self.disk_start_btn.setEnabled(True)
        self.disk_stop_btn.setEnabled(False)
        self.disk_pause_btn.setEnabled(False)

    def pause_monitoring(self):
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.toggle_pause()
            self.disk_pause_btn.setText("Продолжить" if self.monitor_thread.pause_event.is_set() else "Пауза")

    def start_quick_timer(self):
        total_sec = (self.timer_hours.value()*3600 +
                     self.timer_mins.value()*60 +
                     self.timer_secs.value())
        if total_sec == 0:
            QMessageBox.warning(self, "Ошибка", "Укажите время больше 0")
            return

        action_idx = self.timer_action.currentIndex()
        action = ['s','r','h','b'][action_idx]

        config = {
            'type': 'timer',
            'shutdown_delay': total_sec,
            'action_mode': action
        }

        self.start_monitoring(config)

# ============================================================================
# Окно мониторинга (общее для всех типов)
# ============================================================================

class MonitorWindow(QDialog):
    def __init__(self, config: Dict, thread: MonitorThread):
        super().__init__()
        self.thread = thread
        self.setWindowTitle("Мониторинг активен")
        self.resize(600, 400)

        layout = QVBoxLayout()

        title = QLabel(f"Профиль: {config.get('name', 'Быстрый запуск')}")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.plot = pg.PlotWidget(title="Скорость (МБ/с)")
        self.curve = self.plot.plot(pen='y')
        self.data = []
        layout.addWidget(self.plot)

        self.status_label = QLabel("Запуск...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.pause_btn = QPushButton("Пауза")
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.cancel)
        self.pause_btn.clicked.connect(self.toggle_pause)
        buttons.addWidget(self.pause_btn)
        buttons.addWidget(self.cancel_btn)
        layout.addLayout(buttons)

        self.setLayout(layout)

        # Горячие клавиши в этом окне
        QShortcut(QKeySequence("Escape"), self, self.cancel)
        QShortcut(QKeySequence("Ctrl+S"), self, self.toggle_pause)
        QShortcut(QKeySequence("Ctrl+D"), self, DisplayManager.turn_off)

    def update_plot(self, value: float):
        self.data.append(value)
        if len(self.data) > 100:
            self.data = self.data[-100:]
        self.curve.setData(self.data)

    def toggle_pause(self):
        self.thread.toggle_pause()
        self.pause_btn.setText("Продолжить" if self.thread.pause_event.is_set() else "Пауза")

    def cancel(self):
        self.thread.stop()
        SystemActions.cancel_shutdown()
        self.close()

# ============================================================================
# Диалог создания/редактирования профиля
# ============================================================================

class ProfileDialog(QDialog):
    def __init__(self, parent=None, existing: Dict = None):
        super().__init__(parent)
        self.setWindowTitle("Создание профиля")
        self.resize(500, 500)
        layout = QVBoxLayout()

        self.type_combo = QComboBox()
        self.type_combo.addItems(["Таймер", "Мониторинг дисков", "Мониторинг сети"])
        layout.addWidget(QLabel("Тип профиля:"))
        layout.addWidget(self.type_combo)

        self.stacked = QWidget()
        self.stack_layout = QVBoxLayout()
        self.stacked.setLayout(self.stack_layout)
        layout.addWidget(self.stacked)

        self.pages = {}

        # Страница таймера
        timer_page = QWidget()
        t_form = QFormLayout()
        self.t_delay = QSpinBox()
        self.t_delay.setRange(1, 86400)
        self.t_delay.setValue(1800)
        self.t_action = QComboBox()
        self.t_action.addItems(["Выключение", "Перезагрузка", "Спящий режим", "Звуковой сигнал"])
        t_form.addRow("Задержка (сек):", self.t_delay)
        t_form.addRow("Действие:", self.t_action)
        timer_page.setLayout(t_form)
        self.pages["timer"] = timer_page

        # Страница дисков
        disk_page = QWidget()
        d_form = QFormLayout()
        self.d_disk = QComboBox()
        self.d_disk.addItem("Все диски", None)
        for p in psutil.disk_partitions():
            if 'cdrom' not in p.opts:
                try:
                    self.d_disk.addItem(p.device, p.device.rstrip('\\'))
                except:
                    pass
        self.d_thresh = QDoubleSpinBox()
        self.d_thresh.setValue(1.0)
        self.d_thresh.setSuffix(" МБ/с")
        self.d_fails = QSpinBox()
        self.d_fails.setValue(3)
        self.d_interval = QSpinBox()
        self.d_interval.setValue(5)
        self.d_delay = QSpinBox()
        self.d_delay.setValue(30)
        self.d_action = QComboBox()
        self.d_action.addItems(["Выключение", "Перезагрузка", "Спящий режим", "Звуковой сигнал"])
        d_form.addRow("Диск:", self.d_disk)
        d_form.addRow("Порог:", self.d_thresh)
        d_form.addRow("Пропусков:", self.d_fails)
        d_form.addRow("Интервал (сек):", self.d_interval)
        d_form.addRow("Задержка (сек):", self.d_delay)
        d_form.addRow("Действие:", self.d_action)
        disk_page.setLayout(d_form)
        self.pages["disk"] = disk_page

        # Страница сети (упрощённая)
        net_page = QWidget()
        n_form = QFormLayout()
        self.n_iface = QComboBox()
        for iface in psutil.net_io_counters(pernic=True).keys():
            self.n_iface.addItem(iface)
        self.n_dir = QComboBox()
        self.n_dir.addItems(["Download", "Upload"])
        self.n_thresh = QDoubleSpinBox()
        self.n_thresh.setValue(0.5)
        self.n_thresh.setSuffix(" МБ/с")
        self.n_fails = QSpinBox()
        self.n_fails.setValue(3)
        self.n_interval = QSpinBox()
        self.n_interval.setValue(5)
        self.n_delay = QSpinBox()
        self.n_delay.setValue(30)
        self.n_action = QComboBox()
        self.n_action.addItems(["Выключение", "Перезагрузка", "Спящий режим", "Звуковой сигнал"])
        n_form.addRow("Интерфейс:", self.n_iface)
        n_form.addRow("Направление:", self.n_dir)
        n_form.addRow("Порог:", self.n_thresh)
        n_form.addRow("Пропусков:", self.n_fails)
        n_form.addRow("Интервал (сек):", self.n_interval)
        n_form.addRow("Задержка (сек):", self.n_delay)
        n_form.addRow("Действие:", self.n_action)
        net_page.setLayout(n_form)
        self.pages["network"] = net_page

        self.type_combo.currentIndexChanged.connect(self.switch_page)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

        if existing:
            self.load_existing(existing)
        else:
            self.switch_page(0)

    def switch_page(self, index: int):
        # Удаляем старую страницу
        if self.stack_layout.count():
            old = self.stack_layout.takeAt(0).widget()
            old.hide()
        types = ["timer", "disk", "network"]
        page = self.pages[types[index]]
        self.stack_layout.addWidget(page)
        page.show()

    def load_existing(self, settings: Dict):
        types = {"timer": 0, "disk": 1, "network": 2}
        t = settings.get("type", "timer")
        self.type_combo.setCurrentIndex(types.get(t, 0))
        self.switch_page(self.type_combo.currentIndex())

        if t == "timer":
            self.t_delay.setValue(settings.get("shutdown_delay", 1800))
            idx = ['s','r','h','b'].index(settings.get("action_mode", 's'))
            self.t_action.setCurrentIndex(idx)
        elif t == "disk":
            letter = settings.get("disk_letter")
            if letter:
                idx = self.d_disk.findData(letter)
                if idx >= 0:
                    self.d_disk.setCurrentIndex(idx)
            self.d_thresh.setValue(settings.get("disk_threshold", 1.0))
            self.d_fails.setValue(settings.get("allowed_failures", 3))
            self.d_interval.setValue(settings.get("interval", 5))
            self.d_delay.setValue(settings.get("shutdown_delay", 30))
            idx = ['s','r','h','b'].index(settings.get("action_mode", 's'))
            self.d_action.setCurrentIndex(idx)
        elif t == "network":
            iface = settings.get("interface", "")
            idx = self.n_iface.findText(iface)
            if idx >= 0:
                self.n_iface.setCurrentIndex(idx)
            self.n_dir.setCurrentIndex(0 if settings.get("traffic_type", 'd') == 'd' else 1)
            self.n_thresh.setValue(settings.get("threshold", 0.5))
            self.n_fails.setValue(settings.get("allowed_failures", 3))
            self.n_interval.setValue(settings.get("interval", 5))
            self.n_delay.setValue(settings.get("shutdown_delay", 30))
            idx = ['s','r','h','b'].index(settings.get("action_mode", 's'))
            self.n_action.setCurrentIndex(idx)

    def get_settings(self) -> Dict:
        idx = self.type_combo.currentIndex()
        types = ["timer", "disk", "network"]
        t = types[idx]
        s = {"type": t}

        if t == "timer":
            s["shutdown_delay"] = self.t_delay.value()
            s["action_mode"] = ['s','r','h','b'][self.t_action.currentIndex()]
        elif t == "disk":
            s["disk_letter"] = self.d_disk.currentData()
            s["disk_threshold"] = self.d_thresh.value()
            s["allowed_failures"] = self.d_fails.value()
            s["interval"] = self.d_interval.value()
            s["shutdown_delay"] = self.d_delay.value()
            s["action_mode"] = ['s','r','h','b'][self.d_action.currentIndex()]
        elif t == "network":
            s["interface"] = self.n_iface.currentText()
            s["traffic_type"] = 'd' if self.n_dir.currentIndex() == 0 else 'u'
            s["threshold"] = self.n_thresh.value()
            s["allowed_failures"] = self.n_fails.value()
            s["interval"] = self.n_interval.value()
            s["shutdown_delay"] = self.n_delay.value()
            s["action_mode"] = ['s','r','h','b'][self.n_action.currentIndex()]

        return s

# ============================================================================
# Запуск
# ============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Красивый современный стиль

    win = MainWindow()
    win.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()