"""
This file is part of CdpUnpack.

Copyright (C) 2026 Peter Grønbæk Andersen <peter@grnbk.io>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json
import struct
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .error import CdpError
from .lzss import decompress_lzss


@dataclass
class Tag:
    """A parsed CDP tag and its type-specific value."""
    tag_type: int
    name: str

    children: Optional[List["Tag"]] = None
    values: Optional[list] = None
    value: Optional[str] = None
    data: Optional[bytes] = None
    user_id: Optional[int] = None
    content_id: Optional[int] = None


@dataclass
class CdpDocument:
    """A parsed CDP document containing its header fields and top-level tags."""
    version: int
    reserved: int
    body_length: int
    tags: List[Tag]


def read_uint32(data: bytes, offset: int) -> int:
    """
    Read an unsigned 32-bit little-endian integer.

    Args:
        data: Binary data to read from.
        offset: Byte offset of the integer.

    Returns:
        The decoded integer.

    Raises:
        CdpError: If the data is truncated.
    """
    if offset + 4 > len(data):
        raise CdpError("truncated uint32")

    return struct.unpack_from("<I", data, offset)[0]


def read_int32(data: bytes, offset: int) -> int:
    """
    Read a signed 32-bit little-endian integer.

    Args:
        data: Binary data to read from.
        offset: Byte offset of the integer.

    Returns:
        The decoded integer.

    Raises:
        CdpError: If the data is truncated.
    """
    if offset + 4 > len(data):
        raise CdpError("truncated int32")

    return struct.unpack_from("<i", data, offset)[0]


def read_float32(data: bytes, offset: int) -> float:
    """
    Read a 32-bit little-endian floating-point value.

    Args:
        data: Binary data to read from.
        offset: Byte offset of the value.

    Returns:
        The decoded value.

    Raises:
        CdpError: If the data is truncated.
    """
    if offset + 4 > len(data):
        raise CdpError("truncated float32")

    return struct.unpack_from("<f", data, offset)[0]


def parse_tags(data: bytes, offset: int, end: int) -> List[Tag]:
    """
    Parse CDP tags from a section of binary data.

    Args:
        data: Binary CDP data.
        offset: Start of the tag data.
        end: End of the tag data.

    Returns:
        The parsed tags.
    """
    tags: List[Tag] = []

    while offset + 6 <= end:
        tag_start = offset

        tag_len = read_uint32(data, offset)
        offset += 4

        if offset >= end:
            break

        name_len = data[offset]
        offset += 1

        if name_len > 0:
            if offset + name_len > end:
                break

            name_bytes = data[offset : offset + name_len - 1]
            name = name_bytes.decode("utf-8", errors="replace")

            offset += name_len

        else:
            name = ""

        if offset >= end:
            break

        tag_type = data[offset]
        offset += 1

        value_end = tag_start + 4 + tag_len

        if value_end < tag_start or value_end > end:
            break

        if offset > value_end:
            break

        value_data = data[offset:value_end]

        if tag_type == 0x00:
            children = parse_tags(data, offset, value_end)

            tag = Tag(
                tag_type=tag_type,
                name=name,
                children=children,
            )

        elif tag_type == 0x01:
            values = []
            pos = 0

            while pos + 4 <= len(value_data):
                values.append(read_int32(value_data, pos))
                pos += 4

            tag = Tag(
                tag_type=tag_type,
                name=name,
                values=values,
            )

        elif tag_type == 0x02:
            values = []
            pos = 0

            while pos + 4 <= len(value_data):
                values.append(read_float32(value_data, pos))
                pos += 4

            tag = Tag(
                tag_type=tag_type,
                name=name,
                values=values,
            )

        elif tag_type == 0x03:
            string_bytes = value_data.split(b"\0", 1)[0]
            value = string_bytes.decode("utf-8", errors="replace")

            tag = Tag(
                tag_type=tag_type,
                name=name,
                value=value,
            )

        elif tag_type == 0x04:
            tag = Tag(
                tag_type=tag_type,
                name=name,
                data=bytes(value_data),
            )

        elif tag_type == 0x05:
            tag = Tag(
                tag_type=tag_type,
                name=name,
            )

        elif tag_type == 0x0D:
            user_id = read_uint32(value_data, 0) if len(value_data) >= 4 else 0
            content_id = read_int32(value_data, 4) if len(value_data) >= 8 else 0

            tag = Tag(
                tag_type=tag_type,
                name=name,
                user_id=user_id,
                content_id=content_id,
            )

        else:
            tag = Tag(
                tag_type=0x04,
                name=name,
                data=bytes(value_data),
            )

        tags.append(tag)

        offset = value_end

    return tags


def parse_cdp(data: bytes) -> CdpDocument:
    """
    Parse a CDP document from binary data.

    Args:
        data: Complete CDP file contents.

    Returns:
        The parsed CDP document.

    Raises:
        CdpError: If the CDP header or body is invalid.
    """
    if len(data) < 16:
        raise CdpError("file is smaller than CDP header")

    if data[:4] != b"ACS$":
        raise CdpError("not a CDP file: missing ACS$ magic")

    version = read_uint32(data, 4)
    reserved = read_uint32(data, 8)
    body_length = read_uint32(data, 12)

    if body_length > len(data) - 16:
        raise CdpError("CDP body length exceeds file size")

    tags = parse_tags(data, 16, len(data))

    return CdpDocument(
        version=version,
        reserved=reserved,
        body_length=body_length,
        tags=tags,
    )


def format_kuid(user_id: int, content_id: int) -> str:
    """
    Format a user ID and content ID as a KUID string.

    Args:
        user_id: Encoded user identifier.
        content_id: Content identifier.

    Returns:
        The formatted KUID.
    """
    flags = (user_id >> 22) & 0x3
    uid = user_id & 0x3FFFFF

    if flags == 0:
        return f"<kuid:{uid}:{content_id}>"

    return f"<kuid{flags}:{uid}:{content_id}>"


def tag_to_json(tag: Tag):
    """
    Convert a CDP tag to a JSON-compatible key-value pair.

    Args:
        tag: Tag to convert.

    Returns:
        A ``(name, value)`` pair, or ``None`` if the tag is omitted.
    """
    if tag.tag_type == 0x00:
        obj = {}

        for child in tag.children or []:
            result = tag_to_json(child)

            if result is not None:
                key, value = result
                obj[key] = value

        return tag.name, obj

    if tag.tag_type == 0x03:
        return tag.name, tag.value or ""

    if tag.tag_type == 0x01:
        vals = tag.values or []

        if len(vals) == 1:
            return tag.name, vals[0]

        return tag.name, vals

    if tag.tag_type == 0x02:
        vals = tag.values or []

        if len(vals) == 1:
            value = vals[0]

            if value != value or value in (float("inf"), float("-inf")):
                value = None

            return tag.name, value

        cleaned = []

        for value in vals:
            if value != value or value in (float("inf"), float("-inf")):
                cleaned.append(None)
            else:
                cleaned.append(value)

        return tag.name, cleaned

    if tag.tag_type == 0x0D:
        return tag.name, format_kuid(
            tag.user_id or 0,
            tag.content_id or 0,
        )

    if tag.tag_type == 0x05:
        return tag.name, None

    if tag.tag_type == 0x04:
        return None

    return None


def build_config_json(asset_name: str, children: List[Tag]) -> bytes:
    """
    Build the JSON configuration for an asset.

    Args:
        asset_name: Asset name.
        children: Asset child tags.

    Returns:
        UTF-8 encoded JSON data.
    """
    obj = {
        "_container": asset_name,
        "_generated-by": "https://github.com/pgroenbaek/cdp-unpacker",
    }

    for child in children:
        # Skip files container.
        if child.tag_type == 0x00 and child.name == "files":
            continue

        # Skip compression string.
        if child.tag_type == 0x03 and child.name == "compression":
            continue

        result = tag_to_json(child)

        if result is not None:
            key, value = result
            obj[key] = value

    text = json.dumps(
        obj,
        indent=4,
        ensure_ascii=False,
        separators=(",", ": "),
        allow_nan=False,
    )

    return text.encode("utf-8")


def safe_component(component: str) -> str:
    """
    Sanitize a path component for safe filesystem use.

    Args:
        component: Path component to sanitize.

    Returns:
        The sanitized component.

    Raises:
        CdpError: If the component is empty or unsafe.
    """
    if not component:
        raise CdpError("empty path component")

    if component in (".", ".."):
        raise CdpError(f"unsafe path component: {component!r}")

    for char in ':"/\\|?*\x00':
        component = component.replace(char, "_")

    for char in '<>"/\\|?*\x00':
        component = component.replace(char, "")

    component = "".join(
        "_" if ord(c) < 32 else c
        for c in component
    )

    if component.endswith(":"):
        component = component[:-1] + "_"

    component = component.strip(". ")

    if not component:
        raise CdpError("empty path component after sanitization")

    return component


def safe_join(root: Path, relative: str) -> Path:
    """
    Join a relative path to a root directory without escaping it.

    Args:
        root: Output root directory.
        relative: Relative path to resolve.

    Returns:
        The resolved path.

    Raises:
        CdpError: If the path escapes the output root.
    """
    parts = relative.replace("\\", "/").split("/")

    clean = []

    for part in parts:
        if part == "":
            continue

        clean.append(safe_component(part))

    destination = root.joinpath(*clean)

    try:
        destination.relative_to(root)
    except ValueError:
        raise CdpError(
            f"unsafe output path: {relative!r}"
        )

    return destination


def decompress_file_blob(tag_name: str, data: bytes) -> bytes:
    """Decompress a CDP file payload.

    Args:
        tag_name: File name used in error messages.
        data: File payload including its uncompressed size prefix.

    Returns:
        The decompressed file data.

    Raises:
        CdpError: If the payload does not contain a size prefix.
    """
    if len(data) < 4:
        raise CdpError(
            f"file {tag_name!r}: "
            "binary payload has no size prefix"
        )

    uncompressed_size = struct.unpack_from("<I", data, 0,)[0]

    compressed_data = data[4:]

    return decompress_lzss(
        compressed_data,
        uncompressed_size,
    )


def extract_file_tree(
    tags: List[Tag],
    prefix_parts: List[str],
    output_root: Path,
    asset_label: str,
) -> int:
    """
    Recursively extract files from a CDP tag tree.

    Args:
        tags: Tags containing files or nested containers.
        prefix_parts: Path components for the current tree level.
        output_root: Root directory for extracted files.
        asset_label: Asset name used in extraction output.

    Returns:
        The number of files extracted.
    """
    count = 0

    for tag in tags:

        if tag.tag_type == 0x04:
            if tag.data is None:
                continue

            if len(tag.data) < 4:
                continue

            output_data = decompress_file_blob(
                tag.name,
                tag.data,
            )

            relative_parts = (
                prefix_parts
                + [tag.name]
            )

            relative = "/".join(
                relative_parts
            )

            destination = safe_join(
                output_root,
                relative,
            )

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with destination.open("wb") as f:
                f.write(output_data)

            count += 1

            print(
                f"  extracted {asset_label}/{relative}"
                f" ({len(output_data)} bytes)"
            )

        elif tag.tag_type == 0x00:
            child_prefix = prefix_parts + [safe_component(tag.name)]

            count += extract_file_tree(
                tag.children or [],
                child_prefix,
                output_root,
                asset_label,
            )

    return count


def find_files_container(children: List[Tag]) -> Optional[Tag]:
    """
    Find the files container among an asset's child tags.

    Args:
        children: Asset child tags.

    Returns:
        The files container, or ``None`` if not found.
    """
    for tag in children:
        if tag.tag_type == 0x00 and tag.name == "files":
            return tag

    return None


def extract_document(document: CdpDocument, output_root: Path) -> Tuple[int, int]:
    """
    Extract an entire CDP document to a directory.

    Args:
        document: Parsed CDP document.
        output_root: Directory where assets will be written.

    Returns:
        A tuple containing the number of assets and files extracted.

    Raises:
        CdpError: If the document does not contain an assets container.
    """
    assets_container = None

    for tag in document.tags:
        if tag.tag_type == 0x00 and tag.name == "assets":
            assets_container = tag
            break

    if assets_container is None:
        raise CdpError("CDP contains no 'assets' container")

    asset_count = 0
    file_count = 0

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    for asset in assets_container.children or []:
        if asset.tag_type != 0x00:
            continue

        asset_name = safe_component(asset.name)
        asset_root = output_root / "assets" / asset_name

        asset_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        children = asset.children or []

        config = build_config_json(asset_name, children,)
        config_path = asset_root / "config.json"

        with config_path.open("wb") as f:
            f.write(config)

        print(
            f"asset {asset_name}: "
            f"config.json ({len(config)} bytes)"
        )

        files_container = find_files_container(children)

        if files_container is not None:
            file_count += extract_file_tree(
                files_container.children or [],
                [
                    "assets",
                    asset_name,
                ],
                output_root,
                asset_name,
            )

        asset_count += 1

    return asset_count, file_count


def print_tag_tree(tags: List[Tag], depth: int = 0) -> None:
    """
    Print a hierarchical representation of parsed CDP tags.

    Args:
        tags: Tags to print.
        depth: Current indentation depth.
    """
    indent = "  " * depth

    for tag in tags:
        if tag.tag_type == 0x00:
            print(f"{indent}[CONTAINER] {tag.name}")

            print_tag_tree(
                tag.children or [],
                depth + 1,
            )

        elif tag.tag_type == 0x01:
            print(f"{indent}[INT] {tag.name}")

        elif tag.tag_type == 0x02:
            print(f"{indent}[FLOAT] {tag.name}")

        elif tag.tag_type == 0x03:
            print(f"{indent}[STRING] {tag.name}")

        elif tag.tag_type == 0x04:
            print(
                f"{indent}[BINARY] "
                f"{tag.name} "
                f"({len(tag.data or b'')} bytes)"
            )

        elif tag.tag_type == 0x05:
            print(f"{indent}[NULL] {tag.name}")

        elif tag.tag_type == 0x0D:
            print(
                f"{indent}[KUID] {tag.name} = "
                f"{format_kuid(tag.user_id or 0, tag.content_id or 0)}"
            )

        else:
            print(
                f"{indent}[UNKNOWN 0x{tag.tag_type:02x}] "
                f"{tag.name}"
            )
