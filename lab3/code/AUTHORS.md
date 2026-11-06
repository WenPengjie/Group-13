# 实验三实现与来源

- 本次小组：2511057 祝安毅、2511955 洪亮、2511565 闻鹏杰。个人实际分工没有完整记录，报告不虚构成员贡献。
- 基础框架：`RISC-V/labcodes/lab3/lab3_new`，保留了课程测试、头文件和初始化流程。
- Lab3 新增实现：`kern/trap/trapentry.S`、`kern/trap/trap.c` 的指定标记区域，由本次 Codex 会话依据指导书生成和验证。
- Lab2 依赖：迁入目录中已有 `Lab2_2511057_祝安毅/code` 的 `page_init` 与 Best-Fit 实现。该目录标注了祝安毅、洪亮；代码注释还注明更早实现来源学号 2511565（闻鹏杰）。本次保留来源说明，不将继承部分声称为重新独立编写。
- 迁移适配：Lab3 头文件没有 Lab2 的 `PHYSICAL_MEMORY_END` 和 `KERNEL_BEGIN_PADDR`，使用已有 `PADDR(KERNTOP)` 和 `PADDR(KERNBASE)` 表达同一边界，不改课程头文件。
- 本次补充测试位于 `tests/`。`tools/` 内的官方测试、评分脚本和注入器均与原始框架一致。
