# Validation checklist

## Static contract

- [ ] Board and FPGA part are recorded.
- [ ] Tool and PYNQ versions are recorded.
- [ ] bit/hwh stems and hashes are recorded.
- [ ] HWH parses and expected IP blocks exist.
- [ ] Driver register offsets match generated headers/HWH.
- [ ] Stream width, pixel packing, byte count and TLAST contract are documented.

## Correctness

- [ ] A deterministic synthetic vector passes.
- [ ] At least one recorded real input passes.
- [ ] CPU and PL use identical parameters.
- [ ] Exact agreement, IoU and differing pixel count are reported.
- [ ] Raw input, CPU output and PL output are archived for failures.

## Performance

- [ ] Warm-up frames are excluded.
- [ ] Capture, DMA/kernel, postprocess and display are timed separately.
- [ ] Mean, P50, P95, standard deviation and failures are reported.
- [ ] CPU and PL tests use identical resolution and samples.
- [ ] Post-route resources, WNS/TNS and power are distinguished from HLS estimates.

## Stability and stopping conditions

- [ ] A bounded long run is completed.
- [ ] DMA timeout count and invalid output count are recorded.
- [ ] Test stops after three repeated identical hardware failures for diagnosis.
- [ ] No reset/reprogram loop hides a persistent error.

## Common diagnosis

| Symptom | Check first |
|---|---|
| DMA send hangs | Receive started first, output backpressure, TLAST, byte count |
| Output shifted/corrupted | Pixel packing, stride, word width, buffer shape |
| Mask inverted | Raw foreground and border ratios, output convention |
| CPU/PL mismatch at edges | Border padding and morphology kernel definition |
| Live UI slow but kernel fast | Rendering, resize, JPEG and browser transfer timings |
| Accuracy drops after PL | Thresholds, color order, white balance and model input distribution |
