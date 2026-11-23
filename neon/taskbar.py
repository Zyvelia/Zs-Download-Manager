"""Optional Windows taskbar progress via ITaskbarList3; no-op on other platforms."""
import os

class TaskbarProgress:
    def __init__(self, window):
        self.window = window
        self.interface = None
        if os.name != 'nt': return
        try:
            import ctypes
            from ctypes import wintypes
            class GUID(ctypes.Structure):
                _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD), ('Data4', ctypes.c_ubyte * 8)]
            clsid = GUID(0x56FDF344,0xFD6D,0x11d0,(ctypes.c_ubyte*8)(0x95,0x8a,0x00,0x60,0x97,0xc9,0xa0,0x90))
            iid = GUID(0xea1afb91,0x9e28,0x4b86,(ctypes.c_ubyte*8)(0x90,0xe9,0x9e,0x9f,0x8a,0x5e,0xef,0xaf))
            ole = ctypes.OleDLL('ole32'); result = ctypes.c_void_p()
            ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
            ole.CoCreateInstance.restype = ctypes.c_long
            if ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(result)) < 0: return
            self.interface = result; self.ctypes = ctypes; self.wintypes = wintypes
            if self._call(3, ctypes.c_long, []) < 0: self.close()
        except (OSError, AttributeError, ValueError):
            self.interface = None

    def _call(self, index, restype, types, *args):
        c = self.ctypes
        table = c.cast(self.interface, c.POINTER(c.POINTER(c.c_void_p))).contents
        method = c.WINFUNCTYPE(restype, c.c_void_p, *types)(table[index])
        return method(self.interface, *args)

    def update(self, transfers):
        if not self.interface: return
        try:
            active = [d for d in transfers if d['status'] in ('Connecting', 'Downloading', 'Fetching metadata', 'Verifying')]
            hwnd = self.wintypes.HWND(int(self.window.winId()))
            state = 0 if not active else (1 if any(not d['total'] for d in active) else 2)
            self._call(10, self.ctypes.c_long, [self.wintypes.HWND, self.wintypes.DWORD], hwnd, state)
            if state == 2:
                done = sum(min(d['done'], d['total']) for d in active); total = sum(d['total'] for d in active)
                self._call(9, self.ctypes.c_long, [self.wintypes.HWND, self.ctypes.c_ulonglong, self.ctypes.c_ulonglong], hwnd, done, total)
        except (OSError, AttributeError, ValueError, OverflowError):
            self.close()

    def close(self):
        if self.interface:
            self._call(2, self.ctypes.c_ulong, [])
            self.interface = None
