#!/usr/bin/env python3
"""Pin moving Meson wrap revisions in the selected native source checkout.

This is intentionally strict: it edits only four known wrap files, verifies
their upstream URLs and refuses unknown revisions instead of rewriting blindly.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

PINNED_DEPENDENCIES: dict[str, tuple[str, str]] = {
    "libntr.wrap": (
        "https://github.com/cybervisi0n/libntr.git",
        "1555d911ac80c0190ac1c321f99f1323de8b3c09",
    ),
    "libntrsystem.wrap": (
        "https://github.com/cybervisi0n/libntrsystem.git",
        "cd778c9d5e45869f8ecb8245b316ac20ea576958",
    ),
    "libntrwifi.wrap": (
        "https://github.com/cybervisi0n/libntrwifi.git",
        "067dabb137dfaf80b8ceeb3b3c4a7256bfabc3e0",
    ),
    "libntrdwc.wrap": (
        "https://github.com/cybervisi0n/libntrdwc.git",
        "16246ba7b4269e6686f3e4da068e3c996a103739",
    ),
}
_ALLOWED_CURRENT_REVISIONS = {"main"}


class PinningError(RuntimeError):
    """Raised for missing, altered, or ambiguous dependency wrap metadata."""


def pin_native_dependencies(native_root: str | Path) -> list[str]:
    """Pin the known dependency wraps; return the filenames changed."""
    root = Path(native_root).expanduser().resolve()
    subprojects = root / "subprojects"
    if not subprojects.is_dir():
        raise PinningError(f"Diretório subprojects ausente: {subprojects}")

    changed: list[str] = []
    for filename, (expected_url, expected_revision) in PINNED_DEPENDENCIES.items():
        path = subprojects / filename
        if not path.is_file():
            raise PinningError(f"Arquivo de dependência ausente: {path}")

        original = path.read_text(encoding="utf-8")
        urls = re.findall(r"(?m)^\s*url\s*=\s*(\S+)\s*$", original)
        revisions = re.findall(r"(?m)^\s*revision\s*=\s*(\S+)\s*$", original)
        if urls != [expected_url]:
            raise PinningError(
                f"URL inesperada em {filename}; esperado exatamente {expected_url!r}, recebido {urls!r}."
            )
        if len(revisions) != 1:
            raise PinningError(f"Esperava uma única chave revision em {filename}; recebido {len(revisions)}.")

        current_revision = revisions[0]
        if current_revision == expected_revision:
            continue
        if current_revision not in _ALLOWED_CURRENT_REVISIONS:
            raise PinningError(
                f"Revisão desconhecida em {filename}: {current_revision!r}. "
                "Revise a dependência antes de atualizar o pin."
            )

        updated, count = re.subn(
            r"(?m)^(\s*revision\s*=\s*)\S+\s*$",
            lambda match: match.group(1) + expected_revision,
            original,
            count=1,
        )
        if count != 1:
            raise PinningError(f"Não foi possível atualizar a revisão de {filename}.")

        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=subprojects)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        changed.append(filename)

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fixa os commits de dependências Meson conhecidas do porte nativo desktop."
    )
    parser.add_argument(
        "native_root",
        nargs="?",
        default="vendor/pokeplatinum-native",
        help="Diretório do checkout nativo (padrão: vendor/pokeplatinum-native).",
    )
    args = parser.parse_args(argv)
    try:
        changed = pin_native_dependencies(args.native_root)
    except (OSError, PinningError) as exc:
        print(f"Erro ao fixar dependências: {exc}", file=sys.stderr)
        return 2

    if changed:
        print("Revisões Meson fixadas: " + ", ".join(changed))
    else:
        print("As dependências Meson já estavam fixadas nas revisões esperadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
