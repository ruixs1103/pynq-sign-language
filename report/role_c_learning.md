# 角色 C 学习与答辩说明

你的模块相当于系统的“输出和设备交互管理”。B决定手势是什么，C把这个决定转换成中文声音；A做FPGA硬件，C负责从Python正确加载、访问和测试它。这里的PS是运行Python的ARM处理器，PL是FPGA逻辑。

## 一 核心工作原理

预测器返回的label如`hello`，不是中文音频本身。`labels.py`给出对应文字`你好`；C根据同一label找到`hello.wav`。结果是unknown、置信度不足、处于冷却或重复窗口时，不排入播放队列。后台只有一个播放器，不会同时叠加多句话；队列满时立即告知主程序。

Overlay由bit与hwh组成。bit配置FPGA电路，hwh描述IP名称、地址、寄存器和连接。C读取这份描述再访问寄存器，所以不需要猜地址。现有工程只有4个LED的GPIO，图像DMA还没有出现。

DMA让PL访问PS内存。普通NumPy数组的虚拟地址不能直接交给硬件，需要`pynq.allocate`分配物理连续缓冲。CPU有Cache：CPU刚写的数据可能还在缓存，PL看不到，所以发送前flush；PL写了结果之后，CPU可能还拿到旧缓存，所以接收完成后invalidate。它们不是“清零”，而是保证两边看到同一份最新内容。

先启动接收，相当于先准备好接水的桶，再打开水龙头。否则图像IP输出满了，输入也可能停住；软件若先等待发送完成，就可能互相等待。TLAST是流中“这包结束”的标记，缺失会让接收一直等；提前出现可能得到不完整帧。因此C同时检查状态和实际字节数。

超时后不能直接把缓冲释放。DMA若还在写，这块物理内存可能已经分给其他程序，造成破坏。C先软复位并检查复位结束及双通道停止；失败则保留缓冲。即使DMA复位成功，上游HLS也可能残留半帧状态，所以要重建整个数据通路。

## 二 最关键的五个文件

| 文件 | 重点读什么 | 为什么必须读懂 |
|---|---|---|
| `audio/speech_map.py` | SPEECH_MAP、wav_path_for_label、validate_result | 类别唯一来源、unknown静默、五字段结果检查 |
| `audio/play_audio.py` | AudioAnnouncer.submit/_run/close | 过滤次序、有界队列、后台错误、推理不被播放阻塞 |
| `board/load_overlay.py` | inspect_overlay、OverlaySession | bit/hwh、地址、加载校验及驱动重建 |
| `board/dma_transfer.py` | transfer/_wait_complete/_reset_hardware/close | 缓存时序、超时复位、物理内存生命周期 |
| `tests/test_role_c_dma.py` | FakeBuffer、FakeMMIO、超时/1000次事务测试 | 如何用独立参考和故障注入验证软件逻辑 |

另外必须对照阅读B的`labels.py`、`predictor.py`已有结果接口，以及`models/config.json`。你不需要为角色C重写SVM/HOG，但要能解释C接收什么、什么时候播放、如何保护硬件资源。

## 三 最重要的状态和时序

```text
音频结果 -> 校验 -> 过滤 -> queued -> 后台played/failed
                  |
                  +-> unknown/low_confidence/cooldown/repeat/queue_full

DMA READY -> ACTIVE -> READY
                 |
                 +-> FAULTED -> 复位确认 -> CLOSED
                            -> 复位失败 -> 保留缓冲，等待处理
```

音频使用monotonic计时：系统校时不会使冷却窗口突然变长或变短。结果中的timestamp仍保持B的墙上时间字段，它用于记录，不用于C自己的超时。

DMA关键顺序是输入复制和flush、接收缓冲flush、启动接收、启动IP、启动发送、有限轮询、确认字节数、invalidate、复制结果。查完idle再调用PYNQ wait，不把没有timeout参数的wait直接当成有期限等待。

“仿真/软件模型通过”和“FPGA成功”是不同的。FakeBuffer故意保留CPU与设备两份数组，不flush/invalidate就会拿到旧数据。FakeMMIO能延迟完成或永不完成；它验证C控制逻辑，并没有模拟每一个AXI时钟拍，更没有证明HLS综合和真实TLAST。

## 四 可能的答辩问题

| 问题 | 你应该能回答的要点 |
|---|---|
| 为什么C主要是Python，没有写Verilog？ | 更新分工把HLS/RTL交给A，算法交给B，C负责PS音频和板端交互；不能越过团队接口 |
| 类别为何不在音频目录重新定义？ | 避免B输出hello而C按sign_01命名；从labels派生即可同步 |
| 为什么unknown没有WAV？ | 识别不确定时不误播报，这是结果处理策略 |
| 如何证明没有用固定答案伪造DMA测试？ | 模型按每次发送的数据计算输出，交替输入1000次，黄金比对另行计算；真实硬件仍待验收 |
| 为什么普通NumPy不够？ | 虚拟地址不能代表PL可访问的物理连续内存 |
| flush和invalidate有什么区别？ | CPU写入送到设备可见内存；设备写入后让CPU丢弃旧缓存 |
| 为什么接收先启动？ | 接住PL输出，避免输出反压使上游发送无法完成 |
| 超时有哪些原因？ | 缺TLAST、未启动IP、输出尺寸或字节数错误、复位/时钟/AXI连接问题；看真实状态日志定位 |
| 复位成功后为何还禁止复用实例？ | DMA驱动和上游HLS的状态未必同步，需重建整个通路 |
| 为什么不能把音频放在取帧循环同步播放？ | 词语约1秒多，阻塞播放会拖慢取帧；后台有界队列保持控制响应 |
| 105项通过是否证明15FPS、85%准确率？ | 不能，单元测试检查功能；板卡吞吐和独立数据集准确率需分别测量 |
| 当前的61.523FPS代表什么？ | Intel PC的现有尺寸图像预处理计算吞吐，不含采集/分类；不是ARM或FPGA性能 |
| 还有哪两项测试失败？ | 旧版根目录中文字面量乱码；已保留真实失败，不改输出迎合错误预期 |

## 五 亲自复现

先打开PowerShell到项目根目录，再用已建立的专用环境：

```powershell
Set-Location 'D:\01_Projects\FPGA创新赛\比赛项目——基于PYNQ的手势识别系统\code\sign-language-pynq'
& .venv_role_c\Scripts\python.exe -m board.verify_role_c
```

期望当前测试105 passed、其他离线检查PASS；日志在 `report/role_c_logs/reproduce/`。环境需重建时参考 `board/README_role_c.md`，不要使用导入后失效的原venv。

只看你负责的DMA与音频测试：

```powershell
& .venv_role_c\Scripts\python.exe -m pytest tests/test_role_c_dma.py tests/test_role_c_audio.py --import-mode=importlib -q
& .venv_role_c\Scripts\python.exe -m pytest tests/test_role_c_dma.py::test_1000_continuous_transactions --import-mode=importlib -q
& .venv_role_c\Scripts\python.exe -m audio.test_audio
& .venv_role_c\Scripts\python.exe -m board.overlay_register_test --inspect
```

第一条对应39+34=73项，第二条是1000次**软件模型事务**，第三条只检查音频文件，第四条只读真实HWH。需要听声音时亲自执行 `python -m audio.test_audio --play` 并逐词听辨；PYNQ上先 `aplay -l` 选实际设备。

看完整旧版回归问题：

```powershell
& .venv_role_c\Scripts\python.exe -m board.verify_role_c --include-legacy
```

期望124通过、2失败、退出码1；这两项失败应交给B修复编码，而不是删除用例。实际板卡顺序及DMA接口待交付清单见 `board/README_role_c.md`。
