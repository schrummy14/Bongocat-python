#version 330 core

uniform sampler2D texture0;

in vec2 v_uv;
out vec4 f_color;

void main() {
    f_color = texture(texture0, v_uv);
}
