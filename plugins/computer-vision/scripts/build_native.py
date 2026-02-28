"""Build shim32.dll + shim64.dll + injector.exe from C++ sources.

Usage:
    uv run python scripts/build_native.py

Prerequisites:
    - Visual Studio Build Tools 2019+ (with C++ workload)
    - Windows SDK (10.0.x)
    - CMake 3.21+ (ships with VS Build Tools)

The script detects VS Build Tools via vswhere.exe, then runs CMake
for both Win32 and x64 architectures. Outputs are copied to
src/sandbox/native/build/.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
NATIVE_DIR = PROJECT_ROOT / "src" / "sandbox" / "native"
OUTPUT_DIR = NATIVE_DIR / "build"
CMAKE_LISTS = NATIVE_DIR / "CMakeLists.txt"


def find_vswhere() -> Path | None:
    """Find vswhere.exe in standard VS installation paths."""
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    # Check PATH
    which = shutil.which("vswhere")
    return Path(which) if which else None


def find_cmake() -> Path | None:
    """Find cmake.exe — prefer the one bundled with VS Build Tools."""
    which = shutil.which("cmake")
    return Path(which) if which else None


def detect_vs_generator() -> str:
    """Detect the best CMake generator for the installed VS version."""
    vswhere = find_vswhere()
    if vswhere is None:
        print("ERROR: vswhere.exe not found. Install Visual Studio Build Tools.")
        sys.exit(1)

    result = subprocess.run(
        [str(vswhere), "-latest", "-property", "catalog_productLineVersion"],
        capture_output=True, text=True,
    )
    version = result.stdout.strip()

    generators = {
        "2022": "Visual Studio 17 2022",
        "2019": "Visual Studio 16 2019",
    }

    generator = generators.get(version)
    if generator is None:
        print(f"WARNING: VS version '{version}' not recognized. Trying VS 2022.")
        generator = "Visual Studio 17 2022"

    return generator


def build_arch(cmake: Path, generator: str, arch: str, build_dir: Path) -> bool:
    """Run CMake configure + build for a single architecture."""
    print(f"\n{'='*60}")
    print(f"Building {arch}...")
    print(f"{'='*60}")

    # Configure
    configure_cmd = [
        str(cmake),
        "-G", generator,
        "-A", arch,
        "-B", str(build_dir),
        "-S", str(NATIVE_DIR),
    ]
    print(f"  Configure: {' '.join(configure_cmd)}")
    result = subprocess.run(configure_cmd, cwd=str(NATIVE_DIR))
    if result.returncode != 0:
        print(f"  ERROR: CMake configure failed for {arch}")
        return False

    # Build
    build_cmd = [
        str(cmake),
        "--build", str(build_dir),
        "--config", "Release",
    ]
    print(f"  Build: {' '.join(build_cmd)}")
    result = subprocess.run(build_cmd, cwd=str(NATIVE_DIR))
    if result.returncode != 0:
        print(f"  ERROR: CMake build failed for {arch}")
        return False

    print(f"  {arch} build succeeded.")
    return True


def collect_outputs(build32: Path, build64: Path) -> list[str]:
    """Copy built artifacts to the output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    collected = []

    artifacts = [
        (build32 / "Release" / "shim32.dll", "shim32.dll"),
        (build64 / "Release" / "shim64.dll", "shim64.dll"),
        (build64 / "Release" / "injector.exe", "injector.exe"),
        # Also check non-Release paths (some generators put it differently)
        (build32 / "shim32.dll", "shim32.dll"),
        (build64 / "shim64.dll", "shim64.dll"),
        (build64 / "injector.exe", "injector.exe"),
    ]

    for src, name in artifacts:
        dest = OUTPUT_DIR / name
        if src.exists() and not dest.exists():
            shutil.copy2(src, dest)
            collected.append(name)
            print(f"  Copied: {name} -> {dest}")
        elif dest.exists():
            # Already collected from a previous candidate path
            if name not in collected:
                collected.append(name)

    return collected


def main() -> int:
    """Main build entry point."""
    print("Sandbox Native Build Script")
    print(f"  Native dir: {NATIVE_DIR}")
    print(f"  Output dir: {OUTPUT_DIR}")

    if not CMAKE_LISTS.exists():
        print(f"ERROR: CMakeLists.txt not found at {CMAKE_LISTS}")
        return 1

    cmake = find_cmake()
    if cmake is None:
        print("ERROR: cmake not found. Install VS Build Tools with C++ CMake tools.")
        return 1
    print(f"  CMake: {cmake}")

    generator = detect_vs_generator()
    print(f"  Generator: {generator}")

    build32 = NATIVE_DIR / "build32"
    build64 = NATIVE_DIR / "build64"

    ok_32 = build_arch(cmake, generator, "Win32", build32)
    ok_64 = build_arch(cmake, generator, "x64", build64)

    if not ok_32 and not ok_64:
        print("\nERROR: Both architectures failed to build.")
        return 1

    collected = collect_outputs(build32, build64)

    print(f"\n{'='*60}")
    print("Build Summary")
    print(f"{'='*60}")
    print(f"  Win32: {'OK' if ok_32 else 'FAILED'}")
    print(f"  x64:   {'OK' if ok_64 else 'FAILED'}")
    print(f"  Artifacts: {', '.join(collected) if collected else 'none'}")
    print(f"  Output: {OUTPUT_DIR}")

    if not ok_32 or not ok_64:
        print("\nWARNING: One architecture failed. Partial build available.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
