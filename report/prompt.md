# Lab4 提示词

下面按实验模块记录四段式提示词。Lab2 的物理内存管理和 Lab3 的 Trap 处理沿用了上次实验中的提示词及其实现，移植时需要满足本次框架的接口。

## 任务说明

根据 Lab4 指导书完成三项编程练习和两道 Challenge。用课程提供的用例验证，在报告中记录实现过程、提示词和测试结果。成员信息和 AI 工具沿用前次实验。

## 前置任务：迁入 Lab2 / Lab3

```text
[PROMPT]
根据本地上一版已完成的 Lab2/Lab3 实现，补齐 Lab4 的物理页初始化、Best-Fit 和 Trap 处理。

[RELY]
使用 lab3_2511057/code 中已经迁入的 Lab2 实现及该目录的 Trap 实现；以 Lab4 的 default_pmm_manager、boot_page_table_sv39、forkrets 和 trapframe 接口为准。

[GUARANTEE]
沿用 Lab4 的启动流程、测试注入点和 forkrets。使用课程原有评分用例。

[SPECIFICATION]
从 DTB 确定内存范围，保留固件、内核和 Page 描述符区域；Best-Fit 选最小足够块，切分、按地址插入和合并，正确维护空闲计数。Trap 汇编按 Lab4 给出的帧布局传入 tf，先恢复 sstatus、sepc，再恢复通用寄存器并最后恢复 sp；时钟事件续设并累加，断点及非法指令按指令长度更新 epc。去掉 Lab3 的定次关机策略。
```

## 功能模块一：虚拟内存页操作

```text
[PROMPT]
在 kern/mm/pmm.c 补全 page_insert 和 page_remove，写出页表项、物理页引用和 TLB 的更新顺序。

[RELY]
get_pte、pte_create、pte2page、page2ppn、page_ref_inc/dec、alloc_page/free_page、tlb_invalidate；当前为单核 Sv39，映射 API 处理普通 4 KiB 页。

[GUARANTEE]
保留课程自检和评分用例，不改变调用者传入的权限位。get_pte(create=0) 不分配页表页，不把上级大页叶项当作下一级目录。

[SPECIFICATION]
新映射增加目标页引用；同一页重复插入只替换权限；异页替换及删除先更新或清空 PTE、失效旧翻译，再减少旧页引用，归零才释放。未映射的地址可重复删除；创建失败返回 -E_NO_MEM，撤销本次因失败而新增的中间页表，不更改目标数据页引用。
```

## 功能模块二：进程创建与初始化

```text
[PROMPT]
在 kern/process/proc.c 实现 alloc_proc、proc_init、kernel_thread、do_fork、copy_thread 和 copy_mm，让 initproc 可以被查到并具备首次运行的现场。

[RELY]
proc_struct、context、trapframe、bootstack、boot_pgdir_pa、kmalloc/kfree、setup_kstack/put_kstack、get_pid、hash_proc、find_proc、wakeup_proc、forkret、forkrets 和 kernel_thread_entry。

[GUARANTEE]
共享内核页表且 mm 为 NULL；idle 复用启动栈，普通线程各自有内核栈。保留官方注入使用的函数边界及框架 do_exit 占位行为。

[SPECIFICATION]
初始化 PCB 为 PROC_UNINIT、pid=-1 和有效的空链表；idle PID 0，设为 current 并请求调度；创建 init 并通过 PID 1 查回。新线程使用 s0/s1 传入函数和参数，保存当前 gp/tp，SPP 和 SPIE 置位、SIE 清零。将 TrapFrame 复制到新栈顶，子线程 a0=0，sp 默认指向新栈顶，context 从 forkret 开始。创建失败按相反顺序清理；成功时在本核关中断的范围内分配 PID、登记哈希表和链表、计数并唤醒。
```

## 功能模块三：进程调度

```text
[PROMPT]
实现 cpu_idle、schedule、proc_run、switch_to，并用 QEMU 检查 init 和评分脚本注入的两个协作线程能切换。

[RELY]
proc_list、current、idleproc、need_resched、PROC_RUNNABLE、runs、local_intr_save/restore、write_csr、SATP_MODE_SV39、RISCV_PGSHIFT、flush_tlb、struct context；RV64 的 a0/a1 传入两个 context 指针。

[GUARANTEE]
保持协作式调度；不在时钟中断里调用 schedule，不实现后续实验的用户进程管理。用课程原始用例检验结果。

[SPECIFICATION]
idle 检测 need_resched 后进入调度。清除请求，从当前线程之后开始环形扫描，idle 从表头开始，跳过哨兵和非 RUNNABLE 线程，无候选则回到 idle。递增所选线程 runs；仅在不同线程间切换时，在本核关中断范围内更新 current。按指导书直接用 Sv39 模式和页表根的物理页号构造 satp，再用 flush_tlb 执行 sfence.vma。switch_to 按 8 字节偏移保存和恢复 ra、sp、s0–s11；ret 回到旧线程的暂停点或新线程的 forkret。恢复各自保存的中断状态。
```

## 复核与交付

```text
[PROMPT]
在本地完成课程要求的三组用例验证，依据真实输出写报告和整理图片。

[RELY]
课程 tools/inject.py、tools/test_lab4.c、tools/grade.sh；上一份组员和工具核对稿；本地报告模板和本次指导书。

[GUARANTEE]
使用原有测试文件和判分规则，保留本次运行的原始输出。

[SPECIFICATION]
在 WSL 的临时构建目录运行 make qemu 与 make grade，保留版本、启动输出和评分日志；解释 init 返回后的框架行为。按模板记录核心函数、规格、提示词、问题及修正、两道 Challenge 和与 OS 原理的对应关系。模型版本和分工根据已有记录填写。
```
