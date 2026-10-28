#!/usr/bin/env python3
"""Temporarily pin moving Meson wraps for a reproducible native build.

Only four known wrap files and their expected upstream URLs are accepted.
Updates are planned and validated before any write, then restored after builds
so the external source checkout is not left dirty.
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
MOVING_REVISION = "main"
REVISION_RE = re.compile(r"(?m)^(\s*revision\s*=\s*)\S+\s*$")


class PinningError(RuntimeError):
    """Raised for missing, altered, or ambiguous dependency wrap metadata."""


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _plan_updates(native_root: str | Path, *, restore: bool) -> list[tuple[Path, str, str]]:
    root = Path(native_root).expanduser().resolve()
    subprojects = root / "subprojects"
    if not subprojects.is_dir():
        raise PinningError(f"Diretório subprojects ausente: {subprojects}")

    plans: list[tuple[Path, str, str]] = []
    # Validate every wrap first so a missing/unknown later file cannot leave
    # earlier wraps partially modified.
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
            raise PinningError(
                f"Esperava uma única chave revision em {filename}; recebido {len(revisions)}."
            )

        current_revision = revisions[0]
        allowed = {MOVING_REVISION, expected_revision}
        if current_revision not in allowed:
            message = "revisão inesperada" if restore else "Revisão desconhecida"
            raise PinningError(
                f"{message} em {filename}: {current_revision!r}. "
                "Revise a dependência antes de atualizar o pin."
            )

        desired_revision = MOVING_REVISION if restore else expected_revision
        if current_revision == desired_revision:
            continue
        updated, count = REVISION_RE.subn(
            lambda match: match.group(1) + desired_revision,
            original,
            count=1,
        )
        if count != 1:
            raise PinningError(f"Não foi possível atualizar a revisão de {filename}.")
        plans.append((path, original, updated))

    return plans


def _apply_updates(plans: list[tuple[Path, str, str]]) -> list[str]:
    written: list[tuple[Path, str]] = []
    try:
        for path, original, updated in plans:
            _atomic_write(path, updated)
            written.append((path, original))
    except Exception:
        # Best-effort rollback of earlier files if a later filesystem write fails.
        for path, original in reversed(written):
            try:
                _atomic_write(path, original)
            except OSError:
                print(f"Aviso: rollback falhou para {path}", file=sys.stderr)
        raise
    return [path.name for path, _original, _updated in plans]


def pin_native_dependencies(native_root: str | Path) -> list[str]:
    """Change known moving refs to pinned SHAs; return the filenames changed."""
    return _apply_updates(_plan_updates(native_root, restore=False))


def restore_native_dependencies(native_root: str | Path) -> list[str]:
    """Restore known pinned refs to upstream 'main' without overwriting unknown values."""
    return _apply_updates(_plan_updates(native_root, restore=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fixa ou restaura revisões Meson wrap conhecidas do porte nativo."
    )
    parser.add_argument(
        "native_root",
        nargs="?",
        default="vendor/pokeplatinum-native",
        help="Diretório do checkout nativo (padrão: vendor/pokeplatinum-native).",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restaura as revisões fixadas para a referência upstream main após o build.",
    )
    args = parser.parse_args(argv)
    try:
        if args.restore:
            changed = restore_native_dependencies(args.native_root)
            action = "Restauradas"
        else:
            changed = pin_native_dependencies(args.native_root)
            action = "Fixadas"
    except (OSError, PinningError) as exc:
        print(f"Erro ao atualizar dependências: {exc}", file=sys.stderr)
        return 2

    if changed:
        print(f"{action} revisões Meson: " + ", ".join(changed))
    else:
        print("Nenhuma alteração necessária nas revisões Meson.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
