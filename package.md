### Принцип
> Упаковка через дашборд

### Настройка в commands.conf
```
[packageapps]
filename = package.py
chunked = false
enableheader = true
outputheader = false
requires_srinfo = false
supports_rawargs = true
python.version = python3
```

### Пример работы


> • Запуск для всех приложений:splunk
> `| packageapps apps=all pack=true`
> • Запуск для конкретных папок (без упаковки):splunk
> `| packageapps apps="my_app_1, my_app_2" pack=false`

> 1. каждый раз при старте берет системное время, проверяет/создает папку (например, /var/log/release_man/2026-10-02/) и создает там уникальный файл (например, 21_19_00.log).
> 2. Вся внутренняя кухня (создание директорий, перенос файлов, трассировка ошибок try-except) подробно пишется в этот файл лога.

<img width="1563" height="377" alt="image" src="https://github.com/user-attachments/assets/23681744-f611-4fab-b575-bd8d84253e0a" />
<img width="1557" height="293" alt="image" src="https://github.com/user-attachments/assets/da5c42af-a3a1-4e95-a73b-e5868c6ddbfb" />



>[!NOTE]- Скрипт
>```python
>#!/usr/bin/env python3
>import os
>import sys
>import shutil
>import tarfile
>import configparser
>import csv
>import logging
>from datetime import datetime
>
>class SplunkConfigParser(configparser.ConfigParser):
>    def optionxform(self, optionstr):
>        return optionstr
>
>BLACKLIST_APPS = {
>    'framework', 'gettingstarted', 'launcher', 'learned', 'search', 
>    'splunk_monitoring_console', 'splunk_httpinput', 'splunk_instrumentation',
>    'SplunkForwarder', 'SplunkLightForwarder', '_cluster'
>}
>
>def get_apps_list(apps_root_path):
>    if not os.path.exists(apps_root_path):
>        logging.error(f"Путь к папке apps не найден: {apps_root_path}")
>        return [], f"Путь к папке apps не найден: {apps_root_path}"
>    
>    apps = []
>    for app_name in os.listdir(apps_root_path):
>        app_path = os.path.join(apps_root_path, app_name)
>        if os.path.isdir(app_path) and app_name not in BLACKLIST_APPS:
>            if os.path.exists(os.path.join(app_path, 'local')):
>                apps.append(app_name)
>    return sorted(apps), None
>
>def pack_app_to_tar(apps_root_path, app_name, export_dir):
>    app_path = os.path.join(apps_root_path, app_name)
>    archive_name = os.path.join(export_dir, f"{app_name}.tar.gz")
>    try:
>        logging.info(f"[{app_name}] Начало упаковки в tar.gz")
>        with tarfile.open(archive_name, "w:gz") as tar:
>            tar.add(app_path, arcname=app_name)
>        msg = f"Архив создан: {archive_name}"
>        logging.info(f"[{app_name}] {msg}")
>        return msg
>    except Exception as e:
>        msg = f"Ошибка архивации: {e}"
>        logging.error(f"[{app_name}] {msg}", exc_info=True)
>        return msg
>
>def process_app(apps_root_path, app_name, export_dir, should_pack):
>    app_path = os.path.join(apps_root_path, app_name)
>    local_dir = os.path.join(app_path, 'local')
>    default_dir = os.path.join(app_path, 'default')
>    logs = []
>
>    logging.info(f"--- Старт обработки приложения: {app_name} ---")
>
>    if not os.path.exists(default_dir):
>        os.makedirs(default_dir)
>        logging.info(f"[{app_name}] Создана директория default")
>
>    for filename in os.listdir(local_dir):
>        local_file = os.path.join(local_dir, filename)
>        if os.path.isdir(local_file) or not filename.endswith('.conf'):
>            continue
>
>        default_file = os.path.join(default_dir, filename)
>
>        if os.path.exists(local_file):
>            with open(local_file, 'r', encoding='utf-8-sig') as test_f:
>                content = test_f.read().strip()
>            if not content or content == "# Изменения перенесены в default скриптом":
>                continue
>
>        local_cfg = SplunkConfigParser(allow_no_value=True, strict=False, interpolation=None)
>        try:
>            local_cfg.read(local_file, encoding='utf-8-sig')
>        except configparser.Error as e:
>            msg = f"Ошибка чтения {filename}: {e}"
>            logging.error(f"[{app_name}] {msg}")
>            logs.append(msg)
>            continue
>
>        if not local_cfg.sections():
>            continue
>
>        default_cfg = SplunkConfigParser(allow_no_value=True, strict=False, interpolation=None)
>        if os.path.exists(default_file):
>            try:
>                default_cfg.read(default_file, encoding='utf-8-sig')
>            except configparser.Error:
>                pass
>
>        for section in local_cfg.sections():
>            if not default_cfg.has_section(section):
>                default_cfg.add_section(section)
>            for option in local_cfg.options(section):
>                value = local_cfg.get(section, option)
>                default_cfg.set(section, option, value)
>
>        with open(default_file, 'w', encoding='utf-8', newline='\n') as f:
>            default_cfg.write(f, space_around_delimiters=True)
>        
>        msg = f"Перенесен конфиг: {filename}"
>        logging.info(f"[{app_name}] {msg}")
>        logs.append(msg)
>
>        with open(local_file, 'w', encoding='utf-8', newline='\n') as f:
>            f.write("# Изменения перенесены в default скриптом\n")
>        logging.info(f"[{app_name}] Очищен local/{filename}")
>
>    local_data_dir = os.path.join(local_dir, 'data')
>    if os.path.exists(local_data_dir) and os.path.isdir(local_data_dir):
>        default_data_dir = os.path.join(default_dir, 'data')
>        logging.info(f"[{app_name}] Обнаружена папка UI (local/data)")
>
>        for root, dirs, files in os.walk(local_data_dir):
>            for file in files:
>                local_file_path = os.path.join(root, file)
>                rel_path = os.path.relpath(local_file_path, local_data_dir)
>                default_file_path = os.path.join(default_data_dir, rel_path)
>                os.makedirs(os.path.dirname(default_file_path), exist_ok=True)
>                
>                try:
>                    with open(local_file_path, 'r', encoding='utf-8-sig') as src_f:
>                        file_content = src_f.read()
>                    with open(default_file_path, 'w', encoding='utf-8', newline='\n') as dest_f:
>                        dest_f.write(file_content)
>                    
>                    msg = f"Перенесен UI: data/{rel_path}"
>                    logging.info(f"[{app_name}] {msg}")
>                    logs.append(msg)
>                except Exception as e:
>                    msg = f"Ошибка UI {rel_path}: {e}"
>                    logging.error(f"[{app_name}] {msg}", exc_info=True)
>                    logs.append(msg)
>
>        try:
>            shutil.rmtree(local_data_dir)
>            logging.info(f"[{app_name}] Успешно удалена папка local/data")
>        except Exception as e:
>            logging.warning(f"[{app_name}] Папка local/data не удалена: {e}")
>
>    pack_status = "Не запрашивалось"
>    if should_pack:
>        pack_status = pack_app_to_tar(apps_root_path, app_name, export_dir)
>
>    logging.info(f"--- Завершена обработка приложения: {app_name} ---\n")
>    return logs, pack_status
>
>def parse_splunk_args():
>    args = {'apps': 'all', 'pack': 'true'}
>    for arg in sys.argv[1:]:
>        if '=' in arg:
>            k, v = arg.split('=', 1)
>            args[k.strip().lower()] = v.strip().strip('"').strip("'")
>    return args
>
>def setup_logging():
>    """Динамическое создание структуры папок и инициализация логгера"""
>    now = datetime.now()
>    date_str = now.strftime("%Y-%m-%d")    # Папка: 2026-10-02
>    time_str = now.strftime("%H_%M_%S")    # Файл: 21_15_03.log
>    
>    log_dir = os.path.join("/var/log/release_man", date_str)
>    os.makedirs(log_dir, exist_ok=True)
>    
>    log_file_path = os.path.join(log_dir, f"{time_str}.log")
>    
>    # Конфигурируем логгер (только в файл, чтобы не засорять stdout для Splunk)
>    logging.basicConfig(
>        filename=log_file_path,
>        level=logging.INFO,
>        format='%(asctime)s [%(levelname)s] %(message)s',
>        datefmt='%Y-%m-%d %H:%M:%S'
>    )
>    logging.info(f"=== Скрипт запущен. Лог пишется в {log_file_path} ===")
>
>def main():
>    setup_logging()
>
>    # Вычитываем stdin заголовки от Splunk (v1 протокол)
>    try:
>        while True:
>            line = sys.stdin.readline()
>            if not line or line.strip() == "":
>                break
>    except Exception as e:
>        logging.error(f"Ошибка чтения stdin от Splunk: {e}")
>
>    splunk_args = parse_splunk_args()
>    param_apps = splunk_args.get('apps', 'all')
>    param_pack = splunk_args.get('pack', 'true').lower() in ('true', '1', 'yes', 'y')
>
>    logging.info(f"Параметры запуска: apps={param_apps}, pack={param_pack}")
>
>    target_path = "/opt/splunk/etc/apps"
>    export_packages_dir = "/opt/splunk/etc/apps/release_man/appserver/packages"
>    os.makedirs(export_packages_dir, exist_ok=True)
>
>    fieldnames = ['app_name', 'actions_taken', 'packing_status', 'error']
>    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
>    writer.writeheader()
>
>    available_apps, err = get_apps_list(target_path)
>    if err:
>        writer.writerow({'app_name': 'N/A', 'actions_taken': 'None', 'packing_status': 'None', 'error': err})
>        return
>
>    if param_apps.lower() == 'all':
>        target_apps = available_apps
>    else:
>        target_apps = [a.strip() for a in param_apps.split(',') if a.strip() in available_apps]
>
>    if not target_apps:
>        msg = f"Приложения не найдены. Доступны: {', '.join(available_apps)}"
>        logging.warning(msg)
>        writer.writerow({'app_name': 'N/A', 'actions_taken': 'None', 'packing_status': 'None', 'error': msg})
>        return
>
>    for app in target_apps:
>        try:
>            logs, pack_status = process_app(target_path, app, export_packages_dir, param_pack)
>            writer.writerow({
>                'app_name': app,
>                'actions_taken': "; ".join(logs) if logs else "Конфиги актуальны",
>                'packing_status': pack_status,
>                'error': ''
>            })
>        except Exception as e:
>            logging.critical(f"Критический сбой при обработке {app}: {e}", exc_info=True)
>            writer.writerow({
>                'app_name': app,
>                'actions_taken': 'Ошибка в процессе',
>                'packing_status': 'Ошибка',
>                'error': str(e)
>            })
>            
>    logging.info("=== Работа скрипта успешно завершена ===")
>
>if __name__ == '__main__':
>    main()
>```
