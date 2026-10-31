# 角色 C 板端集成

所有命令均从 `sign-language-pynq` 工程根目录运行。C 的脚本不修改 Vivado 工程或预测器，不自行定义图像 IP 名、像素打包、HLS 控制寄存器或 TLAST 规则。

## PC 复现

本轮专用环境是 `.venv_role_c`，原 `.venv` 保留。下面的路径是当前工作区绝对路径：

```powershell
Set-Location 'D:\01_Projects\FPGA创新赛\比赛项目——基于PYNQ的手势识别系统\code\sign-language-pynq'
& .venv_role_c\Scripts\python.exe -m board.verify_role_c
```

环境重建：使用可工作的 Python 3.12 执行 `python -m venv .venv_role_c`，然后 `& .venv_role_c\Scripts\python.exe -m pip install -r requirements_role_c.txt`。此锁定文件是本轮 Windows/Python 3.12 测试环境，不应直接覆盖板卡镜像的 PYNQ/NumPy 环境。

`python -m board.verify_role_c --include-legacy` 同时运行旧版根目录测试，当前应返回退出码 1，并准确暴露两个既有中文乱码断言。当前唯一有效计划指定的 `tests/` 返回退出码 0。工具会继续完成其他检查，把每个命令、退出码、输出和摘要写到日志目录。

## 现有 LED Overlay

```bash
python -m board.load_overlay --inspect
python -m board.overlay_register_test --inspect
python -m board.load_overlay --log board/logs/overlay.json
python -m board.overlay_register_test --hold-s 0.2 --log board/logs/registers.json
python -m board.load_overlay --reload --log board/logs/overlay_reload.json
```

前两条只读取元数据，后面三条在 PYNQ 板卡执行。实际 IP 为 `axi_gpio_0`，地址 `0x41200000`，GPIO 宽度 4 位。寄存器偏移从同名 HWH 读取；测试依次写 0、1、2、4、8、15、0，并在 finally 中恢复读取到的数据和方向值。重载会重建 Overlay/IP 驱动，不能在未结束或未确认复位的 DMA 事务中重载。

工具核对同名 `.bit/.hwh` 是否存在和非空、PYNQ 的加载状态以及运行时 `ip_dict` 地址。文件哈希只是追踪文件版本，并不能证明任意两份 bit/hwh 的逻辑内容相匹配；最终需由 A 交付同一次构建导出的配对文件。

## DMA 接入条件

2026-10-09 用户已确认 A 尚未交付图像 HLS/Overlay。两个现有 Overlay 都没有 AXI DMA。`--inspect` 正确输出 `dma_available=false`、`dma_executed=false`，不能把它当作 DMA 验收通过。

A 后续需提供真实 bit/hwh 配对、DMA IP 路径、DMA 模式和通道配置、输入/输出 shape/dtype、逐像素字节序和打包规则、TKEEP/TLAST 位置、HLS register_map、时钟复位连接，以及对应输入的独立黄金输出。

`DmaTransfer` 的 shape/dtype 都是必填参数。它支持普通 AXI Simple DMA，要求 MM2S/S2MM 双通道；SG/Micro 模式明确拒绝。最大长度、地址位宽和无 DRE 对齐从实际 HWH 对应的 `ip_dict` 参数取得。它返回独立 NumPy 副本，不把借用的物理缓冲交给后续算法长期保存。

DMA 测试向量采用 **C 工具自己的文件格式**：NPZ 中 `inputs`、`expected` 两个数组，第一轴为样本编号，其余维度和 dtype 是 A 确认的真实线格式。`expected` 必须来自独立参考结果；图像预处理不是 loopback，不能默认以输入作为预期输出。

C 提供的软件扩展点为 `start_ip(session)`、`reset_ip(session)`；这些是适配模块的 Python 函数，不是已经存在的硬件端口。A 可在适配模块中按真实 register_map 实现。只有 A 确认 IP 是自由运行方式时，才用 `--free-running`。

交付后可按实际参数运行以下命令；占位符必须替换，当前不执行：

```bash
python -m board.dma_board_test --bit <A提供的bit路径> --dma <HWH中的真实DMA名称> --vectors <黄金向量npz> --adapter <A的Python适配模块> --frames 100
python -m board.dma_board_test --bit <A提供的bit路径> --dma <HWH中的真实DMA名称> --vectors <黄金向量npz> --adapter <A的Python适配模块> --frames 1000
python -m board.dma_board_test --bit <A提供的bit路径> --dma <HWH中的真实DMA名称> --vectors <黄金向量npz> --adapter <A的Python适配模块> --frames 1000 --duration-s 1800
```

连续测试的帧数和时长同时指定时，二者均达到才结束。默认黄金结果要求完全相等；若 HLS 有可解释的定点像素误差，应由 A/B 明确容差并另行实现参考比对，C 不主动弱化判定。

顺序为：复制输入 → 输入 flush → 清接收缓冲并 flush → 启动接收 → 启动真实 IP → 启动发送 → 有期限地轮询状态 → 检查实际字节数 → 接收 invalidate → 复制输出。

超时或错误触发标准 AXI DMA 软复位；确认 reset 位自清除且双通道 halted 后才能释放缓冲。故障实例不能继续传输，因为 DMA 软复位不保证 HLS 的内部状态同步复位。应关闭旧事务、按 A 的方案复位/重载整个数据通路、取得新驱动并重建 `DmaTransfer`。复位未确认时保留物理缓冲强引用，`close()` 明确报错；可 `retry_reset()` 后释放，仍不能恢复旧实例传输。

PYNQ 2.7 原生 DMA 构造/启动过程含无期限轮询。C 的事务轮询与软复位具有期限，但不能声称第三方驱动初始化也具有超时。适配回调必须自行保证返回，不能将阻塞硬件等待放在回调中。

## 音频与日志

```bash
python -m board.audio_board_test --label hello --validate-only
python -m board.audio_board_test --label hello --backend aplay --device <实际ALSA设备>
python -m board.audio_board_test --results <B输出的JSONL> --backend aplay --device <实际ALSA设备>
```

`--label` 是手工触发，不代表模型识别。JSONL 使用 B 已定义的五字段结果结构。`--validate-only` 不访问扬声器。后台失败应通过 `poll_events()` 进入主程序日志。

目前 B 的预测器接收 BGR 单帧/帧序列并在内部执行 CPU 预处理，没有公开的 PL 掩膜分类入口。A/B 需另行确认 PL 输出如何复用到特征/分类链路；直接将 DMA 掩膜传给现有 `predict()` 会不兼容。C 没有修改 B 的算法接口。

日志均记录执行模式，JSON 中区分 `offline_metadata`、`offline_audio_mapping`、`hardware_overlay`、`hardware_register`、`hardware_dma_golden`、`hardware_audio` 和 `pc_cpu_reference`。模型事务测试和 PC CPU FPS 不得写入板卡实测栏。
