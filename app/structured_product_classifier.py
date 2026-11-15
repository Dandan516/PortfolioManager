from __future__ import annotations

import re
from typing import Final


STRUCTURED_PRODUCT_TYPES: Final[tuple[str, ...]] = (
	"Accumulator",
	"Autocallable Note",
	"Barrier Note",
	"Bonus Certificate",
	"Capital-Protected Note",
	"Commodity-Linked Note",
	"Covered Call",
	"Credit-Linked Note",
	"Discount Certificate",
	"Participation Note",
	"Range Accrual Note",
	"Reverse Convertible",
	"Basket Note",
	"Unknown",
)

_PRODUCT_ALIASES: Final[dict[str, str]] = {
	"accumulator": "Accumulator",
	"autocall": "Autocallable Note",
	"autocallable": "Autocallable Note",
	"barrier note": "Barrier Note",
	"bonus certificate": "Bonus Certificate",
	"capital protected": "Capital-Protected Note",
	"capital-protected": "Capital-Protected Note",
	"commodity linked": "Commodity-Linked Note",
	"commodity-linked": "Commodity-Linked Note",
	"covered call": "Covered Call",
	"credit linked": "Credit-Linked Note",
	"credit-linked": "Credit-Linked Note",
	"discount certificate": "Discount Certificate",
	"participation note": "Participation Note",
	"range accrual": "Range Accrual Note",
	"range accrual note": "Range Accrual Note",
	"reverse convertible": "Reverse Convertible",
	"basket note": "Basket Note",
}

_CONTRACT_PRODUCT_HINTS: Final[tuple[tuple[str, str], ...]] = (
	("autocallable", "Autocallable Note"),
	("autocall", "Autocallable Note"),
	("accumulator", "Accumulator"),
	("covered call", "Covered Call"),
	("reverse convertible", "Reverse Convertible"),
	("barrier note", "Barrier Note"),
	("bonus certificate", "Bonus Certificate"),
	("discount certificate", "Discount Certificate"),
	("range accrual", "Range Accrual Note"),
	("participation note", "Participation Note"),
	("credit-linked note", "Credit-Linked Note"),
	("commodity-linked note", "Commodity-Linked Note"),
	("capital-protected note", "Capital-Protected Note"),
	("basket note", "Basket Note"),
)


def normalize_product_type(model_output: str) -> str:
	"""Map free-form model output to one supported product type."""
	normalized_output = re.sub(r"\s+", " ", model_output.casefold()).strip()
	matches = [
		(match.start(), _PRODUCT_ALIASES[alias])
		for alias in _PRODUCT_ALIASES
		for match in re.finditer(rf"\b{re.escape(alias)}\b", normalized_output)
	]
	if matches:
		return max(matches, key=lambda match: match[0])[1]
	return "Unknown"


def build_classification_prompt(contract_text: str) -> str:
	"""Build the constrained prompt used to classify contract text."""
	if not contract_text.strip():
		raise ValueError("contract_text must not be empty")

	allowed_types = ", ".join(STRUCTURED_PRODUCT_TYPES[:-1])
	return (
		"Classify the following financial contract. Choose exactly one product type "
		f"from this list: {allowed_types}. If none applies, choose Unknown. "
		"Return only the product type name, with no explanation.\n\n"
		f"CONTRACT:\n{contract_text}\n\n"
		"ANSWER:"
	)


def infer_product_type_from_contract(contract_text: str) -> str:
	"""Use explicit product wording as a fallback for an unhelpful model response."""
	normalized_text = re.sub(r"\s+", " ", contract_text.casefold())
	for phrase, product_type in _CONTRACT_PRODUCT_HINTS:
		if re.search(rf"\b{re.escape(phrase)}\b", normalized_text):
			return product_type
	return "Unknown"


def classify_structured_product(
	contract_text: str,
	model_name: str = "Qwen/Qwen2.5-0.5B-Instruct",
	max_new_tokens: int = 128,
) -> str:
	"""Classify contract text using the configured local language model."""
	from app.local_llm import generate_text

	model_output = generate_text(
		model_name,
		build_classification_prompt(contract_text),
		max_new_tokens,
	)
	product_type = normalize_product_type(model_output)
	if product_type == "Unknown":
		return infer_product_type_from_contract(contract_text)
	return product_type
