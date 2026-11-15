from __future__ import annotations

import json
import re
from calendar import monthrange
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, Final

from app.structured_product_classifier import (
	STRUCTURED_PRODUCT_TYPES,
	infer_product_type_from_contract,
	normalize_product_type,
)


CONTRACT_SUMMARY_COLUMNS = (
	"Source Contract",
	"Product Type",
	"Trade Date",
	"Maturity Date",
	"Underlying",
	"Currency",
	"Notional",
	"Strike Price",
	"Barrier",
	"Coupon Rate",
	"Quantity",
	"Premium",
	"Status",
	"Error",
)

TRANSACTION_COLUMNS = (
	"Date",
	"Status",
	"Event Type",
	"Source Contract",
	"Product Type",
	"Underlying",
	"Currency",
	"Notional",
	"Strike Price",
	"Barrier",
	"Coupon Rate",
	"Quantity",
	"Premium",
	"Frequency",
	"Maturity Date",
)

_TERM_KEYS = (
	"trade_date",
	"maturity_date",
	"underlying",
	"currency",
	"notional",
	"strike_price",
	"barrier",
	"coupon_rate",
	"quantity",
	"premium",
)

MAX_EXTRACTION_TOKENS: Final = 256


def extract_contract_transactions(
	contract_text: str,
	source_contract: str,
	model_name: str = "Qwen/Qwen2.5-0.5B-Instruct",
	text_generator: Callable[[str, str, int], str] | None = None,
	progress_callback: Callable[[int], None] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
	"""Extract contract terms and event-level transaction rows from contract text."""
	allowed_types = ", ".join(STRUCTURED_PRODUCT_TYPES)
	prompt = (
		"Extract structured product terms and transaction events from this financial contract. "
		"Return only valid JSON, with no markdown or explanation, using this schema: "
		'{"product_type":"one allowed type",'
		'"terms":{"trade_date":"YYYY-MM-DD or null",'
		'"maturity_date":"YYYY-MM-DD or null", "underlying":null, "currency":null, '
		'"notional":null, "strike_price":null, "barrier":null, "coupon_rate":null, '
		'"quantity":null, "premium":null}, '
		'"events":[{"event_type":"factual event label", '
		'"date":"YYYY-MM-DD or null", "frequency":"stated recurrence or null", '
		'"first_event_date":"YYYY-MM-DD or null", "end_date":"YYYY-MM-DD or null"}]} '
		f"Allowed product types: {allowed_types}. Extract only terms supported by the text. "
		"Represent each recurring fixing schedule as one event with its frequency, not one "
		"event per fixing. Do not write descriptions. Set first_event_date only when the "
		"first event date is explicitly stated; otherwise leave it null so the schedule can be "
		"inferred from trade_date and frequency. Use maturity_date as the schedule end when "
		"no event-specific end date is stated. Return one fixing per scheduled date after "
		"expansion. For a single event, use date. Do not invent exact dates, rates, or amounts.\n\n"
		f"CONTRACT:\n{contract_text}\n\nJSON:"
	)
	if text_generator is None:
		from app.local_llm import generate_text

		model_output = generate_text(
			model_name,
			prompt,
			MAX_EXTRACTION_TOKENS,
			progress_callback=(
				lambda token_count: progress_callback(
					min(100, round(token_count * 100 / MAX_EXTRACTION_TOKENS))
				)
				if progress_callback is not None
				else None
			),
		)
	else:
		model_output = text_generator(model_name, prompt, MAX_EXTRACTION_TOKENS)
	data = _parse_json_object(model_output)
	terms = data.get("terms")
	if not isinstance(terms, dict):
		terms = {}

	product_type = normalize_product_type(str(data.get("product_type") or "Unknown"))
	if product_type == "Unknown":
		product_type = infer_product_type_from_contract(contract_text)

	parsed_terms = {key: _term_value(terms.get(key)) for key in _TERM_KEYS}
	parsed_terms["trade_date"] = _parse_date(parsed_terms["trade_date"])
	parsed_terms["maturity_date"] = _parse_date(parsed_terms["maturity_date"])
	summary = {
		"Source Contract": source_contract,
		"Product Type": product_type,
		"Trade Date": parsed_terms["trade_date"],
		"Maturity Date": parsed_terms["maturity_date"],
		"Underlying": parsed_terms["underlying"],
		"Currency": parsed_terms["currency"],
		"Notional": parsed_terms["notional"],
		"Strike Price": parsed_terms["strike_price"],
		"Barrier": parsed_terms["barrier"],
		"Coupon Rate": parsed_terms["coupon_rate"],
		"Quantity": parsed_terms["quantity"],
		"Premium": parsed_terms["premium"],
		"Status": "Extracted",
		"Error": "",
	}

	events = data.get("events")
	if not isinstance(events, list):
		events = []

	transactions_by_date: dict[date, dict[str, Any]] = {}
	for event in events:
		if not isinstance(event, dict):
			continue
		for event_date in _event_dates(event, parsed_terms):
			if event_date is None:
				continue
			row = transactions_by_date.setdefault(
				event_date,
				{
					"Date": event_date,
					"Status": "Completed" if event_date <= date.today() else "Upcoming",
					"Event Type": "",
					"Source Contract": source_contract,
					"Product Type": product_type,
					"Underlying": _term_value(terms.get("underlying")),
					"Currency": _term_value(terms.get("currency")),
					"Notional": _term_value(terms.get("notional")),
					"Strike Price": _term_value(terms.get("strike_price")),
					"Barrier": _term_value(terms.get("barrier")),
					"Coupon Rate": _term_value(terms.get("coupon_rate")),
					"Quantity": _term_value(terms.get("quantity")),
					"Premium": _term_value(terms.get("premium")),
					"Frequency": "",
					"Maturity Date": parsed_terms["maturity_date"],
				},
			)
			for column, value in (
				("Event Type", _term_value(event.get("event_type"))),
				("Frequency", _term_value(event.get("frequency"))),
			):
				if value and value not in row[column].split("; "):
					row[column] = "; ".join(filter(None, (row[column], value)))
	transactions = sorted(transactions_by_date.values(), key=lambda row: row["Date"])
	return summary, transactions


def _parse_json_object(model_output: str) -> dict[str, Any]:
	start = model_output.find("{")
	end = model_output.rfind("}")
	if start < 0 or end < start:
		raise ValueError("The model did not return a JSON object.")
	data = json.loads(model_output[start : end + 1])
	if not isinstance(data, dict):
		raise ValueError("The model response must be a JSON object.")
	return data


def _term_value(value: Any) -> str | None:
	if value is None:
		return None
	text = str(value).strip()
	return text or None


def _parse_date(value: Any) -> date | None:
	text = _term_value(value)
	if text is None or text.casefold() in {"null", "unknown", "n/a"}:
		return None
	try:
		return date.fromisoformat(text[:10])
	except ValueError:
		return None


def _event_dates(event: dict[str, Any], terms: dict[str, Any]) -> list[date | None]:
	frequency = _term_value(event.get("frequency"))
	interval = _frequency_interval(frequency)
	first_event_date = _parse_date(event.get("first_event_date"))
	explicit_date = _parse_date(event.get("date"))
	end_date = _parse_date(event.get("end_date")) or terms.get("maturity_date")

	if interval is not None and end_date is not None:
		anchor = first_event_date or explicit_date or terms.get("trade_date")
		if anchor is not None:
			starts_at_anchor = first_event_date is not None or explicit_date is not None
			first_index = 0 if starts_at_anchor else 1
			scheduled_dates: list[date] = []
			index = first_index
			while True:
				event_date = _advance_date(anchor, interval, index)
				if event_date > end_date:
					break
				scheduled_dates.append(event_date)
				index += 1
			return scheduled_dates

	if explicit_date is not None:
		return [explicit_date]
	if first_event_date is not None:
		return [first_event_date]
	if any(word in str(event.get("event_type", "")).casefold() for word in ("maturity", "redemption", "settlement", "expiry")):
		if end_date is not None:
			return [end_date]
	return [None]


def _frequency_interval(frequency: str | None) -> tuple[str, int] | None:
	if not frequency:
		return None
	normalized = re.sub(r"[_-]+", " ", frequency.casefold())
	match = re.search(r"(?:every\s+)?(\d+)\s+(day|week|month|quarter|year)s?", normalized)
	if match:
		count = int(match.group(1))
		unit = match.group(2)
		if unit == "quarter":
			return "month", count * 3
		if unit == "year":
			return "month", count * 12
		return unit, count
	if "biweekly" in normalized or "fortnight" in normalized:
		return "day", 14
	if "daily" in normalized or "each day" in normalized:
		return "day", 1
	if "weekly" in normalized or "each week" in normalized:
		return "day", 7
	if "quarterly" in normalized:
		return "month", 3
	if "monthly" in normalized or "each month" in normalized:
		return "month", 1
	if "semi annual" in normalized or "semiannual" in normalized or "half yearly" in normalized:
		return "month", 6
	if "annually" in normalized or "annual" in normalized or "yearly" in normalized:
		return "month", 12
	return None


def _advance_date(anchor: date, interval: tuple[str, int], index: int) -> date:
	unit, amount = interval
	if unit == "day":
		return anchor + timedelta(days=amount * index)
	month_index = anchor.month - 1 + amount * index
	year = anchor.year + month_index // 12
	month = month_index % 12 + 1
	day = min(anchor.day, monthrange(year, month)[1])
	return date(year, month, day)