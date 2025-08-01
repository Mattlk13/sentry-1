import posixpath
from collections.abc import Mapping
from timeit import default_timer as timer

import sentry_sdk
import symbolic.common

from sentry.constants import NATIVE_UNKNOWN_STRING
from sentry.interfaces.exception import upgrade_legacy_mechanism
from sentry.lang.native.registers import (
    REGISTERS_ARM,
    REGISTERS_ARM64,
    REGISTERS_X86,
    REGISTERS_X86_64,
)
from sentry.lang.native.utils import image_name
from sentry.utils.safe import get_path

REPORT_VERSION = "104"


class AppleCrashReport:
    def __init__(
        self, threads=None, context=None, debug_images=None, symbolicated=False, exceptions=None
    ):
        """
        Create an Apple crash report from the provided data.

        This constructor can modify the passed structures in place.
        """
        self.time_spent_parsing_addrs = 0.0
        self.threads = threads if threads else []
        self.context = context
        self.symbolicated = symbolicated
        self.exceptions = exceptions if exceptions else []
        self.image_addrs_to_vmaddrs = {}

        # Remove frames that don't have an `instruction_addr` and convert
        # sundry addresses into numbers.
        ts = self.exceptions + self.threads
        frame_keys = ["instruction_addr", "image_addr", "symbol_addr"]
        for t in ts:
            if stacktrace := t.get("stacktrace"):
                if frames := stacktrace.pop("frames", []):
                    new_frames = []
                    for frame in frames:
                        if frame.get("instruction_addr", None) is None:
                            continue
                        new_frame = {
                            key: self._parse_addr(frame[key]) if key in frame_keys else value
                            for key, value in frame.items()
                        }
                        new_frames.append(new_frame)
                    stacktrace["frames"] = new_frames

        # Remove debug images that don't have an `image_addr` and convert
        # `image_addr` and `image_vmaddr` to numbers.
        self.debug_images = []
        image_keys = ["image_addr", "image_vmaddr"]
        for image in debug_images or []:
            if image.get("image_addr", None) is None:
                continue
            new_image = {
                key: self._parse_addr(image[key]) if key in image_keys else value
                for key, value in image.items()
            }
            self.debug_images.append(new_image)

            # If the image has an `image_vmaddr`, save the mapping from
            # `image_addr` to `image_vmaddr`. This will be used in
            # `_get_slide_value`.
            if new_image.get("image_vmaddr") is not None:
                self.image_addrs_to_vmaddrs[new_image["image_addr"]] = new_image["image_vmaddr"]

    @sentry_sdk.trace
    def __str__(self):
        rv = []
        rv.append(self._get_meta_header())
        rv.append(self._get_exception_info())
        rv.append(self.get_threads_apple_string())
        rv.append(self._get_crashed_thread_registers())
        rv.append(self.get_binary_images_apple_string())
        current_span = sentry_sdk.get_current_span()

        if current_span:
            current_span.set_data("time_spent_parsing_addrs", self.time_spent_parsing_addrs)

        return "\n\n".join(rv) + "\n\nEOF"

    def _parse_addr(self, x: int | str | None) -> int:
        start = timer()
        res = symbolic.common.parse_addr(x)
        end = timer()
        self.time_spent_parsing_addrs += end - start
        return res

    @sentry_sdk.trace
    def _get_meta_header(self):
        return "OS Version: {} {} ({})\nReport Version: {}".format(
            get_path(self.context, "os", "name"),
            get_path(self.context, "os", "version"),
            get_path(self.context, "os", "build"),
            REPORT_VERSION,
        )

    def _get_register_index(self, register: str, register_map: Mapping[str, int]) -> int:
        return register_map.get(register[1:] if register.startswith("$") else register, -1)

    def _get_sorted_registers(
        self, registers: Mapping[str, str | None], register_map: Mapping[str, int]
    ) -> list[tuple[str, str | None]]:
        return [
            (register_name, registers.get(register_name))
            for register_name in sorted(
                registers.keys(), key=lambda name: self._get_register_index(name, register_map)
            )
        ]

    def _get_register_map_for_arch(self) -> tuple[str, bool, Mapping[str, int]]:
        arch = get_path(self.context, "device", "arch")

        if not isinstance(arch, str):
            return (NATIVE_UNKNOWN_STRING, False, {})

        if arch.startswith("x86_64"):
            return ("x86", True, REGISTERS_X86_64)
        if arch.startswith("x86"):
            return ("x86", False, REGISTERS_X86)
        if arch.startswith("arm64"):
            return ("ARM", True, REGISTERS_ARM64)
        if arch.startswith("arm"):
            return ("ARM", False, REGISTERS_ARM)
        return (arch, False, {})

    def _get_padded_hex_value(self, value: str) -> str:
        try:
            num_value = int(value, 16)
            padded_hex_value = f"{num_value:x}".rjust(16, "0")
            return "0x" + padded_hex_value
        except Exception:
            return value

    @sentry_sdk.trace
    def _get_crashed_thread_registers(self):
        rv = []
        exception = get_path(self.exceptions, 0)
        if not exception:
            return ""

        thread_id = exception.get("thread_id")
        crashed_thread_info = next(
            filter(lambda t: t.get("id") == thread_id, self.threads or []), None
        )
        crashed_thread_registers = get_path(crashed_thread_info, "stacktrace", "registers")

        if not isinstance(crashed_thread_registers, Mapping):
            return ""

        arch_label, is_64_bit, register_map = self._get_register_map_for_arch()

        rv.append(
            "Thread {} crashed with {} Thread State ({}-bit):".format(
                thread_id, arch_label, "64" if is_64_bit else "32"
            )
        )

        line = " "
        for i, register in enumerate(
            self._get_sorted_registers(crashed_thread_registers, register_map)
        ):
            if i != 0 and (i % 4 == 0):
                rv.append(line)
                line = " "

            register_name, register_value = register
            line += "{}: {}".format(
                register_name.rjust(5), self._get_padded_hex_value(register_value or "0x0")
            )

        if line != " ":
            rv.append(line)

        return "\n".join(rv)

    @sentry_sdk.trace
    def _get_exception_info(self):
        rv = []

        # We only have one exception at a time
        exception = get_path(self.exceptions, 0)
        if not exception:
            return ""

        mechanism = upgrade_legacy_mechanism(exception.get("mechanism")) or {}
        mechanism_meta = get_path(mechanism, "meta", default={})

        signal = get_path(mechanism_meta, "signal", "name")
        name = get_path(mechanism_meta, "mach_exception", "name")

        if name or signal:
            rv.append(
                "Exception Type: {}{}".format(
                    name or "Unknown", signal and (" (%s)" % signal) or ""
                )
            )

        exc_name = get_path(mechanism_meta, "signal", "code_name")
        exc_addr = get_path(mechanism, "data", "relevant_address")
        if exc_name:
            rv.append(
                "Exception Codes: %s%s"
                % (exc_name, exc_addr is not None and (" at %s" % exc_addr) or "")
            )

        if exception.get("thread_id") is not None:
            rv.append("Crashed Thread: %s" % exception["thread_id"])

        if exception.get("value"):
            rv.append("\nApplication Specific Information:\n%s" % exception["value"])

        return "\n".join(rv)

    @sentry_sdk.trace
    def get_threads_apple_string(self):
        rv = []
        exception = self.exceptions or []
        threads = self.threads or []
        for thread_info in exception + threads:
            thread_string = self.get_thread_apple_string(thread_info)
            if thread_string is not None:
                rv.append(thread_string)
        return "\n\n".join(rv)

    def get_thread_apple_string(self, thread_info):
        rv = []
        stacktrace = get_path(thread_info, "stacktrace")
        if stacktrace is None:
            return None

        if stacktrace:
            frames = get_path(stacktrace, "frames", filter=True)
            if frames:
                for i, frame in enumerate(reversed(frames)):
                    frame_string = self._convert_frame_to_apple_string(
                        frame=frame,
                        next=frames[len(frames) - i - 2] if i < len(frames) - 1 else None,
                        number=i,
                    )
                    if frame_string is not None:
                        rv.append(frame_string)

        if len(rv) == 0:
            return None  # No frames in thread, so we remove thread

        is_exception = bool(thread_info.get("mechanism"))
        thread_id = thread_info.get("id") or thread_info.get("thread_id") or "0"
        thread_name = thread_info.get("name")
        thread_name_string = " name: %s" % (thread_name) if thread_name else ""
        thread_crashed = thread_info.get("crashed") or is_exception
        thread_crashed_thread = " Crashed:" if thread_crashed else ""
        thread_string = f"Thread {thread_id}{thread_name_string}{thread_crashed_thread}\n"
        return thread_string + "\n".join(rv)

    def _convert_frame_to_apple_string(self, frame, next=None, number=0):
        frame_instruction_addr = frame["instruction_addr"]
        frame_image_addr = frame.get("image_addr", 0)
        slide_value = self._get_slide_value(frame_image_addr)
        instruction_addr = slide_value + frame_instruction_addr
        image_addr = slide_value + frame_image_addr
        offset = ""
        if frame.get("image_addr") is not None and (
            not self.symbolicated
            or (frame.get("function") or NATIVE_UNKNOWN_STRING) == NATIVE_UNKNOWN_STRING
        ):
            offset_value = instruction_addr - slide_value - frame.get("symbol_addr", 0)
            offset = f" + {offset_value}"
        symbol = hex(image_addr)
        if self.symbolicated:
            file = ""
            if frame.get("filename") and frame.get("lineno"):
                file = " ({}:{})".format(
                    posixpath.basename(frame.get("filename") or NATIVE_UNKNOWN_STRING),
                    frame["lineno"],
                )
            symbol = "{}{}".format(frame.get("function") or NATIVE_UNKNOWN_STRING, file)
            if next and frame_instruction_addr == next.get("instruction_addr", 0):
                symbol = "[inlined] " + symbol
        return "{}{}{}{}{}".format(
            str(number).ljust(4, " "),
            image_name(frame.get("package") or NATIVE_UNKNOWN_STRING).ljust(32, " "),
            hex(instruction_addr).ljust(20, " "),
            symbol,
            offset,
        )

    def _get_slide_value(self, image_addr):
        return self.image_addrs_to_vmaddrs.get(image_addr, 0)

    @sentry_sdk.trace
    def get_binary_images_apple_string(self):
        # We don't need binary images on symbolicated crashreport
        if self.symbolicated or not self.debug_images:
            return ""
        binary_images = map(
            lambda i: self._convert_debug_meta_to_binary_image_row(debug_image=i),
            sorted(
                self.debug_images,
                key=lambda i: i["image_addr"],
            ),
        )
        return "Binary Images:\n" + "\n".join(binary_images)

    def _convert_debug_meta_to_binary_image_row(self, debug_image):
        slide_value = debug_image.get("image_vmaddr", 0)
        image_addr = debug_image["image_addr"] + slide_value
        return "{} - {} {} {}  <{}> {}".format(
            hex(image_addr),
            hex(image_addr + debug_image["image_size"] - 1),
            image_name(debug_image.get("code_file") or NATIVE_UNKNOWN_STRING),
            get_path(self.context, "device", "arch") or NATIVE_UNKNOWN_STRING,
            debug_image.get("debug_id").replace("-", "").lower(),
            debug_image.get("code_file") or NATIVE_UNKNOWN_STRING,
        )
