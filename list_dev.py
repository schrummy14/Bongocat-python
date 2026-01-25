import evdev
import os

print(f"{'EVENT PATH':<20} | {'DEVICE NAME'}")
print("-" * 50)

try:
    # 获取所有设备路径
    paths = evdev.list_devices()
    
    # 实例化设备对象
    devices = [evdev.InputDevice(path) for path in paths]
    
    # 遍历打印
    for dev in devices:
        print(f"{dev.path:<20} | {dev.name}")
        # 如果你想看更详细的物理路径（用于区分相同的设备），取消下面这行的注释
        # print(f"   -> Phys: {dev.phys}")

except OSError:
    print("❌ 权限不足！请尝试: sudo python list_devices.py")
except Exception as e:
    print(f"❌ 发生错误: {e}")
