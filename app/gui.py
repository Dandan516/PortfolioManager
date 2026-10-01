from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
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
	QTableWidget,
	QTableWidgetItem,
	QVBoxLayout,
	QWidget,
)

from app.fetch_stock_price import fetch_stock_prices_from_list


class FetchWorker(QObject):
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

			df.to_excel(self.output_path, index=False)
			self.finished.emit(df)
		except FileNotFoundError:
			self.error.emit(f"Input file not found: {self.input_path}")
		except PermissionError:
			self.error.emit(
				f"Cannot write to {self.output_path}. Close the Excel file if it is open and try again."
			)
		except Exception as exc:
			self.error.emit(str(exc))


class MainWindow(QMainWindow):
	def __init__(self) -> None:
		super().__init__()
		self.setWindowTitle("Portfolio Manager")
		self.resize(820, 560)

		self._thread: QThread | None = None
		self._worker: FetchWorker | None = None

		central = QWidget()
		self.setCentralWidget(central)

		layout = QVBoxLayout(central)

		self.tabs = QTabWidget()
		layout.addWidget(self.tabs)

		fetch_tab = QWidget()
		fetch_layout = QVBoxLayout(fetch_tab)

		form_group = QGroupBox("Stock Price Fetcher")
		form_layout = QFormLayout(form_group)

		self.input_path_edit = QLineEdit(str(Path("stock_codes.txt").resolve()))
		self.output_path_edit = QLineEdit(str(Path("stock_prices.xlsx").resolve()))

		input_row = QWidget()
		input_row_layout = QHBoxLayout(input_row)
		input_row_layout.setContentsMargins(0, 0, 0, 0)
		input_row_layout.addWidget(self.input_path_edit)
		input_browse = QPushButton("Browse")
		input_browse.clicked.connect(self.browse_input_file)
		input_row_layout.addWidget(input_browse)

		output_row = QWidget()
		output_row_layout = QHBoxLayout(output_row)
		output_row_layout.setContentsMargins(0, 0, 0, 0)
		output_row_layout.addWidget(self.output_path_edit)
		output_browse = QPushButton("Browse")
		output_browse.clicked.connect(self.browse_output_file)
		output_row_layout.addWidget(output_browse)

		form_layout.addRow("Input text file", input_row)
		form_layout.addRow("Output Excel file", output_row)

		self.run_button = QPushButton("Fetch Prices")
		self.run_button.clicked.connect(self.start_fetch)
		self.run_button.setMinimumHeight(52)
		self.run_button.setStyleSheet(
			"""
			QPushButton {
				background-color: #0057D8;
				color: white;
				font-size: 15px;
				font-weight: 700;
				padding: 12px 20px;
				border: 1px solid #003E9A;
				border-radius: 8px;
			}
			QPushButton:hover {
				background-color: #0069FF;
			}
			QPushButton:pressed {
				background-color: #0047B3;
			}
			QPushButton:disabled {
				background-color: #8AAAE5;
				color: #EAEAEA;
			}
			"""
		)

		self.status_label = QLabel("Ready")

		self.table = QTableWidget(0, 3)
		self.table.setHorizontalHeaderLabels(["Code", "Price", "Timestamp"])
		self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
		self.table.setAlternatingRowColors(True)
		self.table.setEditTriggers(QTableWidget.NoEditTriggers)

		fetch_layout.addWidget(form_group)
		fetch_layout.addWidget(self.run_button)
		fetch_layout.addWidget(self.status_label)
		fetch_layout.addWidget(self.table)

		self.tabs.addTab(fetch_tab, "Fetch Stock Prices")
		self.tabs.addTab(QWidget(), "Future Features")

	def browse_input_file(self) -> None:
		path, _ = QFileDialog.getOpenFileName(
			self,
			"Select stock codes text file",
			str(Path.cwd()),
			"Text Files (*.txt);;All Files (*)",
		)
		if path:
			self.input_path_edit.setText(path)

	def browse_output_file(self) -> None:
		path, _ = QFileDialog.getSaveFileName(
			self,
			"Save Excel file",
			str(Path.cwd() / "stock_prices.xlsx"),
			"Excel Files (*.xlsx)",
		)
		if path:
			if not path.lower().endswith(".xlsx"):
				path += ".xlsx"
			self.output_path_edit.setText(path)

	def start_fetch(self) -> None:
		input_path = self.input_path_edit.text().strip()
		output_path = self.output_path_edit.text().strip()

		if not input_path:
			QMessageBox.warning(self, "Missing input", "Please select a stock codes text file.")
			return

		if not output_path:
			QMessageBox.warning(self, "Missing output", "Please select an output Excel file.")
			return

		self.run_button.setEnabled(False)
		self.status_label.setText("Fetching prices...")

		self._thread = QThread(self)
		self._worker = FetchWorker(input_path, output_path)
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
