#pragma once

// Include this header only in the mobile GLES 3.0 build of the pinned libntr.
// Desktop and Nintendo Switch builds continue to use their existing GL loaders.
#if !defined(SDK_BUILD_ANDROID) && !defined(SDK_BUILD_IOS)
#error "sim_gles3_compat.h is only for Android/iOS GLES 3.0 builds."
#endif

#include <GLES3/gl3.h>
#include <GLES3/gl3ext.h>
#include "program_uniform_compat.hpp"

// The upstream renderer uses desktop glProgramUniform calls to write uniforms
// in programs that are not necessarily active. Route those call sites through
// the state-preserving GLES 3.0 adapters for mobile builds only.
#define glProgramUniform1i(program, location, value) \
    ::SIM::GLES3Compat::ProgramUniform1i((program), (location), (value))
#define glProgramUniform1f(program, location, value) \
    ::SIM::GLES3Compat::ProgramUniform1f((program), (location), (value))
#define glProgramUniform4f(program, location, v0, v1, v2, v3) \
    ::SIM::GLES3Compat::ProgramUniform4f((program), (location), (v0), (v1), (v2), (v3))
#define glProgramUniform1fv(program, location, count, values) \
    ::SIM::GLES3Compat::ProgramUniform1fv((program), (location), (count), (values))
