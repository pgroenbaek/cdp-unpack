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

import sys
import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Trainz CDP archives."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="input .cdp file",
    )

    parser.add_argument(
        "output",
        type=Path,
        help="output directory",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="print the CDP tag tree without extracting",
    )

    args = parser.parse_args()

    input_path: Path = args.input
    output_path: Path = args.output

    if not input_path.is_file():
        print(
            f"error: input file does not exist: "
            f"{input_path}",
            file=sys.stderr,
        )
        return 2

    try:
        print(f"Reading: {input_path}")

        data = input_path.read_bytes()

        print(f"Size: {len(data):,} bytes")

        doc = parse_cdp(data)

        print(f"CDP version: {doc.version}")
        print(f"Reserved: 0x{doc.reserved:08x}")
        print(f"Advertised body: {doc.body_length:,} bytes")

        if args.list:
            print()
            print_tag_tree(doc.tags)
            return 0

        print()
        print(f"Extracting to: {output_path}")

        asset_count, file_count = extract_document(
            doc,
            output_path,
        )

        print()
        print(f"Done.")

        print(f"Assets: {asset_count}")
        print(f"Files:  {file_count}")

        return 0

    except CdpError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    except Exception as e:
        print(f"ERROR: unexpected failure: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())