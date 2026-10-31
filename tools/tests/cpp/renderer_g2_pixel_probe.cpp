#include <EGL/egl.h>
#include <EGL/eglext.h>

#include <array>
#include <cstddef>
#include <cstdint>
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
constexpr size_t kBytesPerScene = static_cast<size_t>(kWidth * kHeight * 4);

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
        if (display == EGL_NO_DISPLAY || !eglInitialize(display, nullptr, nullptr)) {
            throw std::runtime_error("Cannot initialize Mesa surfaceless EGL display");
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
            EGL_WIDTH, kWidth, EGL_HEIGHT, kHeight, EGL_NONE
        };
        surface = eglCreatePbufferSurface(display, config, surfaceAttributes);
        if (surface == EGL_NO_SURFACE) {
            throw std::runtime_error("eglCreatePbufferSurface failed");
        }

#if defined(PLATINA_USE_GLES3)
        const EGLint contextAttributes[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
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
        if (context == EGL_NO_CONTEXT
            || !eglMakeCurrent(display, surface, surface, context)) {
            throw std::runtime_error("Cannot create or activate EGL GL context");
        }

        GLint major = 0;
        GLint minor = 0;
        glGetIntegerv(GL_MAJOR_VERSION, &major);
        glGetIntegerv(GL_MINOR_VERSION, &minor);
#if defined(PLATINA_USE_GLES3)
        if (major < 3) throw std::runtime_error("GLES context is older than 3.0");
#else
        if (major < 4 || (major == 4 && minor < 2)) {
            throw std::runtime_error("Desktop GL context is older than 4.2");
        }
#endif
        const auto *version = reinterpret_cast<const char *>(glGetString(GL_VERSION));
        if (!version) throw std::runtime_error("GL_VERSION is unavailable");
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
};

struct Scene {
    const char *name;
    std::array<GLint, 4> order;
    std::array<GLint, 4> priorities;
    GLint bldcnt;
    GLint bldalpha;
    GLint bldy;
    GLint topScreen;
    GLint dispcnt;
    GLint winout;
    GLint bg0as3d;
    GLint masterMode;
    GLfloat masterFactor;
};

constexpr GLint kBackdropTarget2 = 1 << 13;
constexpr GLint kObjTarget2 = 1 << 12;

const std::array<Scene, 14> kScenes = {{
    {"backdrop_top", {0, 1, 2, 3}, {3, 2, 1, 0}, 0, 0, 0, 1, 0, 0xffff, 0, 0, 0.0f},
    {"backdrop_bottom", {0, 1, 2, 3}, {3, 2, 1, 0}, 0, 0, 0, 0, 0, 0xffff, 0, 0, 0.0f},
    {"bg_stack_default_order", {0, 1, 2, 3}, {3, 2, 1, 0}, 0, 0, 0, 1, 0, 0xffff, 0, 0, 0.0f},
    {"bg_stack_permuted_order", {2, 0, 3, 1}, {1, 3, 0, 2}, 0, 0, 0, 0, 0, 0xffff, 0, 0, 0.0f},
    {"alpha_bg_over_bg", {0, 1, 2, 3}, {3, 2, 1, 0}, (1 << 6) | (1 << 1) | (1 << 8), (9 << 8) | 7, 0, 1, 0, 0xffff, 0, 0, 0.0f},
    {"alpha_bg_over_backdrop", {0, 1, 2, 3}, {3, 2, 1, 0}, (1 << 6) | (1 << 0) | kBackdropTarget2, (6 << 8) | 10, 0, 0, 0, 0xffff, 0, 0, 0.0f},
    {"alpha_bg_over_obj", {0, 1, 2, 3}, {3, 2, 1, 0}, (1 << 6) | (1 << 0) | kObjTarget2, (8 << 8) | 8, 0, 1, 0, 0xffff, 0, 0, 0.0f},
    {"brightness_increase", {0, 1, 2, 3}, {3, 2, 1, 0}, (2 << 6) | (1 << 0), 0, 11, 1, 0, 0xffff, 0, 0, 0.0f},
    {"brightness_decrease", {0, 1, 2, 3}, {3, 2, 1, 0}, (3 << 6) | (1 << 0), 0, 9, 0, 0, 0xffff, 0, 0, 0.0f},
    {"master_brightness_up", {0, 1, 2, 3}, {3, 2, 1, 0}, 0, 0, 0, 1, 0, 0xffff, 0, 1, 6.5f},
    {"master_brightness_down", {0, 1, 2, 3}, {3, 2, 1, 0}, 0, 0, 0, 0, 0, 0xffff, 0, 2, 5.5f},
    {"obj_priority_stack", {0, 1, 2, 3}, {0, 1, 2, 3}, 0, 0, 0, 1, 0, 0xffff, 0, 0, 0.0f},
    {"obj_window_masks", {0, 1, 2, 3}, {3, 2, 1, 0}, 0, 0, 0, 1, 1 << 15, 0x5a5a, 0, 0, 0.0f},
    {"bg0_3d_alpha", {0, 1, 2, 3}, {3, 2, 1, 0}, (1 << 6) | (1 << 0) | kBackdropTarget2, (8 << 8) | 8, 0, 0, 0, 0xffff, 1, 0, 0.0f}
}};

GLuint compileShader(GLenum type, const std::string &source, const char *label) {
    const GLuint shader = glCreateShader(type);
    const char *text = source.c_str();
    glShaderSource(shader, 1, &text, nullptr);
    glCompileShader(shader);
    GLint status = GL_FALSE;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &status);
    if (status != GL_TRUE) {
        GLint length = 0;
        glGetShaderiv(shader, GL_INFO_LOG_LENGTH, &length);
        std::string log(static_cast<size_t>(length > 0 ? length : 1), '\0');
        glGetShaderInfoLog(shader, length, nullptr, log.data());
        glDeleteShader(shader);
        throw std::runtime_error(std::string(label) + " compile failed:\n" + log);
    }
    return shader;
}

GLuint createProgram(const std::string &vertex, const std::string &fragment) {
    const GLuint vs = compileShader(GL_VERTEX_SHADER, vertex, "G2 vertex");
    const GLuint fs = compileShader(GL_FRAGMENT_SHADER, fragment, "G2 fragment");
    const GLuint program = glCreateProgram();
    glAttachShader(program, vs);
    glAttachShader(program, fs);
    glLinkProgram(program);
    glDeleteShader(vs);
    glDeleteShader(fs);
    GLint status = GL_FALSE;
    glGetProgramiv(program, GL_LINK_STATUS, &status);
    if (status != GL_TRUE) {
        GLint length = 0;
        glGetProgramiv(program, GL_INFO_LOG_LENGTH, &length);
        std::string log(static_cast<size_t>(length > 0 ? length : 1), '\0');
        glGetProgramInfoLog(program, length, nullptr, log.data());
        glDeleteProgram(program);
        throw std::runtime_error("G2 link failed:\n" + log);
    }
    return program;
}

std::string readText(const char *path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error(std::string("Cannot read shader ") + path);
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

void setInt(GLuint program, const std::string &name, GLint value) {
    const GLint location = glGetUniformLocation(program, name.c_str());
    if (location >= 0) glUniform1i(location, value);
}
void setInts(GLuint program, const char *name, const GLint *values, GLsizei count) {
    const GLint location = glGetUniformLocation(program, name);
    if (location >= 0) glUniform1iv(location, count, values);
}
void setFloat(GLuint program, const char *name, GLfloat value) {
    const GLint location = glGetUniformLocation(program, name);
    if (location >= 0) glUniform1f(location, value);
}
void setVec4(GLuint program, const char *name, const GLfloat *values) {
    const GLint location = glGetUniformLocation(program, name);
    if (location >= 0) glUniform4fv(location, 1, values);
}

GLuint createTexture(int seed, bool windowTexture = false) {
    constexpr int size = 8;
    std::array<std::uint8_t, size * size * 4> pixels{};
    for (int y = 0; y < size; ++y) {
        for (int x = 0; x < size; ++x) {
            const size_t offset = static_cast<size_t>((y * size + x) * 4);
            const int checker = (x + y + seed) % 5;
            pixels[offset + 0] = static_cast<std::uint8_t>((seed * 37 + x * 29 + y * 11) & 255);
            pixels[offset + 1] = static_cast<std::uint8_t>((seed * 19 + x * 7 + y * 31) & 255);
            pixels[offset + 2] = static_cast<std::uint8_t>((seed * 53 + x * 13 + y * 5) & 255);
            if (windowTexture) {
                pixels[offset + 3] = ((x / 2 + y / 2) % 2 == 0) ? 255 : 0;
            } else {
                pixels[offset + 3] = checker == 0 ? 0 : (checker == 1 ? 72 : 255);
            }
        }
    }
    GLuint texture = 0;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
    return texture;
}

void setSampler(GLuint program, const char *uniformName, GLint unit) {
    const GLint location = glGetUniformLocation(program, uniformName);
    if (location < 0) throw std::runtime_error(std::string("Missing sampler uniform: ") + uniformName);
    glUniform1i(location, unit);
}

GLuint createFramebuffer(GLuint &colorTexture) {
    glGenTextures(1, &colorTexture);
    glBindTexture(GL_TEXTURE_2D, colorTexture);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, kWidth, kHeight, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);

    GLuint framebuffer = 0;
    glGenFramebuffers(1, &framebuffer);
    glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, colorTexture, 0);
    const GLenum drawBuffer = GL_COLOR_ATTACHMENT0;
    glDrawBuffers(1, &drawBuffer);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        throw std::runtime_error("G2 RGBA8 framebuffer is incomplete");
    }
    return framebuffer;
}

void renderScene(
    GLuint program,
    const std::array<GLuint, 4> &bgTextures,
    const std::array<GLuint, 5> &objTextures,
    GLuint objWindowTexture,
    GLuint &vao,
    GLuint &vbo,
    const Scene &scene,
    std::ofstream &output
) {
    const std::array<Vertex, 4> vertices = {{
        {{-1.0f, -1.0f, 0.0f}, {0.0f, 0.0f}},
        {{ 1.0f, -1.0f, 0.0f}, {1.0f, 0.0f}},
        {{-1.0f,  1.0f, 0.0f}, {0.0f, 1.0f}},
        {{ 1.0f,  1.0f, 0.0f}, {1.0f, 1.0f}}
    }};
    if (vao == 0) {
        glGenVertexArrays(1, &vao);
        glGenBuffers(1, &vbo);
    }
    glBindVertexArray(vao);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices.data(), GL_DYNAMIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                          reinterpret_cast<void *>(offsetof(Vertex, position)));
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                          reinterpret_cast<void *>(offsetof(Vertex, texCoord)));

    glViewport(0, 0, kWidth, kHeight);
    glDisable(GL_BLEND);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_DITHER);
    const GLfloat backdrop[4] = {0.08f, 0.17f, 0.31f, 1.0f};
    glClearColor(backdrop[0], backdrop[1], backdrop[2], backdrop[3]);
    glClear(GL_COLOR_BUFFER_BIT);

    glUseProgram(program);
    for (int i = 0; i < 4; ++i) {
        glActiveTexture(GL_TEXTURE0 + i);
        glBindTexture(GL_TEXTURE_2D, bgTextures[static_cast<size_t>(i)]);
        const std::string name = "bgTexture[" + std::to_string(i) + "]";
        setSampler(program, name.c_str(), i);
    }
    for (int i = 0; i < 5; ++i) {
        glActiveTexture(GL_TEXTURE4 + i);
        glBindTexture(GL_TEXTURE_2D, objTextures[static_cast<size_t>(i)]);
        const std::string name = "objTexture[" + std::to_string(i) + "]";
        setSampler(program, name.c_str(), i + 4);
    }
    glActiveTexture(GL_TEXTURE9);
    glBindTexture(GL_TEXTURE_2D, objWindowTexture);
    setSampler(program, "objWindowTexture", 9);

    setInts(program, "bgOrder[0]", scene.order.data(), 4);
    setInts(program, "bgPriorities[0]", scene.priorities.data(), 4);
    setInt(program, "bldcnt", scene.bldcnt);
    setInt(program, "bldalpha", scene.bldalpha);
    setInt(program, "bldy", scene.bldy);
    setInt(program, "topScreen", scene.topScreen);
    setInt(program, "dispcnt", scene.dispcnt);
    setInt(program, "winout", scene.winout);
    setInt(program, "bg0as3d", scene.bg0as3d);
    setFloat(program, "inMasterBrightFactor", scene.masterFactor);
    setInt(program, "inMasterBrightMode", scene.masterMode);
    setVec4(program, "backdropColor", backdrop);

    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    glFinish();
    std::array<std::uint8_t, kBytesPerScene> pixels{};
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(0, 0, kWidth, kHeight, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
    output.write(reinterpret_cast<const char *>(pixels.data()),
                 static_cast<std::streamsize>(pixels.size()));
    if (!output) throw std::runtime_error(std::string("Cannot write scene ") + scene.name);
}

} // namespace

int main(int argc, char **argv) {
    if (argc != 4) {
        std::cerr << "Usage: renderer_g2_pixel_probe <vertex.glsl> <fragment.glsl> <out.rgba>\n";
        return 2;
    }
    try {
        EglContext egl;
        egl.create();
        const GLuint program = createProgram(readText(argv[1]), readText(argv[2]));

        std::array<GLuint, 4> bgTextures{};
        std::array<GLuint, 5> objTextures{};
        for (int i = 0; i < 4; ++i) bgTextures[static_cast<size_t>(i)] = createTexture(i + 1);
        for (int i = 0; i < 5; ++i) objTextures[static_cast<size_t>(i)] = createTexture(i + 7);
        const GLuint objWindowTexture = createTexture(12, true);

        GLuint colorTexture = 0;
        createFramebuffer(colorTexture);
        GLuint vao = 0;
        GLuint vbo = 0;

        std::ofstream output(argv[3], std::ios::binary);
        if (!output) throw std::runtime_error("Cannot create RGBA output file");
        for (const Scene &scene : kScenes) {
            renderScene(program, bgTextures, objTextures, objWindowTexture,
                        vao, vbo, scene, output);
            std::cout << "Rendered " << scene.name << "\n";
        }
        output.close();
        glDeleteProgram(program);
    } catch (const std::exception &error) {
        std::cerr << "G2 host pixel probe failed: " << error.what() << "\n";
        return 1;
    }
    return 0;
}
