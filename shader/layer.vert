#version 330 core

in vec2 in_vert;
in vec2 in_uv;

uniform mat4 model;
uniform vec2 offset;

out vec2 v_uv;

void main() {
    vec4 pos = vec4(in_vert.x + offset.x, in_vert.y + offset.y, 0.0, 1.0);
    gl_Position = model * pos;
    v_uv = in_uv;
}
