"""moderngl renderer: webcam background, glowing fruit, additive blade trails,
particles, and a GPU bloom post-process. Text is rendered via pygame fonts and
uploaded as textures.

Pipeline:
  scene_fbo  <- webcam bg + fruit + halves + trails + particles + flash
  bright_fbo <- bright-pass of scene (half res)
  blur ping/pong (gaussian, 2 passes)
  default fb <- scene + bloom (composite)
  text overlays drawn last, straight to default fb
"""
import math

import numpy as np
import moderngl
import pygame

import config as C

# ---------------- Shaders ----------------

QUAD_VS = """
#version 330
in vec2 in_pos;      // unit quad -1..1
in vec2 in_uv;
out vec2 uv;
void main() {
    uv = in_uv;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

# Webcam background: sample texture, darken.
BG_FS = """
#version 330
uniform sampler2D tex;
uniform float darken;
in vec2 uv;
out vec4 f;
void main() {
    vec3 c = texture(tex, uv).rgb * darken;
    f = vec4(c, 1.0);
}
"""

# Generic fullscreen textured quad (for bloom passes / composite / text).
TEX_FS = """
#version 330
uniform sampler2D tex;
in vec2 uv;
out vec4 f;
void main() { f = texture(tex, uv); }
"""

BRIGHT_FS = """
#version 330
uniform sampler2D tex;
uniform float threshold;
in vec2 uv;
out vec4 f;
void main() {
    vec3 c = texture(tex, uv).rgb;
    float b = max(c.r, max(c.g, c.b));
    float k = max(0.0, b - threshold) / max(0.001, (1.0 - threshold));
    f = vec4(c * k, 1.0);
}
"""

BLUR_FS = """
#version 330
uniform sampler2D tex;
uniform vec2 dir;      // (1/w,0) or (0,1/h)
in vec2 uv;
out vec4 f;
void main() {
    float w[5] = float[](0.227027, 0.194595, 0.121622, 0.054054, 0.016216);
    vec3 c = texture(tex, uv).rgb * w[0];
    for (int i = 1; i < 5; i++) {
        c += texture(tex, uv + dir * float(i)).rgb * w[i];
        c += texture(tex, uv - dir * float(i)).rgb * w[i];
    }
    f = vec4(c, 1.0);
}
"""

COMPOSITE_FS = """
#version 330
uniform sampler2D scene;
uniform sampler2D bloom;
uniform float intensity;
uniform float flash;
uniform vec2 shake;
in vec2 uv;
out vec4 f;
void main() {
    vec2 suv = uv + shake;
    vec3 c = texture(scene, suv).rgb + texture(bloom, suv).rgb * intensity;
    c = mix(c, vec3(1.0), clamp(flash, 0.0, 1.0));
    // gentle filmic-ish tonemap so highlights stay punchy
    c = c / (c + vec3(0.85)) * 1.85;
    f = vec4(c, 1.0);
}
"""

# Circle/glow sprite for fruits, bombs, halves. Drawn on a unit quad scaled+placed.
SPRITE_VS = """
#version 330
in vec2 in_pos;        // unit quad -1..1
uniform vec2 center;   // pixel
uniform float radius;  // pixel (includes glow margin)
uniform vec2 res;
uniform float angle;
out vec2 uv;
void main() {
    uv = in_pos;        // -1..1 local
    float s = sin(angle), c = cos(angle);
    vec2 p = vec2(in_pos.x * c - in_pos.y * s, in_pos.x * s + in_pos.y * c);
    vec2 px = center + p * radius;
    vec2 clip = vec2(px.x / res.x * 2.0 - 1.0, 1.0 - px.y / res.y * 2.0);
    gl_Position = vec4(clip, 0.0, 1.0);
}
"""

SPRITE_FS = """
#version 330
uniform vec3 color;
uniform float core;     // fraction of radius that is solid body
uniform float is_bomb;
uniform float half_side; // 0 = full, -1/+1 = clipped half
in vec2 uv;
out vec4 f;
void main() {
    float d = length(uv);
    if (half_side > 0.5 && uv.x < 0.0) discard;
    if (half_side < -0.5 && uv.x > 0.0) discard;
    float body = smoothstep(core, core - 0.06, d);          // solid disk
    float glow = pow(max(0.0, 1.0 - d), 2.2) * 0.9;          // soft halo
    vec3 col = color;
    if (is_bomb > 0.5) {
        col = mix(vec3(0.05), vec3(0.25), body);
    }
    float a = clamp(body + glow, 0.0, 1.0);
    vec3 outc = col * body + color * glow;                  // glow tinted by color
    f = vec4(outc, a);
}
"""

# Additive blade trail: triangles built on CPU, per-vertex color+alpha.
TRAIL_VS = """
#version 330
in vec2 in_pos;     // pixel
in vec4 in_col;     // rgba
uniform vec2 res;
out vec4 col;
void main() {
    col = in_col;
    vec2 clip = vec2(in_pos.x / res.x * 2.0 - 1.0, 1.0 - in_pos.y / res.y * 2.0);
    gl_Position = vec4(clip, 0.0, 1.0);
}
"""
TRAIL_FS = """
#version 330
in vec4 col;
out vec4 f;
void main() { f = col; }
"""

# Particles as point sprites (additive). Soft round falloff.
PART_VS = """
#version 330
in vec2 in_pos;
in vec4 in_col;
in float in_size;
uniform vec2 res;
out vec4 col;
void main() {
    col = in_col;
    gl_PointSize = in_size;
    vec2 clip = vec2(in_pos.x / res.x * 2.0 - 1.0, 1.0 - in_pos.y / res.y * 2.0);
    gl_Position = vec4(clip, 0.0, 1.0);
}
"""
PART_FS = """
#version 330
in vec4 col;
out vec4 f;
void main() {
    float d = length(gl_PointCoord - vec2(0.5)) * 2.0;
    float a = max(0.0, 1.0 - d);
    f = vec4(col.rgb * col.a, col.a) * a;
}
"""


def _unit_quad(ctx, prog):
    # pos(-1..1) + uv(-1..1) interleaved
    verts = np.array([
        -1, -1, -1, -1,
         1, -1,  1, -1,
        -1,  1, -1,  1,
         1,  1,  1,  1,
    ], dtype="f4")
    vbo = ctx.buffer(verts.tobytes())
    return ctx.vertex_array(prog, [(vbo, "2f 2f", "in_pos", "in_uv")])


def _sprite_quad(ctx, prog):
    # only in_pos is an active attribute (uv is derived from in_pos in-shader)
    verts = np.array([
        -1, -1,
         1, -1,
        -1,  1,
         1,  1,
    ], dtype="f4")
    vbo = ctx.buffer(verts.tobytes())
    return ctx.vertex_array(prog, [(vbo, "2f", "in_pos")])


def _fs_quad(ctx, prog):
    # fullscreen quad with uv 0..1
    verts = np.array([
        -1, -1, 0, 0,
         1, -1, 1, 0,
        -1,  1, 0, 1,
         1,  1, 1, 1,
    ], dtype="f4")
    vbo = ctx.buffer(verts.tobytes())
    return ctx.vertex_array(prog, [(vbo, "2f 2f", "in_pos", "in_uv")])


class Renderer:
    def __init__(self, ctx):
        self.ctx = ctx
        self.res = (C.WIDTH, C.HEIGHT)
        self.half = (C.WIDTH // 2, C.HEIGHT // 2)

        self.bg_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=BG_FS)
        self.tex_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=TEX_FS)
        self.bright_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=BRIGHT_FS)
        self.blur_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=BLUR_FS)
        self.comp_prog = ctx.program(vertex_shader=QUAD_VS, fragment_shader=COMPOSITE_FS)
        self.sprite_prog = ctx.program(vertex_shader=SPRITE_VS, fragment_shader=SPRITE_FS)
        self.trail_prog = ctx.program(vertex_shader=TRAIL_VS, fragment_shader=TRAIL_FS)
        self.part_prog = ctx.program(vertex_shader=PART_VS, fragment_shader=PART_FS)

        self.sprite_prog["res"].value = self.res
        self.trail_prog["res"].value = self.res
        self.part_prog["res"].value = self.res

        self.q_unit = _unit_quad(ctx, self.bg_prog)
        self.q_sprite = _sprite_quad(ctx, self.sprite_prog)
        self.fs_tex = _fs_quad(ctx, self.tex_prog)
        self.fs_bright = _fs_quad(ctx, self.bright_prog)
        self.fs_blur = _fs_quad(ctx, self.blur_prog)
        self.fs_comp = _fs_quad(ctx, self.comp_prog)

        # FBOs
        self.scene_tex = ctx.texture(self.res, 3, dtype="f2")
        self.scene_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.scene_fbo = ctx.framebuffer(color_attachments=[self.scene_tex])

        self.bright_tex = ctx.texture(self.half, 3, dtype="f2")
        self.bright_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.bright_fbo = ctx.framebuffer(color_attachments=[self.bright_tex])

        self.blur_tex = [ctx.texture(self.half, 3, dtype="f2") for _ in range(2)]
        for t in self.blur_tex:
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.blur_fbo = [ctx.framebuffer(color_attachments=[t]) for t in self.blur_tex]

        # webcam texture (created on first frame)
        self.cam_tex = None
        self._cam_size = None

        # dynamic buffers
        self.trail_vbo = ctx.buffer(reserve=1 << 18, dynamic=True)
        self.trail_vao = ctx.vertex_array(
            self.trail_prog, [(self.trail_vbo, "2f 4f", "in_pos", "in_col")])
        self.part_vbo = ctx.buffer(reserve=1 << 20, dynamic=True)
        self.part_vao = ctx.vertex_array(
            self.part_prog, [(self.part_vbo, "2f 4f 1f", "in_pos", "in_col", "in_size")])

        # text texture cache: key -> (texture, w, h)
        self._text_cache = {}
        pygame.font.init()
        self._fonts = {}

    # ---------- helpers ----------
    def _font(self, size):
        if size not in self._fonts:
            # Malgun Gothic supports Korean; fall back to Arial for Latin/symbols.
            self._fonts[size] = pygame.font.SysFont(
                "malgungothic,applegothic,arialblack,arial", size, bold=True)
        return self._fonts[size]

    def _text_texture(self, text, size, color):
        key = (text, size, tuple(round(c * 255) for c in color))
        if key in self._text_cache:
            return self._text_cache[key]
        font = self._font(size)
        col = tuple(int(max(0, min(1, c)) * 255) for c in color)
        surf = font.render(text, True, col).convert_alpha()
        w, h = surf.get_size()
        data = pygame.image.tostring(surf, "RGBA", True)  # flipped for GL
        tex = self.ctx.texture((w, h), 4, data)
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        if len(self._text_cache) > 256:
            self._text_cache.clear()
        self._text_cache[key] = (tex, w, h)
        return self._text_cache[key]

    # ---------- frame ----------
    def begin_scene(self):
        self.scene_fbo.use()
        self.ctx.clear(0.0, 0.0, 0.0)
        self.ctx.enable(moderngl.BLEND)

    def draw_webcam(self, frame):
        if frame is None:
            return
        h, w = frame.shape[:2]
        if self.cam_tex is None or self._cam_size != (w, h):
            if self.cam_tex:
                self.cam_tex.release()
            self.cam_tex = self.ctx.texture((w, h), 3, dtype="u1")
            self.cam_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._cam_size = (w, h)
        # flip vertically for GL origin
        self.cam_tex.write(np.ascontiguousarray(frame[::-1]).tobytes())
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.cam_tex.use(0)
        self.bg_prog["tex"].value = 0
        self.bg_prog["darken"].value = C.WEBCAM_DARKEN
        self.q_unit.render(moderngl.TRIANGLE_STRIP)

    def draw_sprite(self, x, y, radius, color, kind="fruit", angle=0.0, half_side=0.0):
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        glow_margin = 1.7
        self.sprite_prog["center"].value = (x, y)
        self.sprite_prog["radius"].value = radius * glow_margin
        self.sprite_prog["angle"].value = angle
        self.sprite_prog["color"].value = color
        self.sprite_prog["core"].value = 1.0 / glow_margin
        self.sprite_prog["is_bomb"].value = 1.0 if kind == "bomb" else 0.0
        self.sprite_prog["half_side"].value = float(half_side)
        self.q_sprite.render(moderngl.TRIANGLE_STRIP)

    def draw_trails(self, blades):
        """Build additive triangle strips for each blade trail."""
        verts = []
        for b in blades:
            pts = b.trail_points()
            if len(pts) < 2:
                continue
            n = len(pts)
            for i in range(n - 1):
                (x0, y0, in0) = pts[i]
                (x1, y1, in1) = pts[i + 1]
                dx, dy = x1 - x0, y1 - y0
                L = math.hypot(dx, dy) or 1.0
                nx, ny = -dy / L, dx / L
                # taper: older points thinner; width scales with intensity
                fa = (i + 1) / n
                fb = (i + 2) / n
                wa = (C.TRAIL_BASE_WIDTH + (C.TRAIL_MAX_WIDTH - C.TRAIL_BASE_WIDTH) * in0) * fa
                wb = (C.TRAIL_BASE_WIDTH + (C.TRAIL_MAX_WIDTH - C.TRAIL_BASE_WIDTH) * in1) * fb
                # color: cool->white-hot with intensity, alpha by age & intensity
                def col(inten, f):
                    r = 0.4 + 0.6 * inten
                    g = 0.7 + 0.3 * inten
                    bl = 1.0
                    a = (0.15 + 0.85 * inten) * f
                    return (r, g, bl, a)
                ca = col(in0, fa)
                cb = col(in1, fb)
                # two triangles for the quad segment
                p0a = (x0 + nx * wa, y0 + ny * wa)
                p0b = (x0 - nx * wa, y0 - ny * wa)
                p1a = (x1 + nx * wb, y1 + ny * wb)
                p1b = (x1 - nx * wb, y1 - ny * wb)
                for (px, py), c in ((p0a, ca), (p0b, ca), (p1a, cb),
                                    (p1b, cb), (p1a, cb), (p0b, ca)):
                    verts.extend((px, py, *c))
        if not verts:
            return
        data = np.array(verts, dtype="f4").tobytes()
        if len(data) > self.trail_vbo.size:
            self.trail_vbo.orphan(len(data))
        self.trail_vbo.write(data)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE  # additive
        self.trail_vao.render(moderngl.TRIANGLES, vertices=len(verts) // 6)

    def draw_particles(self, particles):
        if not particles:
            return
        arr = np.empty((len(particles), 7), dtype="f4")
        for i, p in enumerate(particles):
            a = p.alpha
            arr[i] = (p.x, p.y, p.color[0], p.color[1], p.color[2], a, p.size)
        data = arr.tobytes()
        if len(data) > self.part_vbo.size:
            self.part_vbo.orphan(len(data))
        self.part_vbo.write(data)
        self.ctx.enable(moderngl.PROGRAM_POINT_SIZE)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE  # additive
        self.part_vao.render(moderngl.POINTS, vertices=len(particles))

    def postprocess(self, flash, shake=(0.0, 0.0)):
        # bright pass -> half res
        self.ctx.disable(moderngl.BLEND)
        self.bright_fbo.use()
        self.ctx.clear(0, 0, 0)
        self.scene_tex.use(0)
        self.bright_prog["tex"].value = 0
        self.bright_prog["threshold"].value = C.BLOOM_THRESHOLD
        self.fs_bright.render(moderngl.TRIANGLE_STRIP)

        # gaussian blur ping-pong
        src = self.bright_tex
        for i in range(4):
            dst = self.blur_fbo[i % 2]
            dst.use()
            self.ctx.clear(0, 0, 0)
            src.use(0)
            self.blur_prog["tex"].value = 0
            if i % 2 == 0:
                self.blur_prog["dir"].value = (1.0 / self.half[0], 0.0)
            else:
                self.blur_prog["dir"].value = (0.0, 1.0 / self.half[1])
            self.fs_blur.render(moderngl.TRIANGLE_STRIP)
            src = self.blur_tex[i % 2]

        # composite to screen
        self.ctx.screen.use()
        self.ctx.clear(0, 0, 0)
        self.scene_tex.use(0)
        src.use(1)
        self.comp_prog["scene"].value = 0
        self.comp_prog["bloom"].value = 1
        self.comp_prog["intensity"].value = C.BLOOM_INTENSITY
        self.comp_prog["flash"].value = flash
        self.comp_prog["shake"].value = (shake[0] / self.res[0], shake[1] / self.res[1])
        self.fs_comp.render(moderngl.TRIANGLE_STRIP)

    def draw_text(self, text, x, y, size, color=(1, 1, 1), center=True, alpha=1.0):
        """Draw text to the currently bound framebuffer (call after postprocess)."""
        tex, w, h = self._text_texture(text, size, color)
        x0 = x - w / 2 if center else x
        y0 = y - h / 2 if center else y
        # build a quad in clip space
        def cx(px): return px / self.res[0] * 2 - 1
        def cy(py): return 1 - py / self.res[1] * 2
        verts = np.array([
            cx(x0),     cy(y0 + h), 0, 0,
            cx(x0 + w), cy(y0 + h), 1, 0,
            cx(x0),     cy(y0),     0, 1,
            cx(x0 + w), cy(y0),     1, 1,
        ], dtype="f4")
        vbo = self.ctx.buffer(verts.tobytes())
        vao = self.ctx.vertex_array(self.tex_prog, [(vbo, "2f 2f", "in_pos", "in_uv")])
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        tex.use(0)
        self.tex_prog["tex"].value = 0
        vao.render(moderngl.TRIANGLE_STRIP)
        vbo.release()
        vao.release()
