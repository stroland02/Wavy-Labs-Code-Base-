# Wavy Labs — Claude Code Instructions

## Auto Build & Run
After completing **any** code change (C++, QSS, QML, Python, CMake), **always build and run without being asked**.

Build command (via Python subprocess — required for proper MSVC env):
```
python3 -c "
import subprocess, sys
r = subprocess.run(
    ['cmd.exe', '/c', r'C:\Users\Willow\Desktop\WL\do_build_lmms.bat'],
    capture_output=True, text=True,
    cwd=r'C:\Users\Willow\Desktop\WL'
)
out = r.stdout + r.stderr
print(out[:2000])
print('...')
print(out[-500:])
sys.exit(r.returncode)
"
```

Launch command (after successful build):
```
powershell.exe -Command "Stop-Process -Name lmms -Force -ErrorAction SilentlyContinue; Start-Sleep 1; Start-Process 'C:\Users\Willow\Desktop\WL\build\lmms.exe' -WorkingDirectory 'C:\Users\Willow\Desktop\WL\build'"
```

## Key Rules
- Kill lmms.exe before rebuilding (`Stop-Process -Name lmms -Force -ErrorAction SilentlyContinue`)
- If build fails, fix errors before launching
- QSS/QML changes require no C++ recompile but DO need a rebuild to regenerate embedded QRC
- Always show the last 20 lines of build output to confirm success
