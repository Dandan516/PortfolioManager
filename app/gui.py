from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.stock_price_fetcher import fetch_stock_prices_from_list
from app import host_file_dialog
from app.contract_parser import read_contract_file
from app.contract_transaction_extractor import (
    CONTRACT_SUMMARY_COLUMNS,
    MAX_EXTRACTION_TOKENS,
    TRANSACTION_COLUMNS,
    extract_contract_transactions,
)
from app.workbook_export import write_workbook_sheets


class TickerWorker(QObject):
    finished = Signal(pd.DataFrame)
    error = Signal(str)

    def __init__(self, input_path: str, output_path: str) -> None:
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path

    def run(self) -> None:
        try:
            with open(self.input_path, "r", encoding="utf-8") as file_obj:
                df = fetch_stock_prices_from_list(file_obj)

            write_workbook_sheets(self.output_path, {"Stock Prices": df})
            self.finished.emit(df)
        except FileNotFoundError:
            self.error.emit(f"Input file not found: {self.input_path}")
        except PermissionError:
            self.error.emit(
                f"Cannot write to {self.output_path}. Close the Excel file if it is open and try again."
            )
        except Exception as exc:
            self.error.emit(str(exc))


class ContractExtractionWorker(QObject):
    progress = Signal(int, str, str)
    finished = Signal(int, int)
    error = Signal(str)

    def __init__(self, contract_paths: list[Path], output_path: str) -> None:
        super().__init__()
        self.contract_paths = contract_paths
        self.output_path = output_path

    def run(self) -> None:
        try:
            summaries = []
            transactions = []
            contract_sheets = {}
            used_sheet_names = {"contract summary", "transactions"}

            for row_index, path in enumerate(self.contract_paths):
                sheet_name = _contract_sheet_name(path, used_sheet_names)
                try:
                    contract_text = read_contract_file(path)
                    self.progress.emit(row_index, "Unknown", "0%")
                    summary, contract_transactions = extract_contract_transactions(
                        contract_text,
                        path.name,
                        progress_callback=lambda percentage: self.progress.emit(
                            row_index,
                            "Unknown",
                            f"{percentage}%",
                        ),
                    )
                    summaries.append(summary)
                    transactions.extend(contract_transactions)
                    contract_sheets[sheet_name] = pd.DataFrame(
                        contract_transactions,
                        columns=TRANSACTION_COLUMNS,
                    )
                    product_type = summary["Product Type"]
                    self.progress.emit(row_index, product_type, "Completed")
                except Exception as exc:
                    summaries.append(
                        {
                            "Source Contract": path.name,
                            "Product Type": "Unknown",
                            "Status": "Error",
                            "Error": str(exc),
                        }
                    )
                    contract_sheets[sheet_name] = pd.DataFrame(
                        columns=TRANSACTION_COLUMNS
                    )

            sheets = {
                "Contract Summary": pd.DataFrame(
                    summaries,
                    columns=CONTRACT_SUMMARY_COLUMNS,
                ),
                "Transactions": pd.DataFrame(
                    transactions,
                    columns=TRANSACTION_COLUMNS,
                ),
            }
            sheets.update(contract_sheets)
            write_workbook_sheets(self.output_path, sheets)
            self.finished.emit(len(summaries), len(transactions))
        except Exception as exc:
            self.error.emit(str(exc))


def _contract_sheet_name(path: Path, used_names: set[str]) -> str:
    base_name = path.stem
    for character in '[]:*?/\\':
        base_name = base_name.replace(character, "_")
    base_name = base_name.strip(" '") or "Contract"
    index = 1
    while True:
        suffix = "" if index == 1 else f" ({index})"
        candidate = f"{base_name[:31 - len(suffix)]}{suffix}"
        if candidate.casefold() not in used_names:
            used_names.add(candidate.casefold())
            return candidate
        index += 1


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Portfolio Manager")
        self.resize(820, 560)

        self._thread: QThread | None = None
        self._worker: TickerWorker | None = None
        self._contract_thread: QThread | None = None
        self._contract_worker: ContractExtractionWorker | None = None
        self.contract_paths: list[Path] = []
        project_directory = Path(__file__).resolve().parent.parent
        self.stock_prices_workbook_path = project_directory / "stock_prices.xlsx"
        self.contracts_workbook_path = project_directory / "contract_transactions.xlsx"

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        ticker_tab = QWidget()
        ticker_layout = QVBoxLayout(ticker_tab)

        form_group = QGroupBox("Ticker")
        form_layout = QFormLayout(form_group)

        self.input_file_path = Path(__file__).resolve().parent.parent / "stock_codes.txt"

        input_row = QWidget()
        input_row_layout = QHBoxLayout(input_row)
        input_row_layout.setContentsMargins(0, 0, 0, 0)
        input_browse = QPushButton("Browse file")
        input_browse.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        input_browse.clicked.connect(self.browse_input_file)
        input_row_layout.addWidget(input_browse, alignment=Qt.AlignmentFlag.AlignLeft)
        windows_input_path = host_file_dialog.to_windows_path(str(self.input_file_path))
        self.input_file_label = QLabel(windows_input_path)
        self.input_file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.input_file_label.setToolTip(windows_input_path)
        input_row_layout.addWidget(self.input_file_label, stretch=1)

        form_layout.addRow("Input text file", input_row)

        self.run_button = QPushButton("Fetch Prices")
        self.run_button.clicked.connect(self.start_fetch)
        self.run_button.setMinimumHeight(52)

        self.status_label = QLabel("Ready")

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Code", "Price", "Timestamp"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        ticker_layout.addWidget(form_group)
        ticker_layout.addWidget(self.run_button)
        ticker_layout.addWidget(self.status_label)
        ticker_layout.addWidget(self.table)

        self.tabs.addTab(ticker_tab, "Fetch Stock Prices")
        self._build_contracts_tab()

    def _build_contracts_tab(self) -> None:
        contracts_tab = QWidget()
        contracts_layout = QVBoxLayout(contracts_tab)

        upload_group = QGroupBox("Contract Files")
        upload_layout = QVBoxLayout(upload_group)
        upload_hint = QLabel(
            "Add PDF, HTML, or text contracts. Folder selection includes supported files in subfolders."
        )
        upload_hint.setWordWrap(True)
        upload_layout.addWidget(upload_hint)

        upload_actions = QHBoxLayout()
        add_files_button = QPushButton("Add Files")
        add_files_button.clicked.connect(self.add_contract_files)
        add_folder_button = QPushButton("Add Folder")
        add_folder_button.clicked.connect(self.add_contract_folder)
        self.extract_contracts_button = QPushButton("Extract Information")
        self.extract_contracts_button.clicked.connect(self.start_contract_extraction)
        self.extract_contracts_button.setMinimumHeight(52)
        self.extract_contracts_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_selected_contracts)
        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self.clear_contracts)
        upload_actions.addWidget(add_files_button)
        upload_actions.addWidget(add_folder_button)
        upload_actions.addStretch()
        upload_actions.addWidget(remove_button)
        upload_actions.addWidget(clear_button)
        upload_layout.addLayout(upload_actions)

        self.contract_table = QTableWidget(0, 4)
        self.contract_table.setHorizontalHeaderLabels(["File", "Format", "Size", "Location"])
        self.contract_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.contract_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.contract_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.contract_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.contract_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.contract_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.contract_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.contract_table.setAlternatingRowColors(True)

        self.contract_status_label = QLabel("No contracts selected")
        self.contract_results_table = QTableWidget(0, 3)
        self.contract_results_table.setHorizontalHeaderLabels(["File", "Product Type", "Status"])
        self.contract_results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.contract_results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.contract_results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.contract_results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.contract_results_table.setAlternatingRowColors(True)
        contracts_layout.addWidget(upload_group)
        contracts_layout.addWidget(self.contract_status_label)
        contracts_layout.addWidget(self.contract_table)
        contracts_layout.addWidget(self.extract_contracts_button)
        contracts_layout.addWidget(QLabel("Extraction Results"))
        contracts_layout.addWidget(self.contract_results_table)

        contracts_tab_index = self.tabs.addTab(contracts_tab, "Contracts")
        self.tabs.setTabEnabled(contracts_tab_index, False)

    def add_contract_files(self) -> None:
        title = "Select contract files"
        initial_directory = str(Path.cwd())
        file_filter = "Contract Files (*.pdf *.html *.htm *.txt);;All Files (*)"
        if host_file_dialog.is_available():
            paths = host_file_dialog.get_open_file_names(title, initial_directory, file_filter)
        else:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                title,
                initial_directory,
                file_filter,
            )
        self._add_contract_paths(Path(path) for path in paths)

    def add_contract_folder(self) -> None:
        title = "Select contract folder"
        initial_directory = str(Path.cwd())
        if host_file_dialog.is_available():
            folder = host_file_dialog.get_existing_directory(title, initial_directory)
        else:
            folder = QFileDialog.getExistingDirectory(self, title, initial_directory)
        if not folder:
            return

        supported_extensions = {".pdf", ".html", ".htm", ".txt"}
        paths = (
            path
            for path in Path(folder).rglob("*")
            if path.is_file() and path.suffix.casefold() in supported_extensions
        )
        self._add_contract_paths(paths)

    def _add_contract_paths(self, paths: Iterable[Path]) -> None:
        existing_paths = {str(path).casefold() for path in self.contract_paths}
        for path in paths:
            contract_path = Path(path).resolve()
            path_key = str(contract_path).casefold()
            if path_key not in existing_paths:
                self.contract_paths.append(contract_path)
                existing_paths.add(path_key)

        self._refresh_contract_table()

    def remove_selected_contracts(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.contract_table.selectedIndexes()},
            reverse=True,
        )
        for row_index in selected_rows:
            self.contract_paths.pop(row_index)
        self._refresh_contract_table()

    def clear_contracts(self) -> None:
        self.contract_paths.clear()
        self.contract_results_table.setRowCount(0)
        self._refresh_contract_table()

    def start_contract_extraction(self) -> None:
        if not self.contract_paths:
            QMessageBox.warning(self, "No contracts", "Add at least one contract before extracting information.")
            return

        self.extract_contracts_button.setEnabled(False)
        self.contract_status_label.setText(
            f"Extracting information from {len(self.contract_paths)} contract(s)..."
        )
        self._contract_thread = QThread(self)
        self._contract_worker = ContractExtractionWorker(
            list(self.contract_paths),
            str(self.contracts_workbook_path),
        )
        self._contract_worker.moveToThread(self._contract_thread)
        self._initialize_contract_results()
        self._contract_thread.started.connect(self._contract_worker.run)
        self._contract_worker.progress.connect(self.on_contract_progress)
        self._contract_worker.finished.connect(self.on_contract_extraction_finished)
        self._contract_worker.error.connect(self.on_contract_extraction_error)
        self._contract_worker.finished.connect(self._contract_thread.quit)
        self._contract_worker.error.connect(self._contract_thread.quit)
        self._contract_thread.finished.connect(self._cleanup_contract_thread)
        self._contract_thread.start()

    def _initialize_contract_results(self) -> None:
        self.contract_results_table.setRowCount(len(self.contract_paths))
        for row_index, path in enumerate(self.contract_paths):
            values = (path.name, "Unknown", "Pending")
            for column_index, value in enumerate(values):
                self.contract_results_table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(value),
                )

    def on_contract_progress(self, row_index: int, product_type: str, status: str) -> None:
        self.contract_results_table.setItem(row_index, 1, QTableWidgetItem(product_type))
        self.contract_results_table.setItem(row_index, 2, QTableWidgetItem(status))

    def on_contract_extraction_finished(
        self,
        contract_count: int,
        transaction_count: int,
    ) -> None:
        self.contract_status_label.setText(
            f"Processed {contract_count} contract(s); exported {transaction_count} transaction(s)"
        )
        self.extract_contracts_button.setEnabled(True)

    def on_contract_extraction_error(self, message: str) -> None:
        self.extract_contracts_button.setEnabled(True)
        self.contract_status_label.setText("Extraction failed")
        QMessageBox.critical(self, "Contract extraction error", message)

    def _cleanup_contract_thread(self) -> None:
        if self._contract_worker is not None:
            self._contract_worker.deleteLater()
            self._contract_worker = None
        if self._contract_thread is not None:
            self._contract_thread.deleteLater()
            self._contract_thread = None

    def _refresh_contract_table(self) -> None:
        self.contract_table.setRowCount(len(self.contract_paths))
        for row_index, path in enumerate(self.contract_paths):
            file_size = path.stat().st_size if path.exists() else 0
            values = (
                path.name,
                path.suffix.removeprefix(".").upper(),
                f"{file_size / 1024:.1f} KB",
                str(path.parent),
            )
            for column_index, value in enumerate(values):
                self.contract_table.setItem(row_index, column_index, QTableWidgetItem(value))

        count = len(self.contract_paths)
        self.contract_status_label.setText(
            f"{count} contract{'s' if count != 1 else ''} selected"
            if count
            else "No contracts selected"
        )

    def browse_input_file(self) -> None:
        title = "Select stock codes text file"
        initial_directory = str(self.input_file_path.parent)
        file_filter = "Text Files (*.txt);;All Files (*)"
        if host_file_dialog.is_available():
            paths = host_file_dialog.get_open_file_names(title, initial_directory, file_filter)
            path = paths[0] if paths else ""
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                title,
                initial_directory,
                file_filter,
            )
        if path:
            self.input_file_path = Path(path)
            windows_path = host_file_dialog.to_windows_path(str(self.input_file_path))
            self.input_file_label.setText(windows_path)
            self.input_file_label.setToolTip(windows_path)

    def start_fetch(self) -> None:
        input_path = self.input_file_path
        if not input_path.is_file():
            QMessageBox.warning(self, "Missing input", f"Stock codes file not found: {input_path}")
            return

        self.run_button.setEnabled(False)
        self.status_label.setText("Fetching prices...")

        self._thread = QThread(self)
        self._worker = TickerWorker(str(input_path), str(self.stock_prices_workbook_path))
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self.on_finished)
        self._worker.error.connect(self.on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)

        self._thread.start()

    def on_finished(self, df: pd.DataFrame) -> None:
        self.populate_table(df)
        self.status_label.setText("Done")
        self.run_button.setEnabled(True)

    def on_error(self, message: str) -> None:
        self.status_label.setText("Error")
        self.run_button.setEnabled(True)
        QMessageBox.critical(self, "Error", message)

    def populate_table(self, df: pd.DataFrame) -> None:
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels(list(df.columns))

        for row_index, row in enumerate(df.itertuples(index=False)):
            for col_index, value in enumerate(row):
                item = QTableWidgetItem("" if value is None else str(value))
                self.table.setItem(row_index, col_index, item)

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
