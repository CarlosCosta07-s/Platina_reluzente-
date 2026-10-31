# Variantes GLES 3.0 — fonte experimental

Estas quatro fontes são variantes móveis do renderer da revisão de libntr 1555d911ac80c0190ac1c321f99f1323de8b3c09. Elas não substituem nem editam as fontes Desktop do submódulo.

O arquivo `program_uniform_compat.hpp` é um helper GLES source-only para as quatro chamadas glProgramUniform usadas no renderer fixado. Ele preserva o programa ativo com um binding temporário. O teste de host usa uma API GLES simulada; o helper ainda não foi incluído no `libntr` e não passou por profiling em GPU. O header `sim_gles3_compat.h` reúne os includes GLES3 e mapeia essas quatro chamadas para os wrappers, mas também ainda não está integrado ao submódulo.

**Importante:** os arquivos ainda não estão ligados a um alvo de build Android/iOS e não constituem um renderer aprovado. São o primeiro passo source-only para avaliar a portabilidade GLSL ES 3.00.

## Correspondência

| Fonte Desktop | Variante desta pasta |
|---|---|
| libraries/sim/src/shaders/g2_vertex.glsl | g2_vertex.glsl |
| libraries/sim/src/shaders/g2_fragment.glsl | g2_fragment.glsl |
| libraries/sim/src/shaders/g3_vertex.glsl | g3_vertex.glsl |
| libraries/sim/src/shaders/g3_fragment.glsl | g3_fragment.glsl |

## Alteração de compatibilidade principal

ESSL 3.00 exige índices constantes nos arrays de samplers. O shader G2 desktop indexa bgTexture com bgNum e currentBgDrawn, e indexa objTexture com j e i. As variantes GLES usam sampleBg e sampleObj, cujos acessos a cada array usam índices literais.

Os arrays de floats fogDepthBoundary[32] e fogDensity[32] no shader G3 não são arrays de samplers e continuam com seleção dinâmica.

## Estado de validação

- [x] Variantes separadas das fontes Desktop.
- [x] Teste estático ROM-free impede indexação dinâmica de sampler arrays.
- [x] GLSL ES 3.00 compile e program link com glslangValidator no workflow host-only 41149162996.
- [x] Adaptador glProgramUniform C++ compila e passa teste de preservação de estado com GLES mock no host.
- [ ] Comparação pixel a pixel contra o Desktop GL 4.2.
- [ ] Renderer GLES exercitado em driver Android real.
- [ ] Mesmo conjunto de cenas aprovado em ANGLE/Metal para iOS.

Não adicionar integração Android/iOS nem executar builds móveis enquanto o contrato MOBILE_PARITY_CONTRACT.md não estiver integralmente aprovado.
