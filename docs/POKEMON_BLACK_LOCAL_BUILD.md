# Pokémon Black — teste local do porte nativo

> **Guia experimental para desenvolvimento local.** Não é um release nem uma autorização para redistribuir o código reconstruído ou binários. O projeto mantém a ROM, os recursos extraídos e os executáveis de Black fora do repositório e da CI. A licença do código reconstruído de Aletheia não concede permissões claras de redistribuição; resolva essa questão antes de publicar qualquer derivado.

Este roteiro usa o par de revisões já auditado pelo projeto:

- Eidos: `b79123f967980d1bb758161891205c03d606dec7`
- Aletheia: `6c2aae879f123bcbc028cf6a8b7f8df614402ac8`

A base documenta um build host x86-64: o código de jogo é compilado para wasm32 durante a etapa de build, convertido para C por `wasm2c` e então compilado pelo toolchain nativo. Não há interpretação de instruções ARM do Nintendo DS durante a partida. `WAMR` é opcional para mods WebAssembly e não é o executor do código do jogo.

## Pré-requisitos

- Uma cópia legal própria de Pokémon Black Version USA/Europe NDSi Enhanced. O par de revisões fixado documenta o SHA-1 `26ad0b9967aa279c4a266ee69f52b9b2332399a5`; compare a cópia local sem enviá-la ao GitHub.
- Git, Python 3.11+, CMake 3.16+, Ninja e um compilador C compatível.
- As dependências SDL3, WAMR, mbedTLS e WASI/WABT, obtidas pelos scripts do Eidos, que validam hashes dos arquivos baixados.
- Espaço em disco e memória suficientes para gerar e compilar o C nativo; use `--fast --host-jobs 2` para limitar o paralelismo enquanto testa.

## 1. Baixar as revisões fixadas

Execute a partir de uma pasta de desenvolvimento fora deste repositório:

```sh
git clone https://github.com/Project-Holon/eidos.git eidos
git -C eidos checkout b79123f967980d1bb758161891205c03d606dec7

git clone https://github.com/Project-Holon/aletheia.git aletheia
git -C aletheia checkout 6c2aae879f123bcbc028cf6a8b7f8df614402ac8
```

Confirme que `eidos/cmake/aletheia_pin.cmake` contém o commit Aletheia indicado acima. Não substitua silenciosamente esses pins por `main`: o código de jogo e a camada nativa precisam usar revisões compatíveis.

## 2. Extrair os dados localmente

A extração é executada pelo utilitário da própria Aletheia; ajuste o caminho para sua cópia:

```sh
cd aletheia
python3 tools/ndsrom.py extract "/caminho/local/Pokemon Black.nds" -o extract
cd ../eidos
```

O diretório `aletheia/extract/` contém dados derivados da ROM e deve permanecer fora do Git, dos artefatos públicos e de qualquer upload de CI. Não comite a ROM, os arquivos extraídos, saves nem capturas com dados pessoais.

## 3. Linux x86-64

Instale as dependências de desenvolvimento SDL3/áudio/entrada necessárias à sua distribuição. O workflow de verificação do projeto usa Ubuntu e explicita os pacotes requeridos. Depois, a partir da raiz de `eidos`:

```sh
python3 tools/fetch_sdl.py --flavor source --build --tag linux-x64
python3 tools/fetch_wamr.py
python3 tools/fetch_mbedtls.py
python3 tools/fetch_wasm.py

SDL_PREFIX="$(python3 tools/fetch_sdl.py --locate source --tag linux-x64)"
python3 tools/build64.py \
  --build-dir build64 \
  --fast --host-jobs 2 \
  --aletheia-root ../aletheia \
  --data-root "$(realpath ../aletheia/extract/data)" \
  --sdl3-prefix "$SDL_PREFIX"

file build64/host/eidos
```

O arquivo esperado pelo script de build é `build64/host/eidos`. Sua presença demonstra compilação, não garante que todas as áreas do jogo funcionem.

## 4. Windows x64

Use um ambiente MSYS2 **MINGW64** com CMake, Ninja, Python, `zip` e `unzip`. Siga o mesmo toolchain xPack GCC 14.2.0 e a mesma validação SHA-256 documentados em [pokemon-black-native-check.yml](../.github/workflows/pokemon-black-native-check.yml). A partir da raiz de `eidos`, em MSYS2:

```sh
python tools/fetch_sdl.py --flavor mingw
python tools/fetch_wamr.py
python tools/fetch_mbedtls.py

gcc_bin="$PWD/.cache/gcc/xpack-mingw-w64-gcc-14.2.0-1/bin"
CC="$gcc_bin/x86_64-w64-mingw32-gcc.exe" \
CXX="$gcc_bin/x86_64-w64-mingw32-g++.exe" \
  python tools/fetch_wasm.py

python tools/build64.py \
  --build-dir build64 \
  --fast --host-jobs 2 \
  --aletheia-root ../aletheia \
  --data-root "$(cygpath -m "$PWD/../aletheia/extract/data")" \
  --cc "$gcc_bin/x86_64-w64-mingw32-gcc.exe"

file build64/host/eidos.exe
```

O arquivo esperado é `build64/host/eidos.exe`. Os nomes exatos de pacotes e pré-requisitos podem mudar no upstream; compare sempre este roteiro com os [documentos oficiais de build do Eidos](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/docs/building.md).

## 5. Validação mínima antes de pensar na integração

1. Execute os testes `ctest --test-dir build --output-on-failure` para a configuração de testes que você construiu, quando aplicável.
2. Execute o binário local com os dados extraídos da própria ROM compatível.
3. Confirme tela de título, entrada, começo de jogo, primeira batalha, menu de campo, gravação e retomada de save.
4. Registre versão/commit, sistema operacional, comando de execução e erros. Não compartilhe ROM, saves, dados extraídos ou binários derivados publicamente.
5. Só depois dos resultados reproduzíveis devemos planejar integração ao launcher; por enquanto, o cartão de Black permanece informativo e sem ação de importar/iniciar.

## Referências

- [Eidos, revisão fixada](https://github.com/Project-Holon/eidos/tree/b79123f967980d1bb758161891205c03d606dec7)
- [Aletheia, revisão fixada](https://github.com/Project-Holon/aletheia/tree/6c2aae879f123bcbc028cf6a8b7f8df614402ac8)
- [Guia de build do Eidos](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/docs/building.md)
- [Arquitetura 64-bit e conversão wasm2c](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/docs/lp64.md)
- [Aviso legal do Eidos](https://github.com/Project-Holon/eidos/blob/b79123f967980d1bb758161891205c03d606dec7/LEGAL.md)
- [Situação de licença e plano do porte neste projeto](POKEMON_BLACK_PORT.md)
