import moderngl
import glfw
import numpy as np
import yaml
import time
import os
import threading
import select

import evdev
from evdev import ecodes

def scale(x, y, z):
    a = np.eye(4, dtype="f4")
    a[0, 0] = x; a[1, 1] = y; a[2, 2] = z
    return a

def rotate(r, axis: tuple):
    a = np.eye(4, dtype="f4")
    c, s = np.cos(r), np.sin(r)
    a[axis[0], axis[0]] = c; a[axis[0], axis[1]] = s
    a[axis[1], axis[0]] = -s; a[axis[1], axis[1]] = c
    return a

def translate(x, y, z):
    a = np.eye(4, dtype="f4")
    a[3, 0] = x; a[3, 1] = y; a[3, 2] = z
    return a

class InputMonitor:
    def __init__(self, screen_w, screen_h, target_paths=None):
        self.mouse_x = screen_w / 2
        self.mouse_y = screen_h / 2
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.active_keys = set()
        self.running = True

        # 灵敏度设置 -> Sensitivity Settings
        self.rel_sensitivity = 4.0    # 普通鼠标灵敏度 -> Standard Mouse Sensitivity
        self.abs_sensitivity = 0.4    # 触控板/数位板相对位移灵敏度 -> Touchpad/Tablet Relative Displacement Sensitivity

        self.monitored_devs = []
        self.abs_info = {}
        self.pending_frames = {}

        # 触控板追踪变量 -> Touchpad Tracking Variables
        self.last_abs_x = None
        self.last_abs_y = None

        print("-" * 30)
        if target_paths:
            try:
                for path in target_paths:
                    self._register_device(evdev.InputDevice(path))
            except Exception:
                print(f"ERROR :: Failed to register input device -> {path}")
                exit(1)
        else:
            for path in evdev.list_devices():
                try:
                    self._register_device(evdev.InputDevice(path), True)
                except: pass

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _register_device(self, dev, auto_filter=False):
        caps = dev.capabilities()
        # print(f"DEBUG :: dev: {dev}")
        if auto_filter and not (ecodes.EV_REL in caps or ecodes.EV_ABS in caps or ecodes.EV_KEY in caps):
            return
        # print(f"  ✔ 挂载: {dev.name}")
        print(f"  ✔ Mounting: {dev.name}")
        self.monitored_devs.append(dev)
        if ecodes.EV_ABS in caps:
            try:
                ax, ay = dev.absinfo(ecodes.ABS_X), dev.absinfo(ecodes.ABS_Y)
                if ax and ay:
                    self.abs_info[dev.fd] = {'min_x': ax.min, 'max_x': ax.max, 'min_y': ay.min, 'max_y': ay.max}
            except: pass

    def _loop(self):
        if not self.monitored_devs: return
        device_map = {dev.fd: dev for dev in self.monitored_devs}
        while self.running:
            try:
                r, _, _ = select.select(device_map, [], [], 1.0)
                for fd in r:
                    dev = device_map[fd]

                    for event in dev.read():
                        # === 1. 处理触控板绝对坐标 {Handling Touchpad Absolute Coordinates} (EV_ABS) ===
                        # 核心逻辑：计算手指滑动的 Delta(增量)，模拟光标移动 -> Core Logic: Calculate the delta (increment) of the finger swipe to simulate cursor movement.
                        # print(f"DEBUG :: New Event -> {event}")
                        if event.type == ecodes.EV_ABS:
                            if event.code == ecodes.ABS_X:
                                if self.last_abs_x is not None:
                                    delta_x = event.value - self.last_abs_x
                                    self.mouse_x += delta_x * self.abs_sensitivity
                                self.last_abs_x = event.value

                            elif event.code == ecodes.ABS_Y:
                                if self.last_abs_y is not None:
                                    delta_y = event.value - self.last_abs_y
                                    self.mouse_y += delta_y * self.abs_sensitivity
                                self.last_abs_y = event.value

                        # === 2. 处理手指抬起/放下 {Handle Finger Lift/Drop} (EV_KEY) ===
                        elif event.type == ecodes.EV_KEY:
                            # 处理键盘按键 -> Handling Keyboard Keys
                            if not event.code == ecodes.BTN_TOUCH:
                                if event.value in [0, 1]:
                                    k = ecodes.KEY.get(event.code)
                                    if isinstance(k, list): k = k[0]
                                    if isinstance(k, str) and not k.startswith("BTN_"):
                                        clean = k.replace("KEY_", "").lower()
                                        if clean in ["enter", "kpenter"]: clean = "enter"
                                        if clean == "leftmeta": clean = "win"
                                        if event.value == 1: self.active_keys.add(clean)
                                        else: self.active_keys.discard(clean)

                            # 🔥 关键：当手指离开触控板时 (BTN_TOUCH 0)，重置位置追踪 -> Key: When the finger lifts off the touchpad (BTN_TOUCH 0), reset position tracking.
                            elif event.code == ecodes.BTN_TOUCH and event.value == 0:
                                self.last_abs_x = None
                                self.last_abs_y = None

                        # === 3. 处理普通鼠标相对移动 (EV_REL) === -> Handling Relative Movement of a Standard Mouse (EV_REL)
                        elif event.type == ecodes.EV_REL:
                            if event.code == ecodes.REL_X:
                                self.mouse_x += event.value * self.rel_sensitivity
                            elif event.code == ecodes.REL_Y:
                                self.mouse_y += event.value * self.rel_sensitivity

                        # 同步信号通常用于绝对坐标的帧结算，在增量模式下可忽略或仅做位置边界检查
                        # Synchronization signals are typically used for frame resolution
                        # in absolute coordinate systems;
                        # in incremental mode, they may be ignored or used solely for position boundary checks.
                        elif event.type == ecodes.EV_SYN:
                            pass

                    # 每一帧结束确保坐标不越界 -> Ensure that coordinates remain within bounds at the end of every frame.
                    self.mouse_x = max(0, min(self.mouse_x, self.screen_w))
                    self.mouse_y = max(0, min(self.mouse_y, self.screen_h))
            except: pass

    def get_mouse_pos(self): return self.mouse_x, self.mouse_y
    def get_keys(self): return list(self.active_keys)
    def stop(self): self.running = False

# === 2. Layer (自动填充 Alpha，修复全透明 Bug) === -> (Auto-fill Alpha, Fix Fully Transparent Bug)
class Layer:
    def __init__(self, ctx, name, bbox, npdata):
        self.ctx = ctx
        self.name = name

        if npdata.dtype == np.uint8:
            npdata = npdata.astype('f4') / 255.0
        else:
            npdata = npdata.astype('f4')

        h, w_img = npdata.shape[:2]
        if npdata.ndim == 2: npdata = np.expand_dims(npdata, axis=2)

        d = 2**int(max(np.log2(w_img), np.log2(h)) + 1)
        texture_data = np.zeros((d, d, 4), dtype='f4')

        channels = npdata.shape[2]
        if channels == 3:
            texture_data[:h, :w_img, :3] = npdata
            texture_data[:h, :w_img, 3] = 1.0
        elif channels == 1:
            texture_data[:h, :w_img, 0] = npdata[:,:,0]
            texture_data[:h, :w_img, 1] = npdata[:,:,0]
            texture_data[:h, :w_img, 2] = npdata[:,:,0]
            texture_data[:h, :w_img, 3] = 1.0
        else:
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

# === 3. Keyboard ===
class Keyboard:
    def __init__(self, ctx, key_yaml):
        self.ctx = ctx
        self.key_layers = {}
        with open(key_yaml, encoding='utf8') as f:
            data = yaml.safe_load(f)
        for key_name, info in data.items():
            try:
                self.key_layers[key_name.lower()] = Layer(self.ctx, key_name, info['bbox'], np.load(info['path']))
            except Exception as e: print(f"Key load error {key_name}: {e}")

    def render(self, program, model_matrix, active_keys):
        for key_name in active_keys:
            if key_name in self.key_layers:
                self.key_layers[key_name].render(program, model_matrix)

# === 4. MouseMapping ===
class MouseMapping:
    def __init__(self, window_height, pad_area):
        monitor = glfw.get_primary_monitor()
        mode = glfw.get_video_mode(monitor)
        self.sw = mode.size.width
        self.sh = mode.size.height
        src = np.array([[0, 0], [self.sw, 0], [self.sw, self.sh], [0, self.sh]], dtype="f4")
        dst = np.array(pad_area, dtype="f4")
        self.M = self._get_perspective_matrix(src, dst)

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
        try:
            h = np.linalg.solve(A, b)
        except Exception:
            return np.eye(3)
        return np.append(h, [1]).reshape((3, 3))

    def update(self, global_mouse_pos):
        mx, my = global_mouse_pos
        mapped = self.M @ np.array([mx, my, 1])
        if mapped[2] != 0:
            return mapped[0] / mapped[2], mapped[1] / mapped[2]
        return 0, 0

# === 5. Main Cat Class ===
class Cat:
    def __init__(self, init_yaml, key_yaml, conf_path):
        with open(conf_path, encoding='utf8') as f:
            conf = yaml.safe_load(f)
            self.bezier_start = conf["bezier_start"]
            self.bezier_finish = conf["bezier_finish"]
            self.draw_constant = conf["draw_constant"]
            self.mouse_map_points = conf.get("mouse_map", None)
            self.input_devices = conf.get("input_devices", None)

        if not glfw.init(): raise Exception("GLFW failed")

        glfw.window_hint(glfw.DECORATED, False)
        glfw.window_hint(glfw.TRANSPARENT_FRAMEBUFFER, True)
        glfw.window_hint(glfw.FLOATING, True)
        glfw.window_hint(glfw.SAMPLES, 4)
        glfw.window_hint(glfw.RESIZABLE, False)
        try: glfw.window_hint(0x0002000D, True) # Mouse Passthrough
        except: pass

        self.window_w, self.window_h = 612*2//3, 354*2//3
        self.window = glfw.create_window(self.window_w, self.window_h, "Cat", None, None)
        if not self.window: glfw.terminate(); return
        glfw.make_context_current(self.window)

        # 输入设备 -> Input Devices
        monitor = glfw.get_primary_monitor()
        mode = glfw.get_video_mode(monitor)
        # my_devices = ['/dev/input/event2', '/dev/input/event4']
        my_devices = self._get_input_devices_from_conf()
        if my_devices:
            self.input_monitor = InputMonitor(mode.size.width, mode.size.height, my_devices)
        else:
            print("WARNING :: No input devices listed in config...")
            print("           Using all discovered input devices.")
            self.input_monitor = InputMonitor(mode.size.width, mode.size.height)

        # Context
        self.ctx = moderngl.create_context()
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)

        # Shaders (去掉 global_alpha 相关逻辑) -> (Remove global_alpha-related logic)
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
                    try: self.layers.append(Layer(self.ctx, name, info['bbox'], np.load(info['path'])))
                    except: pass

        self.key_manager = Keyboard(self.ctx, key_yaml)
        self.input_mapper = MouseMapping(self.window_h, self.mouse_map_points)
        self.bezier_vao = self.ctx.vertex_array(self.bezier_prog, [])

    def _get_input_devices_from_conf(self) -> set[str]:
        if self.input_devices is None:
            return set()
        my_devices = set()
        name2path = {}
        inputPaths = evdev.list_devices()
        for path in inputPaths:
            dev = evdev.InputDevice(path)
            name2path[dev.name] = path

        for entry in self.input_devices:
            k,v = list(entry.keys())[0], list(entry.values())[0]
            if k == "device":
                my_devices.add(v)
            elif k == "name":
                path = name2path.get(v, "None")
                if path == "None":
                    print(f"ERROR :: Device \"{v}\" was not found... Please double check device name.")
                    exit(1)
                my_devices.add(name2path[v])
            else:
                print(f"ERROR :: Invalid key [{k}] in config file...")
        return my_devices


    def _load_shader(self, path):
        with open(path, 'r', encoding='utf-8') as f: return f.read()

    def get_skeleton(self):
        g_mouse = self.input_monitor.get_mouse_pos()
        mx, my = self.input_mapper.update(g_mouse)
        control = np.array([mx, my])

        start = np.array(self.bezier_start[0:2])
        finish = np.array(self.bezier_finish[0:2])
        dist = np.linalg.norm(control - start)
        center_l = start + 1 * np.array([0.69, -0.7237]) * dist / 2
        p_ab = np.array([center_l[1] - control[1], control[0] - center_l[0]])
        le = np.linalg.norm(p_ab)
        if le > 0:
            p_ab = control + (45/le) * p_ab

        dist = np.linalg.norm(finish - p_ab)
        center_r = finish + 0.5 * np.array([0.8, -0.6]) * dist / 2
        p_st = control - center_r
        le = np.linalg.norm(p_st)
        if le > 0:
            p_st = p_st * (20/le)
        p_st2 = p_ab - center_r
        le = np.linalg.norm(p_st2)
        if le > 0:
            p_st2 = p_st2 * (20/le)

        raw_res = (tuple(start), tuple(center_l), tuple(control), tuple(control),
                   tuple(control + p_st), tuple(p_ab + p_st2), tuple(p_ab),
                   tuple(p_ab), tuple(center_r), tuple(finish))
        mouse_dxy = (control + p_ab)/2 + np.array(self.draw_constant[:2]) - np.array([124, 203])
        return raw_res, mouse_dxy

    def render(self):
        self.bezier_prog['model'].write(self.base_model.astype('f4').tobytes())
        self.bezier_prog['total_verts'].value = 100

        while not glfw.window_should_close(self.window):
            # 直接渲染到屏幕 -> Render directly to the screen
            self.ctx.screen.use()
            self.ctx.clear(0, 0, 0, 0)

            raw_res, dxy = self.get_skeleton()

            # 渲染图层 -> Render Layer
            for l in self.layers:
                off = dxy if l.name == "mouse" else (0, 0)
                l.render(self.layer_prog, self.base_model, off)

            active_keys = self.input_monitor.get_keys()
            self.key_manager.render(self.layer_prog, self.base_model, active_keys)

            # 渲染线条 -> Rendering Lines
            if 'color' in self.bezier_prog:
                self.bezier_prog['raw_res'].value = raw_res
                self.bezier_prog['color'].value = (1.0, 1.0, 1.0, 1.0) # Inside of mouse arm
                self.bezier_vao.render(moderngl.TRIANGLE_FAN, vertices=100)
                self.bezier_prog['color'].value = (0.0, 0.0, 0.0, 1.0) # Line of mouse arm
                self.ctx.line_width = self.draw_constant[2]
                self.bezier_vao.render(moderngl.LINE_STRIP, vertices=100)

            glfw.swap_buffers(self.window)
            glfw.poll_events()
            time.sleep(1/30) # ~30 fps

        self.input_monitor.stop()
        glfw.terminate()

if __name__ == '__main__':
    app = Cat("./Cat/init.yaml", "./Cat/keyinf.yaml", "./conf.yaml")
    app.render()
