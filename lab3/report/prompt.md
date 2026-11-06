# Lab3 实现与审查提示词记录

前三部分是输入包继承的最终实现提示词：迁入实验二依赖、Trap入口与上下文恢复、中断与异常处理。它们不是本轮重新执行三次生成的记录，也不据此推断每位组员的个人操作历史。
第四部分保存闻鹏杰本轮实际执行的完整审查优化请求，第五部分列出阶段与证据对应关系。原实现中的2511057署名保留；本轮发起人为闻鹏杰2511565，不批量改署。
各部分使用课程规定的 `[PROMPT]`、`[RELY]`、`[GUARANTEE]`、`[SPECIFICATION]` 结构，分别说明任务、已有接口、实现范围和行为要求。

## 一、前置任务：迁入实验二内存管理实现

```text
[PROMPT]
任务：补齐实验三依赖的实验二内存管理代码。
将实验二的 page_init 和 Best-Fit 实现迁入 kern/mm/pmm.c、
kern/mm/best_fit_pmm.c 中的 lab2 标记处，按实验三现有接口完成适配。
保留实验三的初始化顺序、中断保护和原有检查函数。需要新增的辅助函数
放在对应文件内，设为 static。完成后说明接口适配处，并检查编译和内存自检。

[RELY]
1. dtb_init 已在 page_init 前执行，可通过 get_memory_base()、
   get_memory_size() 取得物理内存范围。
2. 页大小为 PGSIZE。pages 指向 Page 描述符数组；nbase 是内存起始页号；
   npage 是管理范围的物理页号上界，描述符数量为 npage - nbase。
3. PADDR、KERNBASE、KERNTOP、PHYSICAL_MEMORY_OFFSET 以实验三头文件为准。
   实验三未定义的实验二边界宏，应使用已有地址关系适配，不改动头文件。
4. 空闲块用 free_area_t 和 Page.page_link 管理，块首页的 property 记录块长。
   PageReserved、PageProperty、set_page_ref 和链表操作接口均已提供。
5. alloc_pages、free_pages、nr_free_pages 已带本核中断保存与恢复逻辑。

[GUARANTEE]
补齐或迁入以下实现，保持原有函数签名：
static void page_init(void);
static void best_fit_init(void);
static void best_fit_init_memmap(struct Page *base, size_t n);
static struct Page *best_fit_alloc_pages(size_t n);
static void best_fit_free_pages(struct Page *base, size_t n);
static size_t best_fit_nr_free_pages(void);
const struct pmm_manager best_fit_pmm_manager;

[SPECIFICATION]
page_init
Pre-Condition：DTB已解析，内核映射已建立，BSS已清零。
Post-Condition：Page数组与物理页的对应关系正确；固件、内核、描述符数组及
对齐间隙保持保留；只有管理范围内剩余的完整页进入空闲链表。
Case 1：内存范围有效时，先确定DTB范围与内核映射范围的交集，再检查
描述符所需空间，完成各页初始化和空闲区登记。
Case 2：基址不支持、地址计算溢出或描述符空间不足时，通过现有panic报错，
不能越界写入Page数组。

best_fit_init
Pre-Condition：开始初始化Best-Fit管理器，尚未登记空闲区间。
Post-Condition：空闲链表初始化为空，空闲页计数置0。

best_fit_init_memmap
Pre-Condition：管理器已初始化，base指向有效Page区间，n大于0，
区间内各页处于待登记的保留状态。
Post-Condition：给定页转为空闲状态，块首页记录正确长度，空闲计数增加n；
链表按地址有序，物理相邻的空闲区间可以合并。

best_fit_alloc_pages
Pre-Condition：空闲链表与计数一致，请求n大于0。
Post-Condition：成功时返回最小的足够连续块，必要时保留剩余部分；失败时
返回NULL，链表和计数不变。
Case 1：存在精确匹配块，直接使用该块。
Case 2：只有更大的块，从其中最小的块分配；等大时选地址较低者。
Case 3：总空闲页不足或没有足够连续块，返回NULL。

best_fit_free_pages
Pre-Condition：base是已分配区间的起点，n大于0，区间有效。
Post-Condition：归还区间按地址放回链表，与前后物理相邻的空闲块合并，
空闲计数只增加n一次。

best_fit_nr_free_pages
Pre-Condition：管理器已初始化，空闲链表与计数一致。
Post-Condition：返回当前空闲页总数，不改变管理状态。

Requirements：保留basic_check、best_fit_check以及实验三的分配器选择；
不得用旧实验的包装函数覆盖本次已有的中断保护。
```

## 二、功能模块一：Trap上下文恢复与Trap入口

```text
[PROMPT]
任务：完成实验三模块一的Trap入口和上下文恢复。
在 kern/trap/trapentry.S 的 lab3 function1 标记处补全 RESTORE_ALL
和 __alltraps，使保存后的现场能够传给 trap()，处理完成后恢复并返回。
保留lab3注释，将YOUR CODE替换为2511057。不要修改SAVE_ALL、
struct trapframe、trap()的签名以及其他已有代码。

[RELY]
1. 目标为RV64，REGBYTES为8。SAVE_ALL已在内核栈上建立TrapFrame，
   共36个寄存器槽位，大小为288字节。
2. 槽位0至31对应x0至x31；槽位32、33、34、35分别对应
   sstatus、sepc、stval和scause。结构体中的字段名为
   gpr、status、epc、badvaddr、cause。
3. SAVE_ALL分配帧之前将原sp暂存于sscratch，之后把原sp写入槽位2，
   并将sscratch清零。因此槽位2保存的是Trap前的栈顶。
4. C接口为 void trap(struct trapframe *tf)。RISC-V调用约定用a0传递
   第一个参数，C函数返回时应保持调用前的sp。
5. __trapret中已有RESTORE_ALL和sret；sret使用sepc决定返回地址，
   结合sstatus中的SPP、SPIE完成特权级与中断状态返回。

[GUARANTEE]
实现汇编宏 RESTORE_ALL。
补全入口标签 __alltraps 中从保存现场到调用trap()的部分。
现有符号和TrapFrame布局保持不变。

[SPECIFICATION]
RESTORE_ALL
Pre-Condition：sp指向SAVE_ALL建立的有效TrapFrame，C处理函数已经返回。
Post-Condition：恢复所有可写通用寄存器，原sp恢复；sstatus、sepc采用
帧中的最终值，随后能够执行sret。
Case 1：C处理没有改变epc，返回到帧中原有的执行位置。
Case 2：C处理修改了epc，返回到更新后的位置，不能恢复成修改前的地址。
Requirements：恢复所需临时寄存器不能破坏已经恢复的原值；sp最后从
槽位2恢复，保证此前各次加载使用同一帧基址。x0无需恢复，scause和stval
作为诊断信息保留在帧中，无需写回。保留帧中的SPP，不强制切换到用户态。

__alltraps
Pre-Condition：处理器已跳转到Trap入口，当前内核栈可用于保存现场。
Post-Condition：先通过SAVE_ALL保存现场，再将该帧地址按调用约定传给trap；
trap返回后，执行进入__trapret，使用同一份帧恢复现场。
Requirements：传递帧指针即可，不复制整个结构体；调用C函数时保持16字节
栈对齐；原a0和ra必须在调用前已经保存。整个入口、处理和返回过程中，
通用寄存器的原值应保留，只有处理函数明确修改的帧字段按修改后值恢复。
```

## 三、功能模块二：中断与异常处理

```text
[PROMPT]
任务：完成实验三模块二的中断与异常分类处理。
在 kern/trap/trap.c 的 lab3 function2 标记处实现 interrupt_handler
和 exception_handler，保留原函数签名、分发流程和其他已有函数。
保留lab3注释，将YOUR CODE替换为2511057。需要的头文件、局部静态状态
和参数定义放在该实现区域。完成后检查持续时钟、异常返回与未知原因分支。

[RELY]
1. struct trapframe中的cause是scause快照，epc记录返回位置。
   RV64下cause最高位为中断标志，剩余部分为原因号。
2. IRQ_S_TIMER表示S态时钟中断；CAUSE_ILLEGAL_INSTRUCTION和
   CAUSE_BREAKPOINT分别表示非法指令异常和断点异常。
3. ticks在clock_init中初始化为0，类型为volatile size_t。
   clock_set_next_event()只设置一次未来事件；TICK_NUM为100；
   print_ticks()已提供，按课程格式输出100 ticks。
4. print_trapframe(tf)用于输出完整现场，sbi_shutdown()声明于sbi.h。
5. 指导书要求使用SHUTDOWN_AFTER控制统计次数。本地框架未定义该值，
   本次设默认值10，允许编译时覆盖；它表示统计输出次数，不是单次中断数。
6. 本次处理已映射内核代码中的16位和32位异常指令。首半字最低两位
   不为11时是16位编码，普通32位编码最低两位为11。

[GUARANTEE]
void interrupt_handler(struct trapframe *tf);
void exception_handler(struct trapframe *tf);
不得修改print_ticks、idt_init、trap_dispatch、trap及课程测试代码。

[SPECIFICATION]
interrupt_handler
Pre-Condition：tf指向有效TrapFrame，当前事件已由分发器判定为中断。
Post-Condition：完成当前类型对应的处理，保持epc不变；未关机时能够
进入统一返回流程。
Case 1：S态时钟中断，重新设置下一次事件，ticks恰好增加1；达到
TICK_NUM的整数倍时调用print_ticks。统计输出累计达到SHUTDOWN_AFTER
次时调用sbi_shutdown。
Case 2：框架列出的其他软件、时钟和外部中断，输出相应类型提示。
Case 3：未知中断，输出Unknown interrupt: cause N，再打印完整TrapFrame。
Requirements：去掉中断标志位后再识别原因号；每次时钟均需续设事件；
正常时钟路径不分配动态内存，控制台统计输出仅发生在规定的计数点。

exception_handler
Pre-Condition：tf有效；对于要跳过的非法指令和断点，epc指向可读的
16位或32位内核指令。
Post-Condition：支持的异常输出类型和修改前的地址，并把epc移动到下一条
指令；其他异常只输出完整现场，epc不变。
Case 1：非法指令异常，依次输出
  Exception type: Illegal instruction
  Illegal instruction at 0x...
根据实际指令长度使epc增加2或4。
Case 2：断点异常，依次输出
  Exception type: Breakpoint
  Breakpoint at 0x...
同样按实际长度使epc增加2或4，不能只根据异常类型固定偏移量。
Case 3：其他异常，调用print_trapframe后返回，不进入支持异常的epc更新流程。
Requirements：通过首半字判断本次支持的指令长度，不要求指令地址四字节
对齐；公共的长度判断只保留一处，每次异常只更新epc一次。
```


## 四、本轮实际执行的审查与优化提示词

下面是闻鹏杰本轮实际发出的请求，按原四段式结构保存；它不是对早期生成历史的追认。本轮选择保留核心代码、改进验证工具，执行依据与修订原因均在原文和报告第七节中说明。

```text
[PROMPT]

你是我的操作系统实验代码审查与性能优化协作者。请依据附件《Lab3实验指导书》、Lab3原始框架及当前 lab3_2511057(2).zip，在保持课程要求、公开接口和可观察行为不变的前提下，审查并改进代码。

学生：闻鹏杰，2511565。小组已有代码包含其他成员贡献，必须保留真实署名和来源。

一、目标与执行方式

1. 先读真实源码、指导书和测试，再判断哪里值得优化；不要为了产生改动而重写正确代码。
2. 优先保证正确性、可复现和可回滚，其次考虑运行开销、代码体积及可维护性。
3. 性能优化与健壮性修复分开说明。不能把删除重复代码、减少函数体积直接称为实际运行提速。
4. 进入实现阶段必须修改可访问的实际工程文件，不只展示代码片段。
5. 若只能操作附件副本，明确它不是我的WSL工程，并交付相对于本次输入版本的补丁及安全同步方法。
6. 已授权本任务内的常规检查、实现和测试，无须反复询问是否继续；遇到影响课程要求、扩大功能范围或需要新权限的决定再暂停。
7. 不承诺零风险。列出已控制的风险、剩余限制和未验证项目。
8. 本次工作是优化，不要求我先回答知识问题；每阶段用简短例子解释关键变化即可。

二、允许修改范围

- kern/trap/trap.c 中标记允许填写的实现区域。
- kern/mm/pmm.c 中 page_init 的已填充区域。
- kern/mm/best_fit_pmm.c 中已有实现区域，但不得修改原测试。
- 自编 tests、辅助脚本及说明文档。
- 新增独立性能测量、边界测试和回归脚本。

其他文件只读。若有证据表明必须修改上述范围外文件，先说明原因、影响及替代办法，等待确认。

禁止：

- 修改 SAVE_ALL、struct trapframe、trap()接口及其他受保护代码。
- 修改官方 tools/test_lab3*、inject.py、grade.sh，或通过削弱断言制造通过。
- 改变默认物理内存管理器、时钟间隔、统计周期、关机阈值或规定输出，以制造更快结果。
- 删除寄存器恢复、减少必要现场保存、提前恢复sp或擅自开启嵌套中断。
- 覆盖无关改动、批量改署名、自动commit或push。

三、交付要求

给出修改文件、设计依据、真实测试结果、优化前后对比、已知限制、补丁和本机验证步骤。

需要我执行的命令须标明：执行环境、工作目录、作用、预期现象；失败时需要提供什么输出。一次只给一组可完成的步骤并等待反馈。

[RELY]

一、以当前文件为准

我使用Windows＋WSL2 Ubuntu＋VS Code，曾使用QEMU 4.1.1及riscv64-unknown-elf工具链。重新核对实际路径和版本，不重装已可用工具，不假定我已安装上次交付包。

本次待优化版本是 lab3_2511057(2).zip；不要误用旧版或其他审查副本作为基线。

首先阅读：

- Makefile、tools/function.mk、tools/kernel.ld
- kern/init/entry.S、init.c
- kern/trap/trapentry.S、trap.h、trap.c
- kern/driver/clock.c、clock.h、intr.c、intr.h
- kern/sync/sync.h
- kern/mm/pmm.c、pmm.h、memlayout.h、mmu.h
- kern/mm/default_pmm.c、best_fit_pmm.c
- libs/riscv.h、defs.h、sbi.c、sbi.h
- tools/test_lab3.c、test_lab3_context.S、inject.py、grade.sh
- tests中的现有测试、完整性清单和运行脚本
- 已有README、AUTHORS及相关报告记录

二、当前实现及约束

- 正式功能是RESTORE_ALL、__alltraps、interrupt_handler、exception_handler，并需保留Lab2依赖。
- 当前默认管理器为原框架First-Fit；扩展测试在临时副本中切换Best-Fit。
- SAVE_ALL形成36个寄存器宽度的栈帧，RV64下为288字节。
- 原sp存于第2槽，恢复时必须最后处理。
- __alltraps使用a0向trap传入栈帧指针。
- 时钟中断每次必须重设事件、ticks增加一次；每TICK_NUM次输出一次，达到SHUTDOWN_AFTER后关机。
- 当前SHUTDOWN_AFTER默认10是已有实现约定，不是已确认的课程固定数字；本次不得擅自改变。
- 非法指令和断点采用共享的16/32位指令长度判断；未知异常打印现场后直接返回，不能误入共享epc更新。
- 本实验主要处理S态内核Trap，不声称已有完整用户态切栈、多核同步、缺页恢复或任意长度指令支持。
- 现有附件包含满分和扩展测试日志，但它们不能代替本次优化后的重新验证。
- 辅助脚本存在同学机器专用PATH、日志覆盖和管道错误传播方面的迁移风险，需要核实。

如果实际代码与上述描述不同，指出差异并以源码为依据。

[GUARANTEE]

一、必须保持的功能不变量

1. Trap前后的通用寄存器、原sp及返回所需CSR恢复正确。
2. 栈帧布局、栈对齐和RISC-V调用约定不变。
3. C处理函数对tf->epc等字段的合法修改能够传递给返回流程。
4. 正常时钟处理不擅自增加epc，不遗漏重设、计数、统计或关机。
5. 断点及非法指令保留规定输出，支持实验要求的16/32位指令，包括半字对齐的32位指令。
6. 未知异常仍按课程要求兜底，不虚构恢复能力。
7. page_init保持地址转换、内存上界、对齐、保留区和描述符布局正确；不得将内核或元数据交给分配器。
8. Best-Fit保持最小合适块选择、拆分、合并、空闲计数及原测试兼容性。
9. 不把volatile当作同步锁，不把单核关中断当成多核互斥。

二、必须保留的证据

- 修改前源码或可恢复补丁基线。
- 实际使用的本提示词及后续修订原因。
- 每项改动对应的问题、假设、测试及结果。
- 原测试与保护区域保持不变的实际差异检查。
- 优化前后相同配置的结果，而不是混用旧版成绩。
- 明确区分静态分析、宿主测试、交叉编译、QEMU运行和人工调试。

[SPECIFICATION]

阶段一：只读审查与基线

Pre-Condition：资料可读取；当前工程及工具可用性尚待核实。

操作：

1. 检查工作目录、Git状态或文件差异，保护已有改动。
2. 核对原始框架、当前版本和指导书要求。
3. 使用隔离副本记录基线，先检查依赖再构建。
4. 工具具备时执行默认构建、正常启动、官方评分及现有扩展测试。
5. 记录工具版本、编译参数、模拟器配置、退出码和关键输出。
6. 单独说明基线已有失败，不能把它混称为优化引入的问题。

Post-Condition：获得真实基线，或准确列出无法建立基线的阻碍。没有目标工具时可以继续静态检查和安全的宿主验证，但不得声称目标运行通过。

阶段二：提出并筛选优化

每个候选必须回答：

- 当前成本或问题在哪里，有什么源码、反汇编或测量证据？
- 改动为何保持语义，影响哪些状态？
- 预期改善的是运行时间、内存访问、体积还是可维护性？
- 用什么测试检验，怎样回退？

优先检查热路径、重复访问及真正冗余的计算；同时识别编译器已经消除的冗余。

若某候选收益不明确、复杂性过高或可能影响Trap正确性，放弃并说明原因。可以得出“当前核心代码不值得继续改”的结论。

阶段三：小步实现

1. 每次只实施一个可独立审查、测试和回退的改动。
2. 不混合大规模重构、算法替换和性能优化。
3. 每步完成后检查差异并执行相关测试，通过后再推进。
4. 辅助脚本保留调用者PATH，支持明确配置并进行依赖预检。
5. Shell管道正确传播失败；新增日志使用独立目录或运行编号，避免覆盖历史证据。
6. 预期失败测试在独立进程或独立启动配置运行，设置超时并清理自己启动的进程；不误杀用户已有QEMU。
7. 配置变化后清理或隔离构建产物，避免复用错误版本。

阶段四：正确性与健壮性回归

至少核实：

- 原始文件和受保护区域完整性。
- 默认构建、普通启动、规定次数统计及正常关机。
- 官方35/25/40三项评分。
- 全部可写GPR及sp恢复。
- 16位与32位断点、非法指令的正确返回。
- 半字对齐的32位指令。
- SIE原先开启和关闭时的恢复。
- 嵌套临界区不提前开启中断。
- 混合异常后持续时钟仍可工作。
- 其他中断与未知中断、未知异常兜底。
- 如修改内存模块，增加对应边界及分配回收回归。

新增测试必须有独立判定依据，不得只重复实现内部逻辑。

未实际执行的边界项目标记待验证；不通过修改官方用例或放宽条件解决失败。

阶段五：性能验证

1. 优化前后使用相同工具链、编译选项、目标配置和工作负载。
2. 分别记录函数机器码大小、静态指令及有条件获得的动态测量。
3. 静态指令减少不等于实际执行指令减少，代码变小不等于运行更快。
4. 若测量时间或周期，说明计时源、模拟器限制、采样位置、重复次数和统计方法，并保留原始数据。
5. 避免把编译时间、QEMU启动、串口输出和固定时钟等待混作handler运行开销；不能用固定约10秒的关机时间证明handler提速。
6. 如使用额外插桩，仅在独立测量副本或明确关闭的测试配置中进行，不污染提交默认行为。
7. 无可靠动态证据时，结论限定为静态开销或体积改善，不编造提速百分比。
8. 没有明显收益、出现回退或增加不必要风险时，撤回对应候选；只撤回本次改动，不覆盖用户原有修改。

阶段六：交付

最终分开回答：

1. 原有功能是否满足课程要求？
2. 实际修复了哪些风险？
3. 哪些性能收益有证据，哪些只是预期？
4. 通过了哪些测试，哪些尚未验证？
5. 还有哪些限制和剩余风险？

交付修改后的工程、相对于本次输入的补丁、改动说明、测试记录、回滚方法和最小本机复验步骤。

报告只补充真实改动与结果，不替我虚构学习体会，不把其他成员贡献改成我的贡献，不自动提交或推送仓库。

现在从读取当前工程、核对环境和建立优化前基线开始；按上述阶段连续推进，只有遇到资料、权限或必须由我本机完成的操作时才暂停。

## 执行中的修订

未改动用户功能要求。具体实施选择为：缺少目标工具时不追加无测量依据的内核改动，实施已有授权中的验证脚本健壮性与独立静态审计；依据和剩余验证见docs/OPTIMIZATION.md。
```

## 五、提示词与实现测试的对应记录

| 提示词阶段 | 实际行动 | 可验证结果或限制 |
|---|---|---|
| 只读审查与基线 | 核对本次ZIP、原框架、指导书、源码和原测试 | 56个课程文件保持基线字节一致；没有目标运行工具 |
| 候选筛选 | 检查时钟热路径、重复计算、描述符初始化和分配器选择 | 基线已做的优化不重复计功；高风险或无收益证据候选不实施 |
| 小步实现 | 修订运行入口、PATH、独立日志、超时与失败处理，增加宿主回归 | 只改自编测试、脚本和说明，保留署名、默认行为和原测试 |
| 正确性回归 | 真实trap.h布局、24组编码/对齐、1000次计数及12项工具测试 | 宿主通过；不把桩函数执行当作CSR/sret/QEMU验证 |
| 性能验证 | 新增同配置干净构建和nm/objdump静态对比 | 本轮未取得目标静态/动态结果，不宣称提速 |
| 交付 | 保存原始ZIP、差异补丁、真实prompt与日志、WSL复验及回滚说明 | 目标复验、原生截图、真实成员贡献和Git提交待确认 |

### 本轮问题与修订原因

1. 新宿主测试改用真实trap.h后，桩函数print_trapframe的static与头文件外部声明冲突。修复只去掉桩函数static；不改内核接口或头文件。
2. 当前缺少目标工具，按本提示词允许的分支继续静态与宿主检查，不虚构目标基线，也不追加未经测量的内核优化。
3. 本次文档补全明确区分基线目标记录、新宿主记录及待本机验证，避免用旧100/100冒充新版入口的回归结果。

没有将上述整理表或新写的解释伪称为额外执行过的历史提示词。早期三段实现prompt来自输入包，当前实际执行请求见第四节；具体回归证据见[实验报告](report.md)第七节。

