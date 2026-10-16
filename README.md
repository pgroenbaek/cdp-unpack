# cdp-unpack

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/pgroenbaek/cdp-unpack?style=flat&label=Latest%20Version)](https://github.com/pgroenbaek/cdp-unpack/releases)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License MIT](https://img.shields.io/badge/License-MIT-lightgrey?style=flat&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NDAgNTEyIj4KICA8IS0tIEZvbnQgQXdlc29tZSBGcmVlIDYuNy4yIGJ5IEBmb250YXdlc29tZSAtIGh0dHBzOi8vZm9udGF3ZXNvbWUuY29tIExpY2Vuc2UgLSBodHRwczovL2ZvbnRhd2Vzb21lLmNvbS9saWNlbnNlL2ZyZWUgQ29weXJpZ2h0IDIwMjUgRm9udGljb25zLCBJbmMuIC0tPgogIDxwYXRoIGZpbGw9IndoaXRlIiBkPSJNMzg0IDMybDEyOCAwYzE3LjcgMCAzMiAxNC4zIDMyIDMycy0xNC4zIDMyLTMyIDMyTDM5OC40IDk2Yy01LjIgMjUuOC0yMi45IDQ3LjEtNDYuNCA1Ny4zTDM1MiA0NDhsMTYwIDBjMTcuNyAwIDMyIDE0LjMgMzIgMzJzLTE0LjMgMzItMzIgMzJsLTE5MiAwLTE5MiAwYy0xNy43IDAtMzItMTQuMy0zMi0zMnMxNC4zLTMyIDMyLTMybDE2MCAwIDAtMjk0LjdjLTIzLjUtMTAuMy00MS4yLTMxLjYtNDYuNC01Ny4zTDEyOCA5NmMtMTcuNyAwLTMyLTE0LjMtMzItMzJzMTQuMy0zMiAzMi0zMmwxMjggMGMxNC42LTE5LjQgMzcuOC0zMiA2NC0zMnM0OS40IDEyLjYgNjQgMzJ6bTU1LjYgMjg4bDE0NC45IDBMNTEyIDE5NS44IDQzOS42IDMyMHpNNTEyIDQxNmMtNjIuOSAwLTExNS4yLTM0LTEyNi03OC45Yy0yLjYtMTEgMS0yMi4zIDYuNy0zMi4xbDk1LjItMTYzLjJjNS04LjYgMTQuMi0xMy44IDI0LjEtMTMuOHMxOS4xIDUuMyAyNC4xIDEzLjhsOTUuMiAxNjMuMmM1LjcgOS44IDkuMyAyMS4xIDYuNyAzMi4xQzYyNy4yIDM4MiA1NzQuOSA0MTYgNTEyIDQxNnpNMTI2LjggMTk1LjhMNTQuNCAzMjBsMTQ0LjkgMEwxMjYuOCAxOTUuOHpNLjkgMzM3LjFjLTIuNi0xMSAxLTIyLjMgNi43LTMyLjFsOTUuMi0xNjMuMmM1LTguNiAxNC4yLTEzLjggMjQuMS0xMy44czE5LjEgNS4zIDI0LjEgMTMuOGw5NS4yIDE2My4yYzUuNyA5LjggOS4zIDIxLjEgNi43IDMyLjFDMjQyIDM4MiAxODkuNyA0MTYgMTI2LjggNDE2UzExLjcgMzgyIC45IDMzNy4xeiIvPgo8L3N2Zz4=&logoColor=%23ffffff)](https://github.com/pgroenbaek/cdp-unpack/blob/master/LICENSE)

A cross-platform CLI and Python module for extracting files from CDP/CHUMP archives used by Trainz.

## Installation

The CLI or Python module can be installed in the following ways:

### Standalone CLI executable

Download the standalone CLI executable from the [Releases](https://github.com/pgroenbaek/cdp-unpack/releases) page for your operating system, then extract it somewhere you can find it.

See [Usage](#Usage) for details on how to use the CLI.

### Python module from PyPI

```sh
pip install --upgrade cdpunpack
```

### Python module from wheel

If you have downloaded a `.whl` file from the [Releases](https://github.com/pgroenbaek/cdp-unpack/releases) page, install it with:

```sh
pip install path/to/cdpunpack-<version>‑py3‑none‑any.whl
```

Replace `<version>` with the actual version number in the filename.

### Python module from source

```sh
git clone https://github.com/pgroenbaek/cdp-unpack.git
pip install --upgrade ./cdp-unpack
```

## Usage

### Running the CLI

#### Windows

```ps1
.\cdpunpack.exe input.cdp output_folder
```

#### Linux

```bash
./cdpunpack input.cdp output_folder
```

### Listing contents of archives

Use the `--list` parameter to list contents of a `.cdp` file, for example:

```ps1
.\cdpunpack.exe --list input.cdp
```

### Running as a Python module

```bash
python3 -m cdpunpack input.cdp output_folder
```

### Using the module in Python scripts

```python
from pathlib import Path
from cdpunpack import parse_cdp, extract_document

input_path: Path = Path("path/to/input.cdp")
output_path: Path = Path("path/to/output")

data = input_path.read_bytes()

document = parse_cdp(data)

asset_count, file_count = extract_document(
    document,
    output_path,
)

print(f"Extracted Assets: {asset_count}")
print(f"Extracted Files: {file_count}")
```

## Building

### Prerequisites

A Python 3.8+ installation is needed for building the module and standalone CLI executable.

In addition, Nuitka is required for building the standalone CLI executable, install it from `pip` using:

```bash
pip install "nuitka[onefile]"
```

### Building the wheel and CLI executable:

#### Windows

Run the following command in PowerShell:

```ps1
.\tools\package_windows.ps1
```

#### Linux

Run the following command in a terminal:

```bash
./tools/package_linux.sh
```

## Running Tests

You can run tests manually or use `tox` to test across multiple Python versions.

### Run Tests Manually
First, install the required dependencies:

```sh
pip install pytest
```

Then, run tests with:

```sh
pytest
```

### Run Tests with `tox`

First, install the required dependencies:

```sh
pip install tox pytest
```

Then, run tests with:

```sh
tox
```

This will execute tests for all Python versions specified in `tox.ini`.

## License
This project is a Python port/adaptation of the extraction-portion of [cdptool](https://github.com/emmaworley/cdptool).

The original code is Copyright (c) 2026 cdptool contributors and is licensed under the MIT License.

This Python implementation is also released under the [MIT License](https://github.com/pgroenbaek/cdp-unpack/blob/master/LICENSE).
