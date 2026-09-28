#!/usr/bin/env python3
import os
import sys
import shutil
import tarfile
import configparser
import requests
import urllib3

# Отключаем предупреждения о самоподписанных SSL-сертификатах Splunk
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- НАСТРОЙКИ ПРОДУКТОВОГО ИНСТАНСА ---
PROD_HOST = "localhost"  # IP или DNS прода
PROD_PORT = "8089"                      # Management порт Splunk
PROD_USER = "admin"                     # Админский пользователь на проде
PROD_PASSWORD = "adminadmin"     # Пароль на проде

# Пути по умолчанию на текущем (тестовом) сервере
DEFAULT_SPLUNK_PATH = "/opt/splunk/etc/apps"
EXPORT_PACKAGES_DIR = "/opt/splunk/share/app_package"

# Список стандартных приложений Splunk, которые скрипт гарантированно игнорирует
BLACKLIST_APPS = {
    'framework', 'gettingstarted', 'launcher', 'learned', 'search', 
    'splunk_monitoring_console', 'splunk_httpinput', 'splunk_instrumentation',
    'SplunkForwarder', 'SplunkLightForwarder', '_cluster'
}

class SplunkConfigParser(configparser.ConfigParser):
    """Кастомный парсер для сохранения исходного регистра ключей в .conf"""
    def optionxform(self, optionstr):
        return optionstr

def parse_user_selection(selection_str, max_val):
    """Парсит пользовательский ввод вида '1', '1,3,5', '2-4' или 'all'"""
    selected_indices = set()
    selection_str = selection_str.strip().lower()
    
    if selection_str == 'all':
        return list(range(1, max_val + 1))
        
    parts = selection_str.split(',')
    for part in parts:
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
def deploy_stanza_to_prod(app_name, conf_name, stanza_name, keys_dict):
    """Отправка станзы на продуктовый сервер через Splunk Management API"""
    url = f"http://{PROD_HOST}:{PROD_PORT}/servicesNS/nobody/{app_name}/configs/conf-{conf_name}"
    
    # 1. Создаем саму станзу на проде (если её нет)
    create_payload = {'name': stanza_name}
    try:
        response = requests.post(
            url, 
            data=create_payload, 
            auth=(PROD_USER, PROD_PASSWORD), 
            verify=False, 
            params={'output_mode': 'json'},
            timeout=10
        )
        
        if response.status_code in (201, 409):
            if response.status_code == 409:
                print(f"     [Прод] Станза [{stanza_name}] уже есть. Обновляем параметры...")
            else:
                print(f"     [Прод] Станза [{stanza_name}] успешно создана.")
                
            # 2. Обновляем ключи внутри созданной станзы
            update_url = f"{url}/{requests.utils.quote(stanza_name, safe='')}"
            update_response = requests.post(
                update_url, 
                data=keys_dict, 
                auth=(PROD_USER, PROD_PASSWORD), 
                verify=False, 
                params={'output_mode': 'json'},
                timeout=10
            )
            
            if update_response.status_code == 200:
                print(f"     [Прод] [OK] Параметры для [{stanza_name}] применены.")
                # 3. Перезагружаем конкретный конфиг на проде, чтобы изменения применились сразу
                requests.get(f"{url}/_reload", auth=(PROD_USER, PROD_PASSWORD), verify=False, timeout=5)
            else:
                print(f"     [Прод] [Ошибка] Не удалось записать параметры: {update_response.text}")
        else:
            print(f"     [Прод] [Ошибка] Не удалось создать станзу: {response.text}")
    except Exception as e:
        print(f"     [Прод] [Ошибка соединения]: {e}")

def get_apps_list(apps_root_path):
    """Возвращает список приложений, у которых есть папка local"""
    if not os.path.exists(apps_root_path):
        print(f"[-] Путь к папке apps не найден: {apps_root_path}")
        return []
    
    apps = []
    for app_name in os.listdir(apps_root_path):
        app_path = os.path.join(apps_root_path, app_name)
        if os.path.isdir(app_path) and app_name not in BLACKLIST_APPS:
            if os.path.exists(os.path.join(app_path, 'local')):
                apps.append(app_name)
    return sorted(apps)

def pack_app_to_tar(apps_root_path, app_name, export_dir):
    """Запаковывает всё приложение в архив tar.gz"""
    app_path = os.path.join(apps_root_path, app_name)
    archive_name = os.path.join(export_dir, f"{app_name}.tar.gz")
    print(f"  -> Упаковка приложения в архив: {app_name}.tar.gz")
    try:
        with tarfile.open(archive_name, "w:gz") as tar:
            tar.add(app_path, arcname=app_name)
        print(f"     [OK] Архив успешно создан в: {archive_name}")
    except Exception as e:
        print(f"     [Ошибка] Не удалось создать архив для {app_name}: {e}")
def process_app(apps_root_path, app_name, export_dir, should_pack):
    """Основной процесс обработки выбранного приложения"""
    app_path = os.path.join(apps_root_path, app_name)
    local_dir = os.path.join(app_path, 'local')
    default_dir = os.path.join(app_path, 'default')

    print(f"\n[+] Обработка приложения: {app_name}")

    if not os.path.exists(default_dir):
        os.makedirs(default_dir)

    # --- ЧАСТЬ A: Обработка файлов .conf ---
    for filename in os.listdir(local_dir):
        local_file = os.path.join(local_dir, filename)
        
        if os.path.isdir(local_file) or not filename.endswith('.conf'):
            continue

        default_file = os.path.join(default_dir, filename)
        conf_base_name = filename[:-5]

        local_cfg = SplunkConfigParser(allow_no_value=True, strict=False, interpolation=None)
        if os.path.exists(local_file):
            try:
                local_cfg.read(local_file, encoding='utf-8-sig')
            except configparser.Error as e:
                print(f"     [Ошибка] Не удалось прочитать файл {local_file}: {e}")
                continue

        local_sections = local_cfg.sections()
        if not local_sections:
            continue

        print(f"\n  -> Обнаружен конфиг: {filename}")
        print(f"     Доступные станзы в local\\{filename}:")
        for idx, section in enumerate(local_sections, 1):
            print(f"     [{idx}] [{section}]")
            
        stanza_input = input(
            f"     Выберите станзы для мерджа в default (например: '1', '1,2', 'all'): "
        ).strip()
        
        chosen_stanza_indices = parse_user_selection(stanza_input, len(local_sections))
        if not chosen_stanza_indices:
            print(f"     [Пропущено] Станзы для файла {filename} не выбраны.")
            continue

        deploy_input = input(f"     Отправить выбранные станзы на продуктовый сервер? [y/N]: ").strip().lower()
        should_deploy = deploy_input in ('y', 'yes')

        default_cfg = SplunkConfigParser(allow_no_value=True, strict=False, interpolation=None)
        if os.path.exists(default_file):
            try:
                default_cfg.read(default_file, encoding='utf-8-sig')
            except configparser.Error:
                pass

        for idx in chosen_stanza_indices:
            section = local_sections[idx - 1]
            stanza_data = {}
            for option in local_cfg.options(section):
                stanza_data[option] = local_cfg.get(section, option)

            if not default_cfg.has_section(section):
                default_cfg.add_section(section)
            for option, value in stanza_data.items():
                default_cfg.set(section, option, value)
            
            if should_deploy:
                deploy_stanza_to_prod(app_name, conf_base_name, section, stanza_data)

            local_cfg.remove_section(section)

        with open(default_file, 'w', encoding='utf-8', newline='\n') as f:
            default_cfg.write(f, space_around_delimiters=True)
        print(f"     [OK] Выбранные станзы внесены в default\\{filename}")

        if local_cfg.sections():
            with open(local_file, 'w', encoding='utf-8', newline='\n') as f:
                local_cfg.write(f, space_around_delimiters=True)
            print(f"     [OK] Перенесенные станзы удалены из local\\{filename}. Оставшиеся сохранены.")
        else:
            with open(local_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write("# Изменения перенесены в default скриптом\n")
            print(f"     [OK] Файл local\\{filename} полностью очищен.")

    # --- ЧАСТЬ B: Перенос папки data ---
    local_data_dir = os.path.join(local_dir, 'data')
    if os.path.exists(local_data_dir) and os.path.isdir(local_data_dir):
        print(f"\n  -> Обнаружена папка UI/данных: local\\data")
        move_data_input = input("     Перенести папку data полностью? [Y/n]: ").strip().lower()
        
        if move_data_input in ('', 'y', 'yes'):
            default_data_dir = os.path.join(default_dir, 'data')
            for root, dirs, files in os.walk(local_data_dir):
                for file in files:
                    local_file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(local_file_path, local_data_dir)
                    default_file_path = os.path.join(default_data_dir, rel_path)
                    os.makedirs(os.path.dirname(default_file_path), exist_ok=True)
                    try:
                        with open(local_file_path, 'r', encoding='utf-8-sig') as src_f:
                            file_content = src_f.read()
                        with open(default_file_path, 'w', encoding='utf-8', newline='\n') as dest_f:
                            dest_f.write(file_content)
                        print(f"     [OK] Перенесен дашборд/файл: data\\{rel_path}")
                    except Exception as e:
                        print(f"     [Ошибка] Не удалось перенести {rel_path}: {e}")
            try:
                shutil.rmtree(local_data_dir)
                print(f"     [OK] Папка local\\data успешно удалена.")
            except Exception as e:
                print(f"     [Предупреждение] Не удалось удалить папку local\\data: {e}")
        else:
            print("     [Пропущено] Перенос папки data отменен.")

    if should_pack:
        pack_app_to_tar(apps_root_path, app_name, export_dir)

if __name__ == "__main__":
    target_path = sys.argv if len(sys.argv) > 1 else DEFAULT_SPLUNK_PATH
    os.makedirs(EXPORT_PACKAGES_DIR, exist_ok=True)
    
    available_apps = get_apps_list(target_path)
    if not available_apps:
        print("[-] Нет доступных для обработки приложений с папкой 'local'.")
        sys.exit(0)
        
    print("\n=== Доступные Splunk Apps для переноса ===")
    for idx, app in enumerate(available_apps, 1):
        print(f"[{idx}] {app}")
    print("==========================================")
    
    user_input = input(
        "Выберите приложения для обработки.\n"
        "Примеры ввода: '3', '1,3,5', '2-4' или 'all' для всех.\n"
        "Ваш выбор: "
    )
    
    chosen_indices = parse_user_selection(user_input, len(available_apps))
    if not chosen_indices:
        print("[-] Неверный выбор или ничего не выбрано. Выход.")
        sys.exit(0)
        
    pack_input = input("\nНужно ли упаковать выбранные приложения в .tar.gz архив? [Y/n]: ").strip().lower()
    pack_choice = pack_input in ('', 'y', 'yes')
        
    print(f"\n[*] Выбрано приложений для обработки: {len(chosen_indices)}")
    for index in chosen_indices:
        app_to_process = available_apps[index - 1]
        process_app(target_path, app_to_process, EXPORT_PACKAGES_DIR, pack_choice)
        
    print("\n[*] Синхронизация и деплой успешно завершены.")
    if pack_choice:
        print(f"[*] Готовые локальные архивы лежат в папке: {EXPORT_PACKAGES_DIR}")
