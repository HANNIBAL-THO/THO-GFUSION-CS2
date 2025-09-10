import os
import time
import math
import random
import json
import threading
import ctypes
import struct
from ctypes import wintypes
from collections import deque

from Process.offsets import Offsets
from Process.config import Config

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE  = 0x00000008
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260),
    ]

VIRTUAL_KEYS = {
    "mouse1": 0x01,
    "mouse2": 0x02,
    "mouse3": 0x04,
    "mouse4": 0x05,
    "mouse5": 0x06,
    "left_shift": 0xA0,
    "left_ctrl": 0xA2,
    "left_alt": 0xA4,
    "caps_lock": 0x14,
}

def get_vk_code(key_name):
    return VIRTUAL_KEYS.get(key_name.lower(), None)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_PERMISSIONS = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")
NtReadVirtualMemory = ntdll.NtReadVirtualMemory
NtReadVirtualMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t)
]
NtReadVirtualMemory.restype = ctypes.c_ulong

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _fields_ = [("type", ctypes.c_ulong), ("ii", _INPUT)]

SendInput = ctypes.windll.user32.SendInput

def move_mouse(dx, dy):
    mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=None)
    inp = INPUT(type=INPUT_MOUSE, ii=INPUT._INPUT(mi=mi))
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

class IMemoryReader:
    def read(self, address: int, t: str = "int"):
        raise NotImplementedError

    def read_vec3(self, address: int):
        raise NotImplementedError

class RPMReader(IMemoryReader):
    """Read memory using kernel32.ReadProcessMemory"""
    def __init__(self, process_handle):
        self.process_handle = process_handle

    def read(self, addr, t="int"):
        size_map = {"int": 4, "long": 8, "float": 4, "ushort": 2}
        size = size_map.get(t, 4)
        buffer = (ctypes.c_ubyte * size)()
        bytes_read = ctypes.c_size_t()

        success = kernel32.ReadProcessMemory(
            self.process_handle,
            ctypes.c_void_p(addr),
            ctypes.byref(buffer),
            size,
            ctypes.byref(bytes_read)
        )
        if not success or bytes_read.value != size:
            return 0.0 if t == "float" else 0

        raw = bytes(buffer[:size])
        if t == "int":
            return int.from_bytes(raw, "little", signed=True)
        elif t == "long":
            return int.from_bytes(raw, "little", signed=False)
        elif t == "float":
            return struct.unpack("f", raw)[0]
        elif t == "ushort":
            return int.from_bytes(raw, "little", signed=False)
        return 0

    def read_vec3(self, address):
        raw = self.read_bytes(address, 12)
        if raw:
            return list(struct.unpack("fff", raw))
        return [0.0, 0.0, 0.0]

    def read_bytes(self, addr, size):
        buffer = (ctypes.c_ubyte * size)()
        bytes_read = ctypes.c_size_t()
        success = kernel32.ReadProcessMemory(
            self.process_handle,
            ctypes.c_void_p(addr),
            ctypes.byref(buffer),
            size,
            ctypes.byref(bytes_read)
        )
        if not success or bytes_read.value != size:
            return None
        return bytes(buffer[:bytes_read.value])

class NtVMReader(IMemoryReader):
    """Read memory using ntdll.NtReadVirtualMemory"""
    def __init__(self, process_handle):
        self.process_handle = process_handle

    def read(self, addr, t="int"):
        size_map = {"int": 4, "long": 8, "float": 4, "ushort": 2}
        size = size_map.get(t, 4)
        raw = self.read_bytes(addr, size)
        if not raw:
            return 0.0 if t == "float" else 0

        if t == "int":
            return int.from_bytes(raw, "little", signed=True)
        elif t == "long":
            return int.from_bytes(raw, "little", signed=False)
        elif t == "float":
            return struct.unpack("f", raw)[0]
        elif t == "ushort":
            return int.from_bytes(raw, "little", signed=False)
        return 0

    def read_vec3(self, address):
        raw = self.read_bytes(address, 12)
        if raw:
            return list(struct.unpack("fff", raw))
        return [0.0, 0.0, 0.0]

    def read_bytes(self, addr, size):
        buffer = (ctypes.c_ubyte * size)()
        bytes_read = ctypes.c_size_t()
        status = NtReadVirtualMemory(
            self.process_handle,
            ctypes.c_void_p(addr),
            ctypes.byref(buffer),
            size,
            ctypes.byref(bytes_read)
        )
        if status != 0 or bytes_read.value != size:
            return None
        return bytes(buffer[:bytes_read.value])

class CS2Process:
    def __init__(self, proc_name="cs2.exe", mod_name="client.dll", timeout=30):
        self.process_name = proc_name.encode()
        self.module_name = mod_name.encode()
        self.wait_timeout = timeout
        self.process_handle = None
        self.process_id = None
        self.module_base = None

    def _get_pid(self):
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == INVALID_HANDLE_VALUE:
            return None
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if not kernel32.Process32First(snap, ctypes.byref(entry)):
            kernel32.CloseHandle(snap)
            return None
        while True:
            if entry.szExeFile == self.process_name:
                pid = entry.th32ProcessID
                kernel32.CloseHandle(snap)
                return pid
            if not kernel32.Process32Next(snap, ctypes.byref(entry)):
                break
        kernel32.CloseHandle(snap)
        return None

    def _get_module_base(self):
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, self.process_id)
        if snap == INVALID_HANDLE_VALUE:
            return None
        mod = MODULEENTRY32()
        mod.dwSize = ctypes.sizeof(MODULEENTRY32)
        if not kernel32.Module32First(snap, ctypes.byref(mod)):
            kernel32.CloseHandle(snap)
            return None
        while True:
            if mod.szModule == self.module_name:
                base = ctypes.cast(mod.modBaseAddr, ctypes.c_void_p).value
                kernel32.CloseHandle(snap)
                return base
            if not kernel32.Module32Next(snap, ctypes.byref(mod)):
                break
        kernel32.CloseHandle(snap)
        return None

    def wait_for_process(self):
        start = time.time()
        while time.time() - start < self.wait_timeout:
            self.process_id = self._get_pid()
            if self.process_id:
                self.process_handle = kernel32.OpenProcess(PROCESS_PERMISSIONS, False, self.process_id)
                if self.process_handle:
                    return True
            time.sleep(0.5)
        raise TimeoutError("Process not found")

    def get_module_base(self):
        self.module_base = self._get_module_base()
        if not self.module_base:
            raise Exception("Module not found")

    def initialize(self):
        self.wait_for_process()
        self.get_module_base()

    def __repr__(self):
        return f"<CS2Process pid={self.process_id} module_base=0x{self.module_base:x}>" if self.module_base else "<CS2Process not ready>"

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _fields_ = [("type", ctypes.c_ulong), ("ii", _INPUT)]

SendInput = ctypes.windll.user32.SendInput

def move_mouse(dx, dy):
    mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=None)
    inp = INPUT(type=INPUT_MOUSE, ii=INPUT._INPUT(mi=mi))
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


class MemoryReader:
    def __init__(self, process_handle):
        self.process_handle = process_handle

    def read(self, address, t="int"):
        size_map = {"int": 4, "long": 8, "float": 4, "ushort": 2}
        size = size_map.get(t, 4)
        raw = nt_read_memory(self.process_handle, address, size)
        if not raw:
            return 0.0 if t == "float" else 0
        if t == "int":
            return bytes_to_int(raw)
        elif t == "long":
            return bytes_to_int(raw, signed=False)
        elif t == "float":
            return bytes_to_float(raw)
        elif t == "ushort":
            return bytes_to_int(raw, signed=False)
        return 0

    def read_vec3(self, address):
        raw = nt_read_memory(self.process_handle, address, 12)
        if raw:
            return list(bytes_to_vec3(raw))
        return [0.0, 0.0, 0.0]

class CS2WeaponTracker:
    INVALID_WEAPON_IDS = {
        41, 42, 59, 80, 500, 505, 506, 507, 508, 509, 512, 514, 515, 516, 519, 520, 522, 523,
        44, 43, 45, 46, 47, 48, 49
    }

    def __init__(self):
        self.cs2process = CS2Process()
        self.cs2process.wait_for_process()
        self.cs2process.get_module_base()
        self.process_handle = self.cs2process.process_handle
        self.client = self.cs2process.module_base
        
        self.reader = RPMReader(self.process_handle)

    def read_longlong(self, address):
        return self.reader.read(address, "long")

    def read_int(self, address):
        return self.reader.read(address, "int")

    def get_current_weapon_id(self):
        local_player = self.read_longlong(self.client + Offsets.dwLocalPlayerPawn)
        if not local_player:
            return None
        weapon_ptr = self.read_longlong(local_player + Offsets.m_pClippingWeapon)
        if not weapon_ptr:
            return None
        item_idx_addr = weapon_ptr + Offsets.m_AttributeManager + Offsets.m_Item + Offsets.m_iItemDefinitionIndex
        return self.reader.read(item_idx_addr, "ushort")

    def is_weapon_valid_for_aim(self):
        weapon_id = self.get_current_weapon_id()
        if weapon_id is None:
            return True
        return weapon_id not in self.INVALID_WEAPON_IDS
        
class AimbotRCS:
    MAX_DELTA_ANGLE = 60
    SENSITIVITY = None
    INVERT_Y = -1
    LEARN_DIR = None

    def __init__(self, cfg):
        self.cfg = cfg
        self.o = Offsets()
        self.cs2 = CS2Process()
        self.cs2.initialize()
        self.base = self.cs2.module_base
        self.process_handle = self.cs2.process_handle
        
        self.reader = RPMReader(self.process_handle)
        self.local_player_controller = self.base + self.o.dwLocalPlayerController  

        self.bone_indices = {"head": 6, "chest": 18}
        self.left_down = False
        self.shots_fired = 0
        self.last_punch = (0.0, 0.0)
        self.target_id = None
        self.last_target_lost_time = 0
        self.aim_start_time = None
        self.last_aim_angle = None
        self.lock = threading.Lock()

        self.weapon_tracker = CS2WeaponTracker()  

        self.learning_data = {}
        self.learning_dirty = False

        threading.Thread(target=self.periodic_save, daemon=True).start()

        self._isnan = math.isnan
        self._hypot = math.hypot
        self._atan2 = math.atan2
        self._degrees = math.degrees

    def read_vec3(self, addr):
        return self.reader.read_vec3(addr)

    def read(self, addr, t="int"):
        return self.reader.read(addr, t)


    def is_cs2_focused(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return False

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        PROCESS_VM_READ = 0x0010
        PROCESS_QUERY_INFORMATION = 0x0400

        hProcess = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid.value)
        if not hProcess:
            return False

        try:
            buffer_len = wintypes.DWORD(260)
            exe_path_buffer = ctypes.create_unicode_buffer(buffer_len.value)
            
            QueryFullProcessImageName = kernel32.QueryFullProcessImageNameW
            if not QueryFullProcessImageName(hProcess, 0, exe_path_buffer, ctypes.byref(buffer_len)):
                return False

            exe_name = exe_path_buffer.value.split("\\")[-1].lower()
            return exe_name == "cs2.exe"
        finally:
            kernel32.CloseHandle(hProcess)
            
    def periodic_save(self):
        while not self.cfg.aim_stop:
            time.sleep(30)
            if self.cfg.enable_learning and self.learning_dirty:
                self.save_learning()
                self.learning_dirty = False

    def load_learning(self):
        self.learning_data = {}
        if not os.path.exists(self.cfg.learn_dir):
            os.makedirs(self.cfg.learn_dir)

        weapon_id = self.weapon_tracker.get_current_weapon_id()
        if not weapon_id:
            return

        filepath = os.path.join(self.cfg.learn_dir, f"{weapon_id}.json")
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            self.learning_data = {
                tuple(map(float, k.split(','))): deque([tuple(x) for x in v], maxlen=50)
                for k, v in data.items()
            }
        except (FileNotFoundError, json.JSONDecodeError):
            self.learning_data = {}

    def save_learning(self):
        if not self.cfg.enable_learning:
            return

        weapon_id = self.weapon_tracker.get_current_weapon_id()
        if not weapon_id:
            return

        filepath = os.path.join(self.cfg.learn_dir, f"{weapon_id}.json")
        try:
            with self.lock, open(filepath, "w") as f:
                data = {f"{k[0]},{k[1]}": list(v) for k, v in self.learning_data.items()}
                json.dump(data, f)
        except Exception as e:
            print(f"[!] Failed saving learning data for weapon {weapon_id}: {e}")


    kernel32 = ctypes.windll.kernel32

    def get_entity(self, base, idx):
        array_idx = (idx & 0x7FFF) >> 9
        entity_addr = self.read(base + 8 * array_idx + 16, "long")
        if not entity_addr:
            return 0
        ctrl = self.read(entity_addr + 0x78 * (idx & 0x1FF), "long")
        local_ctrl = self.read(self.local_player_controller, "long")  
        return ctrl if ctrl and ctrl != local_ctrl else 0

    def read_bone_pos(self, pawn, idx):
        scene = self.read(pawn + self.o.m_pGameSceneNode, "long")
        if not scene:
            return None
        bones = self.read(scene + self.o.m_pBoneArray, "long")
        if not bones:
            return None
        return self.read_vec3(bones + idx * 32)

    def read_weapon_id(self, pawn):
        w = self.read(pawn + self.o.m_pClippingWeapon, "long")
        if not w:
            return 0
        return self.read(w + self.o.m_AttributeManager + self.o.m_Item + self.o.m_iItemDefinitionIndex, "ushort")

    def calc_angle(self, src, dst):
        dx = dst[0] - src[0]
        dy = dst[1] - src[1]
        dz = dst[2] - src[2]
        hyp = self._hypot(dx, dy)
        pitch = -self._degrees(self._atan2(dz, hyp))
        yaw = self._degrees(self._atan2(dy, dx))
        return pitch, yaw

    def normalize(self, pitch, yaw):
        if self._isnan(pitch) or self._isnan(yaw):
            return 0.0, 0.0
        pitch = max(min(pitch, 89.0), -89.0)
        yaw = (yaw + 180.0) % 360.0 - 180.0
        return pitch, yaw

    def angle_diff(self, a, b):
        d = (a - b + 180) % 360 - 180
        return d

    def in_fov(self, pitch1, yaw1, pitch2, yaw2):
        dp = self.angle_diff(pitch2, pitch1)
        dy = self.angle_diff(yaw2, yaw1)
       
        return (dp * dp + dy * dy) <= (self.cfg.FOV * self.cfg.FOV)

    @staticmethod
    def lerp(a, b, t):
        return a + (b - a) * t

    @staticmethod
    def add_noise(value, max_noise=0.03):
        return value + random.uniform(-max_noise, max_noise)

    def clamp_angle_diff(self, current, target, max_delta=MAX_DELTA_ANGLE):
        d = self.angle_diff(target, current)
        if abs(d) > max_delta:
            d = max_delta if d > 0 else -max_delta
        return current + d

    def on_click(self, x, y, btn, pressed):
        if btn == mouse.Button.left:
            self.left_down = pressed
            self.aim_start_time = time.perf_counter() if pressed else None
            if not pressed:
                self.shots_fired = 0
                self.last_punch = (0.0, 0.0)
                self.last_aim_angle = None

    def update_learning(self, key, dp, dy, alpha=0.15):
        with self.lock:
            if key not in self.learning_data:
                self.learning_data[key] = deque(maxlen=50)
            if self.learning_data[key]:
                last_dp, last_dy = self.learning_data[key][-1]
                dp = (1 - alpha) * last_dp + alpha * dp
                dy = (1 - alpha) * last_dy + alpha * dy
            self.learning_data[key].append((dp, dy))
            self.learning_dirty = True

    def get_learned_correction(self, key):
        if not self.cfg.enable_learning:
            return 0.0, 0.0
        corrections = self.learning_data.get(key)
        if not corrections:
            return 0.0, 0.0
        dp_avg = sum(x[0] for x in corrections) / len(corrections)
        dy_avg = sum(x[1] for x in corrections) / len(corrections)
        return dp_avg, dy_avg

    def quantize_angle(self, pitch, yaw, shots_fired, step=1.0):
        pitch_q = round(pitch / step) * step
        yaw_q = round(yaw / step) * step
        sf_bin = shots_fired
        return (pitch_q, yaw_q, sf_bin)

    def get_current_bone_index(self, pawn=None, my_pos=None, pitch=None, yaw=None, frame_time=1.0/60):
        if not self.cfg.closest_to_crosshair:
            return self.bone_indices.get(self.cfg.target_bone_name, 6)

        if not pawn or not my_pos:
            return self.bone_indices.get("head", 6)

        read = self.read
        bone_pos_fn = self.read_bone_pos
        angle_diff = self.angle_diff
        isnan = self._isnan

        best_index = None
        best_distance = float('inf')

        cfg_bones = self.cfg.bone_indices_to_try
        enable_velocity_prediction = self.cfg.enable_velocity_prediction
        downward_offset = self.cfg.downward_offset

        vp_factor = getattr(self.cfg, 'velocity_prediction_factor', 1.0)
        smoothing = vp_factor * frame_time

        vel = None
        if enable_velocity_prediction:
            vel = self.read_vec3(pawn + self.o.m_vecVelocity)

        for idx in cfg_bones:
            pos = bone_pos_fn(pawn, idx)
            if not pos:
                continue

            if enable_velocity_prediction and vel:
                pos = [pos[i] + vel[i] * smoothing for i in range(3)]

            pos[2] -= downward_offset

            p, y = self.calc_angle(my_pos, pos)
            if isnan(p) or isnan(y):
                continue

            dist = math.hypot(angle_diff(p, pitch), angle_diff(y, yaw))
            if dist < best_distance:
                best_distance = dist
                best_index = idx

        return best_index if best_index is not None else self.bone_indices.get("head", 6)

    def run(self):
        from ctypes import windll
        GetAsyncKeyState = windll.user32.GetAsyncKeyState

        prev_weapon_id = None
        max_fps = 60
        frame_time = 1.0 / max_fps

        entity_cache = {}
        cache_refresh_rate = 0.2  
        last_cache_time = 0

        def normalize_angle_delta(delta):
            while delta > 180:
                delta -= 360
            while delta < -180:
                delta += 360
            return delta

        def squared_distance(a, b):
            return sum((a[i] - b[i]) ** 2 for i in range(3))

        def is_valid_target(pawn, my_team):
            if not pawn:
                return False
            health = self.read(pawn + self.o.m_iHealth)
            if health <= 0:
                return False
            if self.read(pawn + self.o.m_lifeState) != 256:
                return False
            if self.read(pawn + self.o.m_bDormant, "int"):
                return False
            team = self.read(pawn + self.o.m_iTeamNum)
            return self.cfg.DeathMatch or team != my_team

        while not self.cfg.aim_stop:
            start_time = time.perf_counter()

            try:
                aim_vk = get_vk_code(self.cfg.aim_key)
                if aim_vk is None or not self.is_cs2_focused():
                    time.sleep(0.1)
                    continue

                self.left_down = GetAsyncKeyState(aim_vk) & 0x8000 != 0

                if not self.cfg.enabled:
                    time.sleep(0.01)
                    continue

                base = self.base
                o = self.o
                pawn = self.read(base + o.dwLocalPlayerPawn, "long")
                if not pawn:
                    continue

                weapon_id = self.weapon_tracker.get_current_weapon_id()
                if weapon_id != prev_weapon_id:
                    self.load_learning()
                    prev_weapon_id = weapon_id

                if self.read(pawn + o.m_iHealth) <= 0:
                    continue

                if not self.weapon_tracker.is_weapon_valid_for_aim():
                    continue

                ctrl = self.read(base + o.dwLocalPlayerController, "long")
                my_team = self.read(pawn + o.m_iTeamNum)
                my_pos = self.read_vec3(pawn + o.m_vOldOrigin)

                view_angles_addr = base + o.dwViewAngles
                pitch = self.read(view_angles_addr, "float")
                yaw = self.read(view_angles_addr + 4, "float")
                recoil_pitch = self.read(pawn + o.m_aimPunchAngle, "float")
                recoil_yaw = self.read(pawn + o.m_aimPunchAngle + 4, "float")

                entity_list = self.read(base + o.dwEntityList, "long")
                if not entity_list:
                    continue

                if time.time() - last_cache_time > cache_refresh_rate:
                    entity_cache.clear()
                    for i in range(self.cfg.max_entities):
                        ctrl_ent = self.get_entity(entity_list, i)
                        if not ctrl_ent or ctrl_ent == ctrl:
                            continue
                        pawn_ent = self.get_entity(entity_list, self.read(ctrl_ent + o.m_hPlayerPawn) & 0x7FFF)
                        if not pawn_ent or not is_valid_target(pawn_ent, my_team):
                            continue
                        entity_cache[i] = (ctrl_ent, pawn_ent)
                    last_cache_time = time.time()

                target, target_pos = None, None

                if self.target_id in entity_cache:
                    _, t_pawn = entity_cache[self.target_id]
                    bone_idx = self.get_current_bone_index(t_pawn, my_pos, pitch, yaw, frame_time=frame_time)
                    pos = self.read_bone_pos(t_pawn, bone_idx) or self.read_vec3(t_pawn + o.m_vOldOrigin)
                    vel = self.read_vec3(t_pawn + o.m_vecVelocity) if self.cfg.enable_velocity_prediction else [0, 0, 0]
                    prediction_dt = frame_time * getattr(self.cfg, "velocity_prediction_factor", 1.0)
                    predicted = [pos[i] + vel[i] * prediction_dt for i in range(3)]
                    predicted[2] -= self.cfg.downward_offset
                    tp, ty = self.calc_angle(my_pos, predicted)
                    if any(map(math.isnan, (tp, ty))) or not self.in_fov(pitch, yaw, tp, ty):
                        self.target_id = None
                        self.last_target_lost_time = time.time()
                    else:
                        target, target_pos = t_pawn, predicted

                if target is None:
                    if self.last_target_lost_time and (time.time() - self.last_target_lost_time) < self.cfg.target_switch_delay:
                        continue
                    min_dist = float("inf")
                    for i, (_, pawn_ent) in entity_cache.items():
                        bone_idx = self.get_current_bone_index(pawn_ent, my_pos, pitch, yaw, frame_time=frame_time)
                        pos = self.read_bone_pos(pawn_ent, bone_idx) or self.read_vec3(pawn_ent + o.m_vOldOrigin)
                        vel = self.read_vec3(pawn_ent + o.m_vecVelocity) if self.cfg.enable_velocity_prediction else [0, 0, 0]
                        prediction_dt = frame_time * getattr(self.cfg, "velocity_prediction_factor", 1.0)
                        predicted = [pos[j] + vel[j] * prediction_dt for j in range(3)]
                        predicted[2] -= self.cfg.downward_offset
                        tp, ty = self.calc_angle(my_pos, predicted)
                        if any(map(math.isnan, (tp, ty))) or not self.in_fov(pitch, yaw, tp, ty):
                            continue
                        dist = squared_distance(my_pos, predicted)
                        if dist < min_dist:
                            min_dist = dist
                            target, target_pos, self.target_id = pawn_ent, predicted, i

                if self.left_down:
                    self.shots_fired += 1
                    if self.aim_start_time and time.time() - self.aim_start_time < self.cfg.aim_start_delay:
                        continue
                    if target and target_pos:
                        tp, ty = self.calc_angle(my_pos, target_pos)
                        if abs(self.angle_diff(ty, yaw)) > 90:
                            continue

                        scale = self.cfg.rcs_scale * min(self.shots_fired / 2, 1.0)
                        if self.cfg.rcs_enabled:
                            compensated_pitch = self.clamp_angle_diff(pitch, tp - recoil_pitch * scale)
                            compensated_yaw = self.clamp_angle_diff(yaw, ty - recoil_yaw * scale)
                        else:
                            compensated_pitch = self.clamp_angle_diff(pitch, tp)
                            compensated_yaw = self.clamp_angle_diff(yaw, ty)

                        smooth = max(0.01, min(self.cfg.smooth_base + random.uniform(-self.cfg.smooth_var, self.cfg.smooth_var), 0.25))
                        key = self.quantize_angle(compensated_pitch, compensated_yaw, self.shots_fired)
                        dp, dy = self.get_learned_correction(key)
                        compensated_pitch += dp
                        compensated_yaw += dy

                        interp_pitch = pitch + (compensated_pitch - pitch) * smooth
                        interp_yaw = yaw + (compensated_yaw - yaw) * smooth

                        sp = self.add_noise(interp_pitch, 0.03)
                        sy = self.add_noise(interp_yaw, 0.03)
                        sp, sy = self.normalize(sp, sy)

                        delta_pitch = normalize_angle_delta(sp - pitch)
                        delta_yaw = normalize_angle_delta(sy - yaw)

                        delta_pitch = max(min(delta_pitch, self.cfg.max_delta_angle), -self.cfg.max_delta_angle)
                        delta_yaw = max(min(delta_yaw, self.cfg.max_delta_angle), -self.cfg.max_delta_angle)

                        mouse_dx = int(-delta_yaw / self.cfg.sensitivity)
                        mouse_dy = int(-delta_pitch / self.cfg.sensitivity) * self.cfg.invert_y

                        mouse_dx = max(min(mouse_dx, self.cfg.max_mouse_move), -self.cfg.max_mouse_move)
                        mouse_dy = max(min(mouse_dy, self.cfg.max_mouse_move), -self.cfg.max_mouse_move)

                        move_mouse(mouse_dx, mouse_dy)

                        if self.last_aim_angle:
                            lp, ly = self.last_aim_angle
                            if abs(self.angle_diff(sp, lp)) > 0.002 or abs(self.angle_diff(sy, ly)) > 0.002:
                                dp_learn = max(min(sp - pitch, 1.0), -1.0)
                                dy_learn = max(min(sy - yaw, 1.0), -1.0)
                                if abs(dp_learn) > 0.05 or abs(dy_learn) > 0.05:
                                    self.update_learning(key, dp_learn, dy_learn)

                        self.last_aim_angle = (sp, sy)
                    else:
                        self.last_aim_angle = None
                else:
                    self.shots_fired = 0
                    self.last_aim_angle = None

            except Exception as e:
                print(f"[!] AimbotRCS error: {e}")
                time.sleep(0.3)

            elapsed = time.perf_counter() - start_time
            sleep_time = max(0.0, frame_time - elapsed)
            time.sleep(sleep_time)

        if self.cfg.enable_learning:
            self.save_learning()
        print("[AimbotRCS] Stopped.")

def start_aim_rcs(cfg):
    AimbotRCS(cfg).run()