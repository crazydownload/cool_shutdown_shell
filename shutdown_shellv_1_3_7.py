#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ShutdownShell v1.3.7
Обновления в этой версии:
 - Полностью переписанная система ввода (независима от раскладки клавиатуры)
 - В режиме 6 (быстрый таймер) сохранение профиля не предлагается
 - Рефакторинг, чистка кода и небольшие оптимизации
 - Улучшенные подсказки интерфейса
 - Программа продолжает рабожать для входа / выхода по RDP
 - В пежиме "редатировать профиль" если редактируеться созданый "таймер" редатируеться только время
Автор: System Tools (modified)
"""

import os
import sys
import json
import time
import re
import threading
import subprocess
import ctypes
import random
import winsound

try:
    import win32api
    import win32con
    import win32console
    _HAS_PYWIN32 = True
except Exception:
    _HAS_PYWIN32 = False

if _HAS_PYWIN32:
    def console_ctrl_handler(ctrl_type):
        # Игнорируем завершение при логофе / дисконнекте RDP и закрытии консоли
        if ctrl_type in (
            win32con.CTRL_LOGOFF_EVENT,
            win32con.CTRL_SHUTDOWN_EVENT,
            win32con.CTRL_CLOSE_EVENT
        ):
            print("\n[INFO] Перехвачено событие завершения. Продолжаю работу...\n")
            return True  # важно: блокирует завершение процесса
        return False

    try:
        win32api.SetConsoleCtrlHandler(console_ctrl_handler, True)
    except Exception:
        pass

try:
    import psutil
except Exception:
    psutil = None

try:
    import msvcrt
except Exception:
    msvcrt = None

__version__ = "1.3.7"
__author__ = "Crazydownload (modified)"

# ──────────────────────────────────────────────────────────────
# Портативный режим: Settings.json всегда рядом с exe
# ──────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    # Если запущен как .exe (PyInstaller)
    APPLICATION_PATH = os.path.dirname(sys.executable)
else:
    # Если запущен как .py скрипт
    APPLICATION_PATH = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APPLICATION_PATH, "Settings.json")

# Создаём файл-заготовку, если его ещё нет
if not os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
        print("Создан новый файл настроек: Settings.json")
    except Exception as e:
        print(f"Не удалось создать Settings.json: {e}")

# Power management flags
ES_CONTINUOUS = 0x80000000
ES_DISPLAY_REQUIRED = 0x00000002

# ---------------------- Утилиты времени и парсинга ----------------------

def parse_time_input(time_str: str) -> int:
    """Парсит выражение вроде '1h30m15s' -> возвращает секунды."""
    if not time_str:
        return 0
    s = re.sub(r"[^0-9hms]", "", time_str.lower())
    h = m = sec = 0
    if 'h' in s:
        parts = s.split('h', 1)
        h = int(parts[0]) if parts[0] else 0
        s = parts[1] if len(parts) > 1 else ''
    if 'm' in s:
        parts = s.split('m', 1)
        m = int(parts[0]) if parts[0] else 0
        s = parts[1] if len(parts) > 1 else ''
    if 's' in s:
        parts = s.split('s', 1)
        sec = int(parts[0]) if parts[0] else 0
    return h * 3600 + m * 60 + sec


def format_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m or h:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return ' '.join(parts)

# ---------------------- Профили (load/save) ----------------------

def load_profiles() -> dict:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"❗ Ошибка при загрузке профилей: {e}")
        return {}


def save_profiles(profiles: dict) -> bool:
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(profiles, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❗ Ошибка при сохранении профилей: {e}")
        return False


def save_profile(name: str, settings: dict) -> bool:
    profiles = load_profiles()
    profiles[name] = settings
    ok = save_profiles(profiles)
    if ok:
        print(f"✅ Профиль '{name}' сохранён в {CONFIG_FILE}")
    return ok

# ---------------------- Управление дисплеем ----------------------

def turn_off_display() -> bool:
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED)
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        print("\n🖥️ Дисплей выключен")
        return True
    except Exception as e:
        print(f"❌ Ошибка при выключении дисплея: {e}")
        return False


def turn_on_display() -> bool:
    try:
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)
        print("✅ Дисплей включён")
        return True
    except Exception as e:
        print(f"❌ Ошибка при включении дисплея: {e}")
        return False

# ---------------------- Действия (shutdown/restart/hibernate/beep) ----------------------

def perform_action(action_mode: str):
    try:
        if action_mode == 's':
            subprocess.run(['shutdown', '/s', '/t', '0'], capture_output=True, shell=False)
        elif action_mode == 'r':
            subprocess.run(['shutdown', '/r', '/t', '0'], capture_output=True, shell=False)
        elif action_mode == 'h':
            ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
        elif action_mode == 'b':
            for _ in range(3):
                winsound.Beep(1000, 500)
                time.sleep(0.3)
    except Exception as e:
        print(f"❌ Ошибка при выполнении действия: {e}")
        # Попытка резерва
        try:
            if action_mode == 's':
                os.system("shutdown /s /t 1")
            elif action_mode == 'r':
                os.system("shutdown /r /t 1")
        except Exception:
            pass

# ---------------------- Обратный отсчёт ----------------------

def countdown_action(seconds: int, cancel_event: threading.Event, action_mode: str = 's'):
    names = {'s': 'выключение', 'r': 'перезагрузка', 'h': 'переход в спящий режим', 'b': 'звуковой сигнал'}
    action_name = names.get(action_mode, 'выключение')
    try:
        for i in range(seconds, 0, -1):
            if cancel_event.is_set():
                return
            print(f"\r{action_name.capitalize()} через {format_time(i)}. [ESC - отмена]".ljust(80), end='', flush=True)
            time.sleep(1)
        if not cancel_event.is_set():
            print()
            perform_action(action_mode)
    except Exception:
        pass

# ---------------------- Обработка ввода (переписанная) ----------------------

def check_user_input(cancel_event: threading.Event, monitoring_event: threading.Event = None, pause_event: threading.Event = None):
    """Обработчик ввода клавиш, НЕ зависит от раскладки.
    
    Управляющие сочетания:
      ESC -> отмена (код 27)
      Ctrl+S -> пауза/возобновление (код 19)
      Ctrl+D -> выключение дисплея (код 4)
    """
    if msvcrt is None:
        return
    try:
        while not cancel_event.is_set():
            if msvcrt.kbhit():
                b = msvcrt.getch()
                # Некоторые клавиши возвращают префикс 0x00 или 0xE0 - пропускаем их
                if b in (b'\x00', b'\xe0'):
                    _ = msvcrt.getch()  # проглотить код специальной клавиши
                    continue

                # ESC
                if b == bytes([27]):
                    cancel_event.set()
                    if monitoring_event:
                        monitoring_event.set()
                    try:
                        subprocess.run(['shutdown', '/a'], capture_output=True, shell=False)
                    except Exception:
                        pass
                    print("\n🚨 Действие отменено! Нажмите Enter для возврата в меню...")
                    return

                # Ctrl+S
                if b == bytes([19]) and monitoring_event is not None and pause_event is not None:
                    if pause_event.is_set():
                        pause_event.clear()
                        print("\n▶️ Мониторинг продолжен (нажмите Ctrl+S для паузы)")
                    else:
                        pause_event.set()
                        print("\n⏸️ Мониторинг приостановлен (нажмите любую клавишу для продолжения)")
                    continue

                # Ctrl+D
                if b == bytes([4]):
                    try:
                        turn_off_display()
                        print("\n🖥️ Дисплей выключен (мониторинг продолжается)")
                    except Exception as e:
                        print(f"❌ Ошибка при выключении дисплея: {e}")
                    continue

                # Если мониторинг был на паузе — любой ввод снимает паузу
                if pause_event is not None and pause_event.is_set():
                    pause_event.clear()
                    print("▶️ Мониторинг продолжен (нажмите Ctrl+S для паузы)")

            time.sleep(0.08)
    except Exception as e:
        print(f"⚠️ Ошибка в обработчике ввода: {e}")

# ---------------------- Мониторинг дисков ----------------------

def check_disk_activity(threshold_mb=1.0, sample_interval=0.5) -> bool:
    if psutil is None:
        return False
    try:
        s1 = psutil.disk_io_counters()
        time.sleep(sample_interval)
        s2 = psutil.disk_io_counters()
        total = (s2.read_bytes + s2.write_bytes) - (s1.read_bytes + s1.write_bytes)
        mb = total / (1024 * 1024) / sample_interval
        if mb >= threshold_mb:
            print(f"\n💾 Активность дисков: {mb:.2f} МБ/с")
            return True
        return False
    except Exception as e:
        print(f"⚠️ Ошибка проверки дисков: {e}")
        return False


def monitor_disk_only(allowed_failures=3, threshold=1.0, interval=5, shutdown_delay=30, action_mode='s') -> bool:
    if psutil is None:
        print("❗ psutil не установлен — мониторинг невозможен")
        return True

    fail_count = 0
    cancel_event = threading.Event()
    monitoring_event = threading.Event()
    pause_event = threading.Event()

    input_thread = threading.Thread(target=check_user_input, args=(cancel_event, monitoring_event, pause_event), daemon=True)
    input_thread.start()

    print("\nℹ️ Управление мониторингом:")
    print("ESC - остановить мониторинг и вернуться в меню")
    print("Ctrl+S - приостановить/возобновить мониторинг")
    print("Ctrl+D - выключить дисплей (мониторинг продолжается)")

    while not monitoring_event.is_set():
        try:
            if pause_event.is_set():
                time.sleep(0.1)
                continue
            time.sleep(interval)
            if check_disk_activity(threshold, sample_interval=0.5):
                fail_count = 0
                continue
            else:
                fail_count += 1
                print(f"⚠️ Пропусков до действия: {allowed_failures - fail_count}")
                if fail_count >= allowed_failures:
                    print(f"🔴 Критическое падение активности дисков! Инициируется действие...")
                    countdown_action(shutdown_delay, cancel_event, action_mode)
                    if cancel_event.is_set():
                        print("\n🔄 Перезапуск мониторинга...")
                        return True
                    if action_mode == 'b':
                        print("\n🔊 Звуковой сигнал выполнен. Возврат в меню...")
                        return True
                    return False
        except (KeyboardInterrupt, SystemExit):
            print("\n🛑 Мониторинг остановлен пользователем.")
            return True
        except Exception as e:
            print(f"\n⚠️ Ошибка мониторинга: {e}")
            time.sleep(2)
            continue

    print("\n🛑 Мониторинг остановлен по запросу пользователя.")
    return True

# ---------------------- Мониторинг сети ----------------------

def monitor_traffic(interface: str, traffic_type: str = 'd', allowed_failures=3, threshold=0.5 * 1024**2, interval=5, shutdown_delay=30, action_mode='s', monitor_disk=False) -> bool:
    if psutil is None:
        print("❗ psutil не установлен — мониторинг невозможен")
        return True
    try:
        counters = psutil.net_io_counters(pernic=True)
        if interface not in counters:
            print(f"❌ Интерфейс '{interface}' не найден.")
            return True
        old = counters[interface]
        old_bytes = old.bytes_sent if traffic_type == 'u' else old.bytes_recv

        cancel_event = threading.Event()
        monitoring_event = threading.Event()
        pause_event = threading.Event()
        input_thread = threading.Thread(target=check_user_input, args=(cancel_event, monitoring_event, pause_event), daemon=True)
        input_thread.start()

        print("\nℹ️ Управление мониторингом:")
        print("ESC - остановить мониторинг и вернуться в меню")
        print("Ctrl+S - приостановить/возобновить мониторинг")
        print("Ctrl+D - выключить дисплей (мониторинг продолжается)")

        fail_count = 0
        while not monitoring_event.is_set():
            try:
                if pause_event.is_set():
                    time.sleep(0.1)
                    continue
                time.sleep(interval)
                if monitor_disk and check_disk_activity():
                    fail_count = 0
                    old = psutil.net_io_counters(pernic=True)[interface]
                    old_bytes = old.bytes_sent if traffic_type == 'u' else old.bytes_recv
                    continue
                new = psutil.net_io_counters(pernic=True)[interface]
                new_bytes = new.bytes_sent if traffic_type == 'u' else new.bytes_recv
                speed = (new_bytes - old_bytes) / interval
                direction = "📤 Upload" if traffic_type == 'u' else "📥 Download"
                print(f"{direction}: {speed/1024**2:.2f} МБ/с [ESC - стоп | Ctrl+S - пауза | Ctrl+D - выкл. дисплей]")
                if speed < threshold:
                    fail_count += 1
                    print(f"⚠️ Пропусков до действия: {allowed_failures - fail_count}")
                    if fail_count >= allowed_failures:
                        print("🔴 Критическое падение скорости! Инициируется действие...")
                        countdown_action(shutdown_delay, cancel_event, action_mode)
                        if cancel_event.is_set():
                            print("\n🔄 Перезапуск мониторинга...")
                            return True
                        if action_mode == 'b':
                            print("\n🔊 Звуковой сигнал выполнен. Возврат в меню...")
                            return True
                        return False
                else:
                    fail_count = 0
                old_bytes = new_bytes
            except (KeyboardInterrupt, SystemExit):
                print("\n🛑 Мониторинг остановлен пользователем.")
                return True
            except Exception as e:
                print(f"\n⚠️ Ошибка мониторинга: {e}")
                time.sleep(2)
                continue

        print("\n🛑 Мониторинг остановлен по запросу пользователя.")
        return True

    except Exception as e:
        print(f"\n❌ Критическая ошибка мониторинга: {e}")
        return True

# ---------------------- Интерактивный таймер ----------------------

def timed_action_interactive(allow_save: bool = True):
    try:
        modes = {'s': 'Выключение', 'r': 'Перезагрузка', 'h': 'Спящий режим', 'b': 'Звуковой сигнал'}
        print("\n=== Режим: действие по времени ===")
        for k, v in modes.items():
            print(f"{k} - {v}")
        while True:
            mode = input("Введите режим действия (s/r/h/b): ").lower()
            if mode in modes:
                break
            print("❌ Неверный ввод. Попробуйте снова.")
        while True:
            t_in = input("Введите время (например: 1h30m15s) или Enter для отмены: ")
            if not t_in:
                print("Отмена.")
                return
            secs = parse_time_input(t_in)
            if secs <= 0:
                print("❌ Время должно быть больше 0")
                continue
            print(f"\n🕒 Действие будет выполнено через {format_time(secs)}")
            cancel_event = threading.Event()
            input_thread = threading.Thread(target=check_user_input, args=(cancel_event,), daemon=True)
            input_thread.start()
            countdown_action(secs, cancel_event, mode)
            if cancel_event.is_set():
                print("\n🚨 Действие отменено!")
            else:
                print("\n✅ Действие выполнено или инициировано.")
            # В режиме быстрого старта (allow_save=False) не предлагается сохранять профиль
            if allow_save:
                save = input("Сохранить как профиль? (y/n): ").lower()
                if save == 'y':
                    name = input("Имя профиля: ")
                    if name:
                        settings = {'type': 'timer', 'shutdown_delay': secs, 'action_mode': mode}
                        save_profile(name, settings)
            return
    except Exception as e:
        print(f"❌ Ошибка в таймере: {e}")

# ---------------------- Меню и операции над профилями ----------------------

def list_profiles() -> dict:
    profiles = load_profiles()
    if not profiles:
        print("\n❗ Нет сохранённых профилей.")
        return {}
    print("\nДоступные профили:")
    for i, name in enumerate(profiles.keys(), 1):
        print(f"{i}. {name}")
    return profiles


def delete_profile():
    profiles = load_profiles()
    if not profiles:
        print("\n❗ Нет профилей для удаления.")
        return
    names = list(profiles.keys())
    for i, n in enumerate(names, 1):
        print(f"{i}. {n}")
    try:
        choice = input("Введите номер профиля для удаления (0 - отмена): ")
        if not choice or choice == '0':
            return
        idx = int(choice) - 1
        if 0 <= idx < len(names):
            nm = names[idx]
            conf = input(f"Удалить профиль '{nm}'? (y/n): ").lower()
            if conf == 'y':
                del profiles[nm]
                save_profiles(profiles)
                print("✅ Удалено.")
        else:
            print("❌ Неверный номер.")
    except ValueError:
        print("❌ Введите число.")


def edit_profile(profile_name: str) -> bool:
    profiles = load_profiles()
    if profile_name not in profiles:
        print("❌ Профиль не найден.")
        return False
    s = profiles[profile_name]
    new = s.copy()
    print(f"\nРедактирование профиля: {profile_name}")
    print("Нажмите Enter чтобы оставить текущее значение")
    
    # Определяем тип профиля
    ptype = s.get('type', 'network' if 'interface' in s else ('disk' if 'disk_threshold' in s else 'timer'))
    
    # Редактирование в зависимости от типа профиля
    if ptype == 'network':
        print(f"Текущий интерфейс: {s.get('interface', '')}")
        if input("Сменить интерфейс? (y/n): ").lower() == 'y':
            new_int = choose_interface()
            if new_int:
                new['interface'] = new_int
        ttype = input(f"Тип трафика (u/d) [{s.get('traffic_type','d')}]: ").lower()
        if ttype in ('u', 'd'):
            new['traffic_type'] = ttype
        thr = input(f"Порог МБ/с [{s.get('threshold',0)/(1024**2):.2f}]: ")
        if thr:
            try:
                new['threshold'] = float(thr) * 1024**2
            except Exception:
                print("❌ Неверный формат, оставлено старое")
                
    elif ptype == 'disk':
        thr = input(f"Порог дисков МБ/с [{s.get('disk_threshold',1.0)}]: ")
        if thr:
            try:
                new['disk_threshold'] = float(thr)
            except Exception:
                print("❌ Неверный формат")
                
    elif ptype == 'timer':
        # Для таймера показываем только задержку и режим действия
        delay = input(f"Задержка ({format_time(s.get('shutdown_delay',30))}): ")
        if delay:
            secs = parse_time_input(delay)
            if secs > 0:
                new['shutdown_delay'] = secs
            else:
                print("❌ Неверный формат времени")
        
        am = input(f"Режим действия (s/r/h/b) [{s.get('action_mode','s')}]: ").lower()
        if am in ('s', 'r', 'h', 'b'):
            new['action_mode'] = am
    
    # Общие опции (кроме таймера)
    if ptype != 'timer':  # Для таймера не показываем эти вопросы
        try:
            af = input(f"Допустимые пропуски [{s.get('allowed_failures',3)}]: ")
            if af:
                new['allowed_failures'] = int(af)
        except Exception:
            print("❌ Неверный формат числа")
        
        try:
            interval = input(f"Интервал проверки в секундах [{s.get('interval',5)}]: ")
            if interval:
                new['interval'] = int(interval)
        except Exception:
            print("❌ Неверный формат числа")
    
    # Для таймера режим действия уже запрошен выше, для других типов - запрашиваем здесь
    if ptype != 'timer':
        am = input(f"Режим действия (s/r/h/b) [{s.get('action_mode','s')}]: ").lower()
        if am in ('s', 'r', 'h', 'b'):
            new['action_mode'] = am
    
    if save_profile(profile_name, new):
        return True
    return False

# ---------------------- Вспомогательное: выбор интерфейса ----------------------

def choose_interface() -> str:
    if psutil is None:
        print("❗ psutil не установлен")
        return None
    try:
        nics = list(psutil.net_io_counters(pernic=True).keys())
        if not nics:
            print("❗ Интерфейсы не найдены")
            return None
        for i, nic in enumerate(nics, 1):
            print(f"{i}. {nic}")
        while True:
            c = input("Введите номер интерфейса (или Enter для отмены): ")
            if not c:
                return None
            try:
                idx = int(c) - 1
                return nics[idx]
            except Exception:
                print("❌ Неверный ввод")
    except Exception as e:
        print(f"❌ Ошибка получения интерфейсов: {e}")
        return None

# ---------------------- Главное меню ----------------------

def main():
    try:
        while True:
            print(f"\n--- ShutdownShell v{__version__} ---")
            print("1. Выбрать существующий профиль (мониторинг / таймер)")
            print("2. Создать новый профиль")
            print("3. Удалить профиль")
            print("4. Редактировать профиль")
            print("5. Изменить порядок профилей")
            print("6. Таймер быстрый старт (без сохранения)")
            print("7. Мониторинг только дисков")
            print("8. Управление дисплеем")
            print("9. Выход")

            ch = input("\nВыберите вариант (1-9): ")
            
            if ch == '1':
                profiles = load_profiles()
                if not profiles:
                    continue
                names = list(profiles.keys())
                for i, n in enumerate(names, 1):
                    print(f"{i}. {n}")
                sel = input("Введите номер профиля (или Enter для отмены): ")
                if not sel:
                    continue
                try:
                    idx = int(sel) - 1
                    pname = names[idx]
                    p = profiles[pname]
                    print(f"\n✅ Выбран профиль: {pname}")
                    
                    if p.get('type') == 'timer':
                        delay = p.get('shutdown_delay', 30)
                        mode = p.get('action_mode', 's')
                        cancel_event = threading.Event()
                        input_thread = threading.Thread(target=check_user_input, args=(cancel_event,), daemon=True)
                        input_thread.start()
                        countdown_action(delay, cancel_event, mode)
                        print("\n🔙 Возврат в меню...")
                        continue
                    
                    if 'disk_threshold' in p:
                        while True:
                            should_restart = monitor_disk_only(
                                p.get('allowed_failures', 3),
                                p.get('disk_threshold', 1.0),
                                p.get('interval', 5),
                                p.get('shutdown_delay', 30),
                                p.get('action_mode', 's')
                            )
                            if not should_restart:
                                return
                            print("\nНажмите Enter для возврата в меню или любую другую клавишу для перезапуска мониторинга...")
                            if msvcrt and msvcrt.getch() == b'\r':
                                break
                    else:
                        while True:
                            should_restart = monitor_traffic(
                                p.get('interface'),
                                p.get('traffic_type', 'd'),
                                p.get('allowed_failures', 3),
                                p.get('threshold', 0.5 * 1024**2),
                                p.get('interval', 5),
                                p.get('shutdown_delay', 30),
                                p.get('action_mode', 's'),
                                p.get('monitor_disk', False)
                            )
                            if not should_restart:
                                return
                            print("\nНажмите Enter для возврата в меню или любую другую клавишу для перезапуска мониторинга...")
                            if msvcrt and msvcrt.getch() == b'\r':
                                break
                except Exception:
                    print("❌ Неверный выбор. Попробуйте снова.")

            elif ch == '2':
                try:
                    name = input("Имя профиля: ")
                    if not name:
                        print("❌ Имя не может быть пустым")
                        continue
                    
                    print("1. Мониторинг сети\n2. Мониторинг дисков\n3. Таймер")
                    tp = input("Выберите тип (1/2/3): ")
                    
                    if tp == '1':
                        interface = choose_interface()
                        if not interface:
                            continue
                        tt = input("Тип трафика (u/d) [d]: ").lower() or 'd'
                        if tt not in ('u', 'd'):
                            tt = 'd'
                        thr = input("Порог МБ/с [0.5]: ")
                        try:
                            thr = float(thr) if thr else 0.5
                        except Exception:
                            thr = 0.5
                        af = input("Допустимые пропуски [3]: ")
                        try:
                            af = int(af) if af else 3
                        except Exception:
                            af = 3
                        interval = input("Интервал сек [5]: ")
                        try:
                            interval = int(interval) if interval else 5
                        except Exception:
                            interval = 5
                        delay = input("Задержка до действия (пример 1h30m) [30s]: ")
                        sd = parse_time_input(delay) if delay else 30
                        mode = input("Режим (s/r/h/b) [s]: ").lower() or 's'
                        monitor_disk_choice = input("Мониторинг дисков? (y/n) [n]: ").lower() or 'n'
                        md = monitor_disk_choice == 'y'
                        
                        settings = {
                            'type': 'network',
                            'interface': interface,
                            'traffic_type': tt,
                            'threshold': thr * 1024**2,
                            'allowed_failures': af,
                            'interval': interval,
                            'shutdown_delay': sd,
                            'action_mode': mode,
                            'monitor_disk': md
                        }
                        
                    elif tp == '2':
                        thr = input("Порог МБ/с [1.0]: ")
                        try:
                            thr = float(thr) if thr else 1.0
                        except Exception:
                            thr = 1.0
                        af = input("Допустимые пропуски [3]: ")
                        try:
                            af = int(af) if af else 3
                        except Exception:
                            af = 3
                        interval = input("Интервал сек [5]: ")
                        try:
                            interval = int(interval) if interval else 5
                        except Exception:
                            interval = 5
                        delay = input("Задержка до действия [30s]: ")
                        sd = parse_time_input(delay) if delay else 30
                        mode = input("Режим (s/r/h/b) [s]: ").lower() or 's'
                        
                        settings = {
                            'type': 'disk',
                            'disk_threshold': thr,
                            'allowed_failures': af,
                            'interval': interval,
                            'shutdown_delay': sd,
                            'action_mode': mode
                        }
                        
                    elif tp == '3':
                        mode = input("Режим (s/r/h/b) [s]: ").lower() or 's'
                        delay = input("Задержка (пример 1h30m) [30s]: ")
                        sd = parse_time_input(delay) if delay else 30
                        
                        settings = {
                            'type': 'timer',
                            'shutdown_delay': sd,
                            'action_mode': mode
                        }
                        
                    else:
                        print("❌ Неверный выбор")
                        continue
                    
                    save_profile(name, settings)
                    
                except Exception as e:
                    print(f"❌ Ошибка при создании профиля: {e}")

            elif ch == '3':
                delete_profile()

            elif ch == '4':
                profiles = load_profiles()
                if not profiles:
                    continue
                names = list(profiles.keys())
                for i, n in enumerate(names, 1):
                    print(f"{i}. {n}")
                sel = input("Номер профиля для редактирования (или Enter): ")
                if not sel:
                    continue
                try:
                    idx = int(sel) - 1
                    edit_profile(names[idx])
                except Exception:
                    print("❌ Неверный ввод")

            elif ch == '5':
                profiles = load_profiles()
                if not profiles:
                    continue
                keys = list(profiles.keys())
                print("Текущий порядок:")
                for i, k in enumerate(keys, 1):
                    print(f"{i}. {k}")
                try:
                    sel = input("Номер профиля для перемещения (или Enter): ")
                    if not sel:
                        continue
                    idx = int(sel) - 1
                    if not (0 <= idx < len(keys)):
                        print("❌ Неверный номер")
                        continue
                    newpos = int(input(f"Новая позиция для '{keys[idx]}' (1..{len(keys)}): ")) - 1
                    if not (0 <= newpos < len(keys)):
                        print("❌ Неверный номер")
                        continue
                    key = keys.pop(idx)
                    keys.insert(newpos, key)
                    new_profiles = {k: profiles[k] for k in keys}
                    save_profiles(new_profiles)
                    print("✅ Порядок изменён")
                except Exception:
                    print("❌ Ошибка при перемещении")

            elif ch == '6':
                # Быстрый таймер — не предлагает сохранить профиль
                timed_action_interactive(allow_save=False)

            elif ch == '7':
                try:
                    thr = input("Порог МБ/с [1.0]: ")
                    thr = float(thr) if thr else 1.0
                    af = input("Допустимые пропуски [3]: ")
                    af = int(af) if af else 3
                    interval = input("Интервал сек [5]: ")
                    interval = int(interval) if interval else 5
                    delay = input("Задержка до действия [30s]: ")
                    sd = parse_time_input(delay) if delay else 30
                    mode = input("Режим (s/r/h/b) [s]: ").lower() or 's'
                    
                    while True:
                        should_restart = monitor_disk_only(af, thr, interval, sd, mode)
                        if not should_restart:
                            return
                        print("\nНажмите Enter для возврата в меню или любую другую клавишу для перезапуска мониторинга...")
                        if msvcrt and msvcrt.getch() == b'\r':
                            break
                except Exception as e:
                    print(f"❌ Ошибка: {e}")

            elif ch == '8':
                while True:
                    print("\n=== Управление дисплеем ===")
                    print("1. Выключить дисплей")
                    print("2. Включить дисплей")
                    print("3. Переключить (вкл/выкл)")
                    print("4. Назад")
                    c = input("Выберите: ")
                    if c == '1':
                        turn_off_display()
                    elif c == '2':
                        turn_on_display()
                    elif c == '3':
                        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
                        print("Переключено")
                    elif c == '4':
                        break
                    else:
                        print("❌ Неверный выбор")

            elif ch == '9':
                print("\n👋 До свидания!")
                break

            else:
                print("❌ Неверный выбор. Попробуйте снова.")

    except KeyboardInterrupt:
        print("\n\n🛑 Программа прервана пользователем.")
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")


if __name__ == '__main__':
    main()