#version 300 es
precision highp float;
precision highp int;

layout(location = 0) in vec3 position;
layout(location = 1) in vec2 texCoord;

smooth out vec2 fragTexCoord;

void main() {
    gl_Position = vec4(position.x, position.y, position.z, 1.0);
    fragTexCoord = texCoord;
}
