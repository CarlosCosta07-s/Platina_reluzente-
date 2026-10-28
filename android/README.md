# Android port — status real

A etapa atual prepara o renderer real da revisão fixa cybervisi0n/libntr para OpenGL ES 3.2 e valida os quatro shaders. Ela ainda não gera um APK jogável do Pokémon Platinum.

Nesta etapa:
- solicitar SDL/OpenGL ES 3.2 no alvo Android, sem alterar o contexto desktop;
- selecionar headers GLES 3.2 e não inicializar o loader GL desktop no Android;
- selecionar o backend GLES3 do Dear ImGui;
- converter os quatro shaders GLSL 4.20 core para GLSL ES 3.20 e validá-los com glslangValidator;
- detectar GL_EXT_texture_border_clamp; se não houver extensão, usar CLAMP_TO_EDGE com aviso explícito de que as bordas não são idênticas.

O que ainda falta:
1. configurar um alvo Android consistente nos projetos Meson raiz e libntr;
2. compilar e empacotar SDL2 para Android e integrar ciclo de vida/activity;
3. resolver ENet e ferramentas de build que hoje pressupõem Windows/Linux;
4. cross-compilar a lógica nativa para arm64-v8a com Android NDK;
5. integrar toque, controles, áudio, armazenamento e pause/resume;
6. testar renderer, duas telas, inicialização, áudio e save em aparelho Android.

O workflow Android GLES graphics preparation é uma validação dos shaders e das alterações de fonte, não uma build do jogo. A CI não inclui ROM nem recursos proprietários.
