from __future__ import annotations

from pathlib import Path
from threading import Lock

import pandas as pd


_WORKBOOK_WRITE_LOCK = Lock()


def write_workbook_sheets(
	path: str | Path,
	sheets: dict[str, pd.DataFrame],
) -> None:
	"""Write or replace named sheets without removing other workbook sheets."""
	target = Path(path)
	with _WORKBOOK_WRITE_LOCK:
		mode = "a" if target.exists() else "w"
		with pd.ExcelWriter(
			target,
			engine="openpyxl",
			mode=mode,
			if_sheet_exists="replace" if mode == "a" else None,
		) as writer:
			for sheet_name, dataframe in sheets.items():
				dataframe.to_excel(writer, sheet_name=sheet_name, index=False)