#!/usr/bin/env bash
set -Eeuo pipefail

target="${1:-linux}"
case "$target" in
  linux|win64) ;;
  *)
    printf 'Alvo inválido: %s\n' "$target" >&2
    printf 'Uso: %s [linux|win64]\n' "$0" >&2
    exit 2
    ;;
esac

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
native_dir="$repo_root/vendor/pokeplatinum-native"
pin_script="$repo_root/scripts/pin_native_dependencies.py"

if [[ ! -f "$native_dir/Makefile" ]]; then
  printf 'Submódulo nativo não inicializado. Execute:\n  git submodule update --init --recursive\n' >&2
  exit 2
fi

if ! command -v make >/dev/null 2>&1; then
  printf 'A ferramenta make não foi encontrada no PATH. Instale as dependências documentadas pelo upstream.\n' >&2
  exit 127
fi

python_bin="$(command -v python3 || true)"
if [[ -z "$python_bin" ]]; then
  printf 'Python 3 não foi encontrado no PATH; ele é necessário para fixar dependências de forma reproduzível.\n' >&2
  exit 127
fi

restore_pins() {
  "$python_bin" "$pin_script" --restore "$native_dir" || {
    printf 'Aviso: não foi possível restaurar as referências Meson; revise %s/subprojects/*.wrap.\n' "$native_dir" >&2
  }
}
trap restore_pins EXIT

"$python_bin" "$pin_script" "$native_dir"
make -C "$native_dir" "$target"
