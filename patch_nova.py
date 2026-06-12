with open('nova.py', 'r') as f:
    content = f.read()

compatibility_layer = """# --- WSL2 / LINUX COMPATIBILITY LAYER ---
import sys
import platform
from unittest.mock import MagicMock

if platform.system() != "Windows":
    print("🛠️ Linux/WSL2 detected: Activating Windows compatibility shims...")
    
    # 1. Mock winsound
    sys.modules['winsound'] = MagicMock()
    
    # 2. Mock win32com & win32com.client with terminal audio printout
    class MockSpeaker:
        def Speak(self, text):
            print(f"\\n🔊 [NOVA Voice]: {text}\\n")
    
    class MockWin32Client:
        def Dispatch(self, name):
            return MockSpeaker() if name == "SAPI.SpVoice" else MagicMock()
            
    sys.modules['win32com'] = MagicMock()
    sys.modules['win32com.client'] = MockWin32Client()
    
    # 3. Mock pycaw
    sys.modules['pycaw'] = MagicMock()
    sys.modules['pycaw.pycaw'] = MagicMock()
    
    # 4. Mock screen_brightness_control
    sbc_mock = MagicMock()
    sbc_mock.get_brightness.return_value = [50]
    sys.modules['screen_brightness_control'] = sbc_mock
    
    # 5. Mock pyautogui
    sys.modules['pyautogui'] = MagicMock()
# ----------------------------------------
"""

if "# --- WSL2 / LINUX COMPATIBILITY LAYER ---" not in content:
    with open('nova.py', 'w') as f:
        f.write(compatibility_layer + "\n" + content)
    print("🎉 Successfully patched nova.py with Linux compatibility layer!")
else:
    print("⚠️ nova.py is already patched.")
