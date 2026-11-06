# WSL安装与最小复验

## 第一组 只安装新目录并核对工具

环境：Windows里的WSL Ubuntu普通Shell。下载lab3_optimized_20261105.zip至Windows下载目录，执行：

```bash
(
    set -e
    archive=/mnt/c/Users/andyw/Downloads/lab3_optimized_20261105.zip
    test -f "$archive"
    command -v unzip
    stage=$(mktemp -d "$HOME/lab3-opt-import.XXXXXX")
    unzip -q "$archive" -d "$stage"
    bash "$stage/lab3-optimized/INSTALL_WSL.sh"
)
```

预期新目录~/os-lab/src/labcodes/lab3-optimized-20261105/code；目标存在则停止，旧工程不变。下载改名时按真实位置修改archive。

```bash
cd ~/os-lab/src/labcodes/lab3-optimized-20261105/code
export TOOLCHAIN_BIN="$HOME/os-lab/tools/riscv64-unknown-elf-toolchain-10.2.0-2020.12.8-x86_64-linux-ubuntu14/bin"
export QEMU_BIN="$HOME/os-lab/tools/qemu-4.1.1/riscv64-softmmu"
export PATH="$TOOLCHAIN_BIN:$QEMU_BIN:$PATH"
pwd
command -v riscv64-unknown-elf-gcc
command -v qemu-system-riscv64
python3 tests/check_integrity.py
python3 tests/check_baseline.py
```

预期找到工具，两个检查均PASS。这些工具路径来自历史，必须核对。失败发pwd、第一条报错和command -v结果，不重装可用工具。完成本组先反馈。

## 第二组 收到环境确认后再运行

同一终端、同一code目录：

```bash
bash tests/run_required.sh
```

作用：临时副本构建，普通启动检查十次ticks并正常退出，再原官方make grade（独立GRADE_TMP）验35/25/40。预期REQUIRED PASS，summary.json中target_runtime_verified=true。可能需要一分钟以上；只启动单组验证，不同时手工跑另一套grade。
失败查看输出LOG DIRECTORY下build.log/qemu.log/grade.log及summary.json，提供第一条关键错误。缺工具或超时不等于通过。

## 第三组 扩展与静态审计

```bash
python3 tests/extended_qemu.py
```

预期EXTENDED PASS及六条原扩展用例结果，原始串口记录在该轮qemu.log。
静态对比前，将包根baseline-input.zip解压到一个新的临时目录，找到lab3_2511057/code，再执行：

```bash
python3 tests/audit_performance.py --baseline /实际基线目录/lab3_2511057/code
```

两份源码使用相同工具链与-O2，均在新临时目录构建。本次内核未改，预期指标一致。它不报告动态加速。默认配置若环境有MAKEFLAGS/DEFS等覆盖变量会明确拒绝；先检查来源，在验证终端清除后重试，不要全局乱改环境。

可选宿主验证：python3 tests/host_handlers.py（需要gcc）及python3 tests/test_validation_tools.py。它们不是QEMU证据。

## 补丁与恢复

推荐新旧目录并存，不覆盖现有WSL工程。若要补丁同步：先在用户目录备份原工程；进入与本次输入完全对应的lab3_2511057根目录，对changes.patch执行patch -p1 --dry-run，确认无冲突才应用patch -p1。修改后已用整包则不要重复应用。任何冲突先定位，不使用强制覆盖。
反向补丁前也必须dry-run并确认没有后续重叠改动；保留的baseline-input.zip是完整回滚来源。未自动Git提交或推送。
