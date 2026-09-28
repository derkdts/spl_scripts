#!/usr/bin/env python3
import os
import sys
import shutil
import tarfile
import configparser

class SplunkConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr):
        return optionstr

BLACKLIST_APPS = {
    'framework', 'gettingstarted', 'launcher', 'learned', 'search', 
    'splunk_monitoring_console', 'splunk_httpinput', 'splunk_instrumentation',
    'SplunkForwarder', 'SplunkLightForwarder', '_cluster'
}

def get_apps_list(apps_root_path):
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

def parse_user_selection(selection_str, max_val):
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

def pack_app_to_tar(apps_root_path, app_name, export_dir):
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
    app_path = os.path.join(apps_root_path, app_name)
    local_dir = os.path.join(app_path, 'local')
    default_dir = os.path.join(app_path, 'default')

    print(f"\n[+] Обработка приложения: {app_name}")

    if not os.path.exists(default_dir):
        os.makedirs(default_dir)

    for filename in os.listdir(local_dir):
        local_file = os.path.join(local_dir, filename)
        
        if os.path.isdir(local_file) or not filename.endswith('.conf'):
            continue

        default_file = os.path.join(default_dir, filename)

        if os.path.exists(local_file):
            with open(local_file, 'r', encoding='utf-8-sig') as test_f:
                content = test_f.read().strip()
            if not content or content == "# Изменения перенесены в default скриптом":
                continue

        print(f"  -> Обработка конфига: {filename}")

        local_cfg = SplunkConfigParser(allow_no_value=True, strict=False, interpolation=None)
        try:
            local_cfg.read(local_file, encoding='utf-8-sig')
        except configparser.Error as e:
            print(f"     [Ошибка] Не удалось прочитать файл {local_file}: {e}")
            continue

        if not local_cfg.sections():
            continue

        default_cfg = SplunkConfigParser(allow_no_value=True, strict=False, interpolation=None)
        if os.path.exists(default_file):
            try:
                default_cfg.read(default_file, encoding='utf-8-sig')
            except configparser.Error:
                pass

        for section in local_cfg.sections():
            if not default_cfg.has_section(section):
                default_cfg.add_section(section)
            for option in local_cfg.options(section):
                value = local_cfg.get(section, option)
                default_cfg.set(section, option, value)

        with open(default_file, 'w', encoding='utf-8', newline='\n') as f:
            default_cfg.write(f, space_around_delimiters=True)
        print(f"     [OK] Изменения внесены в default\\{filename}")

        with open(local_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write("# Изменения перенесены в default скриптом\n")
        print(f"     [OK] Файл local\\{filename} очищен.")

    local_data_dir = os.path.join(local_dir, 'data')
    if os.path.exists(local_data_dir) and os.path.isdir(local_data_dir):
        print(f"  -> Обнаружена папка UI/данных: local\\data")
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
            print(f"     [OK] Временная папка local\\data успешно удалена.")
        except Exception as e:
            print(f"     [Предупреждение] Не удалось удалить папку local\\data: {e}")

    if should_pack:
        pack_app_to_tar(apps_root_path, app_name, export_dir)

if __name__ == "__main__":
    default_windows_path = "/opt/splunk/etc/apps"
    target_path = sys.argv if len(sys.argv) > 1 else default_windows_path
    
    export_packages_dir = "/opt/splunk/share/app_package"
    os.makedirs(export_packages_dir, exist_ok=True)
    
    available_apps = get_apps_list(target_path)
    if not available_apps:
        print("[-] Нет доступных для обработки приложений с папкой 'local'.")
        sys.exit(0)
        
    print("\n=== Доступные Splunk Apps для переноса ===")
    for idx, app in enumerate(available_apps, 1):
        print(f"[{idx}] {app}")
    print("==========================================")
    
    user_input = input(
        "Выберите приложения для синхронизации.\n"
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
        process_app(target_path, app_to_process, export_packages_dir, pack_choice)
        
    print("\n[*] Синхронизация успешно завершена.")
    if pack_choice:
        print(f"[*] Готовые архивы лежат в папке: {export_packages_dir}")
