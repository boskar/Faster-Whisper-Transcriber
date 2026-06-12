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
SET_LED_COMMAND = 0x02
RECORD_BUTTON_MASK = 1 << 8
INS_OVR_BUTTON_MASK = 1 << 14
LED_MODE_OFF = 0
LED_MODE_BLINK_FAST = 2
LED_MODE_ON = 3


class SpeechMikeHID:
    def __init__(self):
        self.device = None
        self._lock = threading.Lock()
        self._led_data = [0] * 8

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
            with self._lock:
                return self.device.read(64)

        except OSError:
            return None

        except Exception as e:
            logger.debug(f"HID read error: {e}")
            return None

    def _write_led_state(self) -> bool:
        if not self.device:
            return False
        report = [0x00, SET_LED_COMMAND, *self._led_data]

        try:
            with self._lock:
                self.device.write(report)
            return True
        except Exception as e:
            logger.warning(f"Failed to set SpeechMike LED: {e}")
            return False

    def set_append_led(self, enabled: bool) -> bool:
        # Clear INS/OVR green+red bits first.
        self._led_data[6] &= 0x0F

        if enabled:
            self._led_data[6] |= LED_MODE_ON << 4
        else:
            self._led_data[6] |= LED_MODE_ON << 6

        success = self._write_led_state()
        if success:
            logger.info(
                "SpeechMike INS/OVR LED set to %s",
                "green" if enabled else "red",
            )
        return success

    def set_record_led_mode(self, mode: int) -> bool:
        # Clear RECORD green+red bits first.
        self._led_data[5] &= 0xF0
        self._led_data[5] |= mode << 2

        success = self._write_led_state()
        if success:
            logger.info("SpeechMike RECORD LED mode set to %s", mode)
        return success

    def close(self):
        if self.device:
            try:
                self._led_data = [0] * 8
                self._write_led_state()
                with self._lock:
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
    def __init__(self, on_toggle, on_append_toggle=None):
        self.on_toggle = on_toggle
        self.on_append_toggle = on_append_toggle

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
                "(F9 + SpeechMike Record + SpeechMike Ins/Ovr)"
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
                time.sleep(0.002)
                continue

            if mask == last_mask:
                time.sleep(0.002)
                continue

            logger.info(f"SpeechMike button mask: 0x{mask:04x}")

            record_was_pressed = bool(last_mask & RECORD_BUTTON_MASK)
            record_is_pressed = bool(mask & RECORD_BUTTON_MASK)
            ins_ovr_was_pressed = bool(last_mask & INS_OVR_BUTTON_MASK)
            ins_ovr_is_pressed = bool(mask & INS_OVR_BUTTON_MASK)

            last_mask = mask

            if record_is_pressed and not record_was_pressed:
                logger.info("SpeechMike RECORD pressed")
                self.on_toggle()

            if (
                ins_ovr_is_pressed
                and not ins_ovr_was_pressed
                and self.on_append_toggle is not None
            ):
                logger.info("SpeechMike INS/OVR pressed")
                self.on_append_toggle()

            time.sleep(0.005)

    def stop(self) -> None:
        self.running = False

        if self.hid_thread:
            self.hid.close()
            self.hid_thread.join(timeout=1.0)
            self.hid_thread = None

        if self.listener is not None:
            import time as _time

            listener = self.listener
            self.listener = None

            try:
                _t = _time.perf_counter()

                stopper = threading.Thread(
                    target=listener.stop,
                    daemon=True,
                )
                stopper.start()
                stopper.join(0.5)

                logger.info(
                    f"[SHUTDOWN] listener.stop(): "
                    f"{_time.perf_counter() - _t:.3f}s"
                )

                if stopper.is_alive():
                    logger.warning(
                        "Hotkey listener stop is still pending; skipping join"
                    )
                else:
                    _t = _time.perf_counter()

                    listener.join(2.0)

                    logger.info(
                        f"[SHUTDOWN] listener.join(): "
                        f"{_time.perf_counter() - _t:.3f}s "
                        f"(alive={listener.is_alive()})"
                    )

            except Exception as e:
                logger.warning(
                    f"Error stopping hotkey listener: {e}"
                )

    def set_append_led(self, enabled: bool) -> bool:
        return self.hid.set_append_led(enabled)

    def set_record_led_mode(self, mode: int) -> bool:
        return self.hid.set_record_led_mode(mode)
