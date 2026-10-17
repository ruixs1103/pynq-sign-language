"""Single-frame PYNQ DMA smoke test for the 360x360 RGB mask pipeline."""

import time

import numpy as np
from pynq import Overlay, allocate


BIT = "board/overlays/sign_preprocess_2026_1/sign_preprocess_2026_1.bit"
WIDTH = 360
HEIGHT = 360
PIXELS = WIDTH * HEIGHT


def main():
    overlay = Overlay(BIT)
    dma = overlay.axi_dma_0
    ip = overlay.image_preprocess_0

    # DMA memory-side format: 24-bit RGB input and 8-bit mask output.
    input_buf = allocate(shape=(PIXELS * 3,), dtype=np.uint8)
    output_buf = allocate(shape=(PIXELS,), dtype=np.uint8)

    try:
        rgb = np.zeros((PIXELS, 3), dtype=np.uint8)
        rgb[:, 0:3] = [180, 120, 100]

        input_buf[:] = rgb.reshape(-1)
        output_buf[:] = 0

        ip.write(0x10, 45)
        ip.write(0x18, 225)
        ip.write(0x20, 135)
        ip.write(0x28, 190)
        ip.write(0x30, 80)
        ip.write(0x38, 145)
        ip.write(0x40, 1)

        input_buf.flush()
        output_buf.flush()

        # Arm receive first, then start the HLS IP and transmit input.
        dma.recvchannel.transfer(output_buf)
        ip.write(0x00, 1)
        dma.sendchannel.transfer(input_buf)

        begin = time.time()
        while not dma.sendchannel.idle or not dma.recvchannel.idle:
            if time.time() - begin > 5:
                print("MM2S:", dma.sendchannel.register_map)
                print("S2MM:", dma.recvchannel.register_map)
                print("IP CTRL:", hex(ip.read(0x00)))
                raise TimeoutError("DMA transfer timeout")
            time.sleep(0.001)

        output_buf.invalidate()
        mask = np.asarray(output_buf)
        print("DMA transfer OK")
        print("nonzero pixels:", int(np.count_nonzero(mask)))
        print("unique output bytes:", np.unique(mask)[:16])
        print("IP CTRL:", hex(ip.read(0x00)))
    finally:
        input_buf.freebuffer()
        output_buf.freebuffer()


if __name__ == "__main__":
    main()
