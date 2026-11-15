from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import sys


def is_available() -> bool:
    return (
        sys.platform.startswith("linux")
        and shutil.which("powershell.exe") is not None
        and shutil.which("wslpath") is not None
    )


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _convert_path(path: str, option: str) -> str:
    result = subprocess.run(
        ["wslpath", option, path],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.rstrip("\r\n")


def to_windows_path(path: str) -> str:
    if sys.platform.startswith("linux") and shutil.which("wslpath") is not None:
        return _convert_path(path, "-w")
    return path


def _qt_filter_to_windows(qt_filter: str) -> str:
    windows_filters = []
    for entry in qt_filter.split(";;"):
        match = re.fullmatch(r"\s*(.*?)\s*\((.*?)\)\s*", entry)
        if match is None:
            continue
        label, patterns = match.groups()
        pattern_list = ";".join(patterns.split()).replace(";*;", ";*.*;")
        if pattern_list == "*":
            pattern_list = "*.*"
        windows_filters.extend((label, pattern_list))
    return "|".join(windows_filters)


def _run_dialog(script: str):
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-STA",
            "-EncodedCommand",
            encoded_script,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    return json.loads(output) if output else None


def get_open_file_names(title: str, initial_directory: str, qt_filter: str) -> list[str]:
    windows_directory = _powershell_literal(_convert_path(initial_directory, "-w"))
    windows_title = _powershell_literal(title)
    windows_filter = _powershell_literal(_qt_filter_to_windows(qt_filter))
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = {windows_title}
$dialog.InitialDirectory = {windows_directory}
$dialog.Filter = {windows_filter}
$dialog.Multiselect = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
    ConvertTo-Json -InputObject @($dialog.FileNames) -Compress
}}
"""
    selected_paths = _run_dialog(script)
    if not selected_paths:
        return []
    return [_convert_path(path, "-u") for path in selected_paths]


def get_existing_directory(title: str, initial_directory: str) -> str | None:
    windows_directory = _powershell_literal(_convert_path(initial_directory, "-w"))
    windows_title = _powershell_literal(title)
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = {windows_title}
$dialog.SelectedPath = {windows_directory}
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
    ConvertTo-Json -InputObject $dialog.SelectedPath -Compress
}}
"""
    selected_path = _run_dialog(script)
    return _convert_path(selected_path, "-u") if selected_path else None


def get_save_file_name(title: str, initial_path: str, qt_filter: str) -> str | None:
    windows_path = _powershell_literal(_convert_path(initial_path, "-w"))
    windows_title = _powershell_literal(title)
    windows_filter = _powershell_literal(_qt_filter_to_windows(qt_filter))
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.SaveFileDialog
$dialog.Title = {windows_title}
$dialog.FileName = {windows_path}
$dialog.Filter = {windows_filter}
$dialog.DefaultExt = 'xlsx'
$dialog.AddExtension = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
    ConvertTo-Json -InputObject $dialog.FileName -Compress
}}
"""
    selected_path = _run_dialog(script)
    return _convert_path(selected_path, "-u") if selected_path else None