# 提交要求对应表

| 评审要求 | 本项目提交内容 | 对应路径 |
|---|---|---|
| 完整工程文件与源码 | HLS、Vivado、PS 软件、板端脚本、bit/hwh、语音资源 | `hls/`、`vivado_proj/`、`board/` |
| 仿真或验证结果 | HLS 测试台、Overlay/DMA 检查、板端 Mask 与 JSON 记录 | `hls/`、`board/`、`report/board_last_test/` |
| 综合与实现说明 | HLS 综合资源估算、时钟目标、DATAFLOW 和 II=1 结构说明 | `submission/report/implementation_report.md` |
| 上板工程与运行脚本 | PYNQ 入口、Overlay 加载、摄像头检查、产品展示脚本 | `board/` |
| 实测输出与参考结果 | 640×480 采集记录、PL Mask、识别 JSON、最终功能验收 | `report/`、`submission/report/verification_report.md` |
| 可复现构建脚本 | HLS Tcl、Vivado 工程、Overlay 配对检查和复现步骤 | `hls/`、`vivado_proj/`、`skill/`、`submission/report/reproduction_guide.md` |
| Skill 包 | Overlay 验证 Skill 及其说明、检查脚本 | `skill/pynq-overlay-validation/` |
| 设计报告 | 设计背景、架构、软硬件划分、优化过程、协作记录和复现说明 | `submission/report/` |

本表只列出仓库中实际存在且可核查的材料。动态手势实验不属于本次正式静态手势演示范围。
