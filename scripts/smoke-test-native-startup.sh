#!/usr/bin/env bash
set -Eeuo pipefail

# Check that the native desktop package can initialize its first-launch UI on Linux.
# It runs in a temporary working directory without a ROM or extracted game data.
# For AppImages, ask the runtime to extract and run instead of requiring FUSE.

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Uso: $0 /caminho/para/build_linux/pokeplatinum/pokeplatinum.AppImage [segundos-ativos]" >&2
  exit 2
fi

binary="$(realpath -- "$1")"
duration="${2:-15}"

if [[ ! -f "$binary" || ! -x "$binary" ]]; then
  echo "Executável nativo ausente ou sem permissão de execução: $binary" >&2
  exit 2
fi
if ! [[ "$duration" =~ ^[1-9][0-9]*$ ]]; then
  echo "Duração deve ser um inteiro positivo em segundos." >&2
  exit 2
fi
for tool in xvfb-run timeout xdotool; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Ferramenta obrigatória ausente: $tool" >&2
    exit 2
  fi
done

workdir="$(mktemp -d)"
logfile="$(mktemp)"
app_log="$workdir/app.log"
cleanup() {
  rm -rf -- "$workdir"
  rm -f -- "$logfile"
}
trap cleanup EXIT

echo "Testando inicialização pré-ROM do pacote: janela visível + ${duration}s de processo ativo."
echo "Diretório temporário vazio: $workdir"
echo "Nenhuma ROM nem recurso do jogo será copiado para o teste."

status=0
(
  cd "$workdir"
  SDL_AUDIODRIVER=dummy LIBGL_ALWAYS_SOFTWARE=1 \
    xvfb-run -a timeout --signal=TERM --kill-after=3s "$((duration + 20))s" \
    bash -c '
      set -Eeuo pipefail
      logfile="$1"
      active_seconds="$2"

      executable_path="$3"
      APPIMAGE_EXTRACT_AND_RUN=1 "$executable_path" >"$logfile" 2>&1 &
      app_pid=$!
      cleanup_app() {
        if kill -0 "$app_pid" 2>/dev/null; then
          kill -TERM "$app_pid" 2>/dev/null || true
        fi
        wait "$app_pid" 2>/dev/null || true
      }
      trap cleanup_app EXIT

      found=0
      for _ in $(seq 1 10); do
        if ! kill -0 "$app_pid" 2>/dev/null; then
          cat "$logfile" >&2 || true
          echo "Executável encerrou antes de criar a janela." >&2
          exit 1
        fi
        if xdotool search --onlyvisible --name "^libntr Application$" >/dev/null 2>&1; then
          found=1
          break
        fi
        sleep 1
      done

      if [[ "$found" -ne 1 ]]; then
        cat "$logfile" >&2 || true
        echo "Janela visível 'libntr Application' não foi encontrada." >&2
        exit 1
      fi

      echo "Janela visível encontrada; verificando estabilidade por ${active_seconds}s."
      sleep "$active_seconds"
      if ! kill -0 "$app_pid" 2>/dev/null; then
        cat "$logfile" >&2 || true
        echo "Executável encerrou antes do fim da janela de teste." >&2
        exit 1
      fi
      if [[ -s "$logfile" ]]; then
        echo "Saída do executável:"
        cat "$logfile"
      fi
      echo "PASS: janela criada e processo permaneceu ativo."
      echo "Isso confirma apenas a inicialização pré-ROM; não comprova carregamento ou gameplay."
    ' smoke-test "$app_log" "$duration" "$binary"
) >"$logfile" 2>&1 || status=$?

if [[ -s "$logfile" ]]; then
  cat "$logfile"
fi

if [[ "$status" -eq 0 ]]; then
  exit 0
fi

echo "FAIL: o smoke test pré-ROM falhou (código $status)." >&2
echo "Consulte as mensagens acima; inicialização gráfica não foi confirmada." >&2
exit 1
