# Android port — native cross-build milestone

The Android graphics preparation workflow validates the four GLES 3.2 shaders. A separate workflow attempts the next real milestone: compile the reconstructed game and pinned libntr renderer into an ARM64 Android shared library using the Android NDK, SDL2, and ENet.

This workflow does not create a final playable APK and does not bundle ROMs or extracted game data. The output libmain.so is a native build artifact for integration with SDLActivity. Still outstanding after this milestone: SDLActivity/Gradle packaging, ROM selection and data preparation, lifecycle and touch verification, audio, save data, and on-device smoke testing.

The Android path is isolated behind SDK_BUILD_ANDROID and does not replace desktop OpenGL 4.2. If the cross-build exposes missing macros, unsupported assembly, or link dependencies, the workflow will record the exact failure for the next patch.
