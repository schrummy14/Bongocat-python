# Bongocat-python

[![wakatime](https://wakatime.com/badge/user/70908aa3-b2c6-4f44-a07f-7bd45f260e48/project/ca59bf83-0ceb-4a3b-9775-d57abbd8338f.svg)](https://wakatime.com/badge/user/70908aa3-b2c6-4f44-a07f-7bd45f260e48/project/ca59bf83-0ceb-4a3b-9775-d57abbd8338f)

Bongo Cat in python.

- Mouse tracking (with movable arms draw in Bézier lines)
- Keyboard tracking
- Windowless and auto translucency

To run the code, you need to install the packages:

- numpy
- pyopengl
- moderngl
- glfw
- yaml
- ~keyboard~
- pynput
- pywin32

## For Linux (Fedora 43 and Python3.13)

### Installation

To run the code, install the dependencies from requirements.txt

`python3 -m pip install -r requirements.txt`

### First run

You will need to edit the python file for now to have it find the correct input devices.
Comment out the lines:
```python3
my_devices = ['/dev/input/event2', '/dev/input/event4']
self.input_monitor = InputMonitor(mode.size.width, mode.size.height, my_devices)
```
and un-comment:
```python3
self.input_monitor = InputMonitor(mode.size.width, mode.size.height)
```

This will have the code load all of your input devices. You should get something similar when calling it `python3 Cat_linux.py`:
```bash
DEBUG :: dev: device /dev/input/event5, name "Keychron Keychron Q11 Mouse", phys "usb-0000:79:00.0-1.2/input2", uniq ""
  ✔ Mount: Keychron Keychron Q11 Mouse
DEBUG :: dev: device /dev/input/event4, name "Keychron Keychron Q11", phys "usb-0000:79:00.0-1.2/input0", uniq ""
  ✔ Mount: Keychron Keychron Q11
DEBUG :: dev: device /dev/input/event3, name "Logitech G502 X Keyboard", phys "usb-0000:13:00.0-3/input1", uniq "208337695247"
  ✔ Mount: Logitech G502 X Keyboard
DEBUG :: dev: device /dev/input/event2, name "Logitech G502 X", phys "usb-0000:13:00.0-3/input0", uniq "208337695247"
  ✔ Mount: Logitech G502 X
DEBUG :: dev: device /dev/input/event1, name "Power Button", phys "LNXPWRBN/button/input0", uniq ""
  ✔ Mount: Power Button
DEBUG :: dev: device /dev/input/event0, name "Power Button", phys "PNP0C0C/button/input0", uniq ""
  ✔ Mount: Power Button
```

From here, you can either use the program as is or alter the `my_devices` variable to include only the inputs you want.
