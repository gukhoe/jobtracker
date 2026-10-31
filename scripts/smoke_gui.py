"""Synthetic desktop smoke fixture; never reads the author's real profile."""
import json
import sys
import tempfile
import ctypes
import struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jobtracker.desktop import App
from jobtracker.store import Store

tmp=tempfile.TemporaryDirectory(prefix='jobtracker-ui-')
s=Store(tmp.name)
p=s.save_profile('Demo profile',dict(keywords='engineering, design',locations='',currency='USD',minimum_base=100000,facts='Synthetic fixture. No real personal information.'))
s.upsert_job(p,dict(company='Example Robotics',title='Senior Mechanical Engineer',location='Remote',url='https://example.org/careers/1',description='Synthetic demonstration listing. Confirm all real openings on official company pages.',availability='unverified',salary_basis='unknown'))
s.save_resume(p,'Demo source resume','Synthetic engineering experience. Replace with your own verified resume.')
a=App(s)
if '--settings' in sys.argv:
    a.tabs.select(a.pages['AI settings'])
    a.settings_form()
if '--schedule' in sys.argv:
    a.tabs.select(a.pages['Research & schedule'])
    a.schedule_form()
a.update()
Path('build/gui-state.json').write_text(json.dumps(dict(hwnd=a.winfo_id(),width=a.winfo_width(),height=a.winfo_height(),tabs=len(a.tabs.tabs()))))
if '--capture' in sys.argv:
    # Capture this test process's own window on its own desktop. No OS input.
    from ctypes import wintypes as w
    user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    user.GetParent.restype=w.HWND
    user.GetWindowDC.restype=w.HDC
    gdi.CreateCompatibleDC.restype=w.HDC
    gdi.CreateCompatibleBitmap.restype=w.HBITMAP
    gdi.SelectObject.restype=w.HANDLE
    user.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
    user.GetWindowDC.argtypes=[w.HWND]
    user.PrintWindow.argtypes=[w.HWND,w.HDC,w.UINT]
    gdi.CreateCompatibleDC.argtypes=[w.HDC]
    gdi.CreateCompatibleBitmap.argtypes=[w.HDC,ctypes.c_int,ctypes.c_int]
    gdi.SelectObject.argtypes=[w.HDC,w.HANDLE]
    gdi.GetDIBits.argtypes=[w.HDC,w.HBITMAP,w.UINT,w.UINT,ctypes.c_void_p,ctypes.c_void_p,w.UINT]
    child = next((x for x in a.winfo_children() if x.winfo_class() == 'Toplevel'),a)
    hwnd=user.GetParent(child.winfo_id())
    rect=w.RECT(); user.GetWindowRect(hwnd,ctypes.byref(rect))
    width,height=rect.right-rect.left,rect.bottom-rect.top
    dc=user.GetWindowDC(hwnd); mem=gdi.CreateCompatibleDC(dc)
    bitmap=gdi.CreateCompatibleBitmap(dc,width,height); prev=gdi.SelectObject(mem,bitmap)
    ok=user.PrintWindow(hwnd,mem,2)
    header=struct.pack('<IiiHHIIiiII',40,width,height,1,32,0,width*height*4,0,0,0,0)
    info=ctypes.create_string_buffer(header)
    pixels=ctypes.create_string_buffer(width*height*4)
    lines=gdi.GetDIBits(mem,bitmap,0,height,pixels,info,0)
    Path('build/gui-preview.bmp').write_bytes(struct.pack('<2sIHHI',b'BM',54+len(pixels),0,0,54)+header+pixels.raw)
    print('Window capture:',bool(ok),'lines:',lines,'size:',width,height)
if '--quick' in sys.argv:
    a.after(2000,a.destroy)
a.mainloop()
tmp.cleanup()
