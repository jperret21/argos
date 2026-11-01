/**
 * GLSL ES 3.00 (WebGL2) shaders of the image viewer.
 *
 * Texture strategy: the raw uint16 samples are uploaded untouched as an
 * unsigned-integer texture (R16UI, or RGB16UI for colour) and read with
 * usampler2D + texelFetch. Why:
 *  - full 16-bit precision reaches the stretch: integers <= 65535 convert to
 *    highp float exactly, there is no 8-bit (or half-float: 11-bit mantissa)
 *    quantisation anywhere before the transfer function;
 *  - zero CPU conversion: the Uint16Array view of the WebSocket message goes
 *    straight to texSubImage2D (R32F would need a 2x larger Float32Array
 *    copy per frame; R16 normalised needs EXT_texture_norm16, which WebKit
 *    (the future Tauri webview on macOS/Linux) does not expose);
 *  - integer textures are core WebGL2, so this works on every target.
 * Integer textures cannot be filtered by the hardware, so sampling is done in
 * the shader: nearest neighbour at >= 1:1 (one texelFetch per screen pixel),
 * and a box filter over the screen pixel's footprint when zoomed out (up to
 * MAX_TAPS^2 texelFetches, averaged in linear ADU *before* the stretch, which
 * is the physically meaningful order and avoids stars twinkling in and out
 * of existence while zooming).
 */

/** Taps per axis of the zoomed-out box filter (8x8 = 64 fetches max). */
export const MAX_TAPS = 8;

/** Full-screen triangle generated from gl_VertexID: no vertex buffer needed. */
export const VERTEX_SHADER = `#version 300 es
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
`;

export const FRAGMENT_SHADER = `#version 300 es
precision highp float;
precision highp int;
precision highp usampler2D;

#define MAX_TAPS ${MAX_TAPS}

uniform usampler2D u_image;
uniform ivec2 u_size;        // frame (texture) size, px
uniform int u_rot;           // display rotation: clockwise quarter turns (viewer/rotation.ts)
uniform int u_channels;      // 1 (mono) or 3 (RGB)
uniform float u_viewportH;   // drawing buffer height, device px
uniform vec2 u_offset;       // device px position of the image's top-left corner (y down)
uniform float u_scale;       // device px per image px
uniform int u_taps;          // 1 = nearest; >1 = box filter taps per axis
uniform float u_black;
uniform float u_white;
uniform float u_midtones;
uniform int u_mode;          // 0 linear, 1 log, 2 asinh (stretch.py modes)
uniform bool u_nightTint;    // red-only output for the Night Red theme
uniform vec3 u_tint;         // full-scale colour (--viewer-tint): white, or #d80000 in Night Red

out vec4 outColor;

// Constants of argos/core/imaging/stretch.py (_LOG_K, _ASINH_K).
const float LOG_K = 1000.0;
const float ASINH_K = 30.0;

float transfer(float v) {
  float white = u_white <= u_black ? u_black + 1.0 : u_white;
  float n = clamp((v - u_black) / (white - u_black), 0.0, 1.0);
  if (u_mode == 1) {
    n = log(1.0 + LOG_K * n) / log(1.0 + LOG_K);
  } else if (u_mode == 2) {
    n = asinh(ASINH_K * n) / asinh(ASINH_K);
  }
  float m = clamp(u_midtones, 0.001, 0.999);
  if (abs(m - 0.5) > 1e-3) {
    n = ((m - 1.0) * n) / ((2.0 * m - 1.0) * n - m);  // PixInsight MTF
  }
  return clamp(n, 0.0, 1.0);
}

// Displayed size: width and height swap for a quarter turn.
ivec2 displaySize() {
  return (u_rot == 1 || u_rot == 3) ? u_size.yx : u_size;
}

// Displayed pixel -> frame texel: rotation.ts displayToFrame (numpy.rot90(frame, -k)).
ivec2 toTexel(ivec2 p) {
  if (u_rot == 1) return ivec2(p.y, u_size.y - 1 - p.x);
  if (u_rot == 2) return u_size - 1 - p;
  if (u_rot == 3) return ivec2(u_size.x - 1 - p.y, p.x);
  return p;
}

vec3 fetch(ivec2 p) {
  ivec2 d = clamp(p, ivec2(0), displaySize() - 1);
  return vec3(texelFetch(u_image, toTexel(d), 0).rgb);
}

void main() {
  // Device pixel centre, origin at the top-left like the image rows.
  vec2 frag = vec2(gl_FragCoord.x, u_viewportH - gl_FragCoord.y);
  vec2 img = (frag - u_offset) / u_scale;
  ivec2 dsize = displaySize();
  if (img.x < 0.0 || img.y < 0.0 || img.x >= float(dsize.x) || img.y >= float(dsize.y)) {
    outColor = vec4(0.0);  // transparent: the themed background shows through
    return;
  }

  vec3 v;
  if (u_taps <= 1) {
    v = fetch(ivec2(floor(img)));
  } else {
    // Box filter over the footprint of this device pixel in the image.
    float footprint = 1.0 / u_scale;
    float stepSize = footprint / float(u_taps);
    vec2 origin = img - 0.5 * footprint;
    vec3 acc = vec3(0.0);
    for (int j = 0; j < MAX_TAPS; ++j) {
      if (j >= u_taps) break;
      for (int i = 0; i < MAX_TAPS; ++i) {
        if (i >= u_taps) break;
        acc += fetch(ivec2(floor(origin + (vec2(float(i), float(j)) + 0.5) * stepSize)));
      }
    }
    v = acc / float(u_taps * u_taps);
  }

  vec3 c;
  if (u_channels == 1) {
    c = vec3(transfer(v.r));
  } else {
    c = vec3(transfer(v.r), transfer(v.g), transfer(v.b));
  }
  if (u_nightTint) {
    float l = u_channels == 1 ? c.r : dot(c, vec3(0.2126, 0.7152, 0.0722));
    c = vec3(l, 0.0, 0.0);
  }
  // BRAND.md 4.3: a stretched value v is drawn as v x --viewer-tint, so in
  // Night Red the brightest star never outshines the interface text.
  outColor = vec4(c * u_tint, 1.0);
}
`;
