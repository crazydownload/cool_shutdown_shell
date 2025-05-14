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
import win32process
import win32gui
import win32con

CONFIG_FILE = "profiles.json"

# Списки процессов для мониторинга
GAME_LAUNCHERS = [
    'steam.exe', 'epicgameslauncher.exe', 'origin.exe', 
    'battle.net.exe', 'goggalaxy.exe', 'ubisoftconnect.exe',
    'eaapp.exe', 'riotclient.exe', 'bethesda.net.exe'
]

SYSTEM_PROCESSES = [
    'system', 'svchost.exe', 'explorer.exe', 'searchindexer.exe',
    'dllhost.exe', 'taskhostw.exe', 'wininit.exe', 'csrss.exe',
    'winlogon.exe', 'services.exe', 'lsass.exe', 'smss.exe'
]

def turn_off_display():
    """Выключает дисплей"""
    try:
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        print("\n🖥️ Дисплей выключен")
    except Exception as e:
        print(f"❌ Ошибка при выключении дисплея: {e}")

def parse_time_input(time_str):
    """Разбирает строку времени в формате 1h30m15s"""
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
    """Форматирует секунды в читаемый вид"""
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
    """Проверяет, является ли процесс игровым лаунчером"""
    try:
        process = psutil.Process(pid)
        name = process.name().lower()
        return any(launcher in name for launcher in GAME_LAUNCHERS)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

def is_system_process(pid):
    """Проверяет, является ли процесс системным"""
    try:
        process = psutil.Process(pid)
        name = process.name().lower()
        return name in SYSTEM_PROCESSES
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

def check_disk_activity(threshold=1.0):
    """
    Проверяет активность дисков
    threshold - порог в МБ/с (по умолчанию 1 МБ/с)
    Возвращает True если есть значимая активность
    """
    try:
        # Получаем начальные значения
        disk_start = psutil.disk_io_counters()
        processes_start = {}
        
        for proc in psutil.process_iter(['pid', 'name', 'io_counters']):
            try:
                io = proc.info['io_counters']
                if io is not None:
                    processes_start[proc.info['pid']] = {
                        'read_bytes': io.read_bytes,
                        'write_bytes': io.write_bytes
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Ждем 1 секунду для измерения скорости
        time.sleep(1)
        
        # Получаем конечные значения
        disk_end = psutil.disk_io_counters()
        total_bytes = (disk_end.read_bytes + disk_end.write_bytes - 
                      disk_start.read_bytes - disk_start.write_bytes)
        speed_mb = total_bytes / (1024 * 1024)  # МБ/с
        
        # Если активность ниже порога, можно пропустить
        if speed_mb < threshold:
            return False
        
        # Проверяем, какие процессы вызывали активность
        active_processes = set()
        for proc in psutil.process_iter(['pid', 'name', 'io_counters']):
            try:
                if proc.info['pid'] in processes_start:
                    start_io = processes_start[proc.info['pid']]
                    end_io = proc.info['io_counters']
                    
                    if end_io is None:
                        continue
                        
                    read_diff = end_io.read_bytes - start_io['read_bytes']
                    write_diff = end_io.write_bytes - start_io['write_bytes']
                    
                    if read_diff > 0 or write_diff > 0:
                        if not is_system_process(proc.info['pid']):
                            active_processes.add(proc.info['name'])
            
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if active_processes:
            print(f"\n💾 Активность дисков: {speed_mb:.2f} МБ/с (процессы: {', '.join(active_processes)})")
            return True
        
        return False
    
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
        print(f"\n✅ Профиль '{profile_name}' сохранен в 'profiles.json'.")
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
        profiles = load_profiles()
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
        
        print(f"Текущий интерфейс: {settings['interface']}")
        print("1. Выбрать новый интерфейс")
        print("2. Оставить текущий")
        interface_choice = input("Выберите вариант (1/2): ")
        if interface_choice == "1":
            new_interface = get_interface()
            if new_interface:
                new_settings['interface'] = new_interface
        
        current_type = 'Upload (u)' if settings['traffic_type'] == 'u' else 'Download (d)'
        print(f"\nТекущий тип трафика: {current_type}")
        new_type = input("Введите новый тип трафика (u/d) или Enter чтобы оставить текущий: ").lower()
        if new_type in ['u', 'd']:
            new_settings['traffic_type'] = new_type
        
        print(f"\nТекущее количество допустимых пропусков: {settings['allowed_failures']}")
        new_failures = input("Введите новое количество или Enter чтобы оставить текущее: ")
        if new_failures:
            try:
                new_settings['allowed_failures'] = int(new_failures)
            except ValueError:
                print("❌ Неверный формат числа. Оставлено текущее значение.")
        
        current_threshold = settings['threshold'] / 1024**2
        print(f"\nТекущая пороговая скорость: {current_threshold:.2f} МБ/с")
        new_threshold = input("Введите новую пороговую скорость (МБ/с) или Enter чтобы оставить текущую: ")
        if new_threshold:
            try:
                new_settings['threshold'] = float(new_threshold) * 1024**2
            except ValueError:
                print("❌ Неверный формат числа. Оставлено текущее значение.")
        
        print(f"\nТекущий интервал проверки: {settings['interval']} сек")
        new_interval = input("Введите новый интервал (сек) или Enter чтобы оставить текущий: ")
        if new_interval:
            try:
                new_settings['interval'] = int(new_interval)
            except ValueError:
                print("❌ Неверный формат числа. Оставлено текущее значение.")
        
        current_delay = settings['shutdown_delay']
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
        
        # Новая опция: мониторинг активности дисков
        current_disk_monitoring = settings.get('monitor_disk', False)
        print(f"\nТекущая настройка мониторинга дисков: {'Включен' if current_disk_monitoring else 'Отключен'}")
        disk_monitoring = input("Включить мониторинг активности дисков? (y/n) или Enter чтобы оставить текущее: ").lower()
        if disk_monitoring == 'y':
            new_settings['monitor_disk'] = True
        elif disk_monitoring == 'n':
            new_settings['monitor_disk'] = False
        
        print("\nИзмененные настройки:")
        print(f"Интерфейс: {settings['interface']} → {new_settings['interface']}")
        print(f"Тип трафика: {settings['traffic_type']} → {new_settings['traffic_type']}")
        print(f"Допустимые пропуски: {settings['allowed_failures']} → {new_settings['allowed_failures']}")
        print(f"Пороговая скорость: {settings['threshold']/1024**2:.2f} → {new_settings['threshold']/1024**2:.2f} МБ/с")
        print(f"Интервал проверки: {settings['interval']} → {new_settings['interval']} сек")
        print(f"Задержка до выключения: {format_time(settings['shutdown_delay'])} → {format_time(new_settings['shutdown_delay'])}")
        print(f"Режим действия: {action_modes.get(settings.get('action_mode', 's'))} → {action_modes.get(new_settings.get('action_mode', 's'))}")
        print(f"Мониторинг дисков: {'Включен' if settings.get('monitor_disk', False) else 'Отключен'} → {'Включен' if new_settings.get('monitor_disk', False) else 'Отключен'}")
        
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
        if action_mode == 's':  # Выключение
            os.system('shutdown /f /s /t 0')
        elif action_mode == 'r':  # Перезагрузка
            os.system('shutdown /f /r /t 0')
        elif action_mode == 'h':  # Спящий режим
            ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
        elif action_mode == 'b':  # Звуковой сигнал
            for _ in range(3):  # 3 повторения сигнала
                winsound.Beep(1000, 500)  # Частота 1000 Гц, длительность 500 мс
                time.sleep(0.3)
    except Exception as e:
        print(f"❌ Ошибка при выполнении действия: {e}")

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
            perform_action(action_mode)
            if action_mode == 'b':
                return
    except Exception:
        pass

def check_user_input(shutdown_event, monitoring_event=None, pause_event=None):
    """Обработка пользовательского ввода"""
    try:
        while not shutdown_event.is_set():
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\x1b':  # ESC
                    shutdown_event.set()
                    if monitoring_event:
                        monitoring_event.set()
                    os.system('shutdown /a')
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
                    turn_off_display()
    except Exception:
        pass

def monitor_traffic(interface, traffic_type, allowed_failures, threshold, interval, shutdown_delay, action_mode='s', monitor_disk=False):
    """Основная функция мониторинга"""
    try:
        failure_count = 0
        old_stats = psutil.net_io_counters(pernic=True)[interface]
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
        print("Ctrl+D - выключить дисплей")

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
                
                # Проверяем активность дисков, если включена опция
                if monitor_disk and check_disk_activity():
                    print("💾 Обнаружена активность дисков - сброс счетчика пропусков")
                    failure_count = 0
                    old_stats = psutil.net_io_counters(pernic=True)[interface]
                    old_bytes = old_stats.bytes_sent if traffic_type == "u" else old_stats.bytes_recv
                    continue
                
                # Проверяем сетевую активность
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

def timed_action():
    """Выполнение действия по таймеру"""
    try:
        action_modes = {
            's': 'выключение',
            'r': 'перезагрузка',
            'h': 'переход в спящий режим',
            'b': 'звуковой сигнал'
        }
        
        print("\n=== Режим выполнения действия по времени ===")
        print("Укажите время до действия (например: 1h30m15s)")
        print("Доступные форматы: 1h30m15s, 1h 30m 15s, 1h-30m-15s")
        
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
                    return
                
                break
                
            except ValueError:
                print("❌ Неверный формат времени. Попробуйте снова.")
                
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")

def main():
    """Главная функция программы"""
    try:
        while True:
            try:
                print("\n--- Меню ---")
                print("1. Выбрать существующий профиль (мониторинг сети)")
                print("2. Создать новый профиль (мониторинг сети)")
                print("3. Удалить профиль")
                print("4. Редактировать профиль")
                print("5. Изменить порядок профилей")
                print("6. Выполнить действие по времени (без мониторинга)")
                print("7. Выход")
                
                choice = input("\nВыберите вариант (1/2/3/4/5/6/7): ")
                
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
                        selected_profile = profiles[profile_names[profile_choice]]
                        print(f"\n✅ Выбран профиль: {profile_names[profile_choice]}")

                        while True:
                            should_restart = monitor_traffic(
                                selected_profile['interface'],
                                selected_profile['traffic_type'],
                                selected_profile['allowed_failures'],
                                selected_profile['threshold'],
                                selected_profile['interval'],
                                selected_profile['shutdown_delay'],
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
                    interface = get_interface()
                    if not interface:
                        continue

                    while True:
                        traffic_type = input("Мониторить Upload/Download? (u/d): ").lower()
                        if traffic_type in ["u", "d"]:
                            break
                        print("Ошибка! Введите 'u' или 'd'")

                    allowed_failures = 3
                    threshold = 0.1
                    interval = 10
                    shutdown_delay = 30
                    action_mode = 's'
                    monitor_disk = False
                    
                    try:
                        allowed_failures = int(input(f"Допустимые пропуски [по умолчанию: {allowed_failures}]: ") or allowed_failures)
                        threshold = float(input(f"Пороговая скорость (МБ/с) [по умолчанию: {threshold}]: ") or threshold) * 1024**2
                        interval = int(input(f"Интервал проверки (сек) [по умолчанию: {interval}]: ") or interval)
                        
                        default_delay_str = format_time(shutdown_delay)
                        delay_input = input(f"Задержка до действия (Например: 1h30m15s) [по умолчанию: {default_delay_str}]: ")
                        if delay_input:
                            parsed_seconds = parse_time_input(delay_input)
                            if parsed_seconds > 0:
                                shutdown_delay = parsed_seconds
                            else:
                                print("❌ Некорректный формат времени. Используется значение по умолчанию.")
                        
                        print("\nВыберите режим действия при срабатывании:")
                        print("s - Выключение компьютера")
                        print("r - Перезагрузка компьютера")
                        print("h - Спящий режим")
                        print("b - Звуковой сигнал")
                        action_mode = input("Введите режим действия (s/r/h/b) [по умолчанию: s]: ").lower()
                        if action_mode not in ['s', 'r', 'h', 'b']:
                            action_mode = 's'
                            print("Используется режим по умолчанию: выключение")
                            
                        # Новая опция: мониторинг дисков
                        monitor_disk = input("\nВключить мониторинг активности дисков? (y/n) [по умолчанию: n]: ").lower() == 'y'
                    except ValueError:
                        print("❌ Неверный формат числа. Используются значения по умолчанию.")

                    save_choice = input("\nСохранить эти настройки как новый профиль? (y/n): ").lower()
                    if save_choice == "y":
                        profile_name = input("Введите имя профиля: ")
                        if profile_name:
                            settings = {
                                "interface": interface,
                                "traffic_type": traffic_type,
                                "allowed_failures": allowed_failures,
                                "threshold": threshold,
                                "interval": interval,
                                "shutdown_delay": shutdown_delay,
                                "action_mode": action_mode,
                                "monitor_disk": monitor_disk
                            }
                            save_profile(profile_name, settings)

                    while True:
                        should_restart = monitor_traffic(interface, traffic_type, allowed_failures, threshold, interval, shutdown_delay, action_mode, monitor_disk)
                        if not should_restart:
                            return
                        print("\nНажмите Enter для возврата в меню или любую другую клавишу для перезапуска мониторинга...")
                        if msvcrt.getch() == b'\r':
                            break

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
                        profile_to_edit = profile_names[profile_choice]
                        edit_profile(profile_to_edit)
                    except (ValueError, IndexError):
                        print("\n❌ Неверный выбор. Попробуйте снова.")

                elif choice == "5":
                    move_profile()

                elif choice == "6":
                    timed_action()

                elif choice == "7":
                    print("\nВыход из программы.")
                    break

                else:
                    print("\n❌ Неверный выбор. Попробуйте снова.")

            except KeyboardInterrupt:
                print("\n🛑 Операция прервана пользователем. Возврат в меню...")
                continue
                
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
    finally:
        print("\nПрограмма завершена.")

if __name__ == "__main__":
    main()