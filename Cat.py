import moderngl
import glfw
import numpy as np
import yaml
import time
import os
import ctypes

from pynput import keyboard as pynput_keyboard

# WIN 32 API Imports
import win32api
import win32gui
import win32con
import win32print

# Win 高 DPI 支持
ctypes.windll.shcore.SetProcessDpiAwareness(1)

def scale(x, y, z):
    a = np.eye(4, dtype="f4")
    a[0, 0] = x
    a[1, 1] = y
    a[2, 2] = z
    return a

def rotate(r, axis: tuple):
    a = np.eye(4, dtype="f4") 
    c, s = np.cos(r), np.sin(r) 
    a[axis[0], axis[0]] = c
    a[axis[0], axis[1]] = s 
    a[axis[1], axis[0]] = -s
    a[axis[1], axis[1]] = c
    return a

def translate(x, y, z):
    a = np.eye(4, dtype="f4")
    a[3, 0] = x
    a[3, 1] = y
    a[3, 2] = z
    return a

class Layer:
    def __init__(self, ctx, name, bbox, npdata):
        self.ctx = ctx
        self.name = name

        h, w_img = npdata.shape[:2]
        d = 2**int(max(np.log2(w_img), np.log2(h)) + 1)
        texture_data = np.zeros((d, d, 4), dtype='f4')
        texture_data[:h, :w_img] = npdata
        
        self.texture = self.ctx.texture((d, d), 4, texture_data.tobytes(), dtype='f4')
        self.texture.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        self.texture.build_mipmaps()
        self.texture.swizzle = 'BGRA'
        
        w_tex = w_img / d
        q_tex = h / d
        a, b, c, d_box = bbox
        
        vertices = np.array([
            a, d_box, w_tex, 0.0,
            a, b,     0.0,   0.0,
            c, d_box, w_tex, q_tex,
            c, b,     0.0,   q_tex
        ], dtype='f4')
        
        self.vbo = self.ctx.buffer(vertices.tobytes())
        self.vao = None

    def render(self, program, model_matrix, offset=(0, 0)):
        if not self.vao:
            self.vao = self.ctx.vertex_array(program, [(self.vbo, '2f 2f', 'in_vert', 'in_uv')])
        self.texture.use(location=0)
        program['offset'].value = offset
        program['model'].write(model_matrix.astype('f4').tobytes())
        self.vao.render(moderngl.TRIANGLE_STRIP)


class Keyboard:
    def __init__(self, ctx, key_yaml):
        self.ctx = ctx
        self.key_layers = {}
        self.active_keys = set()

        with open(key_yaml, encoding='utf8') as f:
            data = yaml.safe_load(f)

        for key_name, info in data.items():
            try:
                self.key_layers[key_name.lower()] = Layer(self.ctx, key_name, info['bbox'], np.load(info['path']))
            except Exception as e:
                print(f"Failed to load key layer {key_name}: {e}")
                pass
                
        self.listener = pynput_keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.listener.start()

    def _get_key_name(self, key):
        try:
            if hasattr(key, 'char') and key.char:
                return key.char.lower()
            return key.name
        except:
            return str(key)

    def on_press(self, key):
        k = self._get_key_name(key)
        if k == 'return':
            k = 'enter'
        if k in self.key_layers:
            self.active_keys.add(k)

    def on_release(self, key):
        k = self._get_key_name(key)
        if k == 'return':
            k = 'enter'
        if k in self.key_layers:
            self.active_keys.discard(k)

    def render(self, program, model_matrix):
        for key_name in list(self.active_keys):
            if key_name in self.key_layers:
                self.key_layers[key_name].render(program, model_matrix)

    def stop(self):
        self.listener.stop()

class MouseMapping:
    def __init__(self, window_title, window_height, alpha_opt, pad_area):
        self.window_title = window_title
        self.window_h = window_height
        self.y_offset = alpha_opt[0] if alpha_opt else 0
        self.min_alpha = int((alpha_opt[1] if alpha_opt else 0.4) * 255)
        
        hDC = win32gui.GetDC(0)
        self.sw = win32print.GetDeviceCaps(hDC, win32con.DESKTOPHORZRES)
        self.sh = win32print.GetDeviceCaps(hDC, win32con.DESKTOPVERTRES)
        win32gui.ReleaseDC(0, hDC)
        self.hwnd = win32gui.FindWindow(None, self.window_title)
            
        src = np.array([
            [0, 0], 
            [self.sw, 0], 
            [self.sw, self.sh], 
            [0, self.sh]
        ], dtype="f4")
        dst = np.array(pad_area, dtype="f4")
        
        self.M = self._get_perspective_matrix(src, dst)
        self.is_translucent = False 

    def _get_perspective_matrix(self, src, dst):
        A = np.zeros((8, 8))
        b = np.zeros((8))
        
        for i in range(4):
            sx, sy = src[i]
            dx, dy = dst[i]
            A[i*2] = [sx, sy, 1, 0, 0, 0, -sx*dx, -sy*dx]
            A[i*2+1] = [0, 0, 0, sx, sy, 1, -sx*dy, -sy*dy]
            b[i*2] = dx
            b[i*2+1] = dy
            
        h = np.linalg.solve(A, b)
        return np.append(h, [1]).reshape((3, 3))

    def update(self, current_win_pos):
        mx, my = win32api.GetCursorPos()
        
        win_x, win_y = current_win_pos
        win_w, win_h = 612, 354 
        is_hover = (win_x <= mx <= win_x + win_w) and \
                   (win_y <= my <= win_y + win_h - self.y_offset)
        
        if self.hwnd:
            if is_hover and not self.is_translucent:
                win32gui.SetLayeredWindowAttributes(self.hwnd, 0, self.min_alpha, win32con.LWA_ALPHA)
                self.is_translucent = True
            elif not is_hover and self.is_translucent:
                win32gui.SetLayeredWindowAttributes(self.hwnd, 0, 255, win32con.LWA_ALPHA)
                self.is_translucent = False
        
        vec = np.array([mx, my, 1])
        mapped = self.M @ vec
        if mapped[2] != 0:
            return mapped[0] / mapped[2], mapped[1] / mapped[2] 
        return 0, 0

class Cat:
    def __init__(self, init_yaml, key_yaml, conf_path):
        with open(conf_path, encoding='utf8') as f:
            conf = yaml.safe_load(f)
            self.bezier_start = conf["bezier_start"]
            self.bezier_finish = conf["bezier_finish"]
            self.draw_constant = conf["draw_constant"]
            opacity_conf = conf.get("move_up", [0, 0.4]) 
            self.move_up_y = opacity_conf[0]
            self.mouse_map_points = conf.get("mouse_map", None)

        glfw.init()
        glfw.window_hint(glfw.DECORATED, False)
        glfw.window_hint(glfw.TRANSPARENT_FRAMEBUFFER, True)
        glfw.window_hint(glfw.FLOATING, True)
        glfw.window_hint(glfw.SAMPLES, 4)
        glfw.window_hint(glfw.RESIZABLE, False)
        
        self.window_title = "Cat"
        self.window_w, self.window_h = 612, 354
        self.window = glfw.create_window(self.window_w, self.window_h, self.window_title, None, None)
        
        glfw.make_context_current(self.window)
        monitor = glfw.get_primary_monitor()
        mode = glfw.get_video_mode(monitor)
        target_x = mode.size.width - self.window_w
        target_y = mode.size.height - self.window_h - int(self.move_up_y)
        glfw.set_window_pos(self.window, target_x, target_y)

        self.ctx = moderngl.create_context()
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.DEFAULT_BLENDING
        self.ctx.disable(moderngl.CULL_FACE)
        
        hwnd = win32gui.FindWindow(None, self.window_title)
        if hwnd:
            exStyle = win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOOLWINDOW
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, exStyle)
            win32gui.SetLayeredWindowAttributes(hwnd, 0, 255, win32con.LWA_ALPHA)

        self.layer_prog = self.ctx.program(
            vertex_shader=self._load_shader("./shader/layer.vert"), 
            fragment_shader=self._load_shader("./shader/layer.frag")
        )
        self.bezier_prog = self.ctx.program(
            vertex_shader=self._load_shader("./shader/bezier.vert"), 
            fragment_shader=self._load_shader("./shader/bezier.frag")
        )
        
        m_scale = scale(2/354, 2/612, 1) 
        m_trans = translate(-1, -1, 0)
        m_rot = rotate(-np.pi/2, axis=(0, 1))
        self.base_model = m_scale @ m_trans @ m_rot
        
        self.layers = []
        if os.path.exists(init_yaml):
            with open(init_yaml, encoding='utf8') as f:
                data = yaml.safe_load(f)
                for name, info in data.items():
                    try:
                        layer = Layer(self.ctx, name, info['bbox'], np.load(info['path']))
                        self.layers.append(layer)
                    except Exception as e:
                        print(f"Failed to load layer {name}: {e}")
                        pass

        self.key_manager = Keyboard(self.ctx, key_yaml)
        self.input_mapper = MouseMapping(
            self.window_title, 
            self.window_h, 
            opacity_conf, 
            self.mouse_map_points
        )
        
        self.bezier_vao = self.ctx.vertex_array(self.bezier_prog, [])

    def _load_shader(self, file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Shader file not found: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def get_skeleton(self):
        curr_pos = glfw.get_window_pos(self.window)
        map_x, map_y = self.input_mapper.update(curr_pos)
        
        control = np.array([map_x, map_y])
        start = np.array(self.bezier_start[0:2])
        finish = np.array(self.bezier_finish[0:2])
        
        dist = np.linalg.norm(control - start)
        kc = np.array([0.69, -0.7237])
        
        center_l = start + 1 * kc * dist / 2
        p_a = center_l[1] - control[1]
        p_b = control[0] - center_l[0]
        p_ab = np.array([p_a, p_b])
        
        le = np.linalg.norm(p_ab)
        if le > 0:
            p_ab = control + (45/le) * p_ab
        
        dist = np.linalg.norm(finish - p_ab)
        kc2 = np.array([0.8, -0.6])
        center_r = finish + 0.5 * kc2 * dist / 2
        p_st = control - center_r
        
        le = np.linalg.norm(p_st)
        if le > 0:
            p_st = p_st * (20/le)
            
        p_st2 = p_ab - center_r
        le = np.linalg.norm(p_st2)
        if le > 0:
            p_st2 = p_st2 * (20/le)
        
        raw_res = (
            tuple(start), tuple(center_l), tuple(control),
            tuple(control), tuple(control + p_st), tuple(p_ab + p_st2), tuple(p_ab),
            tuple(p_ab), tuple(center_r), tuple(finish)
        )
        
        mouse_dxy = (control + p_ab)/2 + np.array(self.draw_constant[:2]) - np.array([124, 203])
        return raw_res, mouse_dxy

    def render(self):
        self.bezier_prog['model'].write(self.base_model.astype('f4').tobytes())
        self.bezier_prog['total_verts'].value = 100

        while not glfw.window_should_close(self.window):
            self.ctx.clear(0, 0, 0, 0)
            raw_res, mouse_dxy = self.get_skeleton()
            for layer in self.layers:
                offset = mouse_dxy if layer.name == "mouse" else (0, 0)
                layer.render(self.layer_prog, self.base_model, offset)
            self.key_manager.render(self.layer_prog, self.base_model)
            self.bezier_prog['raw_res'].value = raw_res
            self.bezier_prog['color'].value = (1.0, 1.0, 1.0, 1.0)
            self.bezier_vao.render(moderngl.TRIANGLE_FAN, vertices=100)
            self.bezier_prog['color'].value = (0.0, 0.0, 0.0, 1.0)
            self.ctx.line_width = self.draw_constant[2]
            self.bezier_vao.render(moderngl.LINE_STRIP, vertices=100)
            glfw.swap_buffers(self.window)
            glfw.poll_events()
            time.sleep(1/30)
        
        self.key_manager.stop()
        glfw.terminate()

if __name__ == '__main__':
    app = Cat(
        init_yaml="./Cat/init.yaml",
        key_yaml="./Cat/keyinf.yaml",
        conf_path="./conf.yaml"
    )
    app.render()
