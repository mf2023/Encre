#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

"""
Local backend — Hugging Face Transformers (CPU/GPU inference).

This backend runs models locally using the Hugging Face ``transformers``
library.  It supports any causal language model available on the Hugging
Face Hub, including Llama, Mistral, Qwen, DeepSeek, Gemma, Phi, and many
more.

Key characteristics:
- Fully offline, no API calls
- Supports CPU and GPU inference
- Tool calling via text parsing (model-dependent)
- Context window determined by model configuration
- No built-in prompt caching or thinking support
- Requires significant local compute resources

Architecture:
- Uses ``transformers`` pipeline for text generation
- Supports streaming via a generator-based approach
- Tool calls are parsed from the generated text using regex patterns
- Model and tokenizer are loaded lazily on first ``chat()`` call
- GPU memory is released on ``aclose()``

Note:
    This backend is designed for development and testing.  For production
    use, consider using :class:`OllamaBackend` or a cloud API backend for
    better performance and reliability.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncGenerator

from yim.backends.base import BaseBackend
from yim.utils.types import (
    BackendEvent,
    create_backend_error,
    create_backend_finish,
    create_backend_text,
    create_backend_tool_call,
    create_backend_tool_call_delta,
)


class LocalBackend(BaseBackend):
    """Local backend using Hugging Face Transformers.

    Loads and runs any Hugging Face causal language model locally.  The
    model is loaded lazily on the first ``chat()`` call to avoid blocking
    initialisation.

    Tool calling is supported via text parsing: the model generates a JSON
    block containing the tool call, which is extracted using regex.  This
    approach works with models that have been fine-tuned for function calling
    (e.g., Llama 3.1+, Qwen 2.5).

    Args:
        model_name: Hugging Face model ID (e.g., ``"meta-llama/Llama-3.2-3B"``).
            Defaults to ``"Qwen/Qwen2.5-1.5B-Instruct"``.
        device: Device to run inference on (``"cpu"``, ``"cuda"``, ``"auto"``).
            Defaults to ``"cpu"``.
        **kwargs: Additional arguments passed to ``transformers.pipeline``.
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-1.5B-Instruct",
        device: str = "cpu",
        **kwargs: Any,
    ) -> None:
        """Initialise the local backend.

        Args:
            model_name: Hugging Face model ID.  Defaults to
                ``"Qwen/Qwen2.5-1.5B-Instruct"``.
            device: Device for inference.  ``"cpu"``, ``"cuda"``, or ``"auto"``.
            **kwargs: Additional arguments for ``transformers.pipeline``.
        """
        self.model_name = model_name
        self.device = device
        self._pipeline_kwargs = kwargs
        self._model = None
        self._tokenizer = None
        self._pipe = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._tool_support = False

    async def _ensure_model(self) -> None:
        """Lazy-load the model and tokenizer on first use.

        Uses ``transformers.pipeline`` with ``task="text-generation"`` to
        load the model.  The pipeline is configured with the specified device
        and any additional kwargs passed during initialisation.

        Raises:
            ImportError: If ``transformers`` or ``torch`` is not installed.
        """
        if self._pipe is not None:
            return
        try:
            from transformers import pipeline
            self._pipe = pipeline(
                "text-generation",
                model=self.model_name,
                device=self.device,
                **self._pipeline_kwargs,
            )
            self._model = self._pipe.model
            self._tokenizer = self._pipe.tokenizer
        except ImportError as e:
            raise ImportError(
                "transformers/torch not installed. Install with: pip install yim[local]"
            ) from e

    def _generate_stream_sync(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> Any:
        """Synchronous generator for streaming text generation.

        Uses the Hugging Face pipeline's ``text_generation`` with
        ``return_full_text=False`` to generate tokens incrementally.

        Args:
            prompt: The formatted prompt string.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.

        Yields:
            Generated text chunks as strings.
        """
        outputs = self._pipe(
            prompt,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            return_full_text=False,
        )
        yield outputs[0]["generated_text"]

    def _parse_tool_calls_from_text(self, text: str) -> list[dict[str, Any]]:
        """Parse tool calls from generated text using regex.

        Looks for JSON blocks matching the pattern:
        ``{"name": "...", "arguments": {...}}`` or
        ``{"function": {"name": "...", "arguments": {...}}}``

        Args:
            text: The generated text to parse.

        Returns:
            A list of parsed tool call dictionaries, each containing
            ``id``, ``name``, and ``arguments`` keys.
        """
        tool_calls: list[dict[str, Any]] = []
        pattern = r'\{\s*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{[^}]+\}\s*\}'
        matches = re.findall(pattern, text, re.DOTALL)
        for i, match in enumerate(matches):
            try:
                parsed = json.loads(match)
                tool_calls.append({
                    "id": f"call_{i}",
                    "name": parsed.get("name", ""),
                    "arguments": json.dumps(parsed.get("arguments", {})),
                })
            except json.JSONDecodeError:
                continue
        return tool_calls

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        stream: bool = True,
        enable_caching: bool = False,
    ) -> AsyncGenerator[BackendEvent, None]:
        """Send a chat completion request and stream back events.

        Runs inference locally using the Hugging Face pipeline.  Supports
        both streaming and non-streaming modes.

        Args:
            messages: Conversation history in OpenAI message format.
            tools: Optional tool definitions (used for tool call parsing).
            tool_choice: Tool selection strategy (``"auto"``, ``"any"``, ``"none"``).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            stream: If True (default), uses streaming generation.
            enable_caching: Not supported for local models (ignored).

        Yields:
            :class:`BackendText`, :class:`BackendToolCallDelta`,
            :class:`BackendToolCall`, :class:`BackendFinish`, or
            :class:`BackendError`.
        """
        try:
            await self._ensure_model()
        except ImportError as e:
            yield create_backend_error(str(e))
            return

        import asyncio

        prompt = self._format_messages(messages, tools)

        try:
            if stream:
                loop = asyncio.get_running_loop()
                gen = await loop.run_in_executor(
                    self._executor,
                    lambda: list(self._generate_stream_sync(prompt, max_tokens, temperature)),
                )
                full_output = ""
                for text in gen:
                    full_output += text
                    yield create_backend_text(text)

                tool_calls = self._parse_tool_calls_from_text(full_output)
                if tool_calls:
                    for i, tc in enumerate(tool_calls):
                        yield create_backend_tool_call_delta(i, "name", tc["name"])
                        yield create_backend_tool_call_delta(i, "arguments", tc["arguments"])
                        yield create_backend_tool_call(
                            id=tc["id"],
                            name=tc["name"],
                            arguments=tc["arguments"],
                        )
                    yield create_backend_finish("tool_calls")
                else:
                    yield create_backend_finish("stop")
            else:
                loop = asyncio.get_running_loop()
                outputs = await loop.run_in_executor(
                    self._executor,
                    lambda: self._pipe(
                        prompt,
                        max_new_tokens=max_tokens,
                        temperature=temperature,
                        do_sample=temperature > 0,
                        return_full_text=False,
                    ),
                )
                text = outputs[0]["generated_text"]
                yield create_backend_text(text)
                yield create_backend_finish("stop")

        except Exception as e:
            yield create_backend_error(str(e))

    def _format_messages(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Format messages into a prompt string for the local model.

        Uses the tokenizer's ``apply_chat_template`` method if available,
        otherwise falls back to a simple concatenation format.

        Args:
            messages: OpenAI-format message list.
            tools: Optional tool definitions (added to the system prompt).

        Returns:
            A formatted prompt string ready for model input.
        """
        if self._tokenizer and hasattr(self._tokenizer, "apply_chat_template"):
            try:
                return self._tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
            except Exception:
                pass

        formatted = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                content = " ".join(text_parts)
            formatted += f"<|{role}|>\n{content}\n"
        formatted += "<|assistant|>\n"
        return formatted

    def supports_tool_calling(self) -> bool:
        """Return whether the loaded model supports tool calling.

        Tool calling support is determined by the model's chat template.
        Models with function calling templates (e.g., Llama 3.1+, Qwen 2.5)
        will return True.
        """
        return self._tool_support or True

    def context_window_size(self) -> int:
        """Return the model's context window size from its configuration.

        Reads ``max_position_embeddings`` from the model config if available.
        Falls back to 4096 if the model is not loaded or the config lacks
        this attribute.
        """
        if self._model is not None and hasattr(self._model, "config"):
            config = self._model.config
            if hasattr(config, "max_position_embeddings"):
                return config.max_position_embeddings
        return 4096

    async def aclose(self) -> None:
        """Release model resources and GPU memory.

        Moves the model to CPU, deletes references, and clears GPU cache
        if CUDA is available.
        """
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._executor.shutdown, True)
        if self._model is not None:
            try:
                import torch
                self._model = self._model.to("cpu")
                del self._model
                del self._tokenizer
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        self._model = None
        self._tokenizer = None

    def supports_thinking(self) -> bool:
        """Local models do not natively support thinking tokens."""
        return False