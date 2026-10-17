import time
from pathlib import Path

import cv2
import numpy as np

from preprocess import IMG_SIZE, preprocess_mask

DEFAULT_OVERLAY = (
    "board/overlays/sign_preprocess_2026_1/sign_preprocess_2026_1.bit"
)
DEFAULT_DMA_NAME = "axi_dma_0"
DEFAULT_IP_NAME = "image_preprocess_0"


def _safe_channel_max_size(channel):
    return int(getattr(channel, "_max_size", 0) or 0)


class PLPreprocessor:
    """PYNQ overlay wrapper for PL-side skin-mask preprocessing.

    The current hardware interface is fixed at 360x360 RGB input and 360x360
    uint8 mask output. PS still performs connected-component selection and
    128x128 normalization so CPU and PL backends share the same model input.
    """

    def __init__(
        self,
        overlay_path=DEFAULT_OVERLAY,
        dma_name=DEFAULT_DMA_NAME,
        ip_name=DEFAULT_IP_NAME,
        frame_size=360,
        input_layout="packed_rgb",
        timeout_s=3.0,
        enable_morphology=1,
        thresholds=None,
    ):
        try:
            from pynq import Overlay, allocate
        except ImportError as exc:
            raise RuntimeError(
                "PL backend requires the PYNQ runtime on the board"
            ) from exc

        self.allocate = allocate
        self.overlay_path = str(overlay_path)
        self.frame_size = int(frame_size)
        self.input_layout = input_layout
        self.timeout_s = float(timeout_s)

        if self.input_layout not in ("packed_rgb", "rgbx32"):
            raise ValueError("input_layout must be 'packed_rgb' or 'rgbx32'")

        path = Path(self.overlay_path)
        if not path.exists():
            raise FileNotFoundError(f"overlay not found: {path}")

        self.overlay = Overlay(str(path))
        self.dma = getattr(self.overlay, dma_name)
        self.ip = getattr(self.overlay, ip_name)

        self._configure_ip(enable_morphology=enable_morphology,
                           thresholds=thresholds or {})
        self._check_dma_capacity()

    def diagnostics(self):
        """Return board-side details that help diagnose overlay/DMA issues."""
        return {
            "overlay_path": self.overlay_path,
            "frame_size": self.frame_size,
            "input_layout": self.input_layout,
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "dma_send_max_size": _safe_channel_max_size(self.dma.sendchannel),
            "dma_recv_max_size": _safe_channel_max_size(self.dma.recvchannel),
            "ip_names": sorted(list(getattr(self.overlay, "ip_dict", {}).keys())),
        }

    def _check_dma_capacity(self):
        send_max = _safe_channel_max_size(self.dma.sendchannel)
        recv_max = _safe_channel_max_size(self.dma.recvchannel)
        if send_max and send_max < self.input_bytes:
            raise RuntimeError(
                "DMA send max size is too small: "
                f"{send_max} < {self.input_bytes}. "
                "Rebuild/export the overlay after setting "
                "axi_dma_0 CONFIG.c_sg_length_width to 26."
            )
        if recv_max and recv_max < self.output_bytes:
            raise RuntimeError(
                "DMA recv max size is too small: "
                f"{recv_max} < {self.output_bytes}. "
                "Rebuild/export the overlay after setting "
                "axi_dma_0 CONFIG.c_sg_length_width to 26."
            )

    @property
    def input_bytes(self):
        pixels = self.frame_size * self.frame_size
        if self.input_layout == "packed_rgb":
            return pixels * 3
        return pixels * 4

    @property
    def output_bytes(self):
        return self.frame_size * self.frame_size

    def _write_reg(self, offset, value):
        self.ip.write(int(offset), int(value))

    def _configure_ip(self, enable_morphology=1, thresholds=None):
        thresholds = thresholds or {}
        defaults = {
            "y_min": 45,
            "y_max": 225,
            "cr_min": 135,
            "cr_max": 190,
            "cb_min": 80,
            "cb_max": 145,
        }
        defaults.update(thresholds)
        self._write_reg(0x10, defaults["y_min"])
        self._write_reg(0x18, defaults["y_max"])
        self._write_reg(0x20, defaults["cr_min"])
        self._write_reg(0x28, defaults["cr_max"])
        self._write_reg(0x30, defaults["cb_min"])
        self._write_reg(0x38, defaults["cb_max"])
        self._write_reg(0x40, int(bool(enable_morphology)))

    def _pack_frame(self, frame_bgr):
        frame = np.asarray(frame_bgr)
        if frame.ndim != 3 or frame.shape[2] < 3:
            raise ValueError(f"expected BGR frame, got shape={frame.shape}")

        # Keep the camera aspect ratio.  Stretching a 320x240 frame directly
        # to 360x360 changes the hand silhouette seen by the classifier.
        source = np.ascontiguousarray(frame[:, :, :3])
        src_h, src_w = source.shape[:2]
        scale = min(self.frame_size / float(src_w), self.frame_size / float(src_h))
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        resized_small = cv2.resize(
            source, (new_w, new_h), interpolation=cv2.INTER_AREA
        )
        resized = np.zeros(
            (self.frame_size, self.frame_size, 3), dtype=np.uint8
        )
        offset_x = (self.frame_size - new_w) // 2
        offset_y = (self.frame_size - new_h) // 2
        resized[offset_y:offset_y + new_h, offset_x:offset_x + new_w] = resized_small
        # 当前 Overlay 的 AXIS 宽度转换器实际按 BGR 字节顺序传入 HLS。
        # 不再交换 BGR 通道。
        rgb = resized

        if self.input_layout == "packed_rgb":
            return np.ascontiguousarray(rgb.reshape(-1).astype(np.uint8))

        packed = np.zeros((self.frame_size * self.frame_size, 4), dtype=np.uint8)
        packed[:, 0:3] = rgb.reshape(-1, 3)
        return np.ascontiguousarray(packed.reshape(-1))

    def _wait_channel(self, channel, name):
        start = time.time()
        while not channel.idle:
            if time.time() - start > self.timeout_s:
                raise TimeoutError(f"{name} timed out after {self.timeout_s}s")
            time.sleep(0.001)

    def run_mask(self, frame_bgr):
        in_bytes = self._pack_frame(frame_bgr)
        if len(in_bytes) != self.input_bytes:
            raise RuntimeError(
                f"packed input length mismatch: {len(in_bytes)} != {self.input_bytes}"
            )

        in_buf = self.allocate(shape=(self.input_bytes,), dtype=np.uint8)
        out_buf = self.allocate(shape=(self.output_bytes,), dtype=np.uint8)
        try:
            in_buf[:] = in_bytes
            out_buf[:] = 0
            in_buf.flush()
            out_buf.flush()

            self.dma.recvchannel.transfer(out_buf)
            self._write_reg(0x00, 0x01)
            self.dma.sendchannel.transfer(in_buf)

            self._wait_channel(self.dma.sendchannel, "DMA send")
            self._wait_channel(self.dma.recvchannel, "DMA recv")
            out_buf.invalidate()

            mask = np.array(out_buf, dtype=np.uint8).reshape(
                self.frame_size, self.frame_size
            )
            return mask
        finally:
            in_buf.freebuffer()
            out_buf.freebuffer()

    def preprocess_frame(self, frame_bgr, size=IMG_SIZE):
        mask = self.run_mask(frame_bgr)
        binary, info = preprocess_mask(mask, size=size)
        info["backend"] = "pl"
        info["pl_frame_size"] = self.frame_size
        info["pl_input_layout"] = self.input_layout
        return binary, info
