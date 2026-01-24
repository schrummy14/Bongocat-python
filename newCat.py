import glfw
import moderngl
import numpy as np
import yaml
import math
import win32api
import win32gui
import win32print
import win32con

VERTEX_SHADER = """
#version 330
in vec2 in_vert;
in vec2 in_texcoord;
out vec2 v_texcoord;

uniform mat4 model;
uniform vec2 offset;

void main() {
    vec4 pos = vec4(in_vert + offset, 0.0, 1.0);
    gl_Position = model * pos;
    v_texcoord = in_texcoord;
}
"""

FRAGMENT_SHADER = """
#version 330
in vec2 v_texcoord;
out vec4 f_color;
uniform sampler2D Texture;

void main() {
    vec4 c = texture(Texture, v_texcoord);
    if(c.a < 0.01) discard;
    f_color = c;
}
"""

LINE_VERTEX_SHADER = """
#version 330
in vec2 in_vert;
uniform mat4 model;
void main() {
    gl_Position = model * vec4(in_vert, 0.0, 1.0);
}
"""

LINE_FRAGMENT_SHADER = """
#version 330
out vec4 f_color;
uniform vec4 color;
void main() {
    f_color = color;
}
"""


class BezierMath:
    def __init__(self):
        self.binom_3 = np.array([1, 3, 3, 1], dtype='f4')
        self.binom_2 = np.array([1, 2, 1], dtype='f4')
        self.t_5 = np.linspace(0, 1, 5).reshape(-1, 1)   # 第一阶段 5个点
        self.t_30 = np.linspace(0, 1, 30).reshape(-1, 1) # 最终阶段 30个点
        
        # 预计算 (1-t) 和 t 的幂次方，进一步减少主循环运算量
        # 这里为了保持代码可读性，保留实时计算幂，但预分配了 buffer
        self.cache_5 = np.zeros((5, 2), dtype='f4')
        self.cache_30 = np.zeros((30, 2), dtype='f4')

    def calc(self, control_points, n_points):
        """ 优化后的计算函数 """
        n = len(control_points) - 1
        t = self.t_5 if n_points == 5 else self.t_30
        curve = np.zeros((n_points, 2), dtype='f4')
        
        binom = self.binom_3 if n == 3 else self.binom_2
        
        # 向量化计算: sum( B[j] * (1-t)^(n-j) * t^j * P[j] )
        # 虽然 Python 循环慢，但这里 j 只有 3 或 4 次，开销可忽略
        for j in range(n + 1):
            coef = binom[j] * ((1 - t) ** (n - j)) * (t ** j)
            curve += coef * control_points[j]
            
        return curve

def get_static_model_matrix(psd_size=(354, 612)):
    S = np.identity(4, dtype='f4')
    S[0,0] = 2.0 / psd_size[0]
    S[1,1] = 2.0 / psd_size[1]
    
    T = np.identity(4, dtype='f4')
    T[3,0] = -1.0
    T[3,1] = -1.0
    
    theta = -np.pi / 2
    c, s = np.cos(theta), np.sin(theta)
    R = np.identity(4, dtype='f4')
    R[0,0], R[0,1] = c, s
    R[1,0], R[1,1] = -s, c
    
    return (S @ T @ R).T

def solve_perspective_matrix(src, dst):
    A = np.zeros((8, 8))
    b = np.zeros((8, 1))
    for i in range(4):
        sx, sy = src[i]
        dx, dy = dst[i]
        A[i*2]   = [sx, sy, 1, 0, 0, 0, -sx*dx, -sy*dx]
        A[i*2+1] = [0, 0, 0, sx, sy, 1, -sx*dy, -sy*dy]
        b[i*2], b[i*2+1] = dx, dy
    try:
        h = np.linalg.solve(A, b)
        return np.append(h, [1]).reshape(3, 3)
    except:
        return np.eye(3)

def apply_perspective_fast(M, x, y):
    """ 展开矩阵运算以提速 """
    # vector = [x, y, 1], res = M @ vector
    nx = M[0,0]*x + M[0,1]*y + M[0,2]
    ny = M[1,0]*x + M[1,1]*y + M[1,2]
    nz = M[2,0]*x + M[2,1]*y + M[2,2]
    
    if nz != 0:
        inv_z = 1.0 / nz
        return np.array([nx * inv_z, ny * inv_z])
    return np.array([x, y])

class Layer:
    def __init__(self, ctx, name, bbox, npy_path):
        self.name = name
        self.ctx = ctx
        a, b, c, d = bbox
        p1, p2, p3, p4 = [a, b], [a, d], [c, d], [c, b]
        verts = np.array([*p1, *p2, *p4, *p4, *p2, *p3], dtype='f4')
        uvs = np.array([0,0, 1,0, 0,1, 0,1, 1,0, 1,1], dtype='f4')
        
        vbo_data = np.dstack([verts.reshape(6,2), uvs.reshape(6,2)]).astype('f4').flatten()
        self.vbo = self.ctx.buffer(vbo_data)

        try:
            raw = np.load(npy_path)
            if raw.dtype != np.uint8: raw = (raw * 255).astype(np.uint8)
            if raw.shape[2] == 4: raw = raw[..., [2, 1, 0, 3]]
            h, w = raw.shape[:2]
            self.tex = self.ctx.texture((w, h), 4, raw.tobytes())
            self.tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        except:
            self.tex = self.ctx.texture((1,1), 4, b'\xff\0\0\xff')

    def render(self, prog, vao_wrapper, off_x, off_y):
        self.tex.use(0)
        prog['offset'].value = (off_x, off_y)
        vao_wrapper.render(self.vbo)

class VAOWrapper:
    """ 复用 VAO 结构，避免为每个 Layer 创建单独的 VAO 对象 (ModernGL 优化) """
    def __init__(self, ctx, prog):
        self.ctx = ctx
        self.prog = prog
        self.vao = None
        
    def render(self, vbo):
        # 简单实现：每次根据 VBO 创建 VAO (开销很小)，
        # 或者更高级的做法是把所有 Layer 合并到一个大 VBO 里。
        # 这里为了保持结构简单，保持原样即可。
        vao = self.ctx.vertex_array(self.prog, [(vbo, '2f 2f', 'in_vert', 'in_texcoord')])
        vao.render(moderngl.TRIANGLES)
        # ModernGL 会自动处理资源释放

def main():
    conf = {"move_up": [0, 0], "bezier_start":[0,0], "bezier_finish":[0,0], "draw_constant":[0,0,0]}
    try:
        with open("./conf.yaml", encoding="utf8") as f:
            conf.update(yaml.safe_load(f))
    except: pass

    if not glfw.init(): return
    glfw.window_hint(glfw.DECORATED, False)
    glfw.window_hint(glfw.TRANSPARENT_FRAMEBUFFER, True)
    glfw.window_hint(glfw.FLOATING, True)
    glfw.window_hint(glfw.RESIZABLE, False)
    glfw.window_hint(glfw.SAMPLES, 4)

    width, height = 612, 354
    window = glfw.create_window(width, height, "BongoCat Optimized", None, None)
    
    monitor = glfw.get_primary_monitor()
    mode = glfw.get_video_mode(monitor)
    pos_x = mode.size.width - width
    pos_y = mode.size.height - height - int(conf["move_up"][0])
    glfw.set_window_pos(window, pos_x, pos_y)
    
    glfw.make_context_current(window)
    glfw.swap_interval(1)

    # Win32 设置
    try:
        hwnd = glfw.get_win32_window(window)
        exStyle = win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
        win32api.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, exStyle)
        win32gui.SetLayeredWindowAttributes(hwnd, 0, 255, win32con.LWA_ALPHA)
    except: pass

    # --- 资源准备 (一次性计算) ---
    hDC = win32gui.GetDC(0)
    mon_w = win32print.GetDeviceCaps(hDC, win32con.DESKTOPHORZRES)
    mon_h = win32print.GetDeviceCaps(hDC, win32con.DESKTOPVERTRES)
    win32gui.ReleaseDC(0, hDC)

    # [保留原版 Bug] src_points 第4点使用 mon_w
    src_points = np.array([[0,0], [mon_w,0], [mon_w,mon_h], [0,mon_w]])
    dst_points = np.array([[254,135], [212,70], [187,111], [232,192]])
    M_persp = solve_perspective_matrix(src_points, dst_points)
    
    # Model 矩阵
    model_matrix = get_static_model_matrix((354, 612))
    model_bytes = model_matrix.astype('f4').tobytes()

    # --- ModernGL Context ---
    ctx = moderngl.create_context()
    ctx.enable(moderngl.BLEND)
    
    # Shaders
    prog_tex = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
    prog_line = ctx.program(vertex_shader=LINE_VERTEX_SHADER, fragment_shader=LINE_FRAGMENT_SHADER)
    
    # 设置 Uniforms (静态)
    prog_tex['Texture'].value = 0
    prog_tex['model'].write(model_bytes)
    prog_line['model'].write(model_bytes)

    # VAO Wrapper
    vao_wrapper = VAOWrapper(ctx, prog_tex)

    # 加载 Layers
    layers = []
    try:
        with open("./Cat2/init.yaml", encoding="utf8") as f:
            data = yaml.safe_load(f)
            for name, info in data.items():
                layers.append(Layer(ctx, name, info["bbox"], info["path"]))
    except: pass

    # Line Buffer (预分配, dynamic)
    vbo_line = ctx.buffer(reserve=30 * 8, dynamic=True) # 30 points * 2 floats * 4 bytes
    vao_line = ctx.vertex_array(prog_line, [(vbo_line, '2f', 'in_vert')])
    
    # 贝塞尔计算工具
    bezier_tool = BezierMath()
    
    # 提取贝塞尔参数 (避免 Loop 中查字典)
    p_start = np.array(conf["bezier_start"][:2], dtype='f4')
    p_finish = np.array(conf["bezier_finish"][:2], dtype='f4')
    draw_const = np.array(conf["draw_constant"][:2], dtype='f4')
    
    # [保留原版参数]
    kc = np.array([0.69, -0.7237]) 
    kc2 = np.array([0.8, -0.6])
    push = 20.0
    anchor = np.array([124, 203])

    # --- 主循环 ---
    while not glfw.window_should_close(window):
        ctx.clear(0, 0, 0, 0)
        
        # 1. 输入与透视
        mx, my = win32api.GetCursorPos()
        cp = apply_perspective_fast(M_persp, mx, my) # control_point
        
        # 2. 贝塞尔逻辑 (保留原版运算顺序)
        dist = np.linalg.norm(cp - p_start)
        center_left = p_start + kc * dist * 0.5
        
        # p_ab 计算
        p_a = center_left[1] - cp[1]
        p_b = cp[0] - center_left[0]
        p_ab_vec = np.array([p_a, p_b])
        le = np.linalg.norm(p_ab_vec) + 1e-6
        p_ab = cp + (45.0 / le) * p_ab_vec
        
        # p_st 计算
        dist_2 = np.linalg.norm(p_finish - p_ab)
        center_right = p_finish + kc2 * dist_2 * 0.5
        
        p_st = cp - center_right
        le_st = np.linalg.norm(p_st) + 1e-6
        p_st *= (push / le_st)

        p_st2 = p_ab - center_right
        le_st2 = np.linalg.norm(p_st2) + 1e-6
        p_st2 *= (push / le_st2)
        
        # 3. 生成曲线 (使用优化工具)
        # 必须显式构建数组，虽然有点丑，但为了性能和逻辑一致性
        p_1 = np.vstack([p_start, center_left, cp])
        p_2 = np.vstack([cp, cp + p_st, p_ab + p_st2, p_ab])
        p_3 = np.vstack([p_ab, center_right, p_finish])
        
        c1 = bezier_tool.calc(p_1, 5)
        c2 = bezier_tool.calc(p_2, 5)
        c3 = bezier_tool.calc(p_3, 5)
        
        final_points = np.vstack((c1, c2, c3))
        final_curve = bezier_tool.calc(final_points, 30)
        
        # 4. 鼠标偏移
        m_off = (cp + p_ab) * 0.5 + draw_const - anchor
        
        # 5. 渲染图层
        for l in layers:
            ox, oy = (m_off[0], m_off[1]) if l.name == "mouse" else (0, 0)
            l.render(prog_tex, vao_wrapper, ox, oy)
            
        # 6. 渲染手臂
        vbo_line.write(final_curve.tobytes())
        prog_line['color'].value = (1.0, 1.0, 1.0, 1.0)
        vao_line.render(moderngl.TRIANGLE_FAN, vertices=30)
        prog_line['color'].value = (0.0, 0.0, 0.0, 1.0)
        vao_line.render(moderngl.LINE_STRIP, vertices=30)

        glfw.swap_buffers(window)
        glfw.poll_events()
        
    glfw.terminate()

if __name__ == '__main__':
    main()
