#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ShutdownShell v1.3.5
Исправления:
 - Ctrl+D выключает дисплей без блокировки Windows (SetThreadExecutionState)
 - Добавлен тип профиля 'timer' — таймерные профили сохраняются в profiles.json и запускаются как пресеты
Автор: System Tools (modified)
"""

import os
import sys
import subprocess
import time
import psutil
import threading
import msvcrt
import json
import re
import ctypes
import winsound
import random


__version__ = "1.3.5"
__author__ = "Crazydownload"
__description__ = "Automated shutdown utility for download/IO monitoring with timer profiles"

CONFIG_FILE = "Settings.json"

# Списки процессов для мониторинга (не используются в текущем коде, оставлены для расширения)
GAME_LAUNCHERS = [
    'steam.exe', 'epicgameslauncher.exe', 'origin.exe',
    'battle.net.exe', 'goggalaxy.exe', 'ubisoftconnect.exe',
    'eaapp.exe', 'riotclient.exe', 'bethesda.net.exe', "pdr.exe", "pdstyleagent.exe"
]

SYSTEM_PROCESSES = [
    'system', 'svchost.exe', 'explorer.exe', 'searchindexer.exe',
    'dllhost.exe', 'taskhostw.exe', 'wininit.exe', 'csrss.exe',
    'winlogon.exe', 'services.exe', 'lsass.exe', 'smss.exe'
]

# Для управления энергосбережением (чтобы избежать блокировки Windows при выключении дисплея)
ES_CONTINUOUS = 0x80000000
ES_DISPLAY_REQUIRED = 0x00000002

def turn_off_display():
    """Выключает дисплей безопасным способом без блокировки Windows."""
    try:
        # Устанавливаем флаг, чтобы ОС не считала, что пользователь отошел и не блокировала систему
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED)

        # Отправляем сообщение всем окнам для выключения монитора (2 — выключить)
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        print("\n🖥️ Дисплей выключен")
        return True
    except Exception as e:
        print(f"❌ Ошибка при выключении дисплея: {e}")
        return False

def display_control_menu():
    """Меню управления дисплеем"""
    try:
        while True:
            print("\n=== Управление дисплеем ===")
            print("1. Выключить дисплей")
            print("2. Включить дисплей")
            print("3. Переключить дисплей (вкл/выкл)")
            print("4. Назад в главное меню")
            
            choice = input("\nВыберите действие (1/2/3/4): ")
            
            if choice == "1":
                if turn_off_display():
                    print("✅ Дисплей выключен")
                else:
                    print("❌ Не удалось выключить дисплей")
                    
            elif choice == "2":
                try:
                    ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)
                    print("✅ Дисплей включен")
                except Exception as e:
                    print(f"❌ Ошибка при включении дисплея: {e}")
                    
            elif choice == "3":
                try:
                    ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
                    print("✅ Состояние дисплея переключено")
                except Exception as e:
                    print(f"❌ Ошибка при переключении дисплея: {e}")
                    
            elif choice == "4":
                break
            else:
                print("❌ Неверный выбор. Попробуйте снова.")
    except Exception as e:
        print(f"❌ Ошибка в меню управления дисплеем: {e}")

def parse_time_input(time_str):
    """Разбирает строку времени в формате 1h30m15s -> секунды"""
    if not time_str:
        return 0
    cleaned = re.sub(r'[^0-9hms]', '', time_str.lower())
    hours = minutes = seconds = 0
    if 'h' in cleaned:
        parts = cleaned.split('h', 1)
        hours = int(parts[0]) if parts[0] else 0
        cleaned = parts[1] if len(parts) > 1 else ''
    if 'm' in cleaned:
        parts = cleaned.split('m', 1)
        minutes = int(parts[0]) if parts[0] else 0
        cleaned = parts[1] if len(parts) > 1 else ''
    if 's' in cleaned:
        parts = cleaned.split('s', 1)
        seconds = int(parts[0]) if parts[0] else 0
    return hours * 3600 + minutes * 60 + seconds

def format_time(seconds):
    """Форматирует секунды в читаемый вид, пример: 1h 2m 3s"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)

def is_game_launcher(pid):
    try:
        process = psutil.Process(pid)
        name = process.name().lower()
        return any(launcher in name for launcher in GAME_LAUNCHERS)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

def is_system_process(pid):
    try:
        process = psutil.Process(pid)
        name = process.name().lower()
        return name in SYSTEM_PROCESSES
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

def check_disk_activity(threshold=1.0):
    """
    Проверяет активность дисков.
    threshold - порог в МБ/с.
    Возвращает True если есть значимая активность.
    """
    try:
        disk_start = psutil.disk_io_counters()
        time.sleep(0.5)
        disk_end = psutil.disk_io_counters()
        total_bytes = (disk_end.read_bytes + disk_end.write_bytes -
                       disk_start.read_bytes - disk_start.write_bytes)
        speed_mb = total_bytes / (1024 * 1024)
        if speed_mb < threshold:
            return False
        print(f"\n💾 Активность дисков: {speed_mb:.2f} МБ/с")
        return True
    except Exception as e:
        print(f"⚠️ Ошибка проверки дисков: {e}")
        return False

def get_interface():
    """Выбор сетевого интерфейса"""
    try:
        interfaces = list(psutil.net_io_counters(pernic=True).keys())
        if not interfaces:
            print("\n❌ Не найдено сетевых интерфейсов!")
            return None
        print("Доступные интерфейсы:")
        for idx, name in enumerate(interfaces, 1):
            print(f"{idx}. {name}")
        while True:
            try:
                choice = input("\nВведите номер интерфейса (или Enter для отмены): ")
                if not choice:
                    return None
                choice = int(choice) - 1
                return interfaces[choice]
            except (ValueError, IndexError):
                print("❌ Неверный ввод. Попробуйте снова.")
    except Exception as e:
        print(f"\n❌ Ошибка при получении интерфейсов: {e}")
        return None

def save_profile(profile_name, settings):
    """Сохраняет профиль в файл"""
    try:
        profiles = load_profiles()
        profiles[profile_name] = settings
        with open(CONFIG_FILE, "w", encoding='utf-8') as file:
            json.dump(profiles, file, indent=4, ensure_ascii=False)
        print(f"\n✅ Профиль '{profile_name}' сохранен в '{CONFIG_FILE}'.")
        return True
    except Exception as e:
        print(f"\n❌ Ошибка при сохранении профиля: {e}")
        return False

def load_profiles():
    """Загружает профили из файла"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding='utf-8') as file:
                return json.load(file)
        return {}
    except Exception as e:
        print(f"\n❌ Ошибка при загрузке профилей: {e}")
        return {}

def list_profiles():
    """Выводит список сохраненных профилей"""
    try:
        profiles = load_profiles()
        if not profiles:
            print("\n❌ Нет сохраненных профилей.")
            return None
        print("\nДоступные профили:")
        for idx, name in enumerate(profiles.keys(), 1):
            print(f"{idx}. {name}")
        return profiles
    except Exception as e:
        print(f"\n❌ Ошибка при выводе профилей: {e}")
        return None

def delete_profile():
    """Удаляет выбранный профиль"""
    try:
        profiles = list_profiles()
        if not profiles:
            print("\n❌ Нет сохраненных профилей для удаления.")
            return
        print("\nВыберите профиль для удаления:")
        profile_names = list(profiles.keys())
        for idx, name in enumerate(profile_names, 1):
            print(f"{idx}. {name}")
        while True:
            try:
                choice = input("\nВведите номер профиля для удаления (0 - отмена): ")
                if choice == '0':
                    return
                if not choice:
                    continue
                choice = int(choice)
                if 1 <= choice <= len(profile_names):
                    profile_to_delete = profile_names[choice - 1]
                    confirm = input(f"\nВы уверены, что хотите удалить профиль '{profile_to_delete}'? (y/n): ").lower()
                    if confirm == 'y':
                        del profiles[profile_to_delete]
                        with open(CONFIG_FILE, "w", encoding='utf-8') as file:
                            json.dump(profiles, file, indent=4, ensure_ascii=False)
                        print(f"\n✅ Профиль '{profile_to_delete}' успешно удален.")
                        return
                    else:
                        print("\n❌ Удаление отменено.")
                        return
                else:
                    print("❌ Неверный номер профиля. Попробуйте снова.")
            except ValueError:
                print("❌ Введите число. Попробуйте снова.")
    except Exception as e:
        print(f"\n❌ Ошибка при удалении профиля: {e}")

def move_profile():
    """Изменяет порядок профилей"""
    try:
        profiles = load_profiles()
        if not profiles:
            print("\n❌ Нет сохраненных профилей для перемещения.")
            return
        profile_names = list(profiles.keys())
        print("\nТекущий порядок профилей:")
        for idx, name in enumerate(profile_names, 1):
            print(f"{idx}. {name}")
        while True:
            try:
                choice = input("\nВведите номер профиля для перемещения (0 - отмена): ")
                if choice == '0':
                    return
                if not choice:
                    continue
                choice = int(choice)
                if 1 <= choice <= len(profile_names):
                    profile_to_move = profile_names[choice - 1]
                    new_position = input(f"Введите новую позицию для профиля '{profile_to_move}' (1-{len(profile_names)}): ")
                    if not new_position:
                        continue
                    new_position = int(new_position)
                    if 1 <= new_position <= len(profile_names):
                        if choice == new_position:
                            print("\n❌ Профиль уже находится на этой позиции.")
                            continue
                        new_profiles = {}
                        keys = list(profiles.keys())
                        keys.remove(profile_to_move)
                        keys.insert(new_position - 1, profile_to_move)
                        for key in keys:
                            new_profiles[key] = profiles[key]
                        with open(CONFIG_FILE, "w", encoding='utf-8') as file:
                            json.dump(new_profiles, file, indent=4, ensure_ascii=False)
                        print("\n✅ Порядок профилей успешно изменен.")
                        return
                    else:
                        print(f"❌ Позиция должна быть от 1 до {len(profile_names)}.")
                else:
                    print("❌ Неверный номер профиля. Попробуйте снова.")
            except ValueError:
                print("❌ Введите число. Попробуйте снова.")
    except Exception as e:
        print(f"\n❌ Ошибка при перемещении профиля: {e}")

def edit_profile(profile_name):
    """Редактирует выбранный профиль"""
    try:
        profiles = load_profiles()
        if profile_name not in profiles:
            print("\n❌ Профиль не найден.")
            return False
        settings = profiles[profile_name]
        new_settings = settings.copy()
        print(f"\nРедактирование профиля: {profile_name}")
        print("Нажмите Enter, чтобы оставить текущее значение\n")

        profile_type = settings.get('type', 'network' if 'interface' in settings else ('disk' if 'disk_threshold' in settings else 'timer'))

        if profile_type == 'network':
            print(f"Текущий интерфейс: {settings.get('interface', '')}")
            print("1. Выбрать новый интерфейс")
            print("2. Оставить текущий")
            interface_choice = input("Выберите вариант (1/2): ")
            if interface_choice == "1":
                new_interface = get_interface()
                if new_interface:
                    new_settings['interface'] = new_interface

            current_type = 'Upload (u)' if settings.get('traffic_type') == 'u' else 'Download (d)'
            print(f"\nТекущий тип трафика: {current_type}")
            new_type = input("Введите новый тип трафика (u/d) или Enter чтобы оставить текущий: ").lower()
            if new_type in ['u', 'd']:
                new_settings['traffic_type'] = new_type

            current_threshold = settings.get('threshold', 0) / 1024**2
            print(f"\nТекущая пороговая скорость сети: {current_threshold:.2f} МБ/с")
            new_threshold = input("Введите новую пороговую скорость (МБ/с) или Enter чтобы оставить текущую: ")
            if new_threshold:
                try:
                    new_settings['threshold'] = float(new_threshold) * 1024**2
                except ValueError:
                    print("❌ Неверный формат числа. Оставлено текущее значение.")

        elif profile_type == 'disk':
            current_threshold = settings.get('disk_threshold', 1.0)
            print(f"\nТекущая пороговая скорость дисков: {current_threshold:.2f} МБ/с")
            new_threshold = input("Введите новую пороговую скорость (МБ/с) или Enter чтобы оставить текущую: ")
            if new_threshold:
                try:
                    new_settings['disk_threshold'] = float(new_threshold)
                except ValueError:
                    print("❌ Неверный формат числа. Оставлено текущее значение.")
        elif profile_type == 'timer':
            current_delay = settings.get('shutdown_delay', 30)
            print(f"\nТекущая задержка до действия: {format_time(current_delay)}")
            new_delay = input("Введите новую задержку (например, 1h30m15s) или Enter чтобы оставить текущую: ")
            if new_delay:
                try:
                    parsed_seconds = parse_time_input(new_delay)
                    if parsed_seconds > 0:
                        new_settings['shutdown_delay'] = parsed_seconds
                    else:
                        print("❌ Некорректный формат времени. Оставлено текущее значение.")
                except ValueError:
                    print("❌ Неверный формат времени. Оставлено текущее значение.")

        # Общие параметры
        print(f"\nТекущее количество допустимых пропусков: {settings.get('allowed_failures', 3)}")
        new_failures = input("Введите новое количество или Enter чтобы оставить текущее: ")
        if new_failures:
            try:
                new_settings['allowed_failures'] = int(new_failures)
            except ValueError:
                print("❌ Неверный формат числа. Оставлено текущее значение.")

        print(f"\nТекущий интервал проверки: {settings.get('interval', 5)} сек")
        new_interval = input("Введите новый интервал (сек) или Enter чтобы оставить текущий: ")
        if new_interval:
            try:
                new_settings['interval'] = int(new_interval)
            except ValueError:
                print("❌ Неверный формат числа. Оставлено текущее значение.")

        current_delay = settings.get('shutdown_delay', 30)
        print(f"\nТекущая задержка до выключения: {format_time(current_delay)}")
        new_delay = input("Введите новую задержку (например, 1h30m15s) или Enter чтобы оставить текущую: ")
        if new_delay:
            try:
                parsed_seconds = parse_time_input(new_delay)
                if parsed_seconds > 0:
                    new_settings['shutdown_delay'] = parsed_seconds
                else:
                    print("❌ Некорректный формат времени. Оставлено текущее значение.")
            except ValueError:
                print("❌ Неверный формат времени. Оставлено текущее значение.")

        action_modes = {
            's': 'Выключение',
            'r': 'Перезагрузка',
            'h': 'Спящий режим',
            'b': 'Звуковой сигнал'
        }
        current_mode = settings.get('action_mode', 's')
        print(f"\nТекущий режим действия: {action_modes.get(current_mode, 'Выключение')}")
        print("Доступные режимы:")
        print("s - Выключение компьютера")
        print("r - Перезагрузка компьютера")
        print("h - Спящий режим")
        print("b - Звуковой сигнал")
        new_mode = input("Введите новый режим действия (s/r/h/b) или Enter чтобы оставить текущий: ").lower()
        if new_mode in ['s', 'r', 'h', 'b']:
            new_settings['action_mode'] = new_mode

        if profile_type != 'disk' and profile_type != 'timer':
            current_disk_monitoring = settings.get('monitor_disk', False)
            print(f"\nТекущая настройка мониторинга дисков: {'Включен' if current_disk_monitoring else 'Отключен'}")
            disk_monitoring = input("Включить мониторинг активности дисков? (y/n) или Enter чтобы оставить текущее: ").lower()
            if disk_monitoring == 'y':
                new_settings['monitor_disk'] = True
            elif disk_monitoring == 'n':
                new_settings['monitor_disk'] = False

        print("\nИзмененные настройки:")
        print(json.dumps(new_settings, ensure_ascii=False, indent=2))

        save = input("\nСохранить изменения? (y/n): ").lower()
        if save == 'y':
            return save_profile(profile_name, new_settings)
        else:
            print("❌ Изменения не сохранены.")
            return False

    except Exception as e:
        print(f"\n❌ Ошибка при редактировании профиля: {e}")
        return False

def perform_action(action_mode):
    """Выполняет выбранное действие"""
    try:
        if action_mode == 's':
            subprocess.run(['shutdown', '/s', '/t', '0'], capture_output=True, shell=False)
        elif action_mode == 'r':
            subprocess.run(['shutdown', '/r', '/t', '0'], capture_output=True, shell=False)
        elif action_mode == 'h':
            # Hibernate / sleep
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
        except:
            pass

def countdown_action(seconds, shutdown_event, action_mode='s'):
    """Обратный отсчет перед выполнением действия"""
    try:
        action_names = {
            's': 'выключение',
            'r': 'перезагрузка',
            'h': 'переход в спящий режим',
            'b': 'звуковой сигнал'
        }
        action_name = action_names.get(action_mode, 'выключение')
        for i in range(seconds, 0, -1):
            if shutdown_event.is_set():
                return
            print(f"\r{action_name.capitalize()} через {format_time(i)}. [ESC - отмена]".ljust(80), end='', flush=True)
            time.sleep(1)
        if not shutdown_event.is_set():
            print()
            perform_action(action_mode)
            if action_mode == 'b':
                return
    except Exception:
        pass

def check_user_input(shutdown_event, monitoring_event=None, pause_event=None):
    """Обработка пользовательского ввода в потоках"""
    try:
        while not shutdown_event.is_set():
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\x1b':  # ESC
                    shutdown_event.set()
                    if monitoring_event:
                        monitoring_event.set()
                    subprocess.run(['shutdown', '/a'], capture_output=True, shell=False)
                    print("\n🚨 Действие отменено! Нажмите Enter для возврата в меню...")
                    return
                elif key == b'\x13' and monitoring_event and pause_event:  # Ctrl+S
                    if pause_event.is_set():
                        pause_event.clear()
                        print("\n▶️ Мониторинг продолжен (нажмите Ctrl+S для паузы)")
                    else:
                        pause_event.set()
                        print("\n⏸️ Мониторинг приостановлен (нажмите любую клавишу для продолжения)")
                elif key == b'\x04':  # Ctrl+D - выключение дисплея
                    try:
                        turn_off_display()
                        print("\n🖥️ Дисплей выключен (мониторинг продолжается)")
                    except Exception as e:
                        print(f"❌ Ошибка при выключении дисплея: {e}")
            time.sleep(0.1)
    except Exception as e:
        print(f"⚠️ Ошибка в обработчике ввода: {e}")

def monitor_disk_only(allowed_failures, threshold, interval, shutdown_delay, action_mode='s'):
    """Мониторинг только активности дисков"""
    try:
        failure_count = 0
        shutdown_event = threading.Event()
        monitoring_event = threading.Event()
        pause_event = threading.Event()
        input_thread = threading.Thread(target=check_user_input, args=(shutdown_event, monitoring_event, pause_event))
        input_thread.daemon = True
        input_thread.start()

        action_names = {
            's': 'выключение',
            'r': 'перезагрузка',
            'h': 'переход в спящий режим',
            'b': 'звуковой сигнал'
        }
        action_name = action_names.get(action_mode, 'выключение')

        print("\nℹ️ Управление мониторингом:")
        print("ESC - остановить мониторинг и вернуться в меню")
        print("Ctrl+S - приостановить/возобновить мониторинг")
        print("Ctrl+D - выключить дисплей (мониторинг продолжается)")

        while not monitoring_event.is_set():
            try:
                if pause_event.is_set():
                    if msvcrt.kbhit():
                        msvcrt.getch()
                        pause_event.clear()
                        print("▶️ Мониторинг продолжен (нажмите Ctrl+S для паузы)")
                    else:
                        time.sleep(0.1)
                        continue

                time.sleep(interval)

                if check_disk_activity(threshold):
                    failure_count = 0
                    print(f"💾 Обнаружена активность дисков - сброс счетчика пропусков")
                    continue
                else:
                    failure_count += 1
                    print(f"⚠️ Пропусков до {action_name}: {allowed_failures - failure_count}")

                    if failure_count >= allowed_failures:
                        print(f"🔴 Критическое падение активности дисков! Инициируется {action_name}...")
                        countdown_thread = threading.Thread(target=countdown_action, args=(shutdown_delay, shutdown_event, action_mode))
                        countdown_thread.start()
                        countdown_thread.join()

                        if shutdown_event.is_set():
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
                time.sleep(5)
                continue

        print("\n🛑 Мониторинг остановлен по запросу пользователя.")
        return True

    except Exception as e:
        print(f"\n❌ Критическая ошибка мониторинга: {e}")
        return True

def monitor_traffic(interface, traffic_type, allowed_failures, threshold, interval, shutdown_delay, action_mode='s', monitor_disk=False):
    """Основная функция мониторинга сети"""
    try:
        failure_count = 0
        net_counters = psutil.net_io_counters(pernic=True)
        if interface not in net_counters:
            print(f"\n❌ Интерфейс '{interface}' не найден.")
            return True
        old_stats = net_counters[interface]
        old_bytes = old_stats.bytes_sent if traffic_type == "u" else old_stats.bytes_recv

        shutdown_event = threading.Event()
        monitoring_event = threading.Event()
        pause_event = threading.Event()
        input_thread = threading.Thread(target=check_user_input, args=(shutdown_event, monitoring_event, pause_event))
        input_thread.daemon = True
        input_thread.start()

        action_names = {
            's': 'выключение',
            'r': 'перезагрузка',
            'h': 'переход в спящий режим',
            'b': 'звуковой сигнал'
        }
        action_name = action_names.get(action_mode, 'выключение')

        print("\nℹ️ Управление мониторингом:")
        print("ESC - остановить мониторинг и вернуться в меню")
        print("Ctrl+S - приостановить/возобновить мониторинг")
        print("Ctrl+D - выключить дисплей (мониторинг продолжается)")

        while not monitoring_event.is_set():
            try:
                if pause_event.is_set():
                    if msvcrt.kbhit():
                        msvcrt.getch()
                        pause_event.clear()
                        print("▶️ Мониторинг продолжен (нажмите Ctrl+S для паузы)")
                    else:
                        time.sleep(0.1)
                        continue

                time.sleep(interval)

                if monitor_disk and check_disk_activity():
                    print("💾 Обнаружена активность дисков - сброс счетчика пропусков")
                    failure_count = 0
                    old_stats = psutil.net_io_counters(pernic=True)[interface]
                    old_bytes = old_stats.bytes_sent if traffic_type == "u" else old_stats.bytes_recv
                    continue

                new_stats = psutil.net_io_counters(pernic=True)[interface]
                new_bytes = new_stats.bytes_sent if traffic_type == "u" else new_stats.bytes_recv
                speed = (new_bytes - old_bytes) / interval

                direction = "📤 Upload" if traffic_type == "u" else "📥 Download"
                print(f"{direction}: {speed/1024**2:.2f} МБ/с [ESC - стоп | Ctrl+S - пауза | Ctrl+D - выкл. дисплей]")

                if speed < threshold:
                    failure_count += 1
                    print(f"⚠️ Пропусков до {action_name}: {allowed_failures - failure_count}")
                    if failure_count >= allowed_failures:
                        print(f"🔴 Критическое падение скорости! Инициируется {action_name}...")
                        countdown_thread = threading.Thread(target=countdown_action, args=(shutdown_delay, shutdown_event, action_mode))
                        countdown_thread.start()
                        countdown_thread.join()

                        if shutdown_event.is_set():
                            print("\n🔄 Перезапуск мониторинга...")
                            return True

                        if action_mode == 'b':
                            print("\n🔊 Звуковой сигнал выполнен. Возврат в меню...")
                            return True
                        return False
                else:
                    failure_count = 0

                old_bytes = new_bytes

            except (KeyboardInterrupt, SystemExit):
                print("\n🛑 Мониторинг остановлен пользователем.")
                return True
            except Exception as e:
                print(f"\n⚠️ Ошибка мониторинга: {e}")
                time.sleep(5)
                continue

        print("\n🛑 Мониторинг остановлен по запросу пользователя.")
        return True

    except Exception as e:
        print(f"\n❌ Критическая ошибка мониторинга: {e}")
        return True

def timed_action_interactive(allow_save=True):
    """Выполнение действия по таймеру (интерактивно). Можно сохранить как профиль."""
    try:
        action_modes = {
            's': 'выключение',
            'r': 'перезагрузка',
            'h': 'спящий режим',
            'b': 'звуковой сигнал'
        }
        print("\n=== Режим выполнения действия по времени ===")
        print("Укажите время до действия (например: 1h30m15s)")

        print("\nВыберите режим действия:")
        print("s - Выключение компьютера")
        print("r - Перезагрузка компьютера")
        print("h - Спящий режим")
        print("b - Звуковой сигнал")

        while True:
            action_mode = input("\nВведите режим действия (s/r/h/b): ").lower()
            if action_mode in action_modes:
                break
            print("❌ Неверный режим. Попробуйте снова.")

        while True:
            time_input = input(f"\nВведите время до {action_modes[action_mode]} (или Enter для отмены): ")
            if not time_input:
                print("❌ Отмена операции.")
                return
            try:
                seconds = parse_time_input(time_input)
                if seconds <= 0:
                    print("❌ Время должно быть больше 0!")
                    continue

                print(f"\n🕒 Будет выполнено {action_modes[action_mode]} через {format_time(seconds)}")
                print("Нажмите ESC для отмены")

                shutdown_event = threading.Event()
                input_thread = threading.Thread(target=check_user_input, args=(shutdown_event,))
                input_thread.daemon = True
                input_thread.start()

                countdown_action(seconds, shutdown_event, action_mode)

                if shutdown_event.is_set():
                    print("\n🚨 Действие отменено!")
                else:
                    print("\n✅ Действие выполнено (или инициировано).")
                # Предложим сохранение как профиль, если разрешено
                if allow_save:
                    save = input("\nСохранить этот таймер как профиль? (y/n): ").lower()
                    if save == 'y':
                        profile_name = input("Введите имя профиля для сохранения: ")
                        if profile_name:
                            settings = {
                                'type': 'timer',
                                'shutdown_delay': seconds,
                                'action_mode': action_mode
                            }
                            if save_profile(profile_name, settings):
                                print(f"\n✅ Таймер-профиль '{profile_name}' сохранен.")
                return
            except ValueError:
                print("❌ Неверный формат времени. Попробуйте снова.")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")

def main():
    """Главная функция программы"""
    try:
        while True:
            try:
                print(f"\n--- Меню (Версия {__version__}) ---")
                print("1. Выбрать существующий профиль (мониторинг / таймер)")
                print("2. Создать новый профиль")
                print("3. Удалить профиль")
                print("4. Редактировать профиль")
                print("5. Изменить порядок профилей")
                print("6. Таймер быстрый старт (без сохранения в профиль)")
                print("7. Мониторинг только активности дисков")
                print("8. Управление дисплеем")
                print("9. Выход")

                choice = input("\nВыберите вариант (1/2/3/4/5/6/7/8/9): ")

                if choice == "1":
                    profiles = list_profiles()
                    if not profiles:
                        continue
                    profile_names = list(profiles.keys())
                    try:
                        profile_choice = input("\nВведите номер профиля (или Enter для отмены): ")
                        if not profile_choice:
                            continue
                        profile_choice = int(profile_choice) - 1
                        selected_profile_name = profile_names[profile_choice]
                        selected_profile = profiles[selected_profile_name]
                        print(f"\n✅ Выбран профиль: {selected_profile_name}")

                        # Если профиль таймерный — запускаем таймер и возвращаемся в меню
                        if selected_profile.get('type') == 'timer':
                            delay = selected_profile.get('shutdown_delay', 30)
                            action_mode = selected_profile.get('action_mode', 's')
                            print(f"\n⏱ Таймер-профиль: действие через {format_time(delay)} ({action_mode})")
                            shutdown_event = threading.Event()
                            input_thread = threading.Thread(target=check_user_input, args=(shutdown_event,))
                            input_thread.daemon = True
                            input_thread.start()
                            countdown_action(delay, shutdown_event, action_mode)
                            print("\n🔙 Возврат в меню...")
                            continue

                        # Дисковый профиль?
                        if 'disk_threshold' in selected_profile:
                            while True:
                                should_restart = monitor_disk_only(
                                    selected_profile.get('allowed_failures', 3),
                                    selected_profile.get('disk_threshold', 1.0),
                                    selected_profile.get('interval', 5),
                                    selected_profile.get('shutdown_delay', 30),
                                    selected_profile.get('action_mode', 's')
                                )
                                if not should_restart:
                                    return
                                print("\nНажмите Enter для возврата в меню или любую другую клавишу для перезапуска мониторинга...")
                                if msvcrt.getch() == b'\r':
                                    break
                        else:
                            # Сетевой профиль
                            while True:
                                should_restart = monitor_traffic(
                                    selected_profile.get('interface'),
                                    selected_profile.get('traffic_type', 'd'),
                                    selected_profile.get('allowed_failures', 3),
                                    selected_profile.get('threshold', 0.5 * 1024**2),
                                    selected_profile.get('interval', 5),
                                    selected_profile.get('shutdown_delay', 30),
                                    selected_profile.get('action_mode', 's'),
                                    selected_profile.get('monitor_disk', False)
                                )
                                if not should_restart:
                                    return
                                print("\nНажмите Enter для возврата в меню или любую другую клавишу для перезапуска мониторинга...")
                                if msvcrt.getch() == b'\r':
                                    break

                    except (ValueError, IndexError):
                        print("\n❌ Неверный выбор. Попробуйте снова.")

                elif choice == "2":
                    try:
                        print("\n=== Создание нового профиля ===")
                        profile_name = input("Введите имя профиля: ")
                        if not profile_name:
                            print("❌ Имя профиля не может быть пустым!")
                            continue

                        print("\nВыберите тип профиля:")
                        print("1. Мониторинг сетевой активности")
                        print("2. Мониторинг активности дисков")
                        print("3. Таймер (действие по времени)")

                        monitor_type = input("\nВыберите тип (1/2/3): ")

                        if monitor_type == "1":
                            interface = get_interface()
                            if not interface:
                                continue

                            print("\nВыберите тип трафика:")
                            print("u - Upload (исходящий)")
                            print("d - Download (входящий)")

                            traffic_type = input("Введите тип трафика (u/d): ").lower()
                            if traffic_type not in ["u", "d"]:
                                print("❌ Неверный тип трафика!")
                                continue

                            threshold_input = input("Введите пороговую скорость (МБ/с) [по умолчанию 0.5]: ")
                            try:
                                threshold = float(threshold_input) if threshold_input else 0.5
                            except ValueError:
                                print("❌ Неверное значение! Используется значение по умолчанию 0.5 МБ/с")
                                threshold = 0.5

                            allowed_failures_input = input("Введите количество допустимых пропусков [по умолчанию 3]: ")
                            try:
                                allowed_failures = int(allowed_failures_input) if allowed_failures_input else 3
                            except ValueError:
                                print("❌ Неверное значение! Используется значение по умолчанию 3")
                                allowed_failures = 3

                            interval_input = input("Введите интервал проверки в секундах [по умолчанию 5]: ")
                            try:
                                interval = int(interval_input) if interval_input else 5
                            except ValueError:
                                print("❌ Неверное значение! Используется значение по умолчанию 5")
                                interval = 5

                            delay_input = input("Введите задержку до действия (например, 1h30m15s) [по умолчанию 30s]: ")
                            shutdown_delay = parse_time_input(delay_input) if delay_input else 30

                            print("\nВыберите режим действия:")
                            print("s - Выключение компьютера")
                            print("r - Перезагрузка компьютера")
                            print("h - Спящий режим")
                            print("b - Звуковой сигнал")

                            action_mode = input("Введите режим действия (s/r/h/b) [по умолчанию s]: ").lower()
                            if action_mode not in ['s', 'r', 'h', 'b']:
                                action_mode = 's'

                            print("\nВключить мониторинг активности дисков?")
                            monitor_disk_choice = input("y - Да, n - Нет [по умолчанию Нет]: ").lower()
                            monitor_disk = monitor_disk_choice == 'y'

                            settings = {
                                'type': 'network',
                                'interface': interface,
                                'traffic_type': traffic_type,
                                'threshold': threshold * 1024**2,
                                'allowed_failures': allowed_failures,
                                'interval': interval,
                                'shutdown_delay': shutdown_delay,
                                'action_mode': action_mode,
                                'monitor_disk': monitor_disk
                            }

                        elif monitor_type == "2":
                            threshold_input = input("Введите пороговую скорость дисков (МБ/с) [по умолчанию 1.0]: ")
                            try:
                                disk_threshold = float(threshold_input) if threshold_input else 1.0
                            except ValueError:
                                print("❌ Неверное значение! Используется значение по умолчанию 1.0 МБ/с")
                                disk_threshold = 1.0

                            allowed_failures_input = input("Введите количество допустимых пропусков [по умолчанию 3]: ")
                            try:
                                allowed_failures = int(allowed_failures_input) if allowed_failures_input else 3
                            except ValueError:
                                print("❌ Неверное значение! Используется значение по умолчанию 3")
                                allowed_failures = 3

                            interval_input = input("Введите интервал проверки в секундах [по умолчанию 5]: ")
                            try:
                                interval = int(interval_input) if interval_input else 5
                            except ValueError:
                                print("❌ Неверное значение! Используется значение по умолчанию 5")
                                interval = 5

                            delay_input = input("Введите задержку до действия (например, 1h30m15s) [по умолчанию 30s]: ")
                            shutdown_delay = parse_time_input(delay_input) if delay_input else 30

                            print("\nВыберите режим действия:")
                            print("s - Выключение компьютера")
                            print("r - Перезагрузка компьютера")
                            print("h - Спящий режим")
                            print("b - Звуковой сигнал")

                            action_mode = input("Введите режим действия (s/r/h/b) [по умолчанию s]: ").lower()
                            if action_mode not in ['s', 'r', 'h', 'b']:
                                action_mode = 's'

                            settings = {
                                'type': 'disk',
                                'disk_threshold': disk_threshold,
                                'allowed_failures': allowed_failures,
                                'interval': interval,
                                'shutdown_delay': shutdown_delay,
                                'action_mode': action_mode
                            }

                        elif monitor_type == "3":
                            # Создаем таймер-профиль
                            print("\n=== Создание таймер-профиля ===")
                            print("\nВыберите режим действия:")
                            print("s - Выключение компьютера")
                            print("r - Перезагрузка компьютера")
                            print("h - Спящий режим")
                            print("b - Звуковой сигнал")
                            action_mode = input("Введите режим действия (s/r/h/b) [по умолчанию s]: ").lower()
                            if action_mode not in ['s', 'r', 'h', 'b']:
                                action_mode = 's'
                            delay_input = input("Введите задержку (например, 1h30m15s) [по умолчанию 30s]: ")
                            shutdown_delay = parse_time_input(delay_input) if delay_input else 30
                            settings = {
                                'type': 'timer',
                                'shutdown_delay': shutdown_delay,
                                'action_mode': action_mode
                            }
                        else:
                            print("❌ Неверный выбор типа профиля!")
                            continue

                        if save_profile(profile_name, settings):
                            print(f"\n✅ Профиль '{profile_name}' успешно создан!")
                    except Exception as e:
                        print(f"\n❌ Ошибка при создании профиля: {e}")

                elif choice == "3":
                    delete_profile()

                elif choice == "4":
                    profiles = list_profiles()
                    if not profiles:
                        continue
                    profile_names = list(profiles.keys())
                    try:
                        profile_choice = input("\nВведите номер профиля для редактирования (или Enter для отмены): ")
                        if not profile_choice:
                            continue
                        profile_choice = int(profile_choice) - 1
                        selected_profile = profile_names[profile_choice]
                        edit_profile(selected_profile)
                    except (ValueError, IndexError):
                        print("\n❌ Неверный выбор. Попробуйте снова.")

                elif choice == "5":
                    move_profile()

                elif choice == "6":
                    # Выполнить действие по времени (интерактивно), с опцией сохранить как профиль
                    timed_action_interactive(allow_save=False)

                elif choice == "7":
                    try:
                        print("\n=== Мониторинг только активности дисков ===")
                        threshold_input = input("Введите пороговую скорость (МБ/с) [по умолчанию 1.0]: ")
                        try:
                            threshold = float(threshold_input) if threshold_input else 1.0
                        except ValueError:
                            print("❌ Неверное значение! Используется значение по умолчанию 1.0 МБ/с")
                            threshold = 1.0

                        allowed_failures_input = input("Введите количество допустимых пропусков [по умолчанию 3]: ")
                        try:
                            allowed_failures = int(allowed_failures_input) if allowed_failures_input else 3
                        except ValueError:
                            print("❌ Неверное значение! Используется значение по умолчанию 3")
                            allowed_failures = 3

                        interval_input = input("Введите интервал проверки в секундах [по умолчанию 5]: ")
                        try:
                            interval = int(interval_input) if interval_input else 5
                        except ValueError:
                            print("❌ Неверное значение! Используется значение по умолчанию 5")
                            interval = 5

                        delay_input = input("Введите задержку до действия (например, 1h30m15s) [по умолчанию 30s]: ")
                        shutdown_delay = parse_time_input(delay_input) if delay_input else 30

                        print("\nВыберите режим действия:")
                        print("s - Выключение компьютера")
                        print("r - Перезагрузка компьютера")
                        print("h - Спящий режим")
                        print("b - Звуковой сигнал")

                        action_mode = input("Введите режим действия (s/r/h/b) [по умолчанию s]: ").lower()
                        if action_mode not in ['s', 'r', 'h', 'b']:
                            action_mode = 's'

                        while True:
                            should_restart = monitor_disk_only(
                                allowed_failures,
                                threshold,
                                interval,
                                shutdown_delay,
                                action_mode
                            )

                            if not should_restart:
                                return
                            print("\nНажмите Enter для возврата в меню или любую другую клавишу для перезапуска мониторинга...")
                            if msvcrt.getch() == b'\r':
                                break

                    except Exception as e:
                        print(f"\n❌ Ошибка: {e}")

                elif choice == "8":
                    display_control_menu()

                elif choice == "9":
                    print("\n👋 До свидания!")
                    break

                else:
                    print("\n❌ Неверный выбор. Попробуйте снова.")

            except KeyboardInterrupt:
                print("\n\n🛑 Программа прервана пользователем.")
                break
            except Exception as e:
                print(f"\n❌ Неожиданная ошибка: {e}")
                continue

    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")
        input("Нажмите Enter для выхода...")

if __name__ == "__main__":
    main()
