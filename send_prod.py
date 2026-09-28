#!/usr/bin/env python3
import os
import sys
import subprocess
import configparser

# =====================================================================
# НАСТРОЙКИ ПРОДУКТОВОГО СЕРВЕРА (КУДА ОТПРАВЛЯЕМ)
# =====================================================================
PROD_HOST = "localhost"  # IP или DNS прода
PROD_PORT = "8089"                      # Management порт Splunk (обычно 8089)
PROD_USER = "admin"                     # Админский пользователь на проде
PROD_PASSWORD = "adminadmin"     # Пароль на проде

# Путь к приложениям на текущем (тестовом) инстансе
APPS_ROOT = "/opt/splunk/etc/apps"

# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ КЛАССЫ И ФУНКЦИИ ПАРСИНГА
# =====================================================================
class SplunkConfigParser(configparser.ConfigParser):
    """Кастомный парсер для сохранения исходного регистра ключей в .conf"""
    def optionxform(self, optionstr):
        return optionstr

def parse_user_selection(selection_str, max_val):
    """Парсит ввод пользователя (например: 1 или 1,2 или 2-4)"""
    selected_indices = set()
    selection_str = selection_str.strip().lower()
    
    if selection_str == 'all':
        return list(range(1, max_val + 1))
        
    for part in selection_str.split(','):
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                if 1 <= start <= end <= max_val:
                    selected_indices.update(range(start, end + 1))
            except ValueError: 
                continue
        else:
            try:
                val = int(part)
                if 1 <= val <= max_val: 
                    selected_indices.add(val)
            except ValueError: 
                continue
                
    return sorted(list(selected_indices))
def curl_deploy_stanza(app_name, conf_name, stanza_name, keys_dict):
    """Отправка станзы на прод через системный curl в один этап (фикс игнорирования параметров)"""
    # Целевой URL конфигурационного файла
    url = f"https://{PROD_HOST}:{PROD_PORT}/servicesNS/nobody/{app_name}/configs/conf-{conf_name}?output_mode=json"
    
    # Собираем базовую команду. Передаем имя станзы через --data-urlencode
    update_cmd = [
        "curl", "-k", "-s", "-u", f"{PROD_USER}:{PROD_PASSWORD}",
        "-X", "POST", url,
        "--data-urlencode", f"name={stanza_name}"
    ]
    
    # Добавляем все параметры внутри этой станзы в эту же команду
    for key, val in keys_dict.items():
        update_cmd.extend(["--data-urlencode", f"{key}={val}"])
        
    try:
        print(f"\n     [Прод] Отправка станзы [{stanza_name}] и её параметров...")
        result = subprocess.run(update_cmd, capture_output=True, text=True, timeout=10)
        
        # Проверяем ответ от Splunk на критические ошибки прав доступа
        if "Inaccessible" in result.stdout or "Unauthorized" in result.stdout:
            print(f"     [Прод] [Ошибка API]: {result.stdout.strip()}")
        else:
            print(f"     [Прод] [OK] Станза успешно записана в {app_name}/local/{conf_name}.conf")
        
        # --- Перезагрузка конфигурации на проде ---
        reload_url = f"https://{PROD_HOST}:{PROD_PORT}/servicesNS/nobody/{app_name}/configs/conf-{conf_name}/_reload"
        reload_cmd = [
            "curl", "-k", "-s", "-u", f"{PROD_USER}:{PROD_PASSWORD}",
            reload_url
        ]
        subprocess.run(reload_cmd, capture_output=True, timeout=5)
        print(f"     [Прод] [OK] Вызван _reload для конфигурации.")

    except Exception as e:
        print(f"     [Прод] [Ошибка вызова curl]: {e}")

# =====================================================================
# ОСНОВНОЙ СЦЕНАРИЙ (ИНТЕРФЕЙС ВЫБОРА)
# =====================================================================
if __name__ == "__main__":
    # Шаг 1: Выбор Splunk App на тестовом сервере
    if not os.path.exists(APPS_ROOT):
        print(f"[-] Директория с приложениями не найдена: {APPS_ROOT}")
        sys.exit(1)
        
    apps = sorted([d for d in os.listdir(APPS_ROOT) if os.path.isdir(os.path.join(APPS_ROOT, d))])
    
    print("\n=== Шаг 1: Выберите Splunk App ===")
    for idx, app in enumerate(apps, 1):
        print(f"[{idx}] {app}")
        
    app_idx_input = input("Номер приложения: ").strip()
    app_choices = parse_user_selection(app_idx_input, len(apps))
    if not app_choices:
        print("[-] Неверный выбор. Выход.")
        sys.exit(1)
        
    chosen_app = apps[app_choices[0] - 1]
    
    # Шаг 2: Выбор папки (local или default)
    print("\n=== Шаг 2: Из какой папки прочитать конфиг? ===")
    print("[1] local")
    print("[2] default")
    folder_choice = input("Ваш выбор [1/2]: ").strip()
    sub_dir = "default" if folder_choice == "2" else "local"
    target_dir = os.path.join(APPS_ROOT, chosen_app, sub_dir)
    
    if not os.path.exists(target_dir):
        print(f"[-] Папка {sub_dir} в приложении {chosen_app} отсутствует.")
        sys.exit(1)

    # Шаг 3: Выбор файла .conf
    conf_files = sorted([f for f in os.listdir(target_dir) if f.endswith('.conf')])
    if not conf_files:
        print(f"[-] В папке {sub_dir} не найдено .conf файлов.")
        sys.exit(0)
        
    print(f"\n=== Шаг 3: Выберите файл конфигурации в {sub_dir} ===")
    for idx, f_name in enumerate(conf_files, 1):
        print(f"[{idx}] {f_name}")
        
    file_idx_input = input("Номер файла: ").strip()
    file_choices = parse_user_selection(file_idx_input, len(conf_files))
    if not file_choices:
        print("[-] Неверный выбор. Выход.")
        sys.exit(1)
        
    chosen_file = conf_files[file_choices[0] - 1]
    conf_base_name = chosen_file[:-5]  # Убираем '.conf' для API
    full_file_path = os.path.join(target_dir, chosen_file)

    # Шаг 4: Выбор станзы из файла
    cfg = SplunkConfigParser(allow_no_value=True, strict=False, interpolation=None)
    try:
        cfg.read(full_file_path, encoding='utf-8-sig')
    except Exception as e:
        print(f"[-] Ошибка чтения файла {chosen_file}: {e}")
        sys.exit(1)
        
    sections = cfg.sections()
    if not sections:
        print(f"[-] В файле {chosen_file} не обнаружено доступных станз.")
        sys.exit(0)
        
    print(f"\n=== Шаг 4: Выберите станзы для отправки на ПРОД ===")
    for idx, sec in enumerate(sections, 1):
        print(f"[{idx}] [{sec}]")
        
    stanza_idx_input = input("Выберите станзы (например: '1', '1,3', 'all'): ").strip()
    chosen_stanza_indices = parse_user_selection(stanza_idx_input, len(sections))
    
    if not chosen_stanza_indices:
        print("[-] Станзы не выбраны. Выход.")
        sys.exit(0)

    # Шаг 5: Отправка на прод
    print(f"\n[*] Начинается отправка выбранных станз ({len(chosen_stanza_indices)} шт.) на продуктовый сервер...")
    for idx in chosen_stanza_indices:
        section_name = sections[idx - 1]
        
        # Собираем параметры внутри этой станзы
        stanza_data = {}
        for option in cfg.options(section_name):
            stanza_data[option] = cfg.get(section_name, option)
            
        # Запускаем отправку через curl
        curl_deploy_stanza(chosen_app, conf_base_name, section_name, stanza_data)

    print("\n[*] Процесс отправки завершен.")