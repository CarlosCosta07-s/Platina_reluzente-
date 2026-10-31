#pragma once

// Source-only compatibility layer for the pinned libntr renderer.
// Include after GLES3/gl3.h. Do not include this header in Desktop builds.
#if !defined(SDK_BUILD_ANDROID) && !defined(SDK_BUILD_IOS)
#error "GLES3 program-uniform compatibility is only for Android/iOS targets."
#endif

#include <GLES3/gl3.h>

namespace SIM::GLES3Compat {

class ScopedProgramBinding final {
public:
    explicit ScopedProgramBinding(GLuint targetProgram) {
        glGetIntegerv(GL_CURRENT_PROGRAM, &previousProgram_);
        changed_ = static_cast<GLuint>(previousProgram_) != targetProgram;
        if (changed_) {
            glUseProgram(targetProgram);
        }
    }

    ~ScopedProgramBinding() {
        if (changed_) {
            glUseProgram(static_cast<GLuint>(previousProgram_));
        }
    }

    ScopedProgramBinding(const ScopedProgramBinding &) = delete;
    ScopedProgramBinding &operator=(const ScopedProgramBinding &) = delete;
    ScopedProgramBinding(ScopedProgramBinding &&) = delete;
    ScopedProgramBinding &operator=(ScopedProgramBinding &&) = delete;

private:
    GLint previousProgram_ = 0;
    bool changed_ = false;
};

inline void ProgramUniform1i(GLuint program, GLint location, GLint value) {
    ScopedProgramBinding binding(program);
    glUniform1i(location, value);
}

inline void ProgramUniform1f(GLuint program, GLint location, GLfloat value) {
    ScopedProgramBinding binding(program);
    glUniform1f(location, value);
}

inline void ProgramUniform4f(
    GLuint program,
    GLint location,
    GLfloat v0,
    GLfloat v1,
    GLfloat v2,
    GLfloat v3
) {
    ScopedProgramBinding binding(program);
    glUniform4f(location, v0, v1, v2, v3);
}

inline void ProgramUniform1fv(
    GLuint program,
    GLint location,
    GLsizei count,
    const GLfloat *value
) {
    ScopedProgramBinding binding(program);
    glUniform1fv(location, count, value);
}

} // namespace SIM::GLES3Compat
