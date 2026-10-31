#pragma once

typedef unsigned int GLenum;
typedef unsigned int GLuint;
typedef int GLint;
typedef int GLsizei;
typedef float GLfloat;

#define GL_CURRENT_PROGRAM 0x8B8D

#ifdef __cplusplus
extern "C" {
#endif

void glGetIntegerv(GLenum pname, GLint *data);
void glUseProgram(GLuint program);
void glUniform1i(GLint location, GLint v0);
void glUniform1f(GLint location, GLfloat v0);
void glUniform4f(GLint location, GLfloat v0, GLfloat v1, GLfloat v2, GLfloat v3);
void glUniform1fv(GLint location, GLsizei count, const GLfloat *value);

#ifdef __cplusplus
}
#endif
