# 离线多角色情景模拟

保留文本摘要、实体/因素抽取、关系图、角色生成、多轮随机情景、分歧指标、情景报告和存储组件。

## 使用

Python 3.11+。在本目录建立独立虚拟环境：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python cli.py example.json
.venv/bin/python -m unittest discover -v
```

`example.json`从零编写，仅含虚构输入。可以显式提供自己的同结构JSON文件。输出默认为终端；`--output result.json`使用独占创建，避免覆盖已有结果。CLI失败退出码2。

## 数据与边界

不发现本机账号、不读取环境中的模型密钥、不发送消息、不请求远端数据。只处理调用方明确传入的文件、记录或参数。合成示例不代表任何实际业务结果。所有得分是启发式模拟结果，不能当已校准概率；模型聊天、联网资料和原界面未保留。

## 发布状态

本项目源码采用 MIT 许可证，见 LICENSE。依赖按各自上游许可使用，安装的依赖/模型/字体/媒体不随此源码目录分发。

## 可选本地PDF辅助函数

默认CLI只接收JSON内的文本，不需要PDF库。直接调用 `simulation.text_processing.extract_text_from_file` 处理本地PDF时，先安装 `pip install -r requirements-pdf.txt`；仅提取文字层，不做OCR。该可选函数用合成PDF验证，未连接原项目材料。

## 2026-11-08 候选修订

- 报告身份限制安全单一路径组件，拒绝目录跳转。
- 角色数上限统一为实际模板数。
- 每个角色固定平台，不随全局事件序号切换。
- 配置总时长使用已限制轮数。
- 查找遍历全部项目，不截断最新200；数据库连接显式关闭。

使用包内合成样例复跑；发布集合根目录的 `verify_release.py --project personal-scenario-simulator` 会依次执行测试和首次使用命令。原有版本的测试计数属于当时记录，本轮汇总以集合验证报告为准。
