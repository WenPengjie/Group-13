# 实验报告

## 实验基本信息

| 项目 | 内容 |
|---|---|
| 实验名称 | Lab4 进程管理 |
| 小组成员 | 2511057 祝安毅、2511955 洪亮、2511565 闻鹏杰 |
| 完成日期 | 2026-11-10 |
| 实验资料 | [实验指导书](http://oslab.mobisys.top/lab2026/_book/lab4/lab4.html)、[实验练习](http://oslab.mobisys.top/lab2026/_book/lab4/lab4_2_1_exercises.html)、[报告要求](http://oslab.mobisys.top/lab2026/_book/lab4/lab4_5_labs_requirement.html) |

### 小组分工

| 成员 | 练习分工（按代码学号标记） | 报告分工（按模块列示） |
|---|---|---|
| 2511057 祝安毅 | Lab2/3 衔接、页映射操作 | 整体流程、页表和分页模式 |
| 2511955 洪亮 | 进程创建和初始化 | PCB、内核栈和线程入口 |
| 2511565 闻鹏杰 | 调度和上下文切换 | 中断保护、调度和测试结果 |

## 一、实验目的

1. 了解虚拟地址区间、页表和物理页之间的关系，掌握建立和撤销页映射的方法。
2. 理清一个内核线程从分配 PCB 到第一次执行的过程。
3. 实现基本调度，理解线程切换时需要保存哪些寄存器，以及关中断在其中的作用。

## 二、实验环境

在 Windows 的 Ubuntu 26.04.1 LTS（WSL2）中交叉编译。目标为 RV64，使用 Sv39 分页。QEMU 4.1.1 模拟单核 virt 机器，默认内存 128 MiB，固件为 OpenSBI v0.4。编译和调试使用 SiFive GCC-Metal 10.2.0 和 GDB-Metal 10.1，构建脚本使用 GNU Make 4.4.1 和 Python 3.14.4。[环境记录](./logs/01-environment.log)

| 成员 | AI 编程工具 | 底层模型 |
|---|---|---|
| 2511057 祝安毅 | Codex | GPT-6.1-Sol |
| 2511955 洪亮 | DeepSeek | DeepSeek V4 |
| 2511565 闻鹏杰 | Codex（ChatGPT） | gpt-6.1-sol |

## 三、实验整体逻辑分析

### 3.1 主线

启动时只有一个执行流。内核先初始化物理页管理和 Trap 入口，再检查虚拟内存区间，最后把启动执行流登记为 `idle`，由它把 CPU 交给新建的 `init`。这两个线程共用启动页表。线程切换时需要换的是执行现场和栈，页表根的物理地址在本实验中相同。

```text
kern_init → pmm_init → pic_init / idt_init → vmm_init → proc_init
          → clock_init / intr_enable → cpu_idle → schedule → proc_run → switch_to
          → forkret → forkrets → __trapret → sret → kernel_thread_entry → init_main
```

### 3.2 实现顺序

1. 先接上 Lab2 的物理页管理和 Lab3 的 Trap。页表与内核栈需要物理页，第一次运行线程也要经过 Trap 恢复代码。
2. 补齐页映射操作。VMA 用来记录地址范围及属性，页表记录 CPU 实际使用的地址翻译。框架用 `check_vma_struct` 检查区间的排序和半开边界，本实验使用预先建立的页映射。
3. 创建 `idle` 和 `init`，把新线程的栈和入口地址准备好，再把它加入可调度的进程集合。
4. 调度器从链表挑选线程。第一次切换到新线程时，从 `forkret` 开始执行。再次切回来时，从先前暂停的 `switch_to` 返回。

## 四、实验内容与实现

### 前置任务：接入 Lab2 和 Lab3

**负责人**　2511057 祝安毅

`page_init` 从 DTB 读取内存范围，给固件、内核和 `Page` 描述符留出位置，再把剩余的整页交给 Best-Fit。接入时把缺失的 `best_fit_pmm.h` 改为框架中的 `default_pmm.h`，并通过 `default_pmm_manager` 导出分配器。Best-Fit 分配最小的够用块，释放时合并两侧物理地址连续的空闲块。

Lab3 的 Trap 入口和恢复代码按本实验的帧布局接入。新增线程沿用 Lab4 提供的 `forkrets`。时钟仍然续设和计数，去掉了 Lab3 定次关机的逻辑。[前置任务提示词](./prompt.md)

### 功能模块一：虚拟内存页操作

**负责人**　2511057 祝安毅

```c
int page_insert(pde_t *pgdir, struct Page *page, uintptr_t la, uint32_t perm);
void page_remove(pde_t *pgdir, uintptr_t la);
```

插入时先用 `get_pte` 找叶项。新映射增加一次引用，同一个物理页重新插入只更新权限，换成另一页时先写入新项并刷新 TLB，再给旧页减引用。删除时先清空 PTE，再刷新 TLB，最后在引用归零时释放页。重复删除不改变状态。[pmm.c](../code/kern/mm/pmm.c)

#### 最终提示词

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

#### 实现迭代过程

第一次检查分配失败的路径时，发现 `get_pte` 可能已经分配了上一级页表，随后因内存不足而退出。规格里补上了“撤销本次分配”的要求，代码在这个分支清掉目录项、刷新 TLB，再释放上一级页表页。创建中间页表时同步整张 TLB，普通叶项更新只刷新对应地址。

复查启动时还发现，原来的 `check_boot_pgdir` 把高地址截到 `int` 后和物理页上限比较，循环没有实际检查启动映射。启动代码使用的是根页表中的 1 GiB 叶项，因此改为直接检查叶项的物理基址、权限和覆盖范围。普通 4 KiB 映射接口遇到上级大页叶项就停止。原有的低地址别名读写检查仍在，官方 PMM 用例也通过了。官方用例没有模拟中间页表分配失败。

### 功能模块二：进程创建与初始化

**负责人**　2511955 洪亮

```c
static struct proc_struct *alloc_proc(void);
void proc_init(void);
int kernel_thread(int (*fn)(void *), void *arg, uint32_t clone_flags);
int do_fork(uint32_t clone_flags, uintptr_t stack, struct trapframe *tf);
static void copy_thread(struct proc_struct *proc, uintptr_t esp, struct trapframe *tf);
static int copy_mm(uint32_t clone_flags, struct proc_struct *proc);
```

`alloc_proc` 清零 PCB，令 PID 为 -1，并初始化链表节点。 `proc_init` 让 PID 0 的 `idle` 复用启动栈，再创建 PID 1 的 `init`。 `do_fork` 按 PCB、内核栈、地址空间、运行现场的顺序准备资源，失败时倒序释放。资源齐备后才关中断分配 PID、登记链表和哈希表、更新进程计数并把线程设为可运行。内核线程共用启动页表，`copy_mm` 保留接口，`mm` 为 NULL。[proc.c](../code/kern/process/proc.c)

`kernel_thread` 把函数地址和参数放入 TrapFrame 的 `s0` 和 `s1`。 `copy_thread` 将这份帧复制到子线程内核栈顶，并将 `a0` 置零。第一次切换时先进入 `forkret`，`sret` 恢复到 S 态后才进入 `kernel_thread_entry`。这个汇编入口把 `s1` 移到 `a0`，再通过 `s0` 调用线程函数。

#### 最终提示词

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

#### 实现迭代过程

检查 `idle` 和 `init` 的命名时发现，原来的 `set_proc_name` 会从短字符串固定读 15 字节，可能读过字符串结尾。这里改为按实际长度复制，最多取 15 字节。复查新线程的栈时，分别核对了 `context.sp` 和 TrapFrame 中的 `sp`。前者指向帧，后者是 `sret` 后线程函数使用的栈顶。官方用例检查了两个 PCB 的状态和上下文，QEMU 也打印了 PID 1 和名称 `init`。

### 功能模块三：进程调度

**负责人**　2511565 闻鹏杰

```c
void cpu_idle(void);
void schedule(void);
void proc_run(struct proc_struct *proc);
void switch_to(struct context *from, struct context *to);
```

`cpu_idle` 看到 `need_resched` 后调用 `schedule`。调度器清掉请求，从当前线程的下一项开始扫描，`idle` 则从表头开始。找到第一个 `PROC_RUNNABLE` 的线程就增加它的 `runs`，找不到时回到 `idle`。需要切换时，`proc_run` 在关中断期间更新 `current`、写入 `satp` 并切换上下文。

`switch_to` 从 `a0` 和 `a1` 取旧、新两个 `context` 的地址，保存和恢复 `ra`、`sp`、`s0` 到 `s11`。它是一次普通函数调用，调用者保存寄存器由调用点按 ABI 处理。Trap 可能出现在任意指令之间，因此 TrapFrame 需要保存更完整的现场。[sched.c](../code/kern/schedule/sched.c) · [switch.S](../code/kern/process/switch.S)

#### 最终提示词

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

#### 实现迭代过程

复核指导书时确认，框架的 `lsatp` 是 Sv32 遗留接口。调度模块直接以 Sv39 的模式位和页表根物理页号构造 `satp`，随后调用 `flush_tlb`。评分测试创建两个额外线程，两者反复主动让出 CPU，最后都能得到执行机会。

### Challenge 1：保存和恢复中断状态

**负责人**　2511565 闻鹏杰

`local_intr_save` 读 `sstatus.SIE`。原来开着就关掉，并把原值记为真。原来已经关闭就记为假。 `local_intr_restore` 只在标志为真时重新开启中断。因此外层关中断后，内层保存到的是假，内层退出也不会把中断提前打开。

切换线程时，局部标志留在各自的内核栈上。已经运行过的线程再次被选中后，从原来的调用点恢复中断状态。新线程第一次运行时由 `sret` 根据预先设置的 `SPIE` 恢复。该方法保护当前 hart，不能替代多核环境中的锁。[sync.h](../code/kern/sync/sync.h)

### Challenge 2：分页模式与 `get_pte`

**负责人**　2511057 祝安毅

| 模式 | VPN 的分段 | 层数 | PTE 大小 | 一页能容纳的 PTE |
|---|---|---:|---:|---:|
| Sv32 | 10 + 10 位 | 2 | 4 B | 1024 |
| Sv39 | 9 + 9 + 9 位 | 3 | 8 B | 512 |
| Sv48 | 9 + 9 + 9 + 9 位 | 4 | 8 B | 512 |

三种模式的普通页都是 4 KiB，页内偏移占 12 位。Sv39 和 Sv48 的虚拟地址高位分别是第 38 位和第 47 位的符号扩展。Sv39 的 `get_pte` 用 `PDX1` 和 `PDX0` 两次查目录。这两段看起来一样，因为每层都用本级 VPN 做索引，检查有效位，再从非叶项的 PPN 找到下一级页表。目录不存在且允许创建时，就分配并清零下一级页表。最后由 `PTX` 取普通页的叶项。Sv32 少走一层，Sv48 多走一层。上级若已经是叶项，它描述的就是大页。

本实验保留 `create` 参数就够了，因为查找和创建共享同一套遍历逻辑。如果后续需要支持更多层数和大页，可以共用一个内部遍历函数，对外分成“只查找”和“缺失则创建”两个入口。这样调用方是否允许分配更容易看清，回滚也仍然只维护一处。

## 五、测试与验证

| 测试 | 观察结果 |
|---|---|
| `make -j4 qemu` | 内核编译、链接成功，物理页、启动页表和 VMA 自检通过，随后打印 `init` 的 PID 1、名称和两条问候。[启动日志](./logs/02-make-qemu.log) |
| `make grade` | PMM、Process Create 和 Schedule 均为 OK，得分 **30/30**。[评分日志](./logs/03-make-grade.log) |

`init_main` 打印完毕后返回，框架的 `do_exit` 会报告 `process exit!!` 并进入内核调试监控器。线程退出和回收由后续实验实现。编译日志中有框架 SLOB 代码及官方测试的类型警告，两条命令均成功退出。

以下两张截图来自 WSL 中实际运行命令的终端。图中保留编译、启动和评分的关键输出，完整输出见上表日志。

![QEMU 编译和启动](./images/make-qemu.png)

![官方评分](./images/make-grade.png)

## 六、实验总结与收获

### 对操作系统的理解

- **虚拟地址与物理页**。VMA 记录区间用途，PTE 记录实际翻译。两个虚拟地址可以指向同一个物理页，所以删掉一个 PTE 时仍要看引用计数。修改 PTE 后还要处理 TLB 中旧的翻译。
- **线程与进程**。内核线程共用页表，但每个线程有自己的栈和寄存器现场。调度器只负责找出谁能运行，实际切换由汇编完成。
- **调度与中断**。本实验由空闲线程和测试线程主动调用调度器。屏蔽本核中断可以保护切换时的临界区，多核调度还需要锁和跨核协调。

本实验没有实现按需分页、页面置换、写时复制、用户进程的退出回收和时间片抢占。启动阶段仍使用 1 GiB 映射，尚未按 `.text`、`.rodata`、`.data` 和 `.bss` 分别设置权限。

### AI 协作开发的经验

提示词里写“支持替换映射”太宽泛，补上“同一页重插只改权限，引用数不变”以后，才有明确的检查点。类似地，调度不能只写“切换页表”，还要说明当前使用 Sv39，`satp` 里存的是物理页号。用提示词列出接口和边界条件，再顺着真实的启动过程检查代码，比只看最后的评分更容易发现问题。
