#!/usr/bin/env python3
"""Audit desktop OpenGL assumptions before adding an Android graphics backend.

The audit is diagnostic, not a claim that Android is already supported. It
inspects the checked-out native source and produces deterministic JSON or
Markdown without modifying the upstream source tree.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hh", ".hpp", ".glsl", ".vert", ".frag"}
SHADER_VERSION_RE = re.compile(r"^\s*#\s*version\s+(\d+)(?:\s+(core|compatibility|es))?", re.MULTILINE)
DESKTOP_GL_PATTERNS: dict[str, re.Pattern[str]] = {
    "GLSL desktop core shader declaration": re.compile(r"^\s*#\s*version\s+4\d\d\s+core\b"),
    "SDL desktop OpenGL context request": re.compile(r"SDL_GL_SetAttribute\s*\(\s*SDL_GL_CONTEXT_(?:MAJOR|MINOR)_VERSION\s*,"),
    "border-clamp texture mode": re.compile(r"\bGL_CLAMP_TO_BORDER\b"),
    "program-uniform direct state calls": re.compile(r"\bglProgramUniform\w*\s*\("),
    "desktop polygon-mode call": re.compile(r"\bglPolygonMode\s*\("),
    "GL debug output callback": re.compile(r"\bglDebugMessageCallback\s*\("),
}


class GraphicsAuditError(RuntimeError):
    """Raised when the requested source tree cannot be audited."""


def audit_android_graphics(source_root: str | Path) -> dict[str, object]:
    """Inspect libntr's simulator source and return a stable compatibility report."""
    native_root = Path(source_root).expanduser().resolve()
    libntr_root = native_root / "subprojects" / "libntr"
    if not libntr_root.is_dir():
        raise GraphicsAuditError(
            f"libntr source is missing at {libntr_root}; run the native build setup first."
        )

    scan_roots = [
        libntr_root / "libraries" / "sim" / "src",
        libntr_root / "libraries" / "sim" / "include",
    ]
    files = sorted(
        {
            path
            for root in scan_roots
            if root.is_dir()
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES
        },
        key=lambda p: p.as_posix().casefold(),
    )
    if not files:
        raise GraphicsAuditError(
            "No simulator source or shader files were found in the libntr source tree."
        )

    version_counts: dict[str, int] = {}
    shader_files: list[dict[str, object]] = []
    findings: dict[str, list[dict[str, object]]] = {
        key: [] for key in DESKTOP_GL_PATTERNS
    }
    context_request: dict[str, object] = {
        "major": None,
        "minor": None,
        "profile_core": False,
    }
    major_re = re.compile(
        r"SDL_GL_SetAttribute\s*\(\s*SDL_GL_CONTEXT_MAJOR_VERSION\s*,\s*(\d+)\s*\)"
    )
    minor_re = re.compile(
        r"SDL_GL_SetAttribute\s*\(\s*SDL_GL_CONTEXT_MINOR_VERSION\s*,\s*(\d+)\s*\)"
    )

    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise GraphicsAuditError(f"Could not read {path}: {exc}") from exc

        relative_path = path.relative_to(libntr_root).as_posix()
        major_match = major_re.search(content)
        minor_match = minor_re.search(content)
        if major_match:
            context_request["major"] = int(major_match.group(1))
        if minor_match:
            context_request["minor"] = int(minor_match.group(1))
        if "SDL_GL_CONTEXT_PROFILE_CORE" in content and "SDL_GL_CONTEXT_PROFILE_MASK" in content:
            context_request["profile_core"] = True

        for match in SHADER_VERSION_RE.finditer(content):
            version = match.group(1)
            profile = match.group(2) or "unspecified"
            key = f"{version} {profile}"
            version_counts[key] = version_counts.get(key, 0) + 1
            line_number = content.count("\n", 0, match.start()) + 1
            shader_files.append({
                "path": relative_path,
                "line": line_number,
                "version": version,
                "profile": profile,
            })

        lines = content.splitlines()
        for finding_name, pattern in DESKTOP_GL_PATTERNS.items():
            for index, line in enumerate(lines, start=1):
                if pattern.search(line):
                    findings[finding_name].append({
                        "path": relative_path,
                        "line": index,
                        "excerpt": line.strip()[:180],
                    })

    # Keep the report concise and repeatable when symbols appear many times.
    for key, occurrences in findings.items():
        unique: dict[tuple[str, int, str], dict[str, object]] = {}
        for item in occurrences:
            identity = (str(item["path"]), int(item["line"]), str(item["excerpt"]))
            unique[identity] = item
        findings[key] = list(unique.values())

    return {
        "source": "cybervisi0n/libntr simulator",
        "native_source_root": str(native_root),
        "libntr_source_commit_expected": "1555d911ac80c0190ac1c321f99f1323de8b3c09",
        "files_scanned": len(files),
        "context_request": context_request,
        "shader_versions": dict(sorted(version_counts.items())),
        "shader_declarations": shader_files,
        "api_findings": findings,
        "recommendation": (
            "An Android target cannot be enabled by changing only the SDL context. "
            "First port the desktop GLSL shaders, replace or feature-gate border-clamp "
            "behavior, and validate the renderer and Dear ImGui backend on OpenGL ES. "
            "Keep desktop OpenGL unchanged while the Android backend is developed."
        ),
    }


def render_markdown(report: dict[str, object]) -> str:
    """Render a compact, reviewable Markdown report."""
    context = report["context_request"]
    assert isinstance(context, dict)
    major, minor = context.get("major"), context.get("minor")
    if major is None or minor is None:
        context_text = "No explicit SDL OpenGL version request detected"
    else:
        profile = " core profile" if context.get("profile_core") else ""
        context_text = f"OpenGL {major}.{minor}{profile}"

    lines = [
        "# Android graphics compatibility audit",
        "",
        f"- Source: {report['source']}",
        f"- Simulator source files scanned: {report['files_scanned']}",
        f"- Detected desktop context request: **{context_text}**",
        "",
        "## Shader language versions",
        "",
    ]
    versions = report["shader_versions"]
    assert isinstance(versions, dict)
    if versions:
        for version, count in versions.items():
            lines.append(f"- GLSL {version}: {count} declaration(s)")
    else:
        lines.append("- No explicit GLSL version declaration detected.")
    declarations = report["shader_declarations"]
    assert isinstance(declarations, list)
    for item in declarations[:30]:
        assert isinstance(item, dict)
        lines.append(f"  - {item['path']}:{item['line']}")
    if len(declarations) > 30:
        lines.append(f"  - … and {len(declarations) - 30} more declarations")

    lines.extend(["", "## Desktop API usages to review", ""])
    findings = report["api_findings"]
    assert isinstance(findings, dict)
    any_findings = False
    for name, occurrences in findings.items():
        assert isinstance(occurrences, list)
        if not occurrences:
            continue
        any_findings = True
        lines.append(f"- **{name}** — {len(occurrences)} location(s)")
        for item in occurrences[:5]:
            assert isinstance(item, dict)
            lines.append(f"  - {item['path']}:{item['line']} — {item['excerpt']}")
        if len(occurrences) > 5:
            lines.append(f"  - … and {len(occurrences) - 5} more")
    if not any_findings:
        lines.append("- No known desktop-only symbols from this audit's rule set were detected.")

    lines.extend([
        "",
        "## Recommendation",
        "",
        str(report["recommendation"]),
        "",
        "This report is a source-level audit, not proof of Android compatibility or a working Android build.",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audita dependências de OpenGL desktop antes de implementar o backend Android."
    )
    parser.add_argument(
        "--source-root",
        default="vendor/pokeplatinum-native",
        help="Raiz do checkout do porte nativo (padrão: vendor/pokeplatinum-native).",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Formato do relatório.",
    )
    args = parser.parse_args(argv)

    try:
        report = audit_android_graphics(args.source_root)
    except (OSError, GraphicsAuditError) as exc:
        print(f"Erro na auditoria gráfica: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
