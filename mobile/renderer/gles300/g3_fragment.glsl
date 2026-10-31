#version 300 es
precision highp float;
precision highp int;
precision highp sampler2D;

uniform sampler2D myTexture;
uniform int useTexture;
uniform int polygonMode;
uniform int useFog;
uniform vec4 fogColor;
uniform float fogDepthBoundary[32];
uniform float fogDensity[32];

smooth in vec2 fragTexCoord;
smooth in vec4 fragInColor;
smooth in vec4 coords;
out vec4 color;

void main() {
    vec4 shadedColor;
    if (useTexture == 1) {
        vec4 texel = texture(myTexture, fragTexCoord);
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
