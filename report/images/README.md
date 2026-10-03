# 截图放置说明

请在本目录放入以下五张本人本地实验截图：

| 文件名 | 截图内容 |
|---|---|
| `01_build.png` | `make clean && make` 成功，以及 `ls -lh bin`、`file bin/kernel` 的结果 |
| `02_qemu_boot.png` | `make qemu` 后的 OpenSBI 信息和 `(THU.CST) os is loading ...` |
| `03_gdb_reset_0x1000.png` | GDB 中 `info registers pc` 和 `x/10i $pc`，显示复位地址 `0x1000` |
| `04_gdb_kernel_0x80200000.png` | `break *0x80200000` 命中后的 PC 和反汇编 |
| `05_gdb_stack.png` | 执行 `la sp, bootstacktop` 前后 `sp` 的值，以及进入 `kern_init` 的证据 |

截图应保留 VS Code 终端或窗口上下文，使助教能够看出命令与结果的对应关系。不要只截取一小块数字。
