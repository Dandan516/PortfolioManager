import os
import shlex
import subprocess
import sys
from pathlib import Path, PureWindowsPath


def _launch_in_wsl() -> int:
	project_root = Path(__file__).resolve().parent
	windows_root = PureWindowsPath(str(project_root))
	if not windows_root.drive:
		print(f"Cannot map project path into WSL: {project_root}", file=sys.stderr)
		return 1

	root_parts = windows_root.parts[1:]
	wsl_root = f"/mnt/{windows_root.drive[0].lower()}/{'/'.join(root_parts)}"
	distribution = os.environ.get("PORTFOLIO_MANAGER_WSL_DISTRO", "Ubuntu")
	command = (
		f"cd -- {shlex.quote(wsl_root)} && "
		f"exec \"$HOME/.venvs/portfolio-manager/bin/python\" "
		f"{shlex.quote(wsl_root + '/main.py')}"
	)
	try:
		return subprocess.run(
			["wsl.exe", "-d", distribution, "--", "bash", "-lc", command],
			check=False,
		).returncode
	except FileNotFoundError:
		print("WSL was not found. Install WSL and run setup.ps1 first.", file=sys.stderr)
		return 1


def main() -> None:
	if sys.platform == "win32":
		raise SystemExit(_launch_in_wsl())

	wslg_runtime_dir = Path("/mnt/wslg/runtime-dir")
	if sys.platform.startswith("linux") and (wslg_runtime_dir / "wayland-0").exists():
		os.environ["XDG_RUNTIME_DIR"] = str(wslg_runtime_dir)

	from PySide6.QtWidgets import QApplication

	from app.gui import MainWindow

	app = QApplication(sys.argv)
	window = MainWindow()
	window.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
