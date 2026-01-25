#version 330
in vec2 v_uv;
uniform sampler2D texture0;
out vec4 fragColor;

void main() {
    fragColor = texture(texture0, v_uv);
}
