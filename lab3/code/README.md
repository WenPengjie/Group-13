# Lab3：断，都可以断

## 当前安全复验版说明

本目录基于lab3_2511057(2).zip。内核、库、Makefile及官方tools全部保持输入版本原样；本次仅改进自编验证脚本、证据记录和性能审计工具，没有新的内核运行提速结论。
先阅读 [本次审查](docs/OPTIMIZATION.md) 与 [WSL步骤](docs/WSL_VERIFY.md)。下文旧运行成绩和同级report原有记录属于输入版本，不是新版脚本已在QEMU重跑的证明。

新版脚本继承调用者PATH，支持TOOLCHAIN_BIN、QEMU_BIN目录配置；每次使用新的validation目录，在临时副本构建，不覆盖原报告或当前bin/obj。原有三个入口名称保留：

```bash
bash tests/run_required.sh
python3 tests/extended_qemu.py
python3 tests/audit_performance.py --baseline /实际路径/基线code
```

宿主与保护检查：python3 tests/test_validation_tools.py、python3 tests/host_handlers.py、python3 tests/check_integrity.py、python3 tests/check_baseline.py。

以下是输入版本的历史说明；其中同学机器专用路径应改用当前工具配置，日志位置以新版输出LOG DIRECTORY为准。

小组：祝安毅 2511057、洪亮 2511955、闻鹏杰 2511565。

本目录是完整的实验三源码。报告、提示词、讲解、测试图片和原始日志位于同级 `../report/`。用户要求本次只生成作业，未进行 Git 提交。

## 构建与运行

在已安装 RISC-V 交叉工具链、QEMU 的 Ubuntu / WSL Ubuntu 中进入本目录：

```bash
export PATH="/mnt/d/软件基础/RISC-V/toolchain/bin:$PATH"
make
make qemu
```

默认正常运行打印十次 `100 ticks`，即累计1000次时钟中断后调用 `sbi_shutdown()` 正常退出。QEMU 4.1.1 中约需10秒，具体墙钟时间受运行负载影响。要提前退出可用 Ctrl+A，再按 X。

`SHUTDOWN_AFTER` 表示“输出100 ticks的次数”，默认10。该默认值是本次对指导书中未定义参数的明确补充。修改配置时先清理旧构建：

```bash
make clean
make DEFS=-DSHUTDOWN_AFTER=3 qemu
```

## 验证

```bash
python3 tests/check_integrity.py
make grade
python3 tests/extended_qemu.py
```

本机一键复现已记录的必需验证：

```bash
bash tests/run_required.sh
```

Windows PowerShell 中可使用：

```powershell
wsl -d Ubuntu --exec bash /mnt/d/软件基础/lab3_2511057/code/tests/run_required.sh
wsl -d Ubuntu --exec python3 /mnt/d/软件基础/lab3_2511057/code/tests/extended_qemu.py
```

一键脚本与扩展脚本中的工具链路径对应本机环境；迁移到其他机器时调整 PATH。`make grade` 本身使用原始课程脚本，在临时副本注入测试，不向交付源码添加测试钩子。

`extended_qemu.py` 在独立临时副本选择迁入的 Best-Fit，执行其课程自检，再检查明确编码的16/32位异常返回、全部可写GPR、SIE状态及嵌套临界区。交付默认分配器仍为框架原有的 First-Fit。默认QEMU运行与评分不会因为扩展测试而改变。

## 实现范围

- 新增 Lab3 实现只在 `kern/trap/trapentry.S`、`kern/trap/trap.c` 指定区域。
- Lab2 的迁入实现只在 `kern/mm/pmm.c`、`kern/mm/best_fit_pmm.c` 标记区域。
- `SAVE_ALL`、`struct trapframe`、课程测试、评分器、非目标函数均保持原样。
- 本实验实际验证内核 S态 Trap；未实现用户栈/内核栈切换、多核互斥、用户态安全取指、缺页恢复或48位及以上异常指令跳过。
- 完整来源说明见 `AUTHORS.md`。清理后的交付不含 `obj/` 和 `bin/`，首次运行执行 `make` 即可。

## 2026-11-05复核与优化

合并两个异常分支的指令长度解码；未知异常打印后直接返回，避免进入共享epc更新。
清理page_init迁移后恒假的重复边界比较。相同-O2构建中exception_handler从136字节
缩小到100字节（49条静态机器指令减少到35条），不是实际周期数或提速倍数。
优化后再次通过官方100/100、1000次时钟关机及6项边界检查。
报告第五节给出七项书面要求核对表；个人分工/工具信息按用户指示暂空，原生截图待补。
