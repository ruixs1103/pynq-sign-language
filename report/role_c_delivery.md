# 角色 C 最终交付报告

日期：2026-10-09。项目根目录：`D:\01_Projects\FPGA创新赛\比赛项目——基于PYNQ的手势识别系统\code\sign-language-pynq`。

**角色 C 可独立验证的工作已完成并实际落地。当前计划的105项测试全部通过，其中C新增84项、B既有21项；完整加入旧版根目录测试后为124项通过、2项既有乱码断言失败。真实板卡、图像DMA与FPGA性能验收尚未完成。**

本轮遵循 `report/execution_plan.md` 的更新分工，C负责音频与板端。用户已确认A尚未交付图像HLS/Overlay，先完成可独立验证部分。旧Word把C分配为算法负责人，但更新计划明确取代旧分工，且与现有源码一致。

## 一 角色 C 工作总结

完成标签与中文WAV映射、九个中文PCM语音文件、Windows/Linux播放入口、unknown静默、置信度过滤、冷却、防重复、有界队列及后台错误事件。B的 `realtime_sign_pc.py --audio` 无需修改即可导入C提供的函数。

完成真实bit/hwh读取、实际IP/地址/寄存器/时钟/复位提取、PYNQ加载状态与ip_dict校验、重载后重建驱动，以及GPIO LED读写与finally恢复工具。

完成基于实际DMA描述的通用PS字节事务：物理连续缓冲、长度/地址/对齐检查、输入与接收缓存同步、先接收后发送、有限状态轮询、错误/超时软复位、提前TLAST字节数检查、故障实例禁用、未确认复位时保留物理缓冲。未虚构A的像素接口或HLS寄存器。

完成100/1000帧及持续时长黄金向量测试工具、JSON日志、一条命令离线复现工具、PC CPU参考计时、源文件哈希审计和学习说明。新代码均为PS侧Python/PowerShell，不属于新RTL/HLS实现。

开发前快照中271个原有代码、配置、文档及工程产物的SHA-256全部保持不变；没有改动A/B源码、标签、模型接口、Vivado工程、约束或既有测试预期。证据见 `role_c_logs/final/summary.json` 的 `original_files_unchanged`。

## 二 代码变更清单

以下路径均相对本报告顶部的项目根目录，全部为新增。软件替身测试和真实硬件工具分开交付。

| 文件路径 | 新增/修改 | 功能 | 测试状态 |
|---|---|---|---|
| `audio/__init__.py` | 新增 | 音频包 | 导入通过 |
| `audio/speech_map.py` | 新增 | 从labels派生映射、WAV和结果校验 | 自动测试通过 |
| `audio/prepare_audio.py` | 新增 | 原子生成/导入真实语音、manifest | 实际生成九文件；导入/失败保护测试通过 |
| `audio/synthesize_windows.ps1` | 新增 | 已安装中文引擎生成16kHz PCM | 实际生成通过 |
| `audio/play_audio.py` | 新增 | 兼容入口、播放后端、非阻塞播报器 | 自动测试通过；扬声器未实测 |
| `audio/test_audio.py` | 新增 | 全词汇检查/可选真实播放 | 九文件实际检查通过 |
| `audio/wav/*.wav`、`manifest.json` | 新增 | 九个中文音频及来源/格式/哈希 | 文件完整性通过；未人工听辨 |
| `board/__init__.py` | 新增 | 板端工具包 | 导入通过 |
| `board/load_overlay.py` | 新增 | 元数据发现、实际PYNQ加载和重载 | 真实HWH静态检查及软件替身测试通过 |
| `board/overlay_register_test.py` | 新增 | GPIO方向、模式读写和恢复 | 真实寄存器表检查及软件模型通过 |
| `board/audio_board_test.py` | 新增 | 手工/预测JSONL音频联调 | 映射检查和软件测试通过 |
| `board/dma_transfer.py` | 新增 | 缓冲、Cache、事务、超时和复位 | 软件模型测试通过 |
| `board/dma_board_test.py` | 新增 | 黄金向量、连续帧/持续时长统计 | 1000模型事务通过；真实DMA未执行 |
| `board/run_log.py` | 新增 | 记录环境和执行模式的JSON日志 | 实际日志输出通过 |
| `board/role_c_benchmark.py` | 新增 | PC CPU预处理/HOG计时 | 真实图像100帧执行及自动测试通过 |
| `board/verify_role_c.py` | 新增 | 一键复现、实际退出码及原文件审计 | 实际运行通过 |
| `tests/test_role_c_audio.py` | 新增 | 音频正常/边界/错误/队列/关闭 | 34项通过 |
| `tests/test_role_c_overlay.py` | 新增 | 两个真实HWH、加载拒绝、恢复 | 9项通过 |
| `tests/test_role_c_dma.py` | 新增 | Cache/超时/错误/复位/连续模型 | 39项通过 |
| `tests/test_role_c_benchmark.py` | 新增 | CPU计时标识和无效图像 | 2项通过 |
| `requirements_role_c.txt` | 新增 | 本轮PC环境锁定，包括原清单遗漏的依赖 | pip check通过 |
| `audio/README.md`、`board/README_role_c.md` | 新增 | 音频和板端集成/复现 | 文档与已运行命令对照 |
| `report/role_c_analysis.md`、`role_c_source_inventory.md` | 新增 | 分工、架构、接口、完整源码阅读清单 | 与实际源码/HWH/BD核对 |
| `report/role_c_fix_log.md`、`role_c_learning.md`、`role_c_ai_collaboration.md` | 新增 | 修复记录、助教说明和AI记录 | 基于实际过程整理 |
| `report/role_c_logs/` | 新增 | 原快照、实际测试输出、JUnit、性能及摘要 | 可追溯实际结果 |

## 三 模块接口说明

| 入口/接口 | 数据及协议 | 连接关系 |
|---|---|---|
| `play_wav_for_label(label)` | B定义的标签字符串；同步播放；unknown静默 | B现有PC程序→C音频 |
| `AudioAnnouncer.submit(result)` | B已有五字段dict或None；返回过滤/排队状态 | A板端主循环/B预测器→C后台播放器 |
| `AudioAnnouncer.poll_events()` | played/failed事件列表 | C播放状态→A板端日志 |
| `inspect_overlay(bitstream)` | 同名bit/hwh；返回实际元数据及文件哈希 | A工程产物→C检查 |
| `OverlaySession.get_ip(name)` | HWH/ip_dict中的真实名称 | C→实际PYNQ驱动 |
| 现有GPIO | `axi_gpio_0`；AXI32位；GPIO4位；地址0x41200000 | PS GP0→SmartConnect→LED |
| GPIO寄存器 | DATA偏移0x0、TRI偏移0x4；从HWH读取 | C寄存器工具→A已有LED工程 |
| PL时钟/复位 | FCLK_CLK0 100MHz；peripheral_aresetn低有效 | PS/proc_sys_reset→GPIO/互连 |
| `DmaTransfer.transfer(input_array, ...)` | shape/dtype严格匹配调用方约定；返回独立数组 | A待交付DMA→C事务→A/B适配 |
| DMA黄金向量 | C工具的NPZ文件含inputs/expected；首轴为样本编号 | A/B独立参考→C连续比对 |

完整框图、状态机、资源约束及每项设计依据见 `role_c_analysis.md`。新软件API与测试文件格式由C定义；实际图像硬件名称、位宽、地址、像素打包和TLAST仍待A交付，未用软件API名称冒充硬件协议。

PYNQ的wait无timeout参数，因此C先做有限状态轮询，确认双通道idle后才调用原驱动收尾；标准DMA复位规则按官方文档核查。[PYNQ官方驱动](https://pynq.readthedocs.io/en/v2.7.0/_modules/pynq/lib/dma.html)、[AMD PG021复位寄存器](https://docs.amd.com/r/en-US/pg021_axi_dma/MM2S_DMACR-MM2S-DMA-Control-Register-Offset-00h)。

## 四 实际测试结果

下表中的`python`指本轮 `.venv_role_c\Scripts\python.exe`。命令均在项目根目录执行；一键工具的摘要保存了每一条实际完整命令。

| 测试项目 | 执行命令 | 实际结果 | 是否通过/类型 |
|---|---|---|---|
| 当前计划完整离线交付检查 | `python -m board.verify_role_c --log-dir report/role_c_logs/final` | 全部检查退出码0；105项测试通过 | 已实际运行并通过 |
| 模块与B接口回归 | `python -m pytest tests --import-mode=importlib -q` | C84项、B21项通过，无跳过 | 已实际运行并通过 |
| 旧版根目录也纳入回归 | `python -m board.verify_role_c --include-legacy --log-dir report/role_c_logs/legacy_full` | 124通过、2失败，工具退出码1 | 已实际运行但失败；既有乱码问题 |
| 1000次连续DMA模型事务 | `python -m pytest tests/test_role_c_dma.py::test_1000_continuous_transactions --import-mode=importlib -q`（包含于上述测试） | 按交替输入计算输出并逐次比对，1000次通过 | 软件模型；不算真实DMA |
| Cache/缺TLAST/错误/复位 | `python -m pytest tests/test_role_c_dma.py --import-mode=importlib -q`（包含于上述测试） | 39项通过，独立CPU/设备缓存模型 | 软件模型 |
| 中文WAV生成 | `python -m audio.prepare_audio --engine windows` | 九个单声道16kHz/16-bit PCM文件 | 已实际运行并通过 |
| WAV完整性和映射 | `python -m audio.test_audio` | 九文件长度/格式非空通过；自动测试另核SHA-256 | 已实际运行并通过 |
| Overlay/GPIO接口 | `python -m board.overlay_register_test --inspect` | 真实HWH地址、4位GPIO、0x0/0x4偏移通过 | 仅静态元数据检查 |
| 当前DMA能力 | `python -m board.dma_board_test --bit board/overlays/led_test_2026_1/led_test_2026_1.bit --inspect` | dma_available=false，dma_executed=false | 静态检查通过；DMA功能不存在 |
| 音频触发结构 | `python -m board.audio_board_test --label hello --validate-only` | 合法结果映射到真实hello.wav，无播放 | 已实际运行；仅映射检查 |
| B原程序音频兼容 | `python realtime_sign_pc.py --input dataset/raw_initial_20260919/palm/palm_001.jpg --mode static --audio` | 缺正式模型，B假预测器返回unknown；音频模块导入正常且静默 | 软件集成通过；不是识别准确率 |
| Python编译与依赖 | `python -m compileall -q audio board tests`、`python -m pip check` | 编译成功；No broken requirements found | 已实际运行；语法/依赖检查 |
| 原文件保护 | 一键工具对开发前快照逐个SHA-256比对 | 271个检查文件无变化 | 已实际运行并通过 |
| PC CPU参考计时 | `python -m board.role_c_benchmark --input dataset/raw_initial_20260919/palm/palm_001.jpg dataset/raw_initial_20260919/fist/fist.jpg dataset/raw_initial_20260919/unknown/unknown_20260920_135311_931304.jpg --frames 100 --log report/role_c_logs/cpu_reference_final.json` | 见下文；真实图像100帧 | 已实际运行；仅PC参考 |
| PYNQ加载、GPIO真实读写、100/1000帧真实DMA | 板端命令已提供，当前未执行 | 缺PYNQ板卡环境，且A未交付DMA Overlay | 因环境/接口限制未运行 |
| 音箱实际播报、人工听辨 | `python -m audio.test_audio --play`（待执行） | 本轮未调用扬声器 | 因设备验收条件未运行 |
| Vivado/HLS/RTL仿真、综合、实现、STA | 未执行 | 未找到可调用的Vivado/Vitis/xsim/iverilog/verilator；C本轮没有新RTL | 因工具及A源码限制未运行 |
| 板卡30分钟、端到端延迟、FPGA FPS与资源 | 支持对应工具，但等待实际系统 | 没有实测结果 | 未运行，不能声称满足指标 |

CPU参考最后一次实际记录：预处理平均16.254ms，95分位29.353ms，计算吞吐61.523FPS；预处理加HOG平均17.342ms，57.664FPS。样本原始尺寸是1280×960、1280×960和420×320，统计100次、读取与预热不计入。它是当前Intel Windows PC的计算时间，**不含摄像头、分类、音频、ARM或FPGA**，不能作为320×240板端验收或CPU/FPGA加速比。

历史LED实现报告可读到LUT412、FF460、BRAM0、DSP0、WNS3.325ns；同一报告还有TIMING-18及4个输入/4个输出缺delay。它们是原文件中2026-09-20的LED结果，本轮只读取，没有重跑；不能代表本轮图像工程的综合或时序。现有xpr/BD包含2025.2和2026.1两套工程，工具版本需由A锁定。

本轮PC环境为Windows 11、Python3.12.14、NumPy2.4.6、OpenCV4.14.0.94、pytest9.1.1；完整包版本见 `requirements_role_c.txt`。原导入 `.venv` 指向另一用户的Python3.11路径，未覆盖。

## 五 未解决问题及限制

1. **A未交付实际图像接口。** 当前不能接入真实图像DMA，不能执行相关RTL/HLS仿真、PL预处理黄金比对或板卡稳定性验收。下一步按 `board/README_role_c.md` 的接口清单交付A产物。
2. **旧版根目录B测试的两个预期文字乱码。** 第77行期待`涓€`而实际是`一`；第88行期待`浣犲ソ`而实际是`你好`。它们与labels及更新版tests不一致。本轮不修改B的文件或预期；完整回归如实失败，交由B确认修复编码。
3. **正式静态/动态模型不存在。** PC兼容测试使用B明确标识的unknown假预测器。没有准确率结论。
4. **PL输出进入B分类器的接口还缺。** 现有predictor接收BGR并内部CPU预处理；不能把DMA二值掩膜直接传给predict。A/B必须确认预处理结果复用方式。
5. **板卡与扬声器未验收。** 未运行真实GPIO读写、DMA、音频播放、30分钟、ARM性能或端到端延迟。WAV按中文文本生成，但未进行人工听辨。
6. **通用DMA适用范围。** 仅普通Simple DMA双通道；SG/Micro拒绝。PYNQ原生驱动初始化可能阻塞，C并未改变第三方实现；事务/软复位有期限，适配回调必须自行返回。DMA故障后必须复位/重载整条数据通路并重建驱动，不能只清理Python字典。
7. **环境锁定边界。** PC依赖锁不可直接覆盖PYNQ镜像；板卡需确认自身Python/PYNQ/NumPy及音频设备。C代码使用Python≥3.8的标准库功能，但ARM及其版本组合未实际测试。Windows winsound同步调用不能被安全强制取消，后台关闭超时已明确抛错。

## 六 集成与交付说明

把C新增文件保持目录结构放入现有工程即可。交付包只包含C代码、WAV、测试、报告、依赖锁和证据，不包含虚拟环境、pip缓存或A/B的旧文件；它是合入现有工程的增量包，不是独立FPGA工程。

B现有的同步音频钩子已经兼容。A板端实时主循环建议用 `AudioAnnouncer(config=rt.config)`，对真实结果调用 `submit()`，并持续记录 `poll_events()`；unknown和低置信度不会播报。有界队列避免推理线程被语音时长拖慢。

现有LED链路可先在板卡运行加载、寄存器模式和重载工具；它不是图像加速Overlay。DMA待A交付后，使用实际HWH的IP名称和参数、独立黄金向量及真实启动/复位适配。故障后先确认停止访问物理缓冲再释放，随后重建整条数据通路。

建议顺序：板卡版本/ALSA确认 → LED加载/寄存器 → 九词音频实际播放 → A的单帧DMA黄金对比 → 100帧 → 1000帧 → 30分钟 → 真实模型与音频 → 分别测量计算延迟、播报开始与播放结束 → A提供综合/时序资源数据。每一步保留实际模式日志。

一键离线复现：

```powershell
Set-Location 'D:\01_Projects\FPGA创新赛\比赛项目——基于PYNQ的手势识别系统\code\sign-language-pynq'
& .venv_role_c\Scripts\python.exe -m board.verify_role_c
```

更多实机命令和接入条件在 `board/README_role_c.md`，音频使用在 `audio/README.md`。

## 七 学习说明

详见 `role_c_learning.md`，包含核心原理、必须读懂的五个文件、状态机/时序、答辩问题和逐项复现步骤。优先理解“labels是唯一标签源”“物理连续缓冲与Cache同步”“接收先启动”“超时必须确认复位后释放”“推理与音频播放不能共用阻塞循环”五件事。

修复过程逐项见 `role_c_fix_log.md`；既有失败日志完整保留，不删除失败用例、不弱化断言、不伪造板卡或FPGA数据。
