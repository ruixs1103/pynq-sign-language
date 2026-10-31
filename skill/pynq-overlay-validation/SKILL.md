---
name: pynq-overlay-validation
description: Validate and benchmark a PYNQ AXI-Stream Overlay with bit/hwh pairing, AXI-Lite registers, DMA transfers, CPU/PL output comparison, and reproducible evidence. Use for PYNQ image/data-stream projects; do not assume a specific algorithm or board beyond values discovered from the project.
---

# PYNQ Overlay Validation

Use this workflow when a project needs evidence that its Overlay and DMA path are correct, reproducible, and measurably useful.

## Workflow

1. Discover the target board, device, tool versions, bit/hwh pair, IP names, register map, stream width and expected frame size. Never invent these values.
2. Run `scripts/verify_overlay_pair.py` before loading hardware. Stop if stems differ, either file is missing, or HWH XML is invalid.
3. Load the Overlay and compare discovered IP names against the driver. Treat the HWH as the source of truth; do not silently guess alternate IP names or register offsets.
4. Validate one deterministic input before live capture. Start the receive channel before the send channel when the output can backpressure the pipeline.
5. Compare CPU and PL outputs on identical inputs. Report exact agreement, IoU, differing pixels and polarity corrections. Preserve raw outputs when a mismatch occurs.
6. Benchmark only after correctness. Warm up, use identical inputs and parameters, record mean/P50/P95/standard deviation, failure counts and whether display/JPEG time is included.
7. Run a bounded stability test and stop on repeated DMA timeout, invalid output size, or corrupted buffers. Never claim board validation from simulation alone.
8. Archive commands, tool versions, logs, raw metrics, bit/hwh hashes and final commit SHA.

## Non-obvious invariants

- A `.bit` and `.hwh` pair must come from the same build.
- DMA buffer byte counts must match stream word width and pixel count; TLAST conventions must match the IP.
- Cache/coherency behavior depends on the PYNQ buffer API and platform. Use documented flush/invalidate operations when buffers are cacheable.
- Separate capture, PL/DMA, classification, rendering and JPEG timing. A slow UI does not prove a slow PL kernel.
- HLS estimates are not post-route utilization or board performance.
- If a preprocessing change alters model input distribution, revalidate accuracy; speed alone is insufficient.

## Evidence output

Produce a machine-readable JSON record containing board/device, versions, hashes, register/IP discovery, correctness metrics, latency distribution, stability counts and unresolved limitations. Mark unknown measurements as null rather than estimates.

For detailed pass/fail criteria and troubleshooting, read `references/checklist.md`.
