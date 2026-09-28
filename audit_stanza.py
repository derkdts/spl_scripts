#!/usr/bin/env python3
cat << 'EOF' > /tmp/audit_all_apps_local.py
import os
import sys
import csv
import xml.etree.ElementTree as ET
from configparser import ConfigParser

SPLUNK_APPS_DIR = "/opt/splunk/etc/apps"

LOOKUP_NAME = "local_stanzas_audit.csv"
LOOKUP_DIR = os.path.join(SPLUNK_APPS_DIR, "search", "lookups")
OUTPUT_CSV = os.path.join(LOOKUP_DIR, LOOKUP_NAME)

def parse_conf_file(full_path):
    """Парсинг стандартных .conf файлов"""
    results = []
    config = ConfigParser(strict=False, allow_no_value=True)
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            config.read_file(f)
        for stanza in config.sections():
            settings_list = []
            for key in config.options(stanza):
                value = config.get(stanza, key)
                if value is not None:
                    settings_list.append(f"{key}={value}")
                else:
                    settings_list.append(f"{key}")
            settings_str = " | ".join(settings_list) if settings_list else "пустая станза"
            results.append((stanza, settings_str))
    except Exception as e:
        print(f"[Ошибка .conf] {full_path}: {e}")
    return results

def parse_xml_file(full_path, file_type):
    """Парсинг XML файлов (дашборды и навигация)"""
    results = []
    try:
        tree = ET.parse(full_path)
        root = tree.getroot()
        
        if file_type == "nav":
            stanza_name = os.path.basename(full_path)
            # Собираем пункты меню (view, collection, saved)
            items = [elem.attrib.get('name', elem.tag) for elem in root.iter() if elem.attrib.get('name')]
            settings_str = "nav_items=" + (", ".join(items) if items else "empty_nav")
            results.append((stanza_name, settings_str))
            
        elif file_type == "view":
            stanza_name = os.path.basename(full_path)
            label = root.find('label')
            label_text = label.text if label is not None else "No Label"
            
            panels_count = len(root.findall('.//panel'))
            row_count = len(root.findall('.//row'))
            
            settings_str = f"label='{label_text}' | rows={row_count} | panels={panels_count} | type={root.tag}"
            results.append((stanza_name, settings_str))
    except Exception as e:
        results.append((os.path.basename(full_path), f"ошибка парсинга XML: {str(e)[:50]}"))
    return results

def audit_all_local_stanzas():
    if not os.path.exists(SPLUNK_APPS_DIR):
        print(f"[Ошибка] Директория не найдена: {SPLUNK_APPS_DIR}")
        sys.exit(1)

    all_apps = os.listdir(SPLUNK_APPS_DIR)
    report_data = []

    print(f"\n{'Приложение':<20} | {'Тип / Файл':<25} | {'Станза / Объект':<25} | {'Значения параметров'}")
    print("-" * 110)

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
            full_path = os.path.join(local_path, file_name)
            if os.path.isfile(full_path) and file_name.endswith(".conf"):
                conf_data = parse_conf_file(full_path)
                for stanza, settings in conf_data:
                    print(f"{app:<20} | {file_name:<25} | [{stanza}] | {settings[:35]}...")
                    report_data.append([app, file_name, stanza, settings])

        nav_path = os.path.join(local_path, "data", "ui", "nav")
        if os.path.isdir(nav_path):
            for file_name in os.listdir(nav_path):
                if file_name.endswith(".xml"):
                    full_path = os.path.join(nav_path, file_name)
                    xml_data = parse_xml_file(full_path, "nav")
                    for stanza, settings in xml_data:
                        display_file = f"data/ui/nav/{file_name}"
                        print(f"{app:<20} | {display_file:<25} | {stanza:<25} | {settings[:35]}...")
                        report_data.append([app, display_file, stanza, settings])

        views_path = os.path.join(local_path, "data", "ui", "views")
        if os.path.isdir(views_path):
            for file_name in os.listdir(views_path):
                if file_name.endswith(".xml"):
                    full_path = os.path.join(views_path, file_name)
                    xml_data = parse_xml_file(full_path, "view")
                    for stanza, settings in xml_data:
                        display_file = f"data/ui/views/{file_name}"
                        print(f"{app:<20} | {display_file:<25} | {stanza:<25} | {settings[:35]}...")
                        report_data.append([app, display_file, stanza, settings])

    print("-" * 110)
    if not report_data:
        print("Локальных объектов конфигурации не обнаружено.")
        return

    print(f"Всего найдено объектов: {len(report_data)}")
    
    try:
        if not os.path.exists(LOOKUP_DIR):
            os.makedirs(LOOKUP_DIR, exist_ok=True)
        with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["app", "config_file", "stanza", "settings"])
            writer.writerows(report_data)
        print(f"\n[Успех] Лукап обновлен (Включая UI/Nav/Views): {OUTPUT_CSV}")
    except Exception as e:
        print(f"[Ошибка автоматической записи лукапа]: {e}")

if __name__ == "__main__":
    audit_all_local_stanzas()
