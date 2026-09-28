#!/usr/bin/env python3
import os
import sys
import shutil
import configparser

APPS_DIR = "/opt/splunk/etc/apps"

BLACKLIST_APPS = {
    'framework', 'gettingstarted', 'launcher', 'learned', 'search', 
    'splunk_monitoring_console', 'splunk_httpinput', 'splunk_instrumentation',
    'SplunkForwarder', 'SplunkLightForwarder', '_cluster', 'splunk_assist',
    'splunk_archiver', 'splunk_secure_gateway', 'splunk_app_infrastructure',
    'splunk_internal_metrics', 'splunk_metrics_workspace', 'splunk_TA_aws',
    'introspection_generator', 'sample_app', 'alert_webhook', 'alert_logevent',
    'splunk_gdi', 'splunk_app_addon_builder', 'splunk_rapid_diag'
}

def ask_user(prompt):
    """Запрашивает подтверждение (y/n) у пользователя"""
    while True:
        try:
            answer = input(f"{prompt} [y/n]: ").strip().lower()
            if answer in ('y', 'yes'): return True
            if answer in ('n', 'no'): return False
        except (KeyboardInterrupt, EOFError):
            print("\nПрервано пользователем.")
            sys.exit(0)

def ask_choice(prompt, options):
    """Запрашивает выбор одного варианта из числовых опций"""
    print(prompt)
    for idx, opt in enumerate(options, 1):
        print(f" [{idx}] {opt}")
    while True:
        try:
            choice = input("Выберите номер действия: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                return options[int(choice) - 1]
            print("Некорректный выбор. Попробуйте еще раз.")
        except (KeyboardInterrupt, EOFError):
            print("\nПрервано.")
            sys.exit(0)

def scan_and_select_apps():
    """Сканирует директорию Splunk и предлагает интерактивный выбор приложений"""
    if not os.path.exists(APPS_DIR):
        print(f"Ошибка: Директория приложений Splunk не найдена: {APPS_DIR}", file=sys.stderr)
        sys.exit(1)

    available_apps = []
    for app_name in sorted(os.listdir(APPS_DIR)):
        if app_name in BLACKLIST_APPS: continue
        app_path = os.path.join(APPS_DIR, app_name)
        if not os.path.isdir(app_path): continue
            
        local_dir = os.path.join(app_path, "local")
        has_data = False
        if os.path.exists(local_dir):
            try:
                if [f for f in os.listdir(local_dir) if f.endswith('.conf')]:
                    has_data = True
                for sub in ["data/ui/views", "data/ui/nav"]:
                    if os.path.exists(os.path.join(local_dir, sub)) and os.listdir(os.path.join(local_dir, sub)):
                        has_data = True
            except PermissionError: continue

        if has_data:
            available_apps.append(app_name)

    if not available_apps:
        print("Не найдено доступных приложений с данными в 'local'. Используйте sudo.", file=sys.stderr)
        sys.exit(1)

    print("\n=== ВЫБОР ИСХОДНОГО ПРИЛОЖЕНИЯ (SOURCE) ===")
    for idx, app in enumerate(available_apps, 1): print(f" [{idx}] {app}")
    source_app = available_apps[int(input("Выберите номер: ")) - 1]

    target_candidates = [a for a in sorted(os.listdir(APPS_DIR)) if a != source_app and a not in BLACKLIST_APPS]
    print("\n=== ВЫБОР ЦЕЛЕВОГО ПРИЛОЖЕНИЯ (TARGET) ===")
    for idx, app in enumerate(target_candidates, 1): print(f" [{idx}] {app}")
    target_app = target_candidates[int(input("Выберите номер: ")) - 1]

    return source_app, target_app
def comment_out_stanza(file_path, stanza_name):
    """Комментирует станзу символом '#' прямо в файле для сохранения его структуры"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        in_target_stanza = False
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped == f"[{stanza_name}]":
                in_target_stanza = True
            elif stripped.startswith('[') and stripped.endswith(']') and stripped != f"[{stanza_name}]":
                in_target_stanza = False
            
            if in_target_stanza and stripped and not stripped.startswith('#'):
                new_lines.append(f"# {line}")
            else:
                new_lines.append(line)
                
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"     [#] Станза [{stanza_name}] успешно закомментирована в источнике.")
    except Exception as e:
        print(f"     [!] Ошибка при комментировании станзы: {e}", file=sys.stderr)

def process_conf_files(source_app, target_app):
    """Поочередный анализ и перенос станз конфигурационных файлов"""
    source_local_dir = os.path.join(APPS_DIR, source_app, "local")
    if not os.path.exists(source_local_dir): return

    try:
        conf_files = [f for f in os.listdir(source_local_dir) if f.endswith(".conf")]
    except PermissionError:
        print(f" [!] Нет прав на чтение папки {source_local_dir}", file=sys.stderr)
        return

    if not conf_files: return

    print("\n=== РАБОТА С ФАЙЛАМИ КОНФИГУРАЦИИ (.conf) ===")
    for file_name in conf_files:
        source_file = os.path.join(source_local_dir, file_name)
        
        source_config = configparser.ConfigParser(strict=False, interpolation=None)
        source_config.optionxform = str
        source_config.read(source_file, encoding="utf-8")
        
        if not source_config.sections(): continue
        print(f"\n Анализ файла: {file_name}")
        
        for section in source_config.sections():
            if not ask_user(f"  -> Перенести станзу [{section}]?"):
                print(f"     [-] Пропущено.")
                continue
            
            target_folder = ask_choice(
                f"     Куда записать станзу в приложении '{target_app}'?", 
                ["local", "default"]
            )
            target_file = os.path.join(APPS_DIR, target_app, target_folder, file_name)
            
            target_config = configparser.ConfigParser(strict=False, interpolation=None)
            target_config.optionxform = str
            if os.path.exists(target_file):
                target_config.read(target_file, encoding="utf-8")
                
            if not target_config.has_section(section):
                target_config.add_section(section)
            for key, value in source_config.items(section):
                target_config.set(section, key, value)
                
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as cf:
                target_config.write(cf, space_around_delimiters=False)
            print(f"     [✓] Записано в {target_folder}/{file_name}")

            action = ask_choice(
                "     Что сделать с исходной станзой?", 
                ["Закомментировать (#)", "Затереть (Удалить полностью)", "Оставить без изменений"]
            )
            
            if action == "Закомментировать (#)":
                comment_out_stanza(source_file, section)
                source_config.read(source_file, encoding="utf-8")
            elif action == "Затереть (Удалить полностью)":
                source_config.remove_section(section)
                with open(source_file, "w", encoding="utf-8") as cf:
                    source_config.write(cf, space_around_delimiters=False)
                print(f"     [x] Станза [{section}] полностью удалена из источника.")
def process_xml_files(source_app, target_app, sub_path, label):
    """Поочередный анализ и копирование XML-файлов визуализации"""
    source_dir = os.path.join(APPS_DIR, source_app, "local", sub_path)
    if not os.path.exists(source_dir): return

    try:
        files = [f for f in os.listdir(source_dir) if os.path.isfile(os.path.join(source_dir, f)) and f.endswith('.xml')]
    except PermissionError: return

    if not files: return

    print(f"\n--- Анализ интерфейса: {label} ---")
    for item in files:
        s_item = os.path.join(source_dir, item)
        
        if not ask_user(f"  -> Перенести {label} файл '{item}'?"):
            print(f"     [-] Пропущено.")
            continue
            
        target_folder = ask_choice(
            f"     Куда скопировать файл в целевом приложении '{target_app}'?", 
            ["local", "default"]
        )
        target_dir = os.path.join(APPS_DIR, target_app, target_folder, sub_path)
        t_item = os.path.join(target_dir, item)
        
        try:
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(s_item, t_item)
            print(f"     [✓] Скопировано в {target_folder}/.../{item}")
            
            if ask_user("     Удалить оригинальный XML-файл из исходного приложения?"):
                os.remove(s_item)
                print(f"     [x] Оригинальный файл '{item}' успешно удален.")
        except Exception as e:
            print(f" [!] Ошибка при работе с файлом {item}: {e}", file=sys.stderr)

def main():
    source_app, target_app = scan_and_select_apps()
    print(f"\n[СТАРТ] Интерактивный перенос данных из '{source_app}' в '{target_app}'\n")

    process_conf_files(source_app, target_app)

    print("\n=== РАБОТА С ЭЛЕМЕНТАМИ ИНТЕРФЕЙСА (XML) ===")
    process_xml_files(source_app, target_app, "data/ui/views", "Views (Дашборды)")
    process_xml_files(source_app, target_app, "data/ui/nav", "Nav (Меню)")

    print("\nПоочередный перенос всех выбранных компонентов завершен.")

if __name__ == "__main__":
    main()
