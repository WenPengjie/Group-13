# Lab4：进程管理

需要 Linux 或 WSL、RV64 裸机工具链（默认前缀 riscv64-unknown-elf-，含 GCC 和 GDB）、QEMU、Make、Python 3 与 bc。本次使用课程实验环境中的 GCC 10.2.0 和 QEMU 4.1.1。

在本目录执行：

```sh
make qemu
```

评分前退出上一轮 QEMU。在交互终端可按 Ctrl+A，再按 X 退出。

```sh
make grade GRADE_TMP="$(mktemp -d /tmp/lab4-grade.XXXXXXXX)"
```

预期官方评分为 30/30。正常启动会运行 init 内核线程；线程函数返回后进入课程框架的调试监控器。实现说明、提示词和本轮日志见 [实验报告](../report/report.md)。
