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
 *
 * Wave 4 (web/spec/04-viewer-and-image-tools.md 2.5, "client-only"):
 *  - CFA preview (u_preview, palettes/cfa.ts): the super-pixel colour of each
 *    2 x 2 cell with the display balance, or one real-sample plane, computed
 *    from the raw mosaic texels; every view keeps the frame's geometry.
 *  - Palettes (u_palette, u_lut, palettes/lut.ts): after the stretch, Negative
 *    inverts, Fire and Ice read a 256-entry LUT whose OKLab lightness is the
 *    stretched value. Night Red draws the luminance in red only, whatever
 *    reaches here (D30 is enforced before, this is the last guard).
 *  - Saturation (u_sat*): a displayed pixel is painted --viewer-saturated when
 *    any RAW sample behind it (every tap, every sample of its CFA cell) reaches
 *    the threshold, so the test is on the data, not on the stretched picture
 *    (fixes Qt P5); black in Night Red, a hole in a red star.
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
uniform int u_preview;       // 0 as delivered, 1 CFA colour, 2 / 3 / 4 the R / G / B plane (palettes/cfa.ts)
uniform ivec4 u_rb;          // CFA cell sites: R (x, y), B (x, y)
uniform ivec4 u_gg;          // CFA cell sites: G1 (x, y), G2 (x, y)
uniform vec3 u_gains;        // display balance of the colour preview (neutralise_rgb_for_display)
uniform int u_palette;       // 0 none (grey), 1 negative, 2 the LUT (Fire, Ice)
uniform sampler2D u_lut;     // 256 x 1 RGBA8 palette (texture unit 1)
uniform bool u_satOn;        // saturation highlight
uniform float u_satThreshold; // raw ADU
uniform vec3 u_satColour;    // --viewer-saturated (black in Night Red)

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

// What a displayed pixel shows, before the stretch: rgb, and in .a the largest RAW
// sample behind it (the saturation test). Previews: palettes/cfa.ts.
vec4 fetch(ivec2 p) {
  ivec2 t = toTexel(clamp(p, ivec2(0), displaySize() - 1));
  if (u_preview == 0) {
    vec3 v = vec3(texelFetch(u_image, t, 0).rgb);
    return vec4(v, u_channels == 1 ? v.r : max(v.r, max(v.g, v.b)));
  }
  if (u_channels == 3) {
    // One channel of an RGB frame.
    vec3 v = vec3(texelFetch(u_image, t, 0).rgb);
    float c = u_preview == 2 ? v.r : (u_preview == 3 ? v.g : v.b);
    return vec4(c, c, c, c);
  }
  // Raw mosaic: the 2 x 2 cell holding t (an odd last row / column repeats the last
  // complete cell, debayer.expand_cfa_cells).
  ivec2 cell = min((t / 2) * 2, (u_size / 2) * 2 - 2);
  float r = float(texelFetch(u_image, cell + u_rb.xy, 0).r);
  float b = float(texelFetch(u_image, cell + u_rb.zw, 0).r);
  float g1 = float(texelFetch(u_image, cell + u_gg.xy, 0).r);
  float g2 = float(texelFetch(u_image, cell + u_gg.zw, 0).r);
  float g = floor((g1 + g2) * 0.5);  // (G1 + G2) >> 1
  if (u_preview == 1) {
    vec3 c = min(floor(vec3(r, g, b) * u_gains), vec3(65535.0));
    return vec4(c, max(max(r, b), max(g1, g2)));
  }
  float c = u_preview == 2 ? r : (u_preview == 3 ? g : b);
  return vec4(c, c, c, u_preview == 3 ? max(g1, g2) : c);
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
  float rawMax;
  if (u_taps <= 1) {
    vec4 s = fetch(ivec2(floor(img)));
    v = s.rgb;
    rawMax = s.a;
  } else {
    // Box filter over the footprint of this device pixel in the image.
    float footprint = 1.0 / u_scale;
    float stepSize = footprint / float(u_taps);
    vec2 origin = img - 0.5 * footprint;
    vec3 acc = vec3(0.0);
    rawMax = 0.0;
    for (int j = 0; j < MAX_TAPS; ++j) {
      if (j >= u_taps) break;
      for (int i = 0; i < MAX_TAPS; ++i) {
        if (i >= u_taps) break;
        vec4 s = fetch(ivec2(floor(origin + (vec2(float(i), float(j)) + 0.5) * stepSize)));
        acc += s.rgb;
        rawMax = max(rawMax, s.a);
      }
    }
    v = acc / float(u_taps * u_taps);
  }

  // A clipped sample anywhere behind this pixel: the data says so, not the picture.
  if (u_satOn && rawMax >= u_satThreshold) {
    outColor = vec4(u_satColour, 1.0);
    return;
  }

  // One value per pixel: a mono frame, the raw mosaic, or one plane.
  bool mono = (u_channels == 1 && u_preview != 1) || u_preview >= 2;
  vec3 c;
  if (mono) {
    c = vec3(transfer(v.r));
  } else {
    c = vec3(transfer(v.r), transfer(v.g), transfer(v.b));
  }
  if (u_palette != 0) {
    float l = mono ? c.r : dot(c, vec3(0.2126, 0.7152, 0.0722));
    if (u_palette == 1) {
      c = mono ? vec3(1.0 - l) : vec3(1.0) - c;
    } else {
      // Entry centres: v = i / 255 sits at (i + 0.5) / 256.
      c = texture(u_lut, vec2(l * (255.0 / 256.0) + 0.5 / 256.0, 0.5)).rgb;
    }
  }
  if (u_nightTint) {
    float l = mono && u_palette == 0 ? c.r : dot(c, vec3(0.2126, 0.7152, 0.0722));
    c = vec3(l, 0.0, 0.0);
  }
  // BRAND.md 4.3: a stretched value v is drawn as v x --viewer-tint, so in
  // Night Red the brightest star never outshines the interface text.
  outColor = vec4(c * u_tint, 1.0);
}
`;
