#version 300 es
precision highp float;
precision highp int;
precision highp sampler2D;

uniform sampler2D myTexture;
uniform sampler2D bgTexture[4];
uniform sampler2D objTexture[5];
uniform sampler2D objWindowTexture;
uniform int bgOrder[4];
uniform int bgPriorities[4];
uniform int bldcnt;
uniform int bldalpha;
uniform int bldy;
uniform int topScreen;
uniform vec4 backdropColor;
uniform int dispcnt;
uniform int winout;
uniform int bg0as3d;

smooth in vec2 fragTexCoord;
uniform float inMasterBrightFactor;
uniform int inMasterBrightMode;
out vec4 color;

// ESSL 3.00 requires sampler-array indices to be constant integral
// expressions. Keep the DS-selected layer dynamic in ordinary control flow,
// but make every sampler access use a literal array index.
vec4 sampleBg(int index) {
    switch (index) {
        case 0: return texture(bgTexture[0], fragTexCoord);
        case 1: return texture(bgTexture[1], fragTexCoord);
        case 2: return texture(bgTexture[2], fragTexCoord);
        case 3: return texture(bgTexture[3], fragTexCoord);
        default: return vec4(0.0);
    }
}

vec4 sampleObj(int index) {
    switch (index) {
        case 0: return texture(objTexture[0], fragTexCoord);
        case 1: return texture(objTexture[1], fragTexCoord);
        case 2: return texture(objTexture[2], fragTexCoord);
        case 3: return texture(objTexture[3], fragTexCoord);
        case 4: return texture(objTexture[4], fragTexCoord);
        default: return vec4(0.0);
    }
}

void main() {
    int oamsDrawn = 0;
    int currentBgDrawn = 5; // Backdrop
    bool objWindowEnabled = ((dispcnt >> 15) & 1) == 1;

    if (topScreen == 1) {
        if (fragTexCoord.t < 0.5) discard;
    } else {
        if (fragTexCoord.t >= 0.5) discard;
    }

    for (int i = 0; i < 4; i++) {
        int bgNum = bgOrder[i];
        int curPrio = bgPriorities[bgNum];

        // Draw OBJs at or below the current BG priority.
        for (int j = 3 - oamsDrawn; j > curPrio; j--) {
            vec4 objColor = sampleObj(j);
            if (objColor.a > 0.1) {
                color = objColor;
                currentBgDrawn = 4;
            }
            oamsDrawn++;
        }

        // Check OBJ window.
        if (objWindowEnabled && texture(objWindowTexture, fragTexCoord).a > 0.1) {
            if (((winout >> (bgNum + 8)) & 1) == 0) continue;
        } else if (objWindowEnabled) {
            if (((winout >> bgNum) & 1) == 0) continue;
        }

        // Draw the current BG.
        vec4 bgColor = sampleBg(bgNum);
        if (bgColor.a > 0.1) {
            if ((((bldcnt >> 6) & 0x3) == 1) && ((bldcnt >> bgNum & 1) == 1)) {
                // Alpha blending: bgNum is target 1.
                float alphaA = min(16.0, float(bldalpha & 31)) / 16.0;
                float alphaB = min(16.0, float((bldalpha >> 8) & 31)) / 16.0;
                if (bgNum == 0 && bg0as3d != 0) {
                    alphaA = bgColor.a;
                    alphaB = 1.0 - alphaA;
                }

                if (currentBgDrawn < 4
                    && (((bldcnt >> (8 + currentBgDrawn)) & 1) == 1)) {
                    vec4 targetColor = sampleBg(currentBgDrawn);
                    color = vec4(
                        min(1.0, bgColor.r * alphaA + targetColor.r * alphaB),
                        min(1.0, bgColor.g * alphaA + targetColor.g * alphaB),
                        min(1.0, bgColor.b * alphaA + targetColor.b * alphaB),
                        1.0
                    );
                    currentBgDrawn = bgNum;
                } else if (currentBgDrawn == 4
                    && (((bldcnt >> (8 + currentBgDrawn)) & 1) == 1)) {
                    // Alpha blending where the highest OBJ pixel is target 2.
                    color = vec4(
                        min(1.0, bgColor.r * alphaA + color.r * alphaB),
                        min(1.0, bgColor.g * alphaA + color.g * alphaB),
                        min(1.0, bgColor.b * alphaA + color.b * alphaB),
                        1.0
                    );
                } else if (currentBgDrawn == 5
                    && (((bldcnt >> (8 + currentBgDrawn)) & 1) == 1)) {
                    // Alpha blending where the backdrop is target 2.
                    color = vec4(
                        min(1.0, bgColor.r * alphaA + backdropColor.r * alphaB),
                        min(1.0, bgColor.g * alphaA + backdropColor.g * alphaB),
                        min(1.0, bgColor.b * alphaA + backdropColor.b * alphaB),
                        1.0
                    );
                } else {
                    color = bgColor;
                    currentBgDrawn = bgNum;
                }
            } else if ((((bldcnt >> 6) & 0x3) == 2) && ((bldcnt >> bgNum & 1) == 1)) {
                // Brightness increase mode: bgNum is target 1.
                float brightFactor = min(16.0, float(bldy & 31)) / 16.0;
                color = vec4(
                    bgColor.r + (1.0 - bgColor.r) * brightFactor,
                    bgColor.g + (1.0 - bgColor.g) * brightFactor,
                    bgColor.b + (1.0 - bgColor.b) * brightFactor,
                    1.0
                );
                currentBgDrawn = bgNum;
            } else if ((((bldcnt >> 6) & 0x3) == 3) && ((bldcnt >> bgNum & 1) == 1)) {
                // Brightness decrease mode: bgNum is target 1.
                float brightFactor = min(16.0, float(bldy & 31)) / 16.0;
                color = vec4(
                    max(0.0, bgColor.r - bgColor.r * brightFactor),
                    max(0.0, bgColor.g - bgColor.g * brightFactor),
                    max(0.0, bgColor.b - bgColor.b * brightFactor),
                    1.0
                );
                currentBgDrawn = bgNum;
            } else {
                color = vec4(bgColor.rgb, 1.0);
                currentBgDrawn = bgNum;
            }
        }
    }

    // Draw the remaining OBJs.
    for (int i = 3 - oamsDrawn; i >= 0; i--) {
        vec4 objColor = sampleObj(i);
        if (objColor.a > 0.1) {
            color = objColor;
            currentBgDrawn = 4;
        }
    }

    if (currentBgDrawn == 5) color = backdropColor;

    if (inMasterBrightMode == 1) {
        color.rgb += (vec3(1.0) - color.rgb) * (inMasterBrightFactor / 16.0);
    } else if (inMasterBrightMode == 2) {
        color.rgb -= color.rgb * (inMasterBrightFactor / 16.0);
    }
}
