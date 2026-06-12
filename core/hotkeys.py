from __future__ import annotations

import threading
import time

from pynput import keyboard

from core.logging_config import get_logger

logger = get_logger(__name__)

try:
    import hid
    HID_AVAILABLE = True
except Exception:
    hid = None
    HID_AVAILABLE = False


VENDOR_ID = 0x0911
BUTTON_PRESS_EVENT = 0x80
RECORD_BUTTON_MASK = 1 << 8


class SpeechMikeHID:
    def __init__(self):
        self.device = None

    def open(self) -> bool:
        if not HID_AVAILABLE:
            return False

        candidates = []

        for d in hid.enumerate():

            if d["vendor_id"] != VENDOR_ID:
                continue

            path = d["path"]

            path_str = (
                path.decode(errors="ignore")
                if isinstance(path, bytes)
                else str(path)
            )

            iface = d.get("interface_number")

            logger.info(
                f"SpeechMike candidate: "
                f"path={path_str} "
                f"iface={iface}"
            )

            score = 0

            # Linux
            if ".4" in path_str:
                score += 100

            # Windows
            if "MI_04" in path_str.upper():
                score += 100

            # macOS fallback
            if iface == 4:
                score += 50

            candidates.append((score, d))

        candidates.sort(key=lambda x: x[0], reverse=True)

        for score, d in candidates:
            try:
                h = hid.device()
                h.open_path(d["path"])
                h.set_nonblocking(True)

                self.device = h

                logger.info(
                    f"SpeechMike connected: "
                    f"path={d['path']} "
                    f"score={score}"
                )

                return True

            except Exception as e:
                logger.warning(
                    f"Failed opening {d['path']}: {e}"
                )

        return False

    def read(self):
        if not self.device:
            return None

        try:
            return self.device.read(64)

        except OSError:
            return None

        except Exception as e:
            logger.debug(f"HID read error: {e}")
            return None

    def close(self):
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass

            self.device = None

    @staticmethod
    def get_button_mask(data) -> int | None:
        if len(data) < 9:
            return None

        if data[0] != BUTTON_PRESS_EVENT:
            return None

        return data[7] | (data[8] << 8)


class GlobalHotkey:
    def __init__(self, on_toggle):
        self.on_toggle = on_toggle

        self.listener = None

        self.hid = SpeechMikeHID()
        self.hid_thread = None
        self.running = False

    def start(self) -> bool:
        try:

            def on_press(key):
                if key == keyboard.Key.f9:
                    logger.info("F9 pressed")
                    self.on_toggle()

            self.listener = keyboard.Listener(on_press=on_press)
            self.listener.daemon = True
            self.listener.start()

            logger.info(
                "Global hotkey listener started "
                "(F9 + SpeechMike Record)"
            )

        except Exception as e:
            logger.error(f"Failed to start keyboard listener: {e}")
            return False

        self.running = True

        if self.hid.open():
            self.hid_thread = threading.Thread(
                target=self._hid_loop,
                daemon=True
            )
            self.hid_thread.start()

        return True

    def _hid_loop(self):
        last_mask = 0

        while self.running:

            data = self.hid.read()

            if not data:
                time.sleep(0.01)
                continue

            mask = self.hid.get_button_mask(data)

            if mask is None:
                continue

            if mask == last_mask:
                continue

            logger.info(f"SpeechMike button mask: 0x{mask:04x}")

            record_was_pressed = bool(last_mask & RECORD_BUTTON_MASK)
            record_is_pressed = bool(mask & RECORD_BUTTON_MASK)

            last_mask = mask

            if record_is_pressed and not record_was_pressed:
                logger.info("SpeechMike RECORD pressed")
                self.on_toggle()

            time.sleep(0.005)

    def stop(self) -> None:
        self.running = False

        if self.listener is not None:
            import time as _time

            try:
                _t = _time.perf_counter()

                self.listener.stop()

                logger.info(
                    f"[SHUTDOWN] listener.stop(): "
                    f"{_time.perf_counter() - _t:.3f}s"
                )

                _t = _time.perf_counter()

                self.listener.join(timeout=2.0)

                logger.info(
                    f"[SHUTDOWN] listener.join(): "
                    f"{_time.perf_counter() - _t:.3f}s "
                    f"(alive={self.listener.is_alive()})"
                )

            except Exception as e:
                logger.warning(
                    f"Error stopping hotkey listener: {e}"
                )

            finally:
                self.listener = None

        if self.hid_thread:
            self.hid_thread.join(timeout=1.0)

        self.hid.close()
