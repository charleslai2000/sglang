import json
import logging
import re
from typing import Any, List, Optional

from sglang.srt.entrypoints.openai.protocol import Tool
from sglang.srt.function_call.base_format_detector import BaseFormatDetector
from sglang.srt.function_call.core_types import (
    StreamingParseResult,
    ToolCallItem,
    _GetInfoFunc,
)
from sglang.srt.function_call.utils import (
    get_schema_properties,
    infer_type_from_json_schema,
    safe_literal_eval,
)

logger = logging.getLogger(__name__)


class Qwen3CoderDetector(BaseFormatDetector):
    def __init__(self):
        super().__init__()

        # Sentinel tokens
        self.tool_call_start_token: str = "<tool_call>"
        self.tool_call_end_token: str = "</tool_call>"
        self.tool_call_prefix: str = "<function="
        self.function_end_token: str = "</function>"
        self.parameter_prefix: str = "<parameter="
        self.parameter_end_token: str = "</parameter>"

        # Regex for non-streaming fallback
        self.tool_call_regex = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
        self.tool_call_function_regex = re.compile(
            r"<function=(.*?)</function>|<function=(.*)$", re.DOTALL
        )
        self.tool_call_parameter_regex = re.compile(
            r"<parameter=(.*?)(?:</parameter>|(?=<parameter=)|(?=</function>)|$)",
            re.DOTALL,
        )

        # Streaming State
        # Base class already initializes _buffer, we just use it directly
        # No need to check with hasattr - we control the lifecycle through inheritance

        # Index pointing to the next character to be processed in buffer.
        # Delay-commit framing: a call is only committed once its framing is
        # complete. Unresolved bytes stay at ``parsed_pos`` in ``_buffer`` (see
        # ``parse_streaming_increment``) and are released as normal text by
        # ``finish`` when the stream ends before framing completes.
        self.parsed_pos: int = 0

        # Locates a complete ``<function=NAME>`` opening tag inside a block.
        self.function_tag_regex = re.compile(r"<function=([^>]*)>")

    def has_tool_call(self, text: str) -> bool:
        return self.tool_call_start_token in text

    def _get_arguments_config(
        self, func_name: str, tools: Optional[list[Tool]]
    ) -> dict:
        """Extract argument configuration for a function."""
        if tools is None:
            return {}
        for config in tools:
            try:
                config_type = config.type
                config_function = config.function
                config_function_name = config_function.name
            except AttributeError:
                continue

            if config_type == "function" and config_function_name == func_name:
                try:
                    params = config_function.parameters
                except AttributeError:
                    return {}

                if isinstance(params, dict):
                    properties = get_schema_properties(params)
                    if properties or "properties" in params:
                        return properties
                    return params
                else:
                    return {}
        logger.warning(f"Tool '{func_name}' is not defined in the tools list.")
        return {}

    def _get_param_type(self, param_schema: Any) -> str:
        """Infer the parser conversion type from a JSON schema parameter."""
        inferred_type = infer_type_from_json_schema(param_schema)
        if inferred_type is None:
            return "string"
        return str(inferred_type).strip().lower()

    def _convert_param_value(
        self, param_value: str, param_name: str, param_config: dict, func_name: str
    ) -> Any:
        """Convert parameter value based on its type in the schema."""
        # Handle null value for any type
        if param_value.lower() == "null":
            return None

        if param_name not in param_config:
            if param_config != {}:
                logger.warning(
                    f"Parsed parameter '{param_name}' is not defined in the tool "
                    f"parameters for tool '{func_name}', directly returning the string value."
                )
            return param_value

        param_type = self._get_param_type(param_config[param_name])
        if param_type in ["string", "str", "text", "varchar", "char", "enum"]:
            return param_value
        elif (
            param_type.startswith("int")
            or param_type.startswith("uint")
            or param_type.startswith("long")
            or param_type.startswith("short")
            or param_type.startswith("unsigned")
        ):
            try:
                param_value = int(param_value)
            except Exception:
                logger.warning(
                    f"Parsed value '{param_value}' of parameter '{param_name}' is not an integer in tool "
                    f"'{func_name}', degenerating to string."
                )
            return param_value
        elif param_type.startswith("num") or param_type.startswith("float"):
            try:
                maybe_convert = (
                    False if "." in param_value or "e" in param_value.lower() else True
                )
                param_value: float = float(param_value)
                if maybe_convert and param_value.is_integer():
                    param_value = int(param_value)
            except Exception:
                logger.warning(
                    f"Parsed value '{param_value}' of parameter '{param_name}' is not a float in tool "
                    f"'{func_name}', degenerating to string."
                )
            return param_value
        elif param_type in ["boolean", "bool", "binary"]:
            param_value = param_value.lower()
            if param_value not in ["true", "false"]:
                logger.warning(
                    f"Parsed value '{param_value}' of parameter '{param_name}' is not a boolean (`true` of `false`) in tool '{func_name}', degenerating to false."
                )
            return param_value == "true"
        else:
            if (
                param_type in ["object", "array", "arr"]
                or param_type.startswith("dict")
                or param_type.startswith("list")
            ):
                try:
                    param_value = json.loads(param_value)
                    return param_value
                except Exception:
                    logger.warning(
                        f"Parsed value '{param_value}' of parameter '{param_name}' cannot be parsed with json.loads in tool "
                        f"'{func_name}', will try other methods to parse it."
                    )
            try:
                param_value = safe_literal_eval(param_value)
            except Exception:
                logger.warning(
                    f"Parsed value '{param_value}' of parameter '{param_name}' cannot be converted via Python `ast.literal_eval()` in tool '{func_name}', degenerating to string."
                )
            return param_value

    @staticmethod
    def _is_well_formed_name(name: str) -> bool:
        """A committed call's name is non-empty and holds no framing chars."""
        return bool(name) and not any(ch in name for ch in "<>\t\r\n ")

    def detect_and_parse(self, text: str, tools: List[Tool]) -> StreamingParseResult:
        """One-shot parsing for non-streaming scenarios."""
        if self.tool_call_start_token not in text:
            return StreamingParseResult(normal_text=text)

        calls = []
        try:
            # Simple cleanup of the text to find tool calls
            # Note: This is a simplified regex approach consistent with vLLM
            raw_tool_calls = self.tool_call_regex.findall(text)
            if not raw_tool_calls:
                # Fallback: maybe the whole text is inside the tag or tags are stripped
                if self.tool_call_prefix in text:
                    raw_tool_calls = [text]

            tool_idx = 0
            for tool_content in raw_tool_calls:
                # Find function calls
                funcs = self.tool_call_function_regex.findall(tool_content)
                for func_match in funcs:
                    func_body = func_match[0] or func_match[1] or ""
                    if ">" not in func_body:
                        continue

                    name_end = func_body.index(">")
                    func_name = func_body[:name_end]
                    # A malformed/empty name (e.g. an unclosed ``<function=``
                    # whose body swallowed a later ``>``) must not be emitted
                    # as a call.
                    if not self._is_well_formed_name(func_name):
                        continue
                    params_str = func_body[name_end + 1 :]

                    param_config = self._get_arguments_config(func_name, tools)
                    parsed_params = {}

                    for p_match in self.tool_call_parameter_regex.findall(params_str):
                        if ">" not in p_match:
                            continue
                        p_idx = p_match.index(">")
                        p_name = p_match[:p_idx]
                        p_val = p_match[p_idx + 1 :]
                        # Remove prefixing and trailing \n
                        if p_val.startswith("\n"):
                            p_val = p_val[1:]
                        if p_val.endswith("\n"):
                            p_val = p_val[:-1]

                        parsed_params[p_name] = self._convert_param_value(
                            p_val, p_name, param_config, func_name
                        )

                    calls.append(
                        ToolCallItem(
                            tool_index=tool_idx,
                            name=func_name,
                            parameters=json.dumps(parsed_params, ensure_ascii=False),
                        )
                    )
                    tool_idx += 1

            # Determine normal text (text before the first tool call)
            start_idx = text.find(self.tool_call_start_token)
            if start_idx == -1:
                start_idx = text.find(self.tool_call_prefix)
            normal_text = text[:start_idx] if start_idx > 0 else ""

            return StreamingParseResult(normal_text=normal_text, calls=calls)

        except Exception as e:
            logger.error(f"Error in detect_and_parse: {e}")
            return StreamingParseResult(normal_text=text)

    def _parse_parameter_values(
        self, body: str, tools: List[Tool], func_name: str
    ) -> tuple:
        """Parse ``<parameter=NAME>VALUE`` entries out of a function body.

        Values terminate at ``</parameter>``, the next ``<parameter=``,
        ``</function>``, or the end of the body (R3). Returns ``(params,
        leftovers)`` where leftovers are body bytes not part of a usable
        parameter and must be released as ordinary content.
        """
        params = {}
        leftovers: List[str] = []
        param_config = self._get_arguments_config(func_name, tools)
        pos = 0
        length = len(body)

        while pos < length:
            tag_idx = body.find(self.parameter_prefix, pos)
            if tag_idx == -1:
                leftovers.append(body[pos:])
                break
            if tag_idx > pos:
                leftovers.append(body[pos:tag_idx])

            name_end = body.find(">", tag_idx + len(self.parameter_prefix))
            if name_end == -1:
                # Malformed opening tag: no usable value.
                leftovers.append(body[tag_idx:])
                break

            param_name = body[tag_idx + len(self.parameter_prefix) : name_end]
            value_start = name_end + 1

            candidates = []
            end_param = body.find(self.parameter_end_token, value_start)
            if end_param != -1:
                candidates.append((end_param, len(self.parameter_end_token)))
            next_param = body.find(self.parameter_prefix, value_start)
            if next_param != -1:
                candidates.append((next_param, 0))
            end_func = body.find(self.function_end_token, value_start)
            if end_func != -1:
                candidates.append((end_func, 0))

            if candidates:
                value_end, term_len = min(candidates, key=lambda x: x[0])
                raw_value = body[value_start:value_end]
                pos = value_end + term_len
            else:
                raw_value = body[value_start:]
                pos = length

            if not self._is_well_formed_name(param_name):
                leftovers.append(body[tag_idx:pos])
                continue

            if raw_value.startswith("\n"):
                raw_value = raw_value[1:]
            if raw_value.endswith("\n"):
                raw_value = raw_value[:-1]
            params[param_name] = self._convert_param_value(
                raw_value, param_name, param_config, func_name
            )

        return params, leftovers

    def _parse_committed_block(
        self, block: str, tools: List[Tool]
    ) -> Optional[tuple]:
        """Parse one completely framed call.

        ``block`` is the text of a closed ``<tool_call>`` block (or a bare
        ``<function=...>...</function>`` region). Returns
        ``(name, params, leftovers)`` or ``None`` when the inner framing is not
        usable, in which case the caller releases the bytes as content.
        """
        match = self.function_tag_regex.search(block)
        if match is None:
            return None

        func_name = match.group(1)
        if not self._is_well_formed_name(func_name):
            return None

        prefix = block[: match.start()]
        after = block[match.end() :]
        func_end = after.find(self.function_end_token)
        if func_end == -1:
            body, tail = after, ""
        else:
            body = after[:func_end]
            tail = after[func_end + len(self.function_end_token) :]

        params, leftovers = self._parse_parameter_values(body, tools, func_name)
        # Independently framed bytes around the body must not be dropped.
        if prefix.strip():
            leftovers.insert(0, prefix)
        if tail.strip():
            leftovers.append(tail)
        return func_name, params, leftovers

    def parse_streaming_increment(
        self, new_text: str, tools: List[Tool]
    ) -> StreamingParseResult:
        """Delay-commit streaming parser.

        A call is only committed once its complete framing has been observed:
        an enclosed call through ``</tool_call>``, or a bare ``<function=...>``
        through ``</function>``. Until then the bytes are held in ``_buffer``
        at ``parsed_pos``. This guarantees every committed call has a
        non-negative, strictly increasing index, a well-formed name and a
        complete JSON object, and that malformed/orphan fragments never become
        calls. Whatever is still held when the stream ends is released as
        ordinary content by ``finish``.
        """
        if new_text:
            self._buffer += new_text

        if not self._buffer:
            return StreamingParseResult()

        calls: List[ToolCallItem] = []
        normal_text_chunks: List[str] = []
        known_tags = (
            self.tool_call_start_token,
            self.tool_call_end_token,
            self.tool_call_prefix,
            self.function_end_token,
            self.parameter_prefix,
            self.parameter_end_token,
        )

        while self.parsed_pos < len(self._buffer):
            current_slice = self._buffer[self.parsed_pos :]

            # 1. Enclosed call: hold until the block's ``</tool_call>``.
            if current_slice.startswith(self.tool_call_start_token):
                block_start = self.parsed_pos + len(self.tool_call_start_token)
                block_end = self._buffer.find(self.tool_call_end_token, block_start)
                if block_end == -1:
                    break  # framing incomplete: keep holding
                block_stop = block_end + len(self.tool_call_end_token)
                parsed = self._parse_committed_block(
                    self._buffer[block_start:block_end], tools
                )
                if parsed is None:
                    normal_text_chunks.append(
                        self._buffer[self.parsed_pos:block_stop]
                    )
                else:
                    func_name, params, leftovers = parsed
                    self.current_tool_id += 1
                    calls.append(
                        ToolCallItem(
                            tool_index=self.current_tool_id,
                            name=func_name,
                            parameters=json.dumps(params, ensure_ascii=False),
                        )
                    )
                    normal_text_chunks.extend(lo for lo in leftovers if lo.strip())
                self.parsed_pos = block_stop
                continue

            # 2. Bare call fallback (no ``<tool_call>``): hold until
            # ``</function>``.
            if current_slice.startswith(self.tool_call_prefix):
                func_end = self._buffer.find(
                    self.function_end_token, self.parsed_pos
                )
                if func_end == -1:
                    break  # framing incomplete: keep holding
                func_stop = func_end + len(self.function_end_token)
                parsed = self._parse_committed_block(
                    self._buffer[self.parsed_pos:func_stop], tools
                )
                if parsed is None:
                    normal_text_chunks.append(
                        self._buffer[self.parsed_pos:func_stop]
                    )
                else:
                    func_name, params, leftovers = parsed
                    self.current_tool_id += 1
                    calls.append(
                        ToolCallItem(
                            tool_index=self.current_tool_id,
                            name=func_name,
                            parameters=json.dumps(params, ensure_ascii=False),
                        )
                    )
                    normal_text_chunks.extend(lo for lo in leftovers if lo.strip())
                self.parsed_pos = func_stop
                continue

            # 3. Ordinary content, or a strict prefix of a framing tag.
            next_open_angle = current_slice.find("<")
            if next_open_angle == -1:
                normal_text_chunks.append(current_slice)
                self.parsed_pos = len(self._buffer)
                break
            if next_open_angle > 0:
                normal_text_chunks.append(current_slice[:next_open_angle])
                self.parsed_pos += next_open_angle
                continue
            if any(
                len(current_slice) < len(tag) and tag.startswith(current_slice)
                for tag in known_tags
            ):
                break  # wait for the rest of the tag
            normal_text_chunks.append("<")
            self.parsed_pos += 1

        # Keep only the unconsumed (held) suffix; drop the consumed prefix.
        if self.parsed_pos > 0:
            self._buffer = self._buffer[self.parsed_pos :]
            self.parsed_pos = 0

        normal_text = "".join(normal_text_chunks) if normal_text_chunks else ""
        return StreamingParseResult(calls=calls, normal_text=normal_text)

    def finish(self, tools: List[Tool]) -> StreamingParseResult:
        """Release uncommitted held text as ordinary content at stream end.

        Because commit is delayed until framing completes, whatever is still
        held when the stream ends is framing-incomplete and must never be
        repaired into a call (R4).
        """
        held_text = self._buffer[self.parsed_pos :]
        self._buffer = ""
        self.parsed_pos = 0
        return StreamingParseResult(normal_text=held_text)

    def supports_structural_tag(self) -> bool:
        return True

    def structure_info(self) -> _GetInfoFunc:
        raise NotImplementedError

    def get_structural_tag_name(self) -> str:
        return "qwen_3_coder"
