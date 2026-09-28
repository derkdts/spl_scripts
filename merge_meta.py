import os
import shutil
import re
import sys

SPLUNK_APPS_DIR = "/opt/splunk/etc/apps"

def parse_meta_body(body_text):
    lines = body_text.strip().split('\n')
    params = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            key, val = line.split('=', 1)
            params[key.strip()] = val.strip()
    return params

def build_meta_body(params_dict):
    return '\n'.join([f"{k} = {v}" for k, v in params_dict.items()])

def parse_meta_file(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    stanzas = re.findall(r'(\[[^\]]+\])(.*?)(?=\n\[|\Z)', content, re.DOTALL)
    return [(header.strip(), body.strip()) for header, body in stanzas]

def save_meta_file(file_path, stanzas_list):
    with open(file_path, 'w', encoding='utf-8') as f:
        for header, body in stanzas_list:
            f.write(f"{header}\n")
            if body:
                f.write(f"{body}\n")
            f.write("\n")

def select_app():
    """Меню выбора приложения"""
    if not os.path.exists(SPLUNK_APPS_DIR):
        print(f"❌ Директория с приложениями не найдена: {SPLUNK_APPS_DIR}")
        apps_dir = input("Введите корректный путь к папке etc/apps: ").strip()
    else:
        apps_dir = SPLUNK_APPS_DIR

    apps = [d for d in os.listdir(apps_dir) if os.path.isdir(os.path.join(apps_dir, d))]
    apps.sort()

    print("\n--- Список доступных приложений (Apps) ---")
    for idx, app in enumerate(apps, 1):
        print(f"[{idx}] {app}")
    
    while True:
        try:
            choice = int(input("\nВыберите номер приложения: "))
            if 1 <= choice <= len(apps):
                return os.path.join(apps_dir, apps[choice - 1]), apps[choice - 1]
            print("❌ Неверный номер. Попробуйте еще раз.")
        except ValueError:
            print("❌ Введите число.")

def select_stanza(app_path):
    """Меню выбора станзы из local.meta"""
    local_meta_path = os.path.join(app_path, 'metadata', 'local.meta')
    if not os.path.exists(local_meta_path):
        print(f"ℹ️ Файл local.meta отсутствует в этом приложении.")
        return None

    stanzas = parse_meta_file(local_meta_path)
    if not stanzas:
        print("ℹ️ В файле local.meta нет активных станз.")
        return None

    print("\n--- Список доступных станз в local.meta ---")
    for idx, (header, _) in enumerate(stanzas, 1):
        print(f"[{idx}] {header}")

    while True:
        try:
            choice = int(input("\nВыберите номер станзы для переноса: "))
            if 1 <= choice <= len(stanzas):
                return stanzas[choice - 1][0]
            print("❌ Неверный номер. Попробуйте еще раз.")
        except ValueError:
            print("❌ Введите число.")

def merge_and_move_stanza(app_path, stanza_name):
    local_meta_path = os.path.join(app_path, 'metadata', 'local.meta')
    default_meta_path = os.path.join(app_path, 'metadata', 'default.meta')

    shutil.copy2(local_meta_path, local_meta_path + '.bak')
    if os.path.exists(default_meta_path):
        shutil.copy2(default_meta_path, default_meta_path + '.bak')
    print("\n💾 Резервные копии .bak успешно созданы.")

    local_stanzas = parse_meta_file(local_meta_path)
    default_stanzas = parse_meta_file(default_meta_path)

    local_body = None
    new_local_stanzas = []
    
    for header, body in local_stanzas:
        if header == stanza_name:
            local_body = body
        else:
            new_local_stanzas.append((header, body))

    local_params = parse_meta_body(local_body)
    new_default_stanzas = []
    merged_in_default = False
    
    for header, body in default_stanzas:
        if header == stanza_name:
            default_params = parse_meta_body(body)
            for k, v in local_params.items():
                if k not in default_params:
                    print(f"➕ Поле добавлено: {k} = {v}")
                elif default_params[k] != v:
                    print(f"🔄 Поле обновлено: {k} ({default_params[k]} -> {v})")
                default_params[k] = v
                
            merged_body = build_meta_body(default_params)
            new_default_stanzas.append((header, merged_body))
            merged_in_default = True
        else:
            new_default_stanzas.append((header, body))
            
    if not merged_in_default:
        new_default_stanzas.append((stanza_name, local_body))
        print(f"➕ Станза {stanza_name} перенесена целиком (ранее отсутствовала в default.meta).")

    save_meta_file(local_meta_path, new_local_stanzas)
    save_meta_file(default_meta_path, new_default_stanzas)
    print("✨ Мерж успешно выполнен!")

if __name__ == "__main__":
    print("=== Утилита интерактивного переноса метаданных Splunk ===")
    app_path, app_name = select_app()
    print(f"Выбрано приложение: {app_name}")
    
    target_stanza = select_stanza(app_path)
    if target_stanza:
        merge_and_move_stanza(app_path, target_stanza)
    else:
        print("🛑 Перенос отменен, так как нечего переносить.")
