#!/usr/bin/env python3
import os
import sys
import csv
from configparser import ConfigParser

# 1. Путь к директории с приложениями Splunk
SPLUNK_APPS_DIR = "/opt/splunk/etc/apps"

# 2. Имя создаваемого лукапа (CSV)
LOOKUP_NAME = "local_stanzas_audit.csv"
LOOKUP_DIR = os.path.join(SPLUNK_APPS_DIR, "search", "lookups")
OUTPUT_CSV = os.path.join(LOOKUP_DIR, LOOKUP_NAME)

def audit_all_local_stanzas():
    if not os.path.exists(SPLUNK_APPS_DIR):
        print(f"[Ошибка] Директория не найдена: {SPLUNK_APPS_DIR}")
        sys.exit(1)

    all_apps = os.listdir(SPLUNK_APPS_DIR)
    report_data = []

    print(f"\n{'Приложение':<20} | {'Файл':<15} | {'Станза':<25} | {'Параметры и Значения'}")
    print("-" * 100)

    for app in all_apps:
        app_path = os.path.join(SPLUNK_APPS_DIR, app)
        if not os.path.isdir(app_path):
            continue

        if app.lower().startswith("splunk"):
            continue

        local_path = os.path.join(app_path, "local")
        if not os.path.isdir(local_path):
            continue

        for file_name in os.listdir(local_path):
            if file_name.endswith(".conf"):
                full_path = os.path.join(local_path, file_name)
                
                # allow_no_value=True позволяет читать ключи без явного знака "="
                config = ConfigParser(strict=False, allow_no_value=True)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        config.read_file(f)
                    
                    for stanza in config.sections():
                        # Собираем все настройки внутри текущей станзы
                        settings_list = []
                        for key in config.options(stanza):
                            value = config.get(stanza, key)
                            if value is not None:
                                settings_list.append(f"{key}={value}")
                            else:
                                settings_list.append(f"{key}")
                        
                        # Объединяем параметры через перенос строки или точку с запятой
                        settings_str = " | ".join(settings_list) if settings_list else "пустая станза"
                        
                        # Вывод в консоль (обрезаем длинный вывод для красоты)
                        display_settings = settings_str if len(settings_str) < 40 else settings_str[:37] + "..."
                        print(f"{app:<20} | {file_name:<15} | [{stanza}]<25 | {display_settings}")
                        
                        # Сохраняем в массив для CSV
                        report_data.append([app, file_name, stanza, settings_str])
                            
                except Exception as e:
                    print(f"[Ошибка чтения] {app} -> {file_name}: {e}")

    print("-" * 100)
    
    if not report_data:
        print("Локальных станз в сторонних приложениях не обнаружено.")
        return

    print(f"Всего найдено строк конфигураций: {len(report_data)}")
    
    # Запись в лукап
    try:
        if not os.path.exists(LOOKUP_DIR):
            os.makedirs(LOOKUP_DIR, exist_ok=True)
            
        with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            # Добавили колонку settings
            writer.writerow(["app", "config_file", "stanza", "settings"])
            writer.writerows(report_data)
            
        print(f"\n[Успех] Лукап обновлен (параметры добавлены): {OUTPUT_CSV}")
        print(f"Поиск в Splunk: | inputlookup {LOOKUP_NAME}")
    except Exception as e:
        print(f"[Ошибка автоматической записи лукапа]: {e}")

if __name__ == "__main__":
    audit_all_local_stanzas()