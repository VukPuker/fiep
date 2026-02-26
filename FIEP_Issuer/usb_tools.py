import os
import json
import shutil
import subprocess
import psutil


# ---------------------------------------------------------
# 1. Поиск флешек (removable drives)
# ---------------------------------------------------------

def list_removable_drives():
    """
    Возвращает список флешек вида:
    [
        {"mount": "E:\\", "label": "USB_DISK"},
        ...
    ]
    """
    drives = []
    partitions = psutil.disk_partitions(all=False)

    for p in partitions:
        if "removable" in p.opts.lower():
            mount = p.mountpoint
            label = os.path.splitdrive(mount)[0]
            drives.append({
                "mount": mount,
                "label": label
            })

    return drives


# ---------------------------------------------------------
# 2. Получение USB-ID (серийный номер устройства)
# ---------------------------------------------------------

def get_usb_id(drive_letter: str) -> str:
    """
    Получает USB-ID через PowerShell (Windows 10/11).
    drive_letter: 'E:\\' или 'E:'
    """
    drive_letter = drive_letter.rstrip("\\")
    letter = drive_letter.replace(":", "")

    # PowerShell: получаем номер физического диска по букве
    ps_script = f"""
    $vol = Get-Volume -DriveLetter {letter}
    $part = Get-Partition -DriveLetter {letter}
    $disk = Get-Disk -Number $part.DiskNumber
    $disk.SerialNumber
    """

    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps_script],
            stderr=subprocess.STDOUT,
            text=True
        ).strip()
    except Exception as e:
        return "UNKNOWN"

    if not output:
        return "UNKNOWN"

    return output



# ---------------------------------------------------------
# 3. Копирование портативного FIEP
# ---------------------------------------------------------

def copy_portable_template(template_dir: str, target_drive: str):
    """
    Копирует содержимое templates/fiep_portable/ на флешку.
    """
    for root, dirs, files in os.walk(template_dir):
        rel = os.path.relpath(root, template_dir)
        dest_dir = os.path.join(target_drive, rel)

        os.makedirs(dest_dir, exist_ok=True)

        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join(dest_dir, f)
            shutil.copy2(src, dst)


# ---------------------------------------------------------
# 4. Запись profile.enc
# ---------------------------------------------------------

def write_profile_enc(target_drive: str, profile_enc_dict: dict):
    path = os.path.join(target_drive, "profile.enc")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile_enc_dict, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------
# 5. Запись activation.key
# ---------------------------------------------------------

def write_activation_key(target_drive: str, activation_key_b32: str):
    path = os.path.join(target_drive, "activation.key")
    with open(path, "w", encoding="utf-8") as f:
        f.write("FIEP-ACT-1\n")
        f.write(activation_key_b32 + "\n")


# ---------------------------------------------------------
# 6. Создание fiep_portable_config.json
# ---------------------------------------------------------

def write_portable_config(target_drive: str, usb_id: str):
    cfg = {
        "version": 1,
        "usb_id": usb_id,
        "data_dir": ".",  # корень флешки
        "portable": True
    }

    path = os.path.join(target_drive, "fiep_portable_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
