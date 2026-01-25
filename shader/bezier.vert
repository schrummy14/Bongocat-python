#version 330 core

uniform mat4 model;
uniform int total_verts;
uniform vec2 raw_res[10]; 

vec2 bezier2(vec2 p0, vec2 p1, vec2 p2, float t) {
    float u = 1.0 - t;
    return u * u * p0 + 2.0 * u * t * p1 + t * t * p2;
}

vec2 bezier3(vec2 p0, vec2 p1, vec2 p2, vec2 p3, float t) {
    float u = 1.0 - t;
    float u2 = u * u;
    float t2 = t * t;
    return u * u2 * p0 + 3.0 * u2 * t * p1 + 3.0 * u * t2 * p2 + t * t2 * p3;
}

void main() {
    vec2 cp[15];
    int idx = 0;

    for(int i = 0; i < 5; i++) { 
        float t = float(i) / 4.0; 
        cp[idx++] = bezier2(raw_res[0], raw_res[1], raw_res[2], t); 
    }
    
    for(int i = 0; i < 5; i++) { 
        float t = float(i) / 4.0; 
        cp[idx++] = bezier3(raw_res[3], raw_res[4], raw_res[5], raw_res[6], t); 
    }
    
    for(int i = 0; i < 5; i++) { 
        float t = float(i) / 4.0; 
        cp[idx++] = bezier2(raw_res[7], raw_res[8], raw_res[9], t); 
    }

    float t_global = float(gl_VertexID) / float(total_verts - 1);
    for (int k = 1; k < 15; k++) {
        for (int i = 0; i < 15 - k; i++) {
            cp[i] = mix(cp[i], cp[i+1], t_global);
        }
    }
    
    gl_Position = model * vec4(cp[0], 0.0, 1.0);
}
