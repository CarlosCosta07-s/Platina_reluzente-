#include <cassert>
#include <cstddef>
#include "mobile/renderer/gles300/sim_gles3_compat.h"

static GLint currentProgram = 7;
static GLuint expectedProgram = 0;
static int bindCalls = 0;
static int uniformCalls = 0;

extern "C" {
void glGetIntegerv(GLenum pname, GLint *data) {
    assert(pname == GL_CURRENT_PROGRAM);
    *data = currentProgram;
}

void glUseProgram(GLuint program) {
    currentProgram = static_cast<GLint>(program);
    ++bindCalls;
}

static void checkProgram() {
    assert(currentProgram == static_cast<GLint>(expectedProgram));
    ++uniformCalls;
}

void glUniform1i(GLint, GLint) { checkProgram(); }
void glUniform1f(GLint, GLfloat) { checkProgram(); }
void glUniform4f(GLint, GLfloat, GLfloat, GLfloat, GLfloat) { checkProgram(); }
void glUniform1fv(GLint, GLsizei, const GLfloat *) { checkProgram(); }
}

int main() {
    expectedProgram = 42;
    glProgramUniform1i(42, 1, 9);
    assert(currentProgram == 7);
    assert(bindCalls == 2);
    assert(uniformCalls == 1);

    // The helper must not rebind when its target is already active.
    currentProgram = 42;
    bindCalls = 0;
    glProgramUniform1f(42, 2, 0.5f);
    assert(currentProgram == 42);
    assert(bindCalls == 0);
    assert(uniformCalls == 2);

    // Verify the remaining wrapper signatures and restoration to program zero.
    currentProgram = 0;
    glProgramUniform4f(42, 3, 1.0f, 2.0f, 3.0f, 4.0f);
    const GLfloat values[2] = {0.25f, 0.75f};
    glProgramUniform1fv(42, 4, 2, values);
    assert(currentProgram == 0);
    assert(uniformCalls == 4);
    assert(bindCalls == 4);

    return 0;
}
