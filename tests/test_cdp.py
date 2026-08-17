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

import pytest
import json
import struct

from cdpunpack.cdp import (
    CdpDocument,
    CdpError,
    Tag,
    build_config_json,
    decompress_file_blob,
    extract_document,
    extract_file_tree,
    find_files_container,
    format_kuid,
    parse_cdp,
    parse_tags,
    read_float32,
    read_int32,
    read_uint32,
    safe_component,
    safe_join,
    tag_to_json,
)


def make_tag(tag_type: int, name: str = "", value: bytes = b"") -> bytes:
    name_bytes = name.encode("utf-8") + b"\0"

    payload = (
        bytes([len(name_bytes)])
        + name_bytes
        + bytes([tag_type])
        + value
    )

    return struct.pack("<I", len(payload)) + payload


def make_container(name: str, *children: bytes) -> bytes:
    return make_tag(0x00, name, b"".join(children))


def make_int_tag(name: str, *values: int) -> bytes:
    return make_tag(
        0x01,
        name,
        b"".join(struct.pack("<i", value) for value in values),
    )


def make_float_tag(name: str, *values: float) -> bytes:
    return make_tag(
        0x02,
        name,
        b"".join(struct.pack("<f", value) for value in values),
    )


def make_string_tag(name: str, value: str) -> bytes:
    return make_tag(
        0x03,
        name,
        value.encode("utf-8") + b"\0",
    )


def make_binary_tag(name: str, value: bytes) -> bytes:
    return make_tag(0x04, name, value)


def make_null_tag(name: str) -> bytes:
    return make_tag(0x05, name)


def make_kuid_tag(
    name: str,
    user_id: int,
    content_id: int,
) -> bytes:
    return make_tag(
        0x0D,
        name,
        struct.pack("<Ii", user_id, content_id),
    )


def make_cdp(
    *tags: bytes,
    version: int = 1,
    reserved: int = 0,
    body_length: int | None = None,
) -> bytes:
    body = b"".join(tags)

    if body_length is None:
        body_length = len(body)

    return (
        b"ACS$"
        + struct.pack(
            "<III",
            version,
            reserved,
            body_length,
        )
        + body
    )


def test_read_uint32():
    data = struct.pack("<I", 0x12345678)

    assert read_uint32(data, 0) == 0x12345678


def test_read_int32():
    data = struct.pack("<i", -123)

    assert read_int32(data, 0) == -123


def test_read_float32():
    data = struct.pack("<f", 1.5)

    assert read_float32(data, 0) == pytest.approx(1.5)


@pytest.mark.parametrize(
    "reader",
    [
        read_uint32,
        read_int32,
        read_float32,
    ],
)
def test_readers_reject_truncated_data(reader):
    with pytest.raises(CdpError, match="truncated"):
        reader(b"\x00\x01\x02", 0)


def test_parse_cdp_reads_header():
    data = make_cdp(
        make_string_tag("name", "hello"),
        version=7,
        reserved=123,
    )

    doc = parse_cdp(data)

    assert doc.version == 7
    assert doc.reserved == 123
    assert doc.body_length == len(data) - 16


def test_parse_cdp_reads_tags():
    data = make_cdp(
        make_string_tag("name", "hello"),
    )

    doc = parse_cdp(data)

    assert doc.tags == [
        Tag(
            tag_type=0x03,
            name="name",
            value="hello",
        )
    ]


def test_parse_cdp_rejects_short_header():
    with pytest.raises(
        CdpError,
        match="smaller than CDP header",
    ):
        parse_cdp(b"ACS$")


def test_parse_cdp_rejects_invalid_magic():
    data = b"NOPE" + b"\0" * 12

    with pytest.raises(
        CdpError,
        match="missing ACS\\$ magic",
    ):
        parse_cdp(data)


def test_parse_cdp_rejects_body_larger_than_file():
    data = make_cdp(
        make_string_tag("name", "hello"),
        body_length=9999,
    )

    with pytest.raises(
        CdpError,
        match="body length exceeds file size",
    ):
        parse_cdp(data)


def test_parse_tags_parses_container():
    data = make_container(
        "outer",
        make_string_tag("name", "hello"),
    )

    tags = parse_tags(data, 0, len(data))

    assert tags == [
        Tag(
            tag_type=0x00,
            name="outer",
            children=[
                Tag(
                    tag_type=0x03,
                    name="name",
                    value="hello",
                )
            ],
        )
    ]


def test_parse_tags_parses_ints():
    data = make_int_tag(
        "numbers",
        -1,
        0,
        42,
    )

    tags = parse_tags(data, 0, len(data))

    assert tags == [
        Tag(
            tag_type=0x01,
            name="numbers",
            values=[-1, 0, 42],
        )
    ]


def test_parse_tags_parses_floats():
    data = make_float_tag(
        "numbers",
        1.5,
        -2.25,
    )

    tags = parse_tags(data, 0, len(data))

    assert tags[0].tag_type == 0x02
    assert tags[0].name == "numbers"
    assert tags[0].values == pytest.approx([1.5, -2.25])


def test_parse_tags_parses_string():
    data = make_string_tag(
        "description",
        "Héllo 日本",
    )

    tags = parse_tags(data, 0, len(data))

    assert tags == [
        Tag(
            tag_type=0x03,
            name="description",
            value="Héllo 日本",
        )
    ]


def test_parse_tags_string_stops_at_null():
    data = make_tag(
        0x03,
        "name",
        b"hello\0ignored",
    )

    tags = parse_tags(data, 0, len(data))

    assert tags[0].value == "hello"


def test_parse_tags_parses_binary():
    data = make_binary_tag(
        "blob",
        b"\x01\x02\x03",
    )

    tags = parse_tags(data, 0, len(data))

    assert tags == [
        Tag(
            tag_type=0x04,
            name="blob",
            data=b"\x01\x02\x03",
        )
    ]


def test_parse_tags_parses_null():
    data = make_null_tag("optional")

    tags = parse_tags(data, 0, len(data))

    assert tags == [
        Tag(
            tag_type=0x05,
            name="optional",
        )
    ]


def test_parse_tags_parses_kuid():
    data = make_kuid_tag(
        "asset-id",
        123,
        456,
    )

    tags = parse_tags(data, 0, len(data))

    assert tags == [
        Tag(
            tag_type=0x0D,
            name="asset-id",
            user_id=123,
            content_id=456,
        )
    ]


def test_parse_tags_unknown_type_becomes_binary():
    data = make_tag(
        0x99,
        "unknown",
        b"\x01\x02\x03",
    )

    tags = parse_tags(data, 0, len(data))

    assert tags == [
        Tag(
            tag_type=0x04,
            name="unknown",
            data=b"\x01\x02\x03",
        )
    ]


def test_parse_tags_nested_containers():
    data = make_container(
        "outer",
        make_container(
            "inner",
            make_int_tag("answer", 42),
        ),
    )

    tags = parse_tags(data, 0, len(data))

    assert tags[0].children[0].children[0] == Tag(
        tag_type=0x01,
        name="answer",
        values=[42],
    )


def test_parse_tags_ignores_trailing_partial_tag():
    complete = make_string_tag("name", "hello")
    partial = b"\x01\x02\x03"

    data = complete + partial

    tags = parse_tags(data, 0, len(data))

    assert len(tags) == 1
    assert tags[0].name == "name"


@pytest.mark.parametrize(
    ("user_id", "content_id", "expected"),
    [
        (0, 0, "<kuid:0:0>"),
        (123, 456, "<kuid:123:456>"),
        (0x3FFFFF, 456, "<kuid:4194303:456>"),
        ((1 << 22) | 123, 456, "<kuid1:123:456>"),
        ((2 << 22) | 123, 456, "<kuid2:123:456>"),
        ((3 << 22) | 123, 456, "<kuid3:123:456>"),
    ],
)
def test_format_kuid(
    user_id,
    content_id,
    expected,
):
    assert format_kuid(
        user_id,
        content_id,
    ) == expected


def test_tag_to_json_container():
    tag = Tag(
        tag_type=0x00,
        name="asset",
        children=[
            Tag(
                0x03,
                "name",
                value="hello",
            ),
            Tag(
                0x01,
                "count",
                values=[3],
            ),
        ],
    )

    assert tag_to_json(tag) == (
        "asset",
        {
            "name": "hello",
            "count": 3,
        },
    )


def test_tag_to_json_string():
    tag = Tag(
        0x03,
        "name",
        value="hello",
    )

    assert tag_to_json(tag) == (
        "name",
        "hello",
    )


def test_tag_to_json_single_int_is_scalar():
    tag = Tag(
        0x01,
        "answer",
        values=[42],
    )

    assert tag_to_json(tag) == (
        "answer",
        42,
    )


def test_tag_to_json_multiple_ints_are_list():
    tag = Tag(
        0x01,
        "answers",
        values=[1, 2, 3],
    )

    assert tag_to_json(tag) == (
        "answers",
        [1, 2, 3],
    )


def test_tag_to_json_single_float_is_scalar():
    tag = Tag(
        0x02,
        "value",
        values=[1.5],
    )

    key, value = tag_to_json(tag)

    assert key == "value"
    assert value == pytest.approx(1.5)


def test_tag_to_json_multiple_floats_are_list():
    tag = Tag(
        0x02,
        "values",
        values=[1.5, 2.5],
    )

    key, value = tag_to_json(tag)

    assert key == "values"
    assert value == pytest.approx([1.5, 2.5])


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_tag_to_json_non_finite_float_becomes_none(value):
    tag = Tag(
        0x02,
        "value",
        values=[value],
    )

    assert tag_to_json(tag) == (
        "value",
        None,
    )


def test_tag_to_json_non_finite_floats_in_list_become_none():
    tag = Tag(
        0x02,
        "values",
        values=[
            1.5,
            float("nan"),
            float("inf"),
            -2.5,
        ],
    )

    assert tag_to_json(tag) == (
        "values",
        [1.5, None, None, -2.5],
    )


def test_tag_to_json_kuid():
    tag = Tag(
        tag_type=0x0D,
        name="asset-id",
        user_id=(2 << 22) | 123,
        content_id=456,
    )

    assert tag_to_json(tag) == (
        "asset-id",
        "<kuid2:123:456>",
    )


def test_tag_to_json_null():
    assert tag_to_json(
        Tag(0x05, "optional")
    ) == (
        "optional",
        None,
    )


def test_tag_to_json_binary_is_omitted():
    assert tag_to_json(
        Tag(
            0x04,
            "blob",
            data=b"abc",
        )
    ) is None


def test_tag_to_json_unknown_is_omitted():
    assert tag_to_json(
        Tag(0x99, "unknown")
    ) is None


def test_build_config_json():
    children = [
        Tag(
            0x03,
            "description",
            value="Héllo",
        ),
        Tag(
            0x03,
            "compression",
            value="lzss",
        ),
        Tag(
            0x00,
            "files",
            children=[],
        ),
        Tag(
            0x04,
            "binary",
            data=b"\x01\x02",
        ),
    ]

    result = build_config_json(
        "my_asset",
        children,
    )

    obj = json.loads(result)

    assert obj == {
        "_container": "my_asset",
        "_generated-by": "https://github.com/pgroenbaek/cdp-unpack",
        "description": "Héllo",
    }


def test_build_config_json_preserves_unicode():
    result = build_config_json(
        "asset",
        [
            Tag(
                0x03,
                "name",
                value="ÆØÅ 日本",
            )
        ],
    )

    obj = json.loads(result)

    assert obj["name"] == "ÆØÅ 日本"


@pytest.mark.parametrize(
    ("component", "expected"),
    [
        ("foo", "foo"),
        ("foo.bar", "foo.bar"),
        ("foo bar", "foo bar"),
        ("foo/bar", "foo_bar"),
        (r"foo\bar", "foo_bar"),
        ("foo|bar", "foo_bar"),
        ("foo?bar", "foo_bar"),
        ("foo*bar", "foo_bar"),
        ("foo<bar>", "foobar"),
        ('foo"bar', "foo_bar"),
        ("foo\x00bar", "foo_bar"),
        ("foo\nbar", "foo_bar"),
        ("foo. ", "foo"),
    ],
)
def test_safe_component(component, expected):
    assert safe_component(component) == expected


@pytest.mark.parametrize(
    "component",
    [
        "",
        ".",
        "..",
        "   ",
        "...",
    ],
)
def test_safe_component_rejects_unsafe_component(component):
    with pytest.raises(CdpError):
        safe_component(component)


def test_safe_component_preserves_unicode():
    assert safe_component("ÆØÅ_日本") == "ÆØÅ_日本"


def test_safe_component_sanitizes_drive_colon():
    assert safe_component("C:") == "C_"


def test_safe_join(tmp_path):
    result = safe_join(
        tmp_path,
        "assets/my_asset/file.txt",
    )

    assert result == (
        tmp_path
        / "assets"
        / "my_asset"
        / "file.txt"
    )


def test_safe_join_normalizes_backslashes(tmp_path):
    result = safe_join(
        tmp_path,
        r"assets\my_asset\file.txt",
    )

    assert result == (
        tmp_path
        / "assets"
        / "my_asset"
        / "file.txt"
    )


def test_safe_join_skips_empty_components(tmp_path):
    result = safe_join(
        tmp_path,
        "assets//my_asset///file.txt",
    )

    assert result == (
        tmp_path
        / "assets"
        / "my_asset"
        / "file.txt"
    )


def test_safe_join_rejects_parent_traversal(tmp_path):
    with pytest.raises(
        CdpError,
        match=r"unsafe path component: '\.\.'",
    ):
        safe_join(
            tmp_path,
            "../../outside/file.txt",
        )


def test_safe_join_rejects_dot_dot_component(tmp_path):
    with pytest.raises(CdpError):
        safe_join(
            tmp_path,
            "assets/../outside/file.txt",
        )


def test_find_files_container():
    files = Tag(
        0x00,
        "files",
        children=[],
    )

    children = [
        Tag(
            0x03,
            "description",
            value="hello",
        ),
        files,
    ]

    assert find_files_container(children) is files


def test_find_files_container_returns_none():
    children = [
        Tag(
            0x03,
            "description",
            value="hello",
        )
    ]

    assert find_files_container(children) is None


def test_decompress_file_blob_rejects_missing_size():
    with pytest.raises(
        CdpError,
        match="binary payload has no size prefix",
    ):
        decompress_file_blob(
            "foo.bin",
            b"\x01\x02\x03",
        )


def test_decompress_file_blob_passes_size_and_payload_to_lzss(monkeypatch):
    calls = []

    def fake_decompress_lzss(compressed_data, uncompressed_size):
        calls.append(
            (
                compressed_data,
                uncompressed_size,
            )
        )

        return b"hello"

    monkeypatch.setattr(
        "cdpunpack.cdp.decompress_lzss",
        fake_decompress_lzss,
    )

    data = (
        struct.pack("<I", 5)
        + b"compressed"
    )

    result = decompress_file_blob(
        "foo.bin",
        data,
    )

    assert result == b"hello"

    assert calls == [
        (
            b"compressed",
            5,
        )
    ]


def test_extract_file_tree_writes_decompressed_file(tmp_path, monkeypatch):
    def fake_decompress_lzss(
        compressed_data,
        uncompressed_size,
    ):
        assert compressed_data == b"compressed"
        assert uncompressed_size == 5

        return b"hello"

    monkeypatch.setattr(
        "cdpunpack.cdp.decompress_lzss",
        fake_decompress_lzss,
    )

    tags = [
        Tag(
            0x04,
            "hello.txt",
            data=(
                struct.pack("<I", 5)
                + b"compressed"
            ),
        )
    ]

    count = extract_file_tree(
        tags,
        ["assets", "my_asset"],
        tmp_path,
        "my_asset",
    )

    assert count == 1

    output_file = (
        tmp_path
        / "assets"
        / "my_asset"
        / "hello.txt"
    )

    assert output_file.read_bytes() == b"hello"


def test_extract_file_tree_creates_nested_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cdpunpack.cdp.decompress_lzss",
        lambda data, size: b"contents",
    )

    tags = [
        Tag(
            0x00,
            "textures",
            children=[
                Tag(
                    0x04,
                    "diffuse.bin",
                    data=(
                        struct.pack("<I", 8)
                        + b"compressed"
                    ),
                )
            ],
        )
    ]

    count = extract_file_tree(
        tags,
        ["assets", "my_asset"],
        tmp_path,
        "my_asset",
    )

    assert count == 1

    output_file = (
        tmp_path
        / "assets"
        / "my_asset"
        / "textures"
        / "diffuse.bin"
    )

    assert output_file.read_bytes() == b"contents"


def test_extract_file_tree_counts_multiple_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cdpunpack.cdp.decompress_lzss",
        lambda data, size: data,
    )

    tags = [
        Tag(
            0x04,
            "one.txt",
            data=struct.pack("<I", 3) + b"one",
        ),
        Tag(
            0x04,
            "two.txt",
            data=struct.pack("<I", 3) + b"two",
        ),
    ]

    count = extract_file_tree(
        tags,
        ["assets", "asset"],
        tmp_path,
        "asset",
    )

    assert count == 2

    assert (
        tmp_path
        / "assets"
        / "asset"
        / "one.txt"
    ).read_bytes() == b"one"

    assert (
        tmp_path
        / "assets"
        / "asset"
        / "two.txt"
    ).read_bytes() == b"two"


def test_extract_file_tree_skips_binary_without_data(tmp_path):
    tags = [
        Tag(
            0x04,
            "missing.bin",
            data=None,
        )
    ]

    assert extract_file_tree(
        tags,
        [],
        tmp_path,
        "asset",
    ) == 0


def test_extract_file_tree_skips_binary_without_size(tmp_path, monkeypatch):
    def should_not_be_called(*args):
        raise AssertionError(
            "LZSS should not be called"
        )

    monkeypatch.setattr(
        "cdpunpack.cdp.decompress_lzss",
        should_not_be_called,
    )

    tags = [
        Tag(
            0x04,
            "truncated.bin",
            data=b"\x01\x02\x03",
        )
    ]

    assert extract_file_tree(
        tags,
        [],
        tmp_path,
        "asset",
    ) == 0


def test_extract_document_creates_config_and_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cdpunpack.cdp.decompress_lzss",
        lambda data, size: b"hello",
    )

    files = Tag(
        0x00,
        "files",
        children=[
            Tag(
                0x04,
                "hello.txt",
                data=(
                    struct.pack("<I", 5)
                    + b"compressed"
                ),
            )
        ],
    )

    asset = Tag(
        0x00,
        "my_asset",
        children=[
            Tag(
                0x03,
                "description",
                value="A test asset",
            ),
            Tag(
                0x03,
                "compression",
                value="lzss",
            ),
            files,
        ],
    )

    doc = CdpDocument(
        version=1,
        reserved=0,
        body_length=0,
        tags=[
            Tag(
                0x00,
                "assets",
                children=[asset],
            )
        ],
    )

    asset_count, file_count = extract_document(
        doc,
        tmp_path,
    )

    assert asset_count == 1
    assert file_count == 1

    asset_root = (
        tmp_path
        / "assets"
        / "my_asset"
    )

    assert (
        asset_root / "config.json"
    ).exists()

    assert (
        asset_root / "hello.txt"
    ).read_bytes() == b"hello"

    config = json.loads(
        (
            asset_root
            / "config.json"
        ).read_bytes()
    )

    assert config["_container"] == "my_asset"
    assert config["description"] == "A test asset"

    assert "compression" not in config
    assert "files" not in config


def test_extract_document_creates_asset_without_files(tmp_path):
    asset = Tag(
        0x00,
        "my_asset",
        children=[
            Tag(
                0x03,
                "description",
                value="hello",
            )
        ],
    )

    doc = CdpDocument(
        version=1,
        reserved=0,
        body_length=0,
        tags=[
            Tag(
                0x00,
                "assets",
                children=[asset],
            )
        ],
    )

    asset_count, file_count = extract_document(
        doc,
        tmp_path,
    )

    assert asset_count == 1
    assert file_count == 0

    config = json.loads(
        (
            tmp_path
            / "assets"
            / "my_asset"
            / "config.json"
        ).read_bytes()
    )

    assert config["description"] == "hello"


def test_extract_document_rejects_missing_assets(tmp_path):
    doc = CdpDocument(
        version=1,
        reserved=0,
        body_length=0,
        tags=[],
    )

    with pytest.raises(
        CdpError,
        match="contains no 'assets' container",
    ):
        extract_document(
            doc,
            tmp_path,
        )


def test_extract_document_ignores_non_asset_children(tmp_path):
    doc = CdpDocument(
        version=1,
        reserved=0,
        body_length=0,
        tags=[
            Tag(
                0x00,
                "assets",
                children=[
                    Tag(
                        0x03,
                        "not-an-asset",
                        value="hello",
                    )
                ],
            )
        ],
    )

    asset_count, file_count = extract_document(
        doc,
        tmp_path,
    )

    assert asset_count == 0
    assert file_count == 0