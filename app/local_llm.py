from __future__ import annotations

import argparse
from collections.abc import Callable
from functools import lru_cache

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


class _TokenProgressStreamer:
	def __init__(self, callback: Callable[[int], None]) -> None:
		self.callback = callback
		self.prompt_seen = False
		self.token_count = 0

	def put(self, value: torch.Tensor) -> None:
		if not self.prompt_seen:
			self.prompt_seen = True
			return
		self.token_count += value.shape[-1]
		if self.token_count % 8 == 0:
			self.callback(self.token_count)

	def end(self) -> None:
		if self.token_count % 8:
			self.callback(self.token_count)


@lru_cache(maxsize=1)
def _load_model(model_name: str):
	tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
	model = AutoModelForCausalLM.from_pretrained(
		model_name,
		trust_remote_code=True,
		dtype=torch.float32,
		device_map=None,
	)
	model.to("cpu")
	model.eval()
	return tokenizer, model


def generate_text(
	model_name: str,
	prompt: str,
	max_new_tokens: int = 64,
	progress_callback: Callable[[int], None] | None = None,
) -> str:
	tokenizer, model = _load_model(model_name)

	if getattr(tokenizer, "chat_template", None):
		inputs = tokenizer.apply_chat_template(
			[{"role": "user", "content": prompt}],
			tokenize=True,
			add_generation_prompt=True,
			return_tensors="pt",
			return_dict=True,
		)
	else:
		inputs = tokenizer(prompt, return_tensors="pt")
	generation_options = {
		"max_new_tokens": max_new_tokens,
		"do_sample": False,
	}
	if progress_callback is not None:
		generation_options["streamer"] = _TokenProgressStreamer(progress_callback)
	with torch.no_grad():
		outputs = model.generate(**inputs, **generation_options)

	input_token_count = inputs["input_ids"].shape[-1]
	generated_tokens = outputs[0][input_token_count:]
	return tokenizer.decode(generated_tokens, skip_special_tokens=True)

def main() -> None:
	parser = argparse.ArgumentParser(description="Run a CPU-only local LLM example.")
	parser.add_argument(
		"--model",
		default="Qwen/Qwen2.5-0.5B-Instruct",
		help="Hugging Face model name to load on CPU.",
	)
	parser.add_argument(
		"--prompt",
		default="Write a one-sentence greeting from a CPU-only local model.",
		help="Prompt to generate from.",
	)
	parser.add_argument(
		"--max-new-tokens",
		type=int,
		default=64,
		help="Maximum number of tokens to generate.",
	)
	args = parser.parse_args()

	print(f"Loading {args.model} on CPU...")
	result = generate_text(args.model, args.prompt, args.max_new_tokens)
	print("\n=== Output ===\n")
	print(result)


if __name__ == "__main__":
	main()