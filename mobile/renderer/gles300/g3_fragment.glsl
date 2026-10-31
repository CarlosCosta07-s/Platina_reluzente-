#version 300 es
precision highp float;
precision highp int;
precision highp sampler2D;

uniform sampler2D myTexture;
uniform int useTexture;
uniform int polygonMode;
uniform int useFog;
uniform int clampToBorderS;
uniform int clampToBorderT;
uniform vec4 fogColor;
uniform float fogDepthBoundary[32];
uniform float fogDensity[32];

smooth in vec2 fragTexCoord;
smooth in vec4 fragInColor;
smooth in vec4 coords;
out vec4 color;

vec4 sampleG3Texture() {
    // Sample before the per-fragment border test so implicit texture
    // derivatives are evaluated outside divergent control flow.
    vec4 texel = texture(myTexture, fragTexCoord);
    // Desktop GL_CLAMP_TO_BORDER uses transparent black by default.
    // GLES 3.0 has no core border-clamp mode; the host adapter must set
    // these flags together with GL_CLAMP_TO_EDGE on the texture object.
    bool outsideS = clampToBorderS == 1
        && (fragTexCoord.s < 0.0 || fragTexCoord.s > 1.0);
    bool outsideT = clampToBorderT == 1
        && (fragTexCoord.t < 0.0 || fragTexCoord.t > 1.0);
    return (outsideS || outsideT) ? vec4(0.0) : texel;
}

void main() {
    vec4 shadedColor;
    if (useTexture == 1) {
        vec4 texel = sampleG3Texture();
        if (polygonMode == 0) {
            shadedColor = texel * fragInColor;
        } else {
            shadedColor = texel;
        }
        if (texel.a < 0.05) discard;
    } else {
        shadedColor = fragInColor;
    }

    if (useFog == 1) {
        float fogFactor = 0.0;
        if (coords.z < fogDepthBoundary[0]) {
            fogFactor = fogDensity[0];
        } else {
            int foundIdx = 31;
            for (int i = 1; i < 32; i++) {
                if (coords.z < fogDepthBoundary[i]) {
                    foundIdx = i;
                    break;
                }
            }
            if (foundIdx == 31) {
                fogFactor = fogDensity[foundIdx];
            } else {
                float interpolationFactor =
                    (fogDepthBoundary[foundIdx - 1] - coords.z)
                    / (fogDepthBoundary[foundIdx] - fogDepthBoundary[foundIdx - 1]);
                fogFactor = fogDensity[foundIdx - 1] * interpolationFactor
                    + fogDensity[foundIdx] * (1.0 - interpolationFactor);
            }
        }
        color = mix(shadedColor, fogColor, fogFactor);
    } else {
        color = shadedColor;
    }
}
