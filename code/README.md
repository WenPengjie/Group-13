# Lab2：2511565 闻鹏杰、2511057 祝安毅、2511955 洪亮

报告、提示词和测试截图在同级 `../report/`；原始测试记录汇入报告附录 A。

## 编译与运行

在 Ubuntu / WSL Ubuntu 中，先将已有 RISC-V 工具链的 `bin` 加入 PATH，确认 `riscv64-unknown-elf-gcc`、`qemu-system-riscv64`、`make`、`python3` 可用。在本目录运行：

```bash
make
make qemu
make qemu PMM=buddy EXT_TEST=1
make qemu PMM=best_fit SLUB=1 EXT_TEST=1
make qemu PMM=buddy SLUB=1 EXT_TEST=1
```

默认参数是 `PMM=best_fit SLUB=0 EXT_TEST=0`。每次启动都应传入所需参数；不同配置不可同时在同一目录构建。最后进入无限循环是正常行为，退出 QEMU 用 Ctrl+A 再 X。

## 验证

```bash
python3 tests/check_protected.py
python3 tests/run_host_tests.py
python3 tests/page_init_host_check.py kern/mm/pmm.c
python3 tests/run_qemu_matrix.py --timeout 180 --log-dir test-results/target
python3 tests/run_qemu_matrix.py --timeout 180 --log-dir test-results/switch --reuse-build
make grade PMM=best_fit SLUB=0 EXT_TEST=0
```

矩阵脚本支持 `--gccprefix /工具链目录/riscv64-unknown-elf-` 和 `--qemu /路径/qemu-system-riscv64`。宿主测试使用真实算法源码与 RAM 适配层，不能代替目标运行。缺工具、超时、缺预期成功标志都会失败。原始官方评分只覆盖其规定的 page_init 和 Best-Fit。

## 页表调试

源码为 QEMU 4.1.1，使用带符号且低优化的独立构建。可执行：

```bash
python3 debug/capture_runtime.py \
  --qemu-debug /qemu-debug/riscv64-softmmu/qemu-system-riscv64 \
  --qemu-source /qemu-4.1.1 \
  --host-gdb gdb --target-gdb riscv64-unknown-elf-gdb
```

调试结果保存到 `../report/logs/debug/`，包括实际客体入口、Sv39 页表遍历、软件 TLB 填充/标签读取和 Bare 对比。宿主调试器必须支持 x86_64，不能用仅支持 RISC-V 的 GDB 代替。详细命令、实际结果与环境兼容处理见报告。

## 范围与来源

本实现为单核串行教学实验。课程保护文件与两个原 Best-Fit 测试未修改。Buddy 取整后释放仍传原请求；SLUB 不保证清零，只接受存活原始指针。分工与继承来源见 `AUTHORS.md`。交付不含编译产物，首次运行请执行 make。
