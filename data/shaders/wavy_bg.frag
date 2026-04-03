#version 440
// Wavy Labs — FBM aurora background shader
// Compile to QSB with:
//   qsb.exe --glsl "100es,120,150" --hlsl 50 --msl 12 -o wavy_bg.frag.qsb wavy_bg.frag
// Or via CMake: qt6_add_shaders (requires Qt6 ShaderTools)

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float iTime;
    float iIntensity;
} ubuf;

// ── Noise / FBM ──────────────────────────────────────────────────────────────

float hash(vec2 p) {
    p = fract(p * vec2(127.1, 311.7));
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash(i + vec2(0.0, 0.0));
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
    float sum = 0.0;
    float amp = 0.5;
    float scale = 1.0;
    for (int i = 0; i < 3; i++) {
        sum += noise(p * scale) * amp;
        amp   *= 0.5;
        scale *= 2.0;
        p += vec2(0.31, 0.17) * float(i + 1);
    }
    return sum;
}

// ── Main ─────────────────────────────────────────────────────────────────────

void main() {
    vec2 uv = qt_TexCoord0;

    float t          = ubuf.iTime * 0.08;
    float intensity  = 0.6 + ubuf.iIntensity * 0.8;

    // Domain-warp: two layers of FBM
    vec2 q = vec2(
        fbm(uv * 2.0 + vec2(0.0, 0.0)   + t * 0.40),
        fbm(uv * 2.0 + vec2(5.2, 1.3)   + t * 0.30)
    );
    vec2 r = vec2(
        fbm(uv * 1.5 + 3.0 * q + vec2(1.7, 9.2) + t * 0.20),
        fbm(uv * 1.5 + 3.0 * q + vec2(8.3, 2.8) + t * 0.15)
    );

    float f = fbm(uv * 1.2 + 3.5 * r + t * 0.10);

    // Palette: very dark (#0a0610) → mid-purple (#1a0835) → teal hint (#0d3040)
    vec3 darkBase   = vec3(0.039, 0.024, 0.063);
    vec3 midPurple  = vec3(0.102, 0.031, 0.208);
    vec3 tealAccent = vec3(0.051, 0.188, 0.251);

    vec3 col = mix(darkBase, midPurple, clamp(f * 1.8, 0.0, 1.0));
    col = mix(col, tealAccent, clamp((f - 0.4) * intensity * 2.0, 0.0, 0.6));

    // Extra highlight pulse when generating
    vec3 highlight = vec3(0.18, 0.08, 0.38);
    col += highlight * clamp((f - 0.6) * ubuf.iIntensity * 3.0, 0.0, 0.4);

    fragColor = vec4(col, 1.0) * ubuf.qt_Opacity;
}
