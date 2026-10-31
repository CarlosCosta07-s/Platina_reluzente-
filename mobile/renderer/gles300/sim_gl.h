#pragma once

// One GL declaration boundary for simulator sources and headers.
// Mobile uses the GLES 3.0 API; Desktop and Switch retain the pinned loaders.
#if defined(SDK_BUILD_ANDROID) || defined(SDK_BUILD_IOS)
#include <GLES3/gl3.h>
#include <GLES3/gl3ext.h>
#elif defined(SDK_BUILD_NX)
#include <glad/glad.h>
#else
#include <simulator/glad/glad.h>
#endif
