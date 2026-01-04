#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ShutdownShell v1.4.5
Обновления в этой версии:
 - Полностью цифровой интерфейс (1/2 вместо y/n, 1-4 вместо s/r/h/b)
 - Добавлена графическая визуализация при создании нового профиля с отображением выбранных параметров
 - Исправлен баг: при создании профиля мониторинга дисков или в быстром мониторинге нажатие Enter (отмена выбора диска) теперь действительно отменяет весь процесс и возвращает в главное меню
 - При создании профиля мониторинга сети с дополнительным мониторингом дисков отмена выбора диска больше не приводит к ошибкам
 - В режиме редактирования профиля показываются изменения с помощью стрелочек (старое → новое значение)
 - Использование цифр 1/2 вместо букв для выбора типа трафика (Download/Upload)
 - ИСПРАВЛЕН БАГ: Управление дисплеем (Ctrl+D) теперь работает корректно и не блокирует дальнейший ввод
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
        if ctrl_type in (
            win32con.CTRL_LOGOFF_EVENT,
            win32con.CTRL_SHUTDOWN_EVENT,
            win32con.CTRL_CLOSE_EVENT
        ):
            print("\n[INFO] Перехвачено событие завершения. Продолжаю работу...\n")
            return True
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

__version__ = "1.4.5"
__author__ = "Crazydownload (modified)"

# ──────────────────────────────────────────────────────────────
# Портативный режим: Settings.json всегда рядом с exe
# ──────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    APPLICATION_PATH = os.path.dirname(sys.executable)
else:
    APPLICATION_PATH = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APPLICATION_PATH, "Settings.json")

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

# ---------------------- Утилиты цифрового ввода ----------------------

def ask_yes_no(question: str, default_yes: bool = False) -> bool:
    """
    Запрашивает подтверждение с цифровым вводом (1/2)
    Возвращает: True (Да) / False (Нет)
    """
    default = "1" if default_yes else "2"
    options = "1 - Да / 2 - Нет"
    
    while True:
        answer = input(f"{question} [{options}] [{default}]: ").strip()
        if not answer:
            answer = default
        
        if answer == '1':
            return True
        elif answer == '2':
            return False
        else:
            print("❌ Неверный ввод. Введите 1 или 2")

def ask_action_mode(question: str, default: str = 's') -> str:
    """
    Запрашивает выбор действия с цифровым вводом (1-4)
    Возвращает: 's', 'r', 'h', 'b'
    """
    print(f"\n{question}")
    print("1. ⏻ Выключение")
    print("2. 🔄 Перезагрузка")
    print("3. 💤 Спящий режим")
    print("4. 🔊 Звуковой сигнал")
    
    default_map = {'s': '1', 'r': '2', 'h': '3', 'b': '4'}
    default_num = default_map.get(default, '1')
    
    while True:
        choice = input(f"Выберите действие (1-4) [{default_num}]: ").strip()
        if not choice:
            choice = default_num
        
        if choice == '1':
            return 's'
        elif choice == '2':
            return 'r'
        elif choice == '3':
            return 'h'
        elif choice == '4':
            return 'b'
        else:
            print("❌ Неверный ввод. Введите число от 1 до 4")

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
    """Выключает дисплей"""
    try:
        # Снимаем флаг ES_DISPLAY_REQUIRED перед выключением дисплея
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        # Выключаем дисплей
        result = ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        print("\n🖥️ Дисплей выключен")
        return True
    except Exception as e:
        print(f"❌ Ошибка при выключении дисплея: {e}")
        return False


def turn_on_display() -> bool:
    """Включает дисплей"""
    try:
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)
        print("✅ Дисплей включён")
        return True
    except Exception as e:
        print(f"❌ Ошибка при включении дисплея: {e}")
        return False


def restore_power_state():
    """Восстанавливает нормальное состояние управления питанием"""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED)
    except Exception as e:
        print(f"⚠️ Ошибка восстановления состояния питания: {e}")

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

# ---------------------- Обработка ввода ----------------------

def check_user_input(cancel_event: threading.Event, monitoring_event: threading.Event = None, pause_event: threading.Event = None):
    if msvcrt is None:
        return
    try:
        while not cancel_event.is_set():
            if msvcrt.kbhit():
                b = msvcrt.getch()
                if b in (b'\x00', b'\xe0'):
                    _ = msvcrt.getch()
                    continue

                if b == bytes([27]):  # ESC
                    cancel_event.set()
                    if monitoring_event:
                        monitoring_event.set()
                    try:
                        subprocess.run(['shutdown', '/a'], capture_output=True, shell=False)
                    except Exception:
                        pass
                    print("\n🚨 Действие отменено! Нажмите Enter для возврата в меню...")
                    return

                if b == bytes([19]) and monitoring_event is not None and pause_event is not None:  # Ctrl+S
                    if pause_event.is_set():
                        pause_event.clear()
                        print("\n▶️ Мониторинг продолжен (нажмите Ctrl+S для паузы)")
                    else:
                        pause_event.set()
                        print("\n⏸️ Мониторинг приостановлен (нажмите любую клавишу для продолжения)")
                    continue

                if b == bytes([4]):  # Ctrl+D
                    try:
                        success = turn_off_display()
                        if success:
                            print("\n🖥️ Дисплей выключен (мониторинг продолжается)")
                            # Восстанавливаем возможность управления системой питания
                            restore_power_state()
                    except Exception as e:
                        print(f"❌ Ошибка при выключении дисплея: {e}")
                    continue

                if pause_event is not None and pause_event.is_set():
                    pause_event.clear()
                    print("▶️ Мониторинг продолжен (нажмите Ctrl+S для паузы)")

            time.sleep(0.08)
    except Exception as e:
        print(f"⚠️ Ошибка в обработчике ввода: {e}")

# ---------------------- Мониторинг дисков ----------------------

def get_disk_partitions():
    if psutil is None:
        return []
    try:
        partitions = psutil.disk_partitions(all=True)
        return [p.device for p in partitions if p.fstype and 'cdrom' not in p.opts]
    except Exception as e:
        print(f"⚠️ Ошибка получения списка дисков: {e}")
        return []


def check_disk_activity_single(disk_letter: str, threshold_mb=1.0, sample_interval=0.5) -> bool:
    if psutil is None:
        return False
    try:
        disk_io = psutil.disk_io_counters(perdisk=True)
        if not disk_io:
            print("❌ Нет данных о дисковых операций")
            return False
        
        disk_letter = disk_letter.rstrip(':\\').upper()
        disk_key = None
        for key in disk_io.keys():
            key_normalized = key.upper()
            if (f"PHYSICALDRIVE" in key_normalized or 
                key_normalized.startswith(disk_letter) or
                disk_letter in key_normalized):
                disk_key = key
                break
        
        if disk_key is None:
            try:
                disk_num = ord(disk_letter) - ord('A')
                for key in disk_io.keys():
                    if f"PHYSICALDRIVE{disk_num}" in key.upper():
                        disk_key = key
                        break
            except:
                pass
        
        if disk_key is None:
            print(f"⚠️ Диск {disk_letter}: не найден в статистике IO, использую общую статистику")
            return check_disk_activity(threshold_mb, sample_interval)
        
        s1 = disk_io[disk_key]
        time.sleep(sample_interval)
        disk_io2 = psutil.disk_io_counters(perdisk=True)
        if disk_key not in disk_io2:
            print(f"⚠️ Диск {disk_letter} ({disk_key}) больше не доступен")
            return False
        
        s2 = disk_io2[disk_key]
        read_diff = s2.read_bytes - s1.read_bytes
        write_diff = s2.write_bytes - s1.write_bytes
        total = read_diff + write_diff
        mb = total / (1024 * 1024) / sample_interval
        
        if mb >= threshold_mb:
            print(f"\n💾 Диск {disk_letter}: {mb:.2f} МБ/с (чтение: {read_diff/1024**2/sample_interval:.2f} МБ/с, запись: {write_diff/1024**2/sample_interval:.2f} МБ/с)")
            return True
        return False
    except Exception as e:
        print(f"⚠️ Ошибка проверки диска {disk_letter}: {e}")
        return False


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
            print(f"\n💾 Общая активность дисков: {mb:.2f} МБ/с")
            return True
        return False
    except Exception as e:
        print(f"⚠️ Ошибка проверки дисков: {e}")
        return False


def monitor_disk_only(allowed_failures=3, threshold=1.0, interval=5, shutdown_delay=30, action_mode='s', disk_letter=None) -> bool:
    if psutil is None:
        print("❗ psutil не установлен — мониторинг невозможен")
        return True

    fail_count = 0
    cancel_event = threading.Event()
    monitoring_event = threading.Event()
    pause_event = threading.Event()

    input_thread = threading.Thread(target=check_user_input, args=(cancel_event, monitoring_event, pause_event), daemon=True)
    input_thread.start()

    if disk_letter:
        print(f"\nℹ️ Мониторинг активности диска: {disk_letter}")
    else:
        print(f"\nℹ️ Мониторинг активности всех дисков")
    
    print("ESC - остановить мониторинг и вернуться в меню")
    print("Ctrl+S - приостановить/возобновить мониторинг")
    print("Ctrl+D - выключить дисплей (мониторинг продолжается)")

    while not monitoring_event.is_set():
        try:
            if pause_event.is_set():
                time.sleep(0.1)
                continue
            time.sleep(interval)
            
            if disk_letter:
                has_activity = check_disk_activity_single(disk_letter, threshold, sample_interval=0.5)
            else:
                has_activity = check_disk_activity(threshold, sample_interval=0.5)
            
            if has_activity:
                fail_count = 0
                continue
            else:
                fail_count += 1
                print(f"⚠️ Пропусков до действия: {allowed_failures - fail_count}")
                if fail_count >= allowed_failures:
                    if disk_letter:
                        print(f"🔴 Критическое падение активности диска {disk_letter}! Инициируется действие...")
                    else:
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


def choose_disk():
    """
    Возвращает:
      - str   — выбран конкретный диск (например 'C')
      - None  — выбран мониторинг всех дисков
      - False — пользователь отменил выбор (нажал Enter на пустом вводе)
    """
    if psutil is None:
        print("❗ psutil не установлен")
        return False
    
    partitions = get_disk_partitions()
    if not partitions:
        print("❗ Дисковые разделы не найдены")
        return False
    
    print("\nДоступные дисковые разделы:")
    for i, disk in enumerate(partitions, 1):
        try:
            usage = psutil.disk_usage(disk)
            free_gb = usage.free / (1024**3)
            total_gb = usage.total / (1024**3)
            percent_used = usage.percent
            print(f"{i}. {disk} ({free_gb:.1f} GB свободно из {total_gb:.1f} GB, {percent_used:.1f}% использовано)")
        except:
            print(f"{i}. {disk} (информация недоступна)")
    
    print(f"{len(partitions) + 1}. Все диски (общая активность)")
    
    while True:
        choice = input(f"\nВыберите диск (1-{len(partitions) + 1}) или Enter для отмены: ").strip()
        if not choice:  # отмена
            return False
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(partitions):
                return partitions[idx].rstrip('\\')
            elif idx == len(partitions):
                return None  # все диски
            else:
                print("❌ Неверный выбор")
        except ValueError:
            print("❌ Введите число")


# ---------------------- Мониторинг сети ----------------------

def monitor_traffic(interface: str, traffic_type: str = 'd', allowed_failures=3, threshold=0.5 * 1024**2, interval=5, shutdown_delay=30, action_mode='s', monitor_disk=False, monitor_disk_type='all', monitor_disk_letter=None) -> bool:
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
                
                if monitor_disk:
                    has_disk_activity = False
                    if monitor_disk_type == 'specific' and monitor_disk_letter:
                        has_disk_activity = check_disk_activity_single(monitor_disk_letter, threshold_mb=1.0, sample_interval=0.5)
                    else:
                        has_disk_activity = check_disk_activity(threshold_mb=1.0, sample_interval=0.5)
                    
                    if has_disk_activity:
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
        print(f"\n{'═' * 60}")
        print("⏰ ТАЙМЕР БЫСТРЫЙ СТАРТ")
        print(f"{'═' * 60}")
        
        # Выбор действия
        action_mode = ask_action_mode("Выберите действие:", 's')
        
        # Ввод времени
        print(f"\n{'─' * 40}")
        print("⏳ ВВЕДИТЕ ВРЕМЯ")
        print("Формат: 1h30m15s (часы: h, минуты: m, секунды: s)")
        print("Примеры: 30s, 1h30m, 2h, 45m10s")
        print(f"{'─' * 40}")
        
        while True:
            t_in = input("\nВведите время или Enter для отмены: ").strip()
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
            
            countdown_action(secs, cancel_event, action_mode)
            
            if cancel_event.is_set():
                print("\n🚨 Действие отменено!")
            else:
                print("\n✅ Действие выполнено или инициировано.")
            
            if allow_save:
                save = ask_yes_no("\nСохранить как профиль?", False)
                if save:
                    name = input("Имя профиля: ").strip()
                    if name:
                        settings = {'type': 'timer', 'shutdown_delay': secs, 'action_mode': action_mode}
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
    
    print(f"\n{'═' * 60}")
    print("🗑️  УДАЛЕНИЕ ПРОФИЛЯ")
    print(f"{'═' * 60}")
    
    names = list(profiles.keys())
    for i, n in enumerate(names, 1):
        print(f"{i}. {n}")
    
    try:
        choice = input(f"\nВведите номер профиля для удаления (1-{len(names)}) или 0 для отмены: ").strip()
        if not choice or choice == '0':
            print("❌ Отмена удаления.")
            return
        
        idx = int(choice) - 1
        if 0 <= idx < len(names):
            nm = names[idx]
            confirm = ask_yes_no(f"Удалить профиль '{nm}'?", False)
            if confirm:
                del profiles[nm]
                save_profiles(profiles)
                print("✅ Профиль удалён.")
            else:
                print("❌ Удаление отменено.")
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
    
    print(f"\n╔{'═' * 60}╗")
    print(f"║{'РЕДАКТИРОВАНИЕ ПРОФИЛЯ':^60}║")
    print(f"║{f'» {profile_name} «':^60}║")
    print(f"╚{'═' * 60}╝")
    
    ptype = s.get('type', 'network' if 'interface' in s else ('disk' if 'disk_threshold' in s else 'timer'))
    
    def show_change(field_name, old_val, new_val):
        if old_val != new_val:
            print(f"  {field_name}: {old_val} → {new_val}")
        else:
            print(f"  {field_name}: {old_val} (без изменений)")
    
    if ptype == 'network':
        print(f"\n📡 ТИП: Мониторинг сети")
        
        # Интерфейс
        old_interface = s.get('interface', '')
        print(f"\nТекущий интерфейс: {old_interface}")
        change_int = ask_yes_no("Сменить интерфейс?", False)
        if change_int:
            new_int = choose_interface()
            if new_int:
                new['interface'] = new_int
        show_change("Интерфейс", old_interface, new.get('interface', old_interface))
        
        # Тип трафика
        old_traffic = s.get('traffic_type', 'd')
        print(f"\nТип трафика:")
        print("1. 📥 Download (входящий трафик)")
        print("2. 📤 Upload (исходящий трафик)")
        
        default_choice = "1" if old_traffic == 'd' else "2"
        ttype = input(f"Выберите тип трафика (1/2) [{default_choice}]: ").strip() or default_choice
        
        if ttype == '1':
            new['traffic_type'] = 'd'
        elif ttype == '2':
            new['traffic_type'] = 'u'
        else:
            new['traffic_type'] = old_traffic
        
        show_change("Тип трафика", 
                   '📥 Download' if old_traffic == 'd' else '📤 Upload',
                   '📥 Download' if new['traffic_type'] == 'd' else '📤 Upload')
        
        # Порог
        old_threshold = s.get('threshold', 0.5 * 1024**2) / (1024**2)
        thr = input(f"\nПорог МБ/с [{old_threshold:.2f}]: ")
        if thr:
            try:
                new['threshold'] = float(thr) * 1024**2
            except Exception:
                print("❌ Неверный формат, оставлено старое значение")
                new['threshold'] = s.get('threshold', 0.5 * 1024**2)
        else:
            new['threshold'] = s.get('threshold', 0.5 * 1024**2)
        show_change("Порог МБ/с", f"{old_threshold:.2f}", f"{new['threshold']/(1024**2):.2f}")
        
        # Мониторинг дисков
        old_monitor_disk = s.get('monitor_disk', False)
        old_monitor_type = s.get('monitor_disk_type', 'all')
        old_monitor_letter = s.get('monitor_disk_letter', '')
        
        print(f"\nТекущий мониторинг дисков: {'✅ ВКЛ' if old_monitor_disk else '❌ ВЫКЛ'}")
        if old_monitor_disk:
            print(f"  Тип мониторинга: {'все диски' if old_monitor_type == 'all' else 'конкретный диск'}")
            if old_monitor_type == 'specific' and old_monitor_letter:
                print(f"  Мониторинг диска: {old_monitor_letter}")
        
        change_disk_mon = ask_yes_no("Изменить мониторинг дисков?", False)
        if change_disk_mon:
            enable_disk_mon = ask_yes_no("Включить мониторинг дисков?", old_monitor_disk)
            if enable_disk_mon:
                new['monitor_disk'] = True
                print("\n1. Мониторинг всех дисков (общая активность)")
                print("2. Мониторинг конкретного диска")
                
                default_mon_type = "1" if old_monitor_type == 'all' else "2"
                disk_mon_type = input(f"Выберите тип мониторинга (1/2) [{default_mon_type}]: ").strip() or default_mon_type
                
                if disk_mon_type == '2':
                    print("\nВыбор диска для мониторинга:")
                    disk_letter = choose_disk()
                    if disk_letter is False:
                        print("❌ Отмена изменения мониторинга дисков.")
                        new['monitor_disk'] = old_monitor_disk
                        new['monitor_disk_type'] = old_monitor_type
                        new['monitor_disk_letter'] = old_monitor_letter
                    elif disk_letter is not None:
                        new['monitor_disk_type'] = 'specific'
                        new['monitor_disk_letter'] = disk_letter
                    else:
                        new['monitor_disk_type'] = 'all'
                else:
                    new['monitor_disk_type'] = 'all'
            else:
                new['monitor_disk'] = False
                new['monitor_disk_type'] = 'all'
        else:
            new['monitor_disk'] = old_monitor_disk
            new['monitor_disk_type'] = old_monitor_type
            new['monitor_disk_letter'] = old_monitor_letter
        
        show_change("Мониторинг дисков", 
                   'ВКЛ' if old_monitor_disk else 'ВЫКЛ',
                   'ВКЛ' if new['monitor_disk'] else 'ВЫКЛ')
        
    elif ptype == 'disk':
        print(f"\n💾 ТИП: Мониторинг дисков")
        
        # Диск
        old_disk = s.get('disk_letter', 'Все диски')
        print(f"\nТекущий диск: {old_disk}")
        change_disk = ask_yes_no("Сменить диск?", False)
        if change_disk:
            new_disk = choose_disk()
            if new_disk is False:
                print("❌ Отмена изменения диска.")
                new['disk_letter'] = old_disk
            elif new_disk is not None:
                new['disk_letter'] = new_disk
            else:
                new['disk_letter'] = 'Все диски'
        else:
            new['disk_letter'] = old_disk
        show_change("Мониторинг диска", old_disk, new['disk_letter'])
        
        # Порог дисков
        old_disk_threshold = s.get('disk_threshold', 1.0)
        thr = input(f"\nПорог дисков МБ/с [{old_disk_threshold}]: ")
        if thr:
            try:
                new['disk_threshold'] = float(thr)
            except Exception:
                print("❌ Неверный формат, оставлено старое")
                new['disk_threshold'] = old_disk_threshold
        else:
            new['disk_threshold'] = old_disk_threshold
        show_change("Порог дисков МБ/с", f"{old_disk_threshold}", f"{new['disk_threshold']}")
                
    elif ptype == 'timer':
        print(f"\n⏰ ТИП: Таймер")
        
        # Задержка
        old_delay = s.get('shutdown_delay', 30)
        print(f"\nТекущая задержка: {format_time(old_delay)}")
        print("Формат: 1h30m15s (часы: h, минуты: m, секунды: s)")
        delay = input("Новая задержка (оставьте пустым чтобы не менять): ").strip()
        
        if delay:
            secs = parse_time_input(delay)
            if secs > 0:
                new['shutdown_delay'] = secs
            else:
                print("❌ Неверный формат времени, оставлено старое")
                new['shutdown_delay'] = old_delay
        else:
            new['shutdown_delay'] = old_delay
        show_change("Задержка", format_time(old_delay), format_time(new['shutdown_delay']))
        
        # Режим действия
        old_action_mode = s.get('action_mode', 's')
        new_action_mode = ask_action_mode("Выберите новое действие:", old_action_mode)
        new['action_mode'] = new_action_mode
        
        action_names = {'s': 'Выключение', 'r': 'Перезагрузка', 'h': 'Спящий режим', 'b': 'Звуковой сигнал'}
        show_change("Дейтие", 
                   action_names.get(old_action_mode, old_action_mode), 
                   action_names.get(new_action_mode, new_action_mode))
    
    # Общие параметры для мониторинга
    if ptype != 'timer':
        # Допустимые пропуски
        old_failures = s.get('allowed_failures', 3)
        try:
            af = input(f"\nДопустимые пропуски [{old_failures}]: ")
            if af:
                new['allowed_failures'] = int(af)
            else:
                new['allowed_failures'] = old_failures
        except Exception:
            print("❌ Неверный формат числа, оставлено старое")
            new['allowed_failures'] = old_failures
        show_change("Допустимые пропуски", old_failures, new['allowed_failures'])
        
        # Интервал проверки
        old_interval = s.get('interval', 5)
        try:
            interval = input(f"\nИнтервал проверки в секундах [{old_interval}]: ")
            if interval:
                new['interval'] = int(interval)
            else:
                new['interval'] = old_interval
        except Exception:
            print("❌ Неверный формат числа, оставлено старое")
            new['interval'] = old_interval
        show_change("Интервал проверки", f"{old_interval} сек", f"{new['interval']} сек")
        
        # Режим действия
        old_action_mode = s.get('action_mode', 's')
        new_action_mode = ask_action_mode("Выберите новое действие:", old_action_mode)
        new['action_mode'] = new_action_mode
        
        action_names = {'s': 'Выключение', 'r': 'Перезагрузка', 'h': 'Спящий режим', 'b': 'Звуковой сигнал'}
        show_change("Действие", 
                   action_names.get(old_action_mode, old_action_mode), 
                   action_names.get(new_action_mode, new_action_mode))
    
    # Показ всех изменений
    print(f"\n{'═' * 60}")
    print("📋 Сводка изменений:")
    print(f"{'═' * 60}")
    
    # Собираем все изменения
    changes = []
    for key in set(list(s.keys()) + list(new.keys())):
        if key in s and key in new:
            if s[key] != new[key]:
                changes.append((key, s[key], new[key]))
        elif key in s:
            changes.append((key, s[key], "УДАЛЕНО"))
        elif key in new:
            changes.append((key, "ДОБАВЛЕНО", new[key]))
    
    if not changes:
        print("  ❌ Изменений нет")
    else:
        for key, old_val, new_val in changes:
            # Форматируем значения для отображения
            if key == 'threshold':
                old_val = f"{old_val/(1024**2):.2f} МБ/с" if isinstance(old_val, (int, float)) else old_val
                new_val = f"{new_val/(1024**2):.2f} МБ/с" if isinstance(new_val, (int, float)) else new_val
            elif key == 'action_mode':
                action_names = {'s': 'Выключение', 'r': 'Перезагрузка', 'h': 'Спящий режим', 'b': 'Звук'}
                old_val = action_names.get(str(old_val), old_val)
                new_val = action_names.get(str(new_val), new_val)
            elif key == 'traffic_type':
                old_val = '📤 Upload' if old_val == 'u' else '📥 Download'
                new_val = '📤 Upload' if new_val == 'u' else '📥 Download'
            elif key == 'monitor_disk':
                old_val = '✅ ВКЛ' if old_val else '❌ ВЫКЛ'
                new_val = '✅ ВКЛ' if new_val else '❌ ВЫКЛ'
            
            print(f"  {key}: {old_val} → {new_val}")
    
    print(f"{'═' * 60}")
    
    # Подтверждение
    confirm = ask_yes_no("\nСохранить изменения?", True)
    if confirm:
        if save_profile(profile_name, new):
            print(f"💾 Профиль '{profile_name}' обновлён!")
            return True
    else:
        print("❌ Изменения отменены")
        return False
    
    return False


def create_new_profile():
    """
    Создание нового профиля с графической визуализацией
    """
    print(f"\n╔{'═' * 60}╗")
    print(f"║{'СОЗДАНИЕ НОВОГО ПРОФИЛЯ':^60}║")
    print(f"╚{'═' * 60}╝")
    
    # Ввод имени профиля
    while True:
        name = input("\n📝 Введите имя профиля: ").strip()
        if not name:
            print("❌ Имя не может быть пустым")
            continue
        profiles = load_profiles()
        if name in profiles:
            print("❌ Профиль с таким именем уже существует")
            continue
        break
    
    # Выбор типа профиля
    print(f"\n{'═' * 60}")
    print("📊 Выберите тип профиля:")
    print("1. 📡 Мониторинг сети")
    print("2. 💾 Мониторинг дисков")
    print("3. ⏰ Таймер")
    print(f"{'═' * 60}")
    
    while True:
        tp = input("\nВыберите тип (1/2/3): ").strip()
        if tp in ('1', '2', '3'):
            break
        print("❌ Неверный выбор")
    
    settings = {}
    
    if tp == '1':  # Мониторинг сети
        print(f"\n{'═' * 60}")
        print("📡 НАСТРОЙКА МОНИТОРИНГА СЕТИ")
        print(f"{'═' * 60}")
        
        # Выбор интерфейса
        print("\n📶 Выберите сетевой интерфейс:")
        interface = choose_interface()
        if not interface:
            print("❌ Создание профиля отменено.")
            return
        
        settings['type'] = 'network'
        settings['interface'] = interface
        
        # Тип трафика
        print(f"\n{'─' * 40}")
        print("📊 Тип трафика:")
        print("1. 📥 Download (входящий трафик)")
        print("2. 📤 Upload (исходящий трафик)")
        
        while True:
            tt_choice = input("\nВыберите тип трафика (1/2) [1]: ").strip() or '1'
            if tt_choice == '1':
                settings['traffic_type'] = 'd'
                break
            elif tt_choice == '2':
                settings['traffic_type'] = 'u'
                break
            else:
                print("❌ Неверный выбор. Введите 1 или 2")
        
        # Порог
        thr = input("\n🔢 Порог МБ/с [0.5]: ")
        try:
            thr_val = float(thr) if thr else 0.5
        except Exception:
            thr_val = 0.5
        settings['threshold'] = thr_val * 1024**2
        
        # Допустимые пропуски
        af = input("\n⚠️  Допустимые пропуски [3]: ")
        try:
            af_val = int(af) if af else 3
        except Exception:
            af_val = 3
        settings['allowed_failures'] = af_val
        
        # Интервал проверки
        interval = input("\n⏱️  Интервал проверки в секундах [5]: ")
        try:
            interval_val = int(interval) if interval else 5
        except Exception:
            interval_val = 5
        settings['interval'] = interval_val
        
        # Задержка до действия
        print(f"\n{'─' * 40}")
        print("⏳ ЗАДЕРЖКА ДО ДЕЙСТВИЯ")
        print("Формат: 1h30m15s (часы: h, минуты: m, секунды: s)")
        print("Примеры: 30s, 1h30m, 2h, 45m10s")
        print(f"{'─' * 40}")
        
        delay = input("\nВведите задержку [30s]: ")
        sd = parse_time_input(delay) if delay else 30
        settings['shutdown_delay'] = sd
        
        # Режим действия
        settings['action_mode'] = ask_action_mode("Выберите действие при срабатывании:", 's')
        
        # Мониторинг дисков
        print(f"\n{'═' * 60}")
        print("💾 ДОПОЛНИТЕЛЬНЫЙ МОНИТОРИНГ ДИСКОВ")
        print(f"{'═' * 60}")
        
        monitor_disk_choice = ask_yes_no("Включить мониторинг дисков?", False)
        
        if monitor_disk_choice:
            settings['monitor_disk'] = True
            print("\n📁 Выберите тип мониторинга дисков:")
            print("1. Все диски (общая активность)")
            print("2. Конкретный диск")
            
            disk_mon_type = input("\nВыберите тип (1/2) [1]: ").strip() or '1'
            
            if disk_mon_type == '2':
                print("\n💿 Выбор диска для мониторинга:")
                disk_letter = choose_disk()
                if disk_letter is False:
                    print("❌ Создание профиля отменено.")
                    return
                elif disk_letter is not None:
                    settings['monitor_disk_type'] = 'specific'
                    settings['monitor_disk_letter'] = disk_letter
                else:
                    settings['monitor_disk_type'] = 'all'
            else:
                settings['monitor_disk_type'] = 'all'
        else:
            settings['monitor_disk'] = False
            settings['monitor_disk_type'] = 'all'
        
    elif tp == '2':  # Мониторинг дисков
        print(f"\n{'═' * 60}")
        print("💾 НАСТРОЙКА МОНИТОРИНГА ДИСКОВ")
        print(f"{'═' * 60}")
        
        settings['type'] = 'disk'
        
        # Выбор диска
        print("\n💿 Выберите диск для мониторинга:")
        disk_letter = choose_disk()
        
        if disk_letter is False:
            print("❌ Создание профиля отменено.")
            return
        
        if disk_letter is not None:
            settings['disk_letter'] = disk_letter
        
        # Порог дисков
        thr = input("\n🔢 Порог МБ/с [1.0]: ")
        try:
            thr_val = float(thr) if thr else 1.0
        except Exception:
            thr_val = 1.0
        settings['disk_threshold'] = thr_val
        
        # Допустимые пропуски
        af = input("\n⚠️  Допустимые пропуски [3]: ")
        try:
            af_val = int(af) if af else 3
        except Exception:
            af_val = 3
        settings['allowed_failures'] = af_val
        
        # Интервал проверки
        interval = input("\n⏱️  Интервал проверки в секундах [5]: ")
        try:
            interval_val = int(interval) if interval else 5
        except Exception:
            interval_val = 5
        settings['interval'] = interval_val
        
        # Задержка до действия
        print(f"\n{'═' * 60}")
        print("⏳ ЗАДЕРЖКА ДО ДЕЙСТВИЯ")
        print(f"{'═' * 60}")
        print("Формат: 1h30m15s (часы: h, минуты: m, секунды: s)")
        print("Примеры: 30s, 1h30m, 2h, 45m10s")
        
        delay = input("\nВведите задержку [30s]: ")
        sd = parse_time_input(delay) if delay else 30
        settings['shutdown_delay'] = sd
        
        # Режим действия
        settings['action_mode'] = ask_action_mode("Выберите действие при срабатывании:", 's')
        
    elif tp == '3':  # Таймер
        print(f"\n{'═' * 60}")
        print("⏰ НАСТРОЙКА ТАЙМЕРА")
        print(f"{'═' * 60}")
        
        settings['type'] = 'timer'
        
        # Задержка
        print(f"\n{'─' * 40}")
        print("⏳ ВВЕДИТЕ ВРЕМЯ ЗАДЕРЖКИ")
        print("Формат: 1h30m15s (часы: h, минуты: m, секунды: s)")
        print("Примеры: 30s, 1h30m, 2h, 45m10s")
        print(f"{'─' * 40}")
        
        while True:
            delay = input("\nВведите время задержки: ").strip()
            if not delay:
                print("❌ Время не может быть пустым")
                continue
            
            sd = parse_time_input(delay)
            if sd <= 0:
                print("❌ Время должно быть больше 0")
                continue
            
            settings['shutdown_delay'] = sd
            break
        
        # Режим действия
        settings['action_mode'] = ask_action_mode("Выберите действие:", 's')
    
    # Показать сводку настроек
    print(f"\n{'═' * 60}")
    print("📋 СВОДКА НАСТРОЕК ПРОФИЛЯ")
    print(f"{'═' * 60}")
    print(f"📝 Имя профиля: {name}")
    print(f"📊 Тип профиля: ", end="")
    
    action_names = {'s': '⏻ Выключение', 'r': '🔄 Перезагрузка', 'h': '💤 Спящий режим', 'b': '🔊 Звуковой сигнал'}
    
    if tp == '1':
        print("📡 Мониторинг сети")
        print(f"  📶 Интерфейс: {settings.get('interface', 'Не указан')}")
        print(f"  📊 Тип трафика: {'📥 Download' if settings.get('traffic_type') == 'd' else '📤 Upload'}")
        print(f"  🔢 Порог: {settings.get('threshold', 0)/(1024**2):.2f} МБ/с")
        print(f"  ⚠️  Допустимые пропуски: {settings.get('allowed_failures', 3)}")
        print(f"  ⏱️  Интервал: {settings.get('interval', 5)} сек")
        print(f"  ⏳ Задержка: {format_time(settings.get('shutdown_delay', 30))}")
        print(f"  ⚡ Действие: {action_names.get(settings.get('action_mode', 's'), 'Выключение')}")
        
        if settings.get('monitor_disk', False):
            print(f"  💾 Мониторинг дисков: ✅ ВКЛ")
            if settings.get('monitor_disk_type') == 'specific':
                print(f"    📁 Диск: {settings.get('monitor_disk_letter', 'Не указан')}")
            else:
                print(f"    📁 Диски: Все диски")
        else:
            print(f"  💾 Мониторинг дисков: ❌ ВЫКЛ")
            
    elif tp == '2':
        print("💾 Мониторинг дисков")
        if 'disk_letter' in settings:
            print(f"  💿 Диск: {settings.get('disk_letter')}")
        else:
            print(f"  💿 Диски: Все диски")
        print(f"  🔢 Порог: {settings.get('disk_threshold', 1.0)} МБ/с")
        print(f"  ⚠️  Допустимые пропуски: {settings.get('allowed_failures', 3)}")
        print(f"  ⏱️  Интервал: {settings.get('interval', 5)} сек")
        print(f"  ⏳ Задержка: {format_time(settings.get('shutdown_delay', 30))}")
        print(f"  ⚡ Действие: {action_names.get(settings.get('action_mode', 's'), 'Выключение')}")
        
    elif tp == '3':
        print("⏰ Таймер")
        print(f"  ⏳ Задержка: {format_time(settings.get('shutdown_delay', 30))}")
        print(f"  ⚡ Действие: {action_names.get(settings.get('action_mode', 's'), 'Выключение')}")
    
    print(f"{'═' * 60}")
    
    # Подтверждение создания
    confirm = ask_yes_no("\nСохранить профиль?", True)
    if confirm:
        if save_profile(name, settings):
            print(f"\n🎉 Профиль '{name}' успешно создан!")
            return True
    else:
        print("❌ Создание профиля отменено")
        return False
    
    return False


def choose_interface() -> str:
    if psutil is None:
        print("❗ psutil не установлен")
        return None
    try:
        nics = list(psutil.net_io_counters(pernic=True).keys())
        if not nics:
            print("❗ Интерфейсы не найдены")
            return None
        
        print(f"\n{'═' * 60}")
        print("📶 ВЫБОР СЕТЕВОГО ИНТЕРФЕЙСА")
        print(f"{'═' * 60}")
        
        for i, nic in enumerate(nics, 1):
            print(f"{i}. {nic}")
        
        while True:
            c = input(f"\nВведите номер интерфейса (1-{len(nics)}) или Enter для отмены: ")
            if not c:
                return None
            try:
                idx = int(c) - 1
                if 0 <= idx < len(nics):
                    selected = nics[idx]
                    print(f"✅ Выбран интерфейс: {selected}")
                    return selected
                else:
                    print("❌ Неверный номер")
            except Exception:
                print("❌ Неверный ввод")
    except Exception as e:
        print(f"❌ Ошибка получения интерфейсов: {e}")
        return None

# ---------------------- Главное меню ----------------------

def main():
    try:
        # Восстанавливаем состояние питания при запуске
        restore_power_state()
        
        while True:
            print(f"\n╔{'═' * 60}╗")
            print(f"║{'ShutdownShell v' + __version__:^60}║")
            print(f"╚{'═' * 60}╝")
            
            print("\n📋 ГЛАВНОЕ МЕНЮ:")
            print("1. 🚀 Выбрать существующий профиль (мониторинг / таймер)")
            print("2. 🆕 Создать новый профиль")
            print("3. 🗑️  Удалить профиль")
            print("4. ✏️  Редактировать профиль")
            print("5. 🔄 Изменить порядок профилей")
            print("6. ⏱️  Таймер быстрый старт (без сохранения)")
            print("7. 💾 Мониторинг только дисков")
            print("8. 🖥️  Управление дисплеем")
            print("9. 🚪 Выход")

            ch = input("\n🔘 Выберите вариант (1-9): ")
            
            if ch == '1':
                profiles = load_profiles()
                if not profiles:
                    print("\n❗ Нет сохранённых профилей.")
                    continue
                
                print(f"\n{'═' * 60}")
                print("📂 ВЫБОР ПРОФИЛЯ")
                print(f"{'═' * 60}")
                
                names = list(profiles.keys())
                for i, n in enumerate(names, 1):
                    ptype = profiles[n].get('type', 'unknown')
                    icon = '📡' if ptype == 'network' else '💾' if ptype == 'disk' else '⏰' if ptype == 'timer' else '❓'
                    print(f"{i}. {icon} {n}")
                
                sel = input(f"\n🔘 Введите номер профиля (1-{len(names)}) или Enter для отмены: ")
                if not sel:
                    continue
                try:
                    idx = int(sel) - 1
                    if idx < 0 or idx >= len(names):
                        print("❌ Неверный номер")
                        continue
                    
                    pname = names[idx]
                    p = profiles[pname]
                    
                    print(f"\n{'═' * 60}")
                    print(f"🚀 ЗАПУСК ПРОФИЛЯ: {pname}")
                    print(f"{'═' * 60}")
                    
                    if p.get('type') == 'timer':
                        delay = p.get('shutdown_delay', 30)
                        mode = p.get('action_mode', 's')
                        cancel_event = threading.Event()
                        input_thread = threading.Thread(target=check_user_input, args=(cancel_event,), daemon=True)
                        input_thread.start()
                        countdown_action(delay, cancel_event, mode)
                        print("\n🔙 Возврат в меню...")
                        continue
                    
                    if p.get('type') == 'disk':
                        disk_letter = p.get('disk_letter')
                        while True:
                            should_restart = monitor_disk_only(
                                p.get('allowed_failures', 3),
                                p.get('disk_threshold', 1.0),
                                p.get('interval', 5),
                                p.get('shutdown_delay', 30),
                                p.get('action_mode', 's'),
                                disk_letter
                            )
                            if not should_restart:
                                return
                            print("\nНажмите Enter для возврата в меню или любую другую клавишу для перезапуска мониторинга...")
                            if msvcrt and msvcrt.getch() == b'\r':
                                break
                    elif p.get('type') == 'network':
                        while True:
                            should_restart = monitor_traffic(
                                p.get('interface'),
                                p.get('traffic_type', 'd'),
                                p.get('allowed_failures', 3),
                                p.get('threshold', 0.5 * 1024**2),
                                p.get('interval', 5),
                                p.get('shutdown_delay', 30),
                                p.get('action_mode', 's'),
                                p.get('monitor_disk', False),
                                p.get('monitor_disk_type', 'all'),
                                p.get('monitor_disk_letter', None)
                            )
                            if not should_restart:
                                return
                            print("\nНажмите Enter для возврата в меню или любую другую клавишу для перезапуска мониторинга...")
                            if msvcrt and msvcrt.getch() == b'\r':
                                break
                except Exception as e:
                    print(f"❌ Ошибка: {e}")

            elif ch == '2':
                create_new_profile()

            elif ch == '3':
                delete_profile()

            elif ch == '4':
                profiles = load_profiles()
                if not profiles:
                    print("\n❗ Нет сохранённых профилей.")
                    continue
                
                print(f"\n{'═' * 60}")
                print("✏️  РЕДАКТИРОВАНИЕ ПРОФИЛЯ")
                print(f"{'═' * 60}")
                
                names = list(profiles.keys())
                for i, n in enumerate(names, 1):
                    ptype = profiles[n].get('type', 'unknown')
                    icon = '📡' if ptype == 'network' else '💾' if ptype == 'disk' else '⏰' if ptype == 'timer' else '❓'
                    print(f"{i}. {icon} {n}")
                
                sel = input(f"\n🔘 Введите номер профиля для редактирования (1-{len(names)}) или Enter для отмены: ")
                if not sel:
                    continue
                try:
                    idx = int(sel) - 1
                    if idx < 0 or idx >= len(names):
                        print("❌ Неверный номер")
                        continue
                    edit_profile(names[idx])
                except Exception:
                    print("❌ Неверный ввод")

            elif ch == '5':
                profiles = load_profiles()
                if not profiles:
                    print("\n❗ Нет сохранённых профилей.")
                    continue
                keys = list(profiles.keys())
                print("\nТекущий порядок:")
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
                timed_action_interactive(allow_save=False)

            elif ch == '7':
                try:
                    print(f"\n{'═' * 60}")
                    print("💾 БЫСТРЫЙ МОНИТОРИНГ ДИСКОВ")
                    print(f"{'═' * 60}")
                    
                    print("\n💿 Выберите диск для мониторинга:")
                    disk_letter = choose_disk()
                    
                    if disk_letter is False:
                        print("❌ Мониторинг отменён.")
                        continue
                    
                    thr = input("\n🔢 Порог МБ/с [1.0]: ")
                    thr = float(thr) if thr else 1.0
                    af = input("\n⚠️  Допустимые пропуски [3]: ")
                    af = int(af) if af else 3
                    interval = input("\n⏱️  Интервал сек [5]: ")
                    interval = int(interval) if interval else 5
                    
                    print(f"\n{'─' * 40}")
                    print("⏳ ЗАДЕРЖКА ДО ДЕЙСТВИЯ")
                    print("Формат: 1h30m15s (часы: h, минуты: m, секунды: s)")
                    print(f"{'─' * 40}")
                    
                    delay = input("\nВведите задержку [30s]: ")
                    sd = parse_time_input(delay) if delay else 30
                    
                    action_mode = ask_action_mode("Выберите действие при срабатывании:", 's')
                    
                    while True:
                        should_restart = monitor_disk_only(af, thr, interval, sd, action_mode, disk_letter)
                        if not should_restart:
                            return
                        print("\nНажмите Enter для возврата в меню или любую другую клавишу для перезапуска мониторинга...")
                        if msvcrt and msvcrt.getch() == b'\r':
                            break
                except Exception as e:
                    print(f"❌ Ошибка: {e}")

            elif ch == '8':
                while True:
                    print(f"\n{'═' * 60}")
                    print("🖥️  УПРАВЛЕНИЕ ДИСПЛЕЕМ")
                    print(f"{'═' * 60}")
                    print("1. Выключить дисплей")
                    print("2. Включить дисплей")
                    print("3. Переключить (вкл/выкл)")
                    print("4. Назад")
                    c = input("\n🔘 Выберите: ")
                    if c == '1':
                        turn_off_display()
                        # Восстанавливаем управление питанием
                        restore_power_state()
                    elif c == '2':
                        turn_on_display()
                    elif c == '3':
                        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
                        time.sleep(0.5)
                        restore_power_state()
                        print("✅ Дисплей переключён")
                    elif c == '4':
                        break
                    else:
                        print("❌ Неверный выбор")

            elif ch == '9':
                print(f"\n{'═' * 60}")
                print("👋 До свидания!")
                print(f"{'═' * 60}")
                break

            else:
                print("❌ Неверный выбор. Попробуйте снова.")

    except KeyboardInterrupt:
        print("\n\n🛑 Программа прервана пользователем.")
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")


if __name__ == '__main__':
    main()