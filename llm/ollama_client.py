from __future__ import annotations

import json
import requests

from typing import Any

from core.tool_call import ToolCall
from core.tool_registry import ToolRegistry
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)


class OllamaClient:

    def __init__(
        self,
        host: str,
        model: str,
        timeout: int = 120,
    ) -> None:

        self.host = host.rstrip("/")

        self.model = model

        self.timeout = timeout

    # ==================================================
    # HTTP helper
    # ==================================================

    def _post(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        response = requests.post(
            f"{self.host}{endpoint}",
            json=payload,
            timeout=self.timeout,
        )

        response.raise_for_status()

        return response.json()

    # ==================================================
    # Generate API
    # ==================================================

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        if system_prompt:
            payload["system"] = system_prompt

        response = self._post(
            "/api/generate",
            payload,
        )

        return response["response"]

    # ==================================================
    # Chat API
    # ==================================================

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:

        response = self._post(
            "/api/chat",
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
            },
        )

        return response["message"]["content"]

    # ==================================================
    # Tool selection
    # ==================================================

    def request_tool_call(
        self,
        messages: list[dict[str, str]],
        registry: ToolRegistry,
    ) -> ToolCall:

        tools_description = (
            self._render_tools_for_prompt(
                registry
            )
        )

        system_message = {
            "role": "system",
            "content": (
                "You are an autonomous agent.\n\n"
                "You may choose one tool to call.\n\n"
                "Available tools:\n\n"
                f"{tools_description}\n\n"
                "Respond ONLY with valid JSON.\n\n"
                "If a tool must be executed:\n\n"
                "{\n"
                '  "tool": "tool_name",\n'
                '  "arguments": {\n'
                '    "param": "value"\n'
                "  }\n"
                "}\n\n"
                "If no tool is required:\n\n"
                "{\n"
                '  "tool": null,\n'
                '  "arguments": {}\n'
                "}\n"
            ),
        }

        full_messages = [
            system_message,
            *messages,
        ]

        response = self.chat(
            full_messages
        )

        return self._parse_tool_call(
            response
        )

    # ==================================================
    # Tool rendering
    # ==================================================

    def _render_tools_for_prompt(
        self,
        registry: ToolRegistry,
    ) -> str:

        sections: list[str] = []

        for tool in (
            registry.list_definitions()
        ):

            sections.append(
                self._render_tool(tool)
            )

        if not sections:
            return "No tools."

        return "\n\n".join(
            sections
        )

    def _render_tool(
        self,
        tool: ToolDefinition,
    ) -> str:

        lines = [
            f"Name: {tool.name}",
            f"Category: {tool.category}",
            (
                f"Description: "
                f"{tool.description}"
            ),
        ]

        if tool.parameters:

            lines.append(
                "Parameters:"
            )

            for param in (
                tool.parameters
            ):

                lines.append(
                    self._render_parameter(
                        param
                    )
                )

        return "\n".join(lines)

    @staticmethod
    def _render_parameter(
        param: ToolParameter,
    ) -> str:

        required = (
            "required"
            if param.required
            else "optional"
        )

        return (
            f"- {param.name} "
            f"({param.param_type}) "
            f"[{required}] "
            f": {param.description}"
        )

    # ==================================================
    # JSON parsing
    # ==================================================

    def _parse_tool_call(
        self,
        response_text: str,
    ) -> ToolCall:

        response_text = response_text.strip()

        #
        # Tentativo 1:
        # JSON puro
        #

        try:

            return self._tool_call_from_json(
                response_text
            )

        except Exception:
            pass

        #
        # Tentativo 2:
        # blocco markdown ```json
        #

        markdown_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            response_text,
            flags=re.DOTALL,
        )

        if markdown_match:

            try:

                return (
                    self._tool_call_from_json(
                        markdown_match.group(1)
                    )
                )

            except Exception:
                pass

        #
        # Tentativo 3:
        # primo oggetto JSON presente
        #

        json_candidate = (
            self._extract_first_json_object(
                response_text
            )
        )

        if json_candidate:

            try:

                return (
                    self._tool_call_from_json(
                        json_candidate
                    )
                )

            except Exception:
                pass

        raise RuntimeError(
            "Unable to extract a valid "
            "ToolCall from model response.\n\n"
            f"{response_text}"
        )


    def _tool_call_from_json(
        self,
        text: str,
    ) -> ToolCall:

        data = json.loads(text)

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "JSON root must be an object"
            )

        return ToolCall(
            tool=data.get(
                "tool",
            ),
            arguments=data.get(
                "arguments",
                {},
            ),
        )
        
        
    def _extract_first_json_object(
        self,
        text: str,
    ) -> str | None:

        start = text.find("{")

        while start != -1:

            depth = 0

            for i in range(
                start,
                len(text),
            ):

                char = text[i]

                if char == "{":
                    depth += 1

                elif char == "}":

                    depth -= 1

                    if depth == 0:

                        candidate = (
                            text[start:i + 1]
                        )

                        try:

                            json.loads(
                                candidate
                            )

                            return candidate

                        except Exception:
                            break

            start = text.find(
                "{",
                start + 1,
            )

        return None        

    def _tool_call_from_json(
        self,
        text: str,
    ) -> ToolCall:

        data = json.loads(text)

        tool = data.get("tool")

        arguments = data.get(
            "arguments",
            {},
        )

        if tool is not None and not isinstance(
            tool,
            str,
        ):
            raise ValueError(
                "'tool' must be string or null"
            )

        if not isinstance(
            arguments,
            dict,
        ):
            raise ValueError(
                "'arguments' must be an object"
            )

        return ToolCall(
            tool=tool,
            arguments=arguments,
        )        