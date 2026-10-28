#!/usr/bin/env bash
set -Eeuo pipefail

# Check that the native executable can initialize its first-launch UI on Linux.
# It intentionally runs with no ROM or extracted runtime data in a temporary
# working directory. It does not test actual gameplay or a ROM load.

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Uso: $0 /caminho/para/build_linux/pokeplatinum/main [timeout-segundos]" >&2
  exit 2
fi

binary="$(realpath -- "$1")"
duration="${2:-15}"

if [[ ! -f "$binary" || ! -x "$binary" ]]; then
  echo "Executável nativo ausente ou sem permissão de execução: $binary" >&2
  exit 2
fi
if ! [[ "$duration" =~ ^[1-9][0-9]*$ ]]; then
  echo "Timeout deve ser um inteiro positivo em segundos." >&2
  exit 2
fi
for tool in xvfb-run timeout cp; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Ferramenta obrigatória ausente: $tool" >&2
    exit 2
  fi
done

workdir="$(mktemp -d)"
logfile="$(mktemp)"
cleanup() {
  rm -rf -- "$workdir"
  rm -f -- "$logfile"
}
trap cleanup EXIT

cp -- "$binary" "$workdir/main"
chmod u+x "$workdir/main"

echo "Testando inicialização pré-ROM por ${duration}s."
echo "Diretório temporário vazio: $workdir"
echo "Nenhuma ROM nem recurso do jogo será copiado para o teste."

status=0
(
  cd "$workdir"
  SDL_AUDIODRIVER=dummy LIBGL_ALWAYS_SOFTWARE=1 \
    xvfb-run -a timeout --signal=TERM --kill-after=3s "${duration}s" ./main
) >"$logfile" 2>&1 || status=$?

if [[ -s "$logfile" ]]; then
  cat "$logfile"
fi

if [[ "$status" -eq 124 ]]; then
  echo "PASS: o executável permaneceu ativo durante a janela de teste sem ROM."
  echo "Isso confirma apenas a inicialização pré-ROM; não comprova carregamento ou gameplay."
  exit 0
fi

echo "FAIL: o executável saiu antes do timeout (código $status)." >&2
echo "Consulte as mensagens acima; inicialização pré-ROM não foi confirmada." >&2
exit 1
