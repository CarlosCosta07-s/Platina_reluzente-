#include <EGL/egl.h>
#include <EGL/eglext.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#if defined(PLATINA_USE_GLES3)
#include <GLES3/gl3.h>
#else
#define GL_GLEXT_PROTOTYPES 1
#include <GL/glcorearb.h>
#endif

namespace {

constexpr int kWidth = 64;
constexpr int kHeight = 64;

struct EglContext {
    EGLDisplay display = EGL_NO_DISPLAY;
    EGLContext context = EGL_NO_CONTEXT;
    EGLSurface surface = EGL_NO_SURFACE;

    void create() {
        auto getPlatformDisplay = reinterpret_cast<PFNEGLGETPLATFORMDISPLAYEXTPROC>(
            eglGetProcAddress("eglGetPlatformDisplayEXT"));
        if (!getPlatformDisplay) {
            throw std::runtime_error("eglGetPlatformDisplayEXT is unavailable");
        }

        display = getPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA,
                                     EGL_DEFAULT_DISPLAY, nullptr);
        if (display == EGL_NO_DISPLAY) {
            throw std::runtime_error("Cannot get Mesa surfaceless EGL display");
        }

        EGLint major = 0;
        EGLint minor = 0;
        if (!eglInitialize(display, &major, &minor)) {
            throw std::runtime_error("eglInitialize failed");
        }

#if defined(PLATINA_USE_GLES3)
        if (!eglBindAPI(EGL_OPENGL_ES_API)) {
            throw std::runtime_error("eglBindAPI OpenGL ES failed");
        }
        const EGLint renderableType = EGL_OPENGL_ES3_BIT_KHR;
#else
        if (!eglBindAPI(EGL_OPENGL_API)) {
            throw std::runtime_error("eglBindAPI OpenGL failed");
        }
        const EGLint renderableType = EGL_OPENGL_BIT;
#endif

        const EGLint configAttributes[] = {
            EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
            EGL_RENDERABLE_TYPE, renderableType,
            EGL_RED_SIZE, 8,
            EGL_GREEN_SIZE, 8,
            EGL_BLUE_SIZE, 8,
            EGL_ALPHA_SIZE, 8,
            EGL_NONE
        };
        EGLConfig config = nullptr;
        EGLint configCount = 0;
        if (!eglChooseConfig(display, configAttributes, &config, 1, &configCount)
            || configCount != 1) {
            throw std::runtime_error("eglChooseConfig failed for requested API");
        }

        const EGLint surfaceAttributes[] = {
            EGL_WIDTH, kWidth,
            EGL_HEIGHT, kHeight,
            EGL_NONE
        };
        surface = eglCreatePbufferSurface(display, config, surfaceAttributes);
        if (surface == EGL_NO_SURFACE) {
            throw std::runtime_error("eglCreatePbufferSurface failed");
        }

#if defined(PLATINA_USE_GLES3)
        const EGLint contextAttributes[] = {
            EGL_CONTEXT_CLIENT_VERSION, 3,
            EGL_NONE
        };
#else
        const EGLint contextAttributes[] = {
            EGL_CONTEXT_MAJOR_VERSION_KHR, 4,
            EGL_CONTEXT_MINOR_VERSION_KHR, 2,
            EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR,
            EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT_KHR,
            EGL_NONE
        };
#endif
        context = eglCreateContext(display, config, EGL_NO_CONTEXT, contextAttributes);
        if (context == EGL_NO_CONTEXT) {
            throw std::runtime_error("eglCreateContext failed");
        }
        if (!eglMakeCurrent(display, surface, surface, context)) {
            throw std::runtime_error("eglMakeCurrent failed");
        }

        const char *version = reinterpret_cast<const char *>(glGetString(GL_VERSION));
        if (!version) {
            throw std::runtime_error("GL_VERSION is unavailable after EGL context creation");
        }
        GLint actualMajor = 0;
        GLint actualMinor = 0;
        glGetIntegerv(GL_MAJOR_VERSION, &actualMajor);
        glGetIntegerv(GL_MINOR_VERSION, &actualMinor);
#if defined(PLATINA_USE_GLES3)
        if (actualMajor < 3) {
            throw std::runtime_error("The host GLES context is older than OpenGL ES 3.0");
        }
#else
        if (actualMajor < 4 || (actualMajor == 4 && actualMinor < 2)) {
            throw std::runtime_error("The host Desktop context is older than OpenGL 4.2");
        }
#endif
        std::cout << "GL_VERSION=" << version << "\n";
    }

    ~EglContext() {
        if (display != EGL_NO_DISPLAY) {
            eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
            if (context != EGL_NO_CONTEXT) eglDestroyContext(display, context);
            if (surface != EGL_NO_SURFACE) eglDestroySurface(display, surface);
            eglTerminate(display);
        }
    }
};

struct Vertex {
    GLfloat position[3];
    GLfloat texCoord[2];
    GLfloat color[4];
};

struct Scene {
    const char *name;
    GLint useTexture;
    GLint polygonMode;
    GLint useFog;
    GLint clampS;
    GLint clampT;
    int wrapS;
    int wrapT;
    bool borderCoordinates;
};

enum WrapMode {
    kRepeat = 0,
    kMirror = 1,
    kBorder = 2
};

const std::array<Scene, 10> kScenes = {{
    {"untextured_vertex_color", 0, 0, 0, 0, 0, kRepeat, kRepeat, false},
    {"texture_times_vertex_color", 1, 0, 0, 0, 0, kRepeat, kRepeat, false},
    {"texture_only", 1, 1, 0, 0, 0, kRepeat, kRepeat, false},
    {"alpha_discard", 1, 0, 0, 0, 0, kRepeat, kRepeat, false},
    {"fogged_texture", 1, 1, 1, 0, 0, kRepeat, kRepeat, false},
    {"transparent_border_s", 1, 1, 0, 1, 0, kBorder, kRepeat, true},
    {"transparent_border_t", 1, 1, 0, 0, 1, kRepeat, kBorder, true},
    {"transparent_border_st", 1, 1, 0, 1, 1, kBorder, kBorder, true},
    {"repeat_s_t", 1, 1, 0, 0, 0, kRepeat, kRepeat, true},
    {"mirror_s_t", 1, 1, 0, 0, 0, kMirror, kMirror, true}
}};

std::string readText(const std::string &path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("Cannot read shader: " + path);
    return std::string(std::istreambuf_iterator<char>(stream),
                       std::istreambuf_iterator<char>());
}

GLuint compileShader(GLenum type, const std::string &source, const char *name) {
    GLuint shader = glCreateShader(type);
    const char *text = source.c_str();
    glShaderSource(shader, 1, &text, nullptr);
    glCompileShader(shader);

    GLint compiled = GL_FALSE;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &compiled);
    if (compiled != GL_TRUE) {
        GLint length = 0;
        glGetShaderiv(shader, GL_INFO_LOG_LENGTH, &length);
        std::string log(static_cast<size_t>(length > 1 ? length : 1), '\0');
        glGetShaderInfoLog(shader, length, nullptr, log.data());
        glDeleteShader(shader);
        throw std::runtime_error(std::string(name) + " shader compile failed:\n" + log);
    }
    return shader;
}

GLuint createProgram(const std::string &vertexSource, const std::string &fragmentSource) {
    const GLuint vertex = compileShader(GL_VERTEX_SHADER, vertexSource, "G3 vertex");
    const GLuint fragment = compileShader(GL_FRAGMENT_SHADER, fragmentSource, "G3 fragment");
    const GLuint program = glCreateProgram();
    glAttachShader(program, vertex);
    glAttachShader(program, fragment);
    glLinkProgram(program);
    glDeleteShader(vertex);
    glDeleteShader(fragment);

    GLint linked = GL_FALSE;
    glGetProgramiv(program, GL_LINK_STATUS, &linked);
    if (linked != GL_TRUE) {
        GLint length = 0;
        glGetProgramiv(program, GL_INFO_LOG_LENGTH, &length);
        std::string log(static_cast<size_t>(length > 1 ? length : 1), '\0');
        glGetProgramInfoLog(program, length, nullptr, log.data());
        glDeleteProgram(program);
        throw std::runtime_error("G3 program link failed:\n" + log);
    }
    return program;
}

GLint uniformLocation(GLuint program, const char *name) {
    return glGetUniformLocation(program, name);
}

void setInt(GLuint program, const char *name, GLint value) {
    const GLint location = uniformLocation(program, name);
    if (location >= 0) glUniform1i(location, value);
}

void setFloat(GLuint program, const char *name, GLfloat value) {
    const GLint location = uniformLocation(program, name);
    if (location >= 0) glUniform1f(location, value);
}

void setVec4(GLuint program, const char *name, const GLfloat *value) {
    const GLint location = uniformLocation(program, name);
    if (location >= 0) glUniform4fv(location, 1, value);
}

void setFloatArray(GLuint program, const char *name, const GLfloat *values, GLsizei count) {
    const GLint location = uniformLocation(program, name);
    if (location >= 0) glUniform1fv(location, count, values);
}

GLuint createTexture() {
    constexpr int textureSize = 8;
    std::array<std::uint8_t, textureSize * textureSize * 4> pixels{};
    for (int y = 0; y < textureSize; ++y) {
        for (int x = 0; x < textureSize; ++x) {
            const size_t offset = static_cast<size_t>((y * textureSize + x) * 4);
            pixels[offset + 0] = static_cast<std::uint8_t>((x * 31 + y * 11 + 13) & 0xff);
            pixels[offset + 1] = static_cast<std::uint8_t>((x * 7 + y * 29 + 71) & 0xff);
            pixels[offset + 2] = static_cast<std::uint8_t>((x * 13 + y * 5 + 151) & 0xff);
            const int alphaPattern = (x + y) % 3;
            pixels[offset + 3] = static_cast<std::uint8_t>(
                alphaPattern == 0 ? 0 : (alphaPattern == 1 ? 96 : 255));
        }
    }

    GLuint texture = 0;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, textureSize, textureSize,
                 0, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    const GLfloat transparentBorder[4] = {0.0f, 0.0f, 0.0f, 0.0f};
#if !defined(PLATINA_USE_GLES3)
    glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, transparentBorder);
#endif
    return texture;
}

GLuint createFramebuffer(GLuint &colorTexture) {
    glGenTextures(1, &colorTexture);
    glBindTexture(GL_TEXTURE_2D, colorTexture);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, kWidth, kHeight,
                 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);

    GLuint framebuffer = 0;
    glGenFramebuffers(1, &framebuffer);
    glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, colorTexture, 0);
    const GLenum drawBuffer = GL_COLOR_ATTACHMENT0;
    glDrawBuffers(1, &drawBuffer);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        throw std::runtime_error("RGBA8 test framebuffer is incomplete");
    }
    return framebuffer;
}

void configureWrap(GLenum coordinate, int mode) {
    GLint value = GL_REPEAT;
    if (mode == kMirror) value = GL_MIRRORED_REPEAT;
#if defined(PLATINA_USE_GLES3)
    if (mode == kBorder) value = GL_CLAMP_TO_EDGE;
#else
    if (mode == kBorder) value = GL_CLAMP_TO_BORDER;
#endif
    glTexParameteri(GL_TEXTURE_2D, coordinate, value);
}

void renderScene(GLuint program, GLuint texture, const Scene &scene,
                 const std::array<Vertex, 4> &baseVertices,
                 std::ofstream &output) {
    std::array<Vertex, 4> vertices = baseVertices;
    if (scene.borderCoordinates) {
        vertices[0].texCoord[0] = -0.25f; vertices[0].texCoord[1] = -0.25f;
        vertices[1].texCoord[0] =  1.25f; vertices[1].texCoord[1] = -0.25f;
        vertices[2].texCoord[0] = -0.25f; vertices[2].texCoord[1] =  1.25f;
        vertices[3].texCoord[0] =  1.25f; vertices[3].texCoord[1] =  1.25f;
    }

    static GLuint vao = 0;
    static GLuint vbo = 0;
    if (vao == 0) {
        glGenVertexArrays(1, &vao);
        glGenBuffers(1, &vbo);
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices.data(), GL_DYNAMIC_DRAW);
        glEnableVertexAttribArray(0);
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                              reinterpret_cast<void *>(offsetof(Vertex, position)));
        glEnableVertexAttribArray(1);
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                              reinterpret_cast<void *>(offsetof(Vertex, texCoord)));
        glEnableVertexAttribArray(2);
        glVertexAttribPointer(2, 4, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                              reinterpret_cast<void *>(offsetof(Vertex, color)));
    } else {
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glBufferSubData(GL_ARRAY_BUFFER, 0, sizeof(vertices), vertices.data());
    }

    glViewport(0, 0, kWidth, kHeight);
    glDisable(GL_BLEND);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_DITHER);
    glClearColor(0.07f, 0.11f, 0.19f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);

    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, texture);
    configureWrap(GL_TEXTURE_WRAP_S, scene.wrapS);
    configureWrap(GL_TEXTURE_WRAP_T, scene.wrapT);

    glUseProgram(program);
    setInt(program, "myTexture", 0);
    setInt(program, "useTexture", scene.useTexture);
    setInt(program, "polygonMode", scene.polygonMode);
    setInt(program, "useFog", scene.useFog);
#if defined(PLATINA_USE_GLES3)
    setInt(program, "clampToBorderS", scene.clampS);
    setInt(program, "clampToBorderT", scene.clampT);
#endif

    const GLfloat fogColor[4] = {0.12f, 0.24f, 0.78f, 0.65f};
    setVec4(program, "fogColor", fogColor);
    std::array<GLfloat, 32> fogBoundaries{};
    std::array<GLfloat, 32> fogDensities{};
    for (int i = 0; i < 32; ++i) {
        fogBoundaries[static_cast<size_t>(i)] = static_cast<GLfloat>(i) / 31.0f;
        fogDensities[static_cast<size_t>(i)] = static_cast<GLfloat>((31 - i) % 9) / 8.0f;
    }
    setFloatArray(program, "fogDepthBoundary[0]", fogBoundaries.data(), 32);
    setFloatArray(program, "fogDensity[0]", fogDensities.data(), 32);

    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    glFinish();

    std::vector<std::uint8_t> pixels(static_cast<size_t>(kWidth * kHeight * 4));
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(0, 0, kWidth, kHeight, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
    if (!output.write(reinterpret_cast<const char *>(pixels.data()),
                      static_cast<std::streamsize>(pixels.size()))) {
        throw std::runtime_error(std::string("Cannot write rendered scene: ") + scene.name);
    }
}

} // namespace

int main(int argc, char **argv) {
    if (argc != 4) {
        std::cerr << "Usage: renderer_g3_pixel_probe <vertex.glsl> <fragment.glsl> <out.rgba>\n";
        return 2;
    }

    try {
        EglContext egl;
        egl.create();

        const GLuint program = createProgram(readText(argv[1]), readText(argv[2]));
        GLuint texture = createTexture();
        GLuint colorTexture = 0;
        GLuint framebuffer = createFramebuffer(colorTexture);
        (void)framebuffer;

        const std::array<Vertex, 4> vertices = {{
            {{-1.0f, -1.0f, 0.12f}, {0.0f, 0.0f}, {1.0f, 0.8f, 0.65f, 1.0f}},
            {{ 1.0f, -1.0f, 0.34f}, {1.0f, 0.0f}, {0.65f, 1.0f, 0.75f, 0.85f}},
            {{-1.0f,  1.0f, 0.68f}, {0.0f, 1.0f}, {0.75f, 0.7f, 1.0f, 0.9f}},
            {{ 1.0f,  1.0f, 0.88f}, {1.0f, 1.0f}, {0.95f, 0.9f, 0.8f, 1.0f}}
        }};

        std::ofstream output(argv[3], std::ios::binary);
        if (!output) throw std::runtime_error("Cannot create RGBA output file");
        for (const Scene &scene : kScenes) {
            renderScene(program, texture, scene, vertices, output);
            std::cout << "Rendered " << scene.name << "\n";
        }
        output.close();

        glDeleteProgram(program);
        glDeleteTextures(1, &texture);
        glDeleteTextures(1, &colorTexture);
    } catch (const std::exception &error) {
        std::cerr << "G3 host pixel probe failed: " << error.what() << "\n";
        return 1;
    }

    return 0;
}
