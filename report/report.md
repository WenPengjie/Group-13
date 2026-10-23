# 实验报告

## 实验基本信息

| 项目 | 内容 |
|------|------|
| **实验名称** | Lab2：物理内存管理与页表查询 |
| **小组成员** | 2511565－闻鹏杰、2511057－祝安毅、2511955－洪亮 |
| **完成日期** | 2026-10-22 |
| **交付结构** | `code/` 为源代码，`report/` 为报告、提示词及测试截图 |

### 小组分工

| 成员 | 负责的练习/模块 |
|------|----------------|
| 2511565－闻鹏杰 | 前期使用 AI 辅助设计提示词并完成 `page_init`、Best-Fit、Buddy、简化 SLUB 及其独立测试的初版实现；完成管理器构建开关、WSL/QEMU 基础运行和第一阶段 GDB 调试。 |
| 2511057－祝安毅 | 本轮代码复核、Best-Fit 搜索优化、Buddy 测试加固、SLUB 位图改进、构建配置复核、真实运行验证、调试记录与报告整理；使用 AI 辅助执行。 |
| 2511955－洪亮 | 实验环境搭建与验证、实验原理梳理与整理，以及各模块审核与报告核对；使用 AI 辅助理解原理和审核报告。 |


---

## 一、实验目的

1. 理解操作系统如何从启动环境获得物理内存范围，区分物理地址、虚拟地址、物理页号及 `Page` 描述符。
2. 完成 `page_init()`，排除固件、内核及管理元数据占用空间，建立可用物理页初始状态。
3. 理解 First-Fit，完成并验证 Best-Fit 和 Buddy 连续物理页分配，掌握拆分、回收、合并及碎片问题。
4. 完成简化 SLUB 扩展，在页分配之上提供不同字节大小对象的分配与释放。
5. 观察 Sv39 地址翻译与 QEMU 软件 TLB，区分操作系统页表、真实硬件行为和模拟器实现。
6. 通过规格、提示词、代码检查和实际测试约束 AI 输出，形成能够复现、能够解释的实验交付。

---

## 二、实验环境

| 项目 | 本次使用情况 |
|------|-------------|
| 主机与运行环境 | Windows 主机、WSL2 Ubuntu，具体系统与工具输出见 附录 A.1 |
| 目标架构 | RISC-V 64 位，QEMU `virt`，单核串行接口，默认 128MiB RAM |
| 交叉编译器 | SiFive `riscv64-unknown-elf-gcc` 10.2.0 |
| 常规目标模拟器 | QEMU 4.1.1 |
| 目标 GDB | SiFive GDB-Metal 10.1 |
| 宿主验证 | GCC、AddressSanitizer、UndefinedBehaviorSanitizer、Python 3 |
| 宿主调试器 | Ubuntu 官方 GDB 17.1，用户目录解包使用，不替换系统工具 |
| 调试模拟器 | 独立构建的 QEMU 4.1.1；调试过程和兼容处理见第四节分支任务 |

### AI 编程工具

| 成员 | AI 编程工具 | 底层模型 | 备注 |
|------|------------|---------|------|
| 2511565－闻鹏杰 | ChatGPT / Codex | 使用时未记录精确模型型号 | 用于四段式提示词设计、代码实现指导、故障定位与验证；结果由编译、QEMU 和官方评分核实。 |
| 2511057－祝安毅 | Codex 桌面应用 | 本轮界面未记录精确模型型号，不推测细分版本 | 用于代码审查、规格执行、测试及文档整理；结果由实际编译和测试约束。 |
| 2511955－洪亮 | Claude Code | DeepSeek-V4-Pro | 用于实验原理讲解、分步操作指导与报告审核；结果由本地编译运行和报告核对验证。 |

所有可执行验证均区分宿主测试与真实 RISC-V 启动。宿主测试直接编译实际分配器源码，但替换了物理 RAM、控制台和启动绑定，不能替代目标验证。

---

## 三、实验整体逻辑分析

### 3.1 本章节的逻辑主线

本实验围绕“把物理 RAM 变成可管理、可分配、可回收的资源”展开。内核不能把全部 RAM 都看作空闲空间：OpenSBI、内核代码、栈、静态数据和页描述符已经占据其中一部分。首先必须准确界定管理范围，随后才有资格把剩余完整页交给分配算法。

逻辑链为：

```text
kern_entry 保存启动参数并启用初始 Sv39 映射
  → kern_init 清 BSS，dtb_init 解析内存信息
  → pmm_init 选择并初始化 pmm_manager
  → page_init 建立 Page 数组，保留已用内存
  → init_memmap 注册可分配页
  → alloc_pages/free_pages 通过统一接口调用具体算法
  → check 验证分配、释放、计数及合并
  → 可选 slub_init/kmalloc/kfree 提供字节对象分配
```

统一接口体现“机制与策略分离”：`pmm_manager` 的函数指针规定调用机制，First-Fit、Best-Fit 和 Buddy 决定分配策略。SLUB 复用页后端，不替代页管理器。页表与分配器同属内存管理，但职责不同：前者解释地址映射，后者管理哪些页可以被占用。

### 3.2 功能的逐步实现

1. **建立内存初始状态。** 先获得 RAM 信息、设置映射偏移、放置描述符，再注册空闲区，避免把内核或元数据分配出去。
2. **阅读 First-Fit 并实现 Best-Fit。** 借助完整 First-Fit 理解链表、块头和计数，再改变候选选择方式；其余拆分、释放和合并仍需保持约定。
3. **接入 Buddy。** 按 2 的幂组织空闲块，用阶与伙伴关系简化递归拆分/合并，并通过独立测试验证。
4. **实现简化 SLUB。** 基于已验证的页接口，把一页划为多个对象槽，减少小对象每次占用整页的浪费。
5. **真实运行和调试。** 除宿主检查外，运行 QEMU 目标矩阵及官方评分，再观察地址翻译与 TLB。

---

## 四、实验内容与实现

### 功能模块一：物理内存探测与页描述符初始化

**负责人：** 2511565－闻鹏杰完成初版实现与初步验证；2511057－祝安毅负责本轮边界复核与完整验证；2511955－洪亮审核实现边界与验证数据。

#### 模块功能描述

```c
static void page_init(void);
static void init_memmap(struct Page *base, size_t n);
void pmm_init(void);
```

设备树解析器通过 `get_memory_base()`、`get_memory_size()` 提供 RAM 信息。`page_init()` 本身不重新编写 DTB 解析器，而是校验该信息、确定上界、建立描述符并注册空闲区。

关键量不能混用：

| 量 | 含义 |
|----|------|
| `va_pa_offset` | 内核高地址与物理地址之间的固定偏移 |
| `nbase` | 第一个 DRAM 物理页号，当前为 `0x80000` |
| `npage` | 管理末端的物理页号，不包含该页 |
| `npage - nbase` | 描述符个数，128MiB 下为 32768 |
| `pages` | `Page` 数组的虚拟地址，不是第一块可分配 RAM 的地址 |
| `nr_free_pages()` | 当前剩余空闲页数，随内核布局和分配状态变化 |

当前 RV64 下 `sizeof(struct Page)=40`，完整描述符数组占 `32768×40=1,310,720` 字节，即 320 页。数组紧随链接符号 `end` 并按页对齐，空闲区位于数组之后。不能使用旧截图中的地址硬编码，因为启用 Buddy 元数据及测试静态数组会增大 BSS 和 `end`。

#### 最终提示词

完整四段式见 [prompt.md](./prompt.md) 的第 1 节，核心约束如下：

```text
[PROMPT] 复核 page_init 的布局、地址转换、溢出和边界。
[RELY] DTB 查询、end、Page、nbase/npage/pages、框架地址及对齐宏。
[GUARANTEE] 正确设置映射偏移、描述符和初始空闲注册。
[SPECIFICATION] 所有容量检查先于写入；已用区保持保留；
无效信息终止初始化；没有完整空闲页时不调用 init_memmap。
```

#### 实现迭代过程

本轮对已有实现进行 **1 轮规格复核和验证**，未发现需要重写函数的确定性问题。首先校验基址、非零大小和加法溢出，再将管理末端限制到 DTB、框架上界和映射范围的交集。随后检查内核末端与整个描述符数组能否容纳，全部通过后才初始化数组。

开始时将每个描述符置为保留状态，清零引用与 `property`，初始化链结；最后仅将数组之后按页对齐的完整页交给管理器。这样“默认保留、明确放行”比直接把全部 RAM 标为空闲更容易保证安全边界。

15 个宿主场景涵盖正常布局、内核末端对齐、256MiB 截断、RAM 末端不齐、零/一页空闲、基址错误、大小为零、地址溢出、内核超界和描述符放不下。所有场景通过；真实 QEMU 启动与官方 page-init 检查也通过。

### 扩展思考：如何获取未知硬件的可用物理内存范围

**负责人：** 2511565－闻鹏杰完成前期思考与提示词；2511057－祝安毅复核并整理成报告；2511955－洪亮审核论证与参考资料。

通常由固件或引导协议提供内存描述：本平台由 QEMU/OpenSBI 启动链将 DTB 地址经 `a1` 交给内核，内核解析 `memory` 节点的 `reg`；其他平台可使用 UEFI 内存映射、BIOS E820 或 Multiboot 信息。还必须区分可用 RAM、固件保留区、MMIO 和生命周期不同的可回收区域。

不能盲目遍历物理地址并写入测试：不存在的地址可能触发总线错误，设备寄存器或固件数据可能被破坏，地址别名也可能导致误判。当前课程解析器仅提供单段 RAM 信息，未实现通用多段与所有 `reserved-memory` 布局支持；本轮不把它包装成完整固件内存映射解析器。

### 功能模块二／任务一：理解 First-Fit 连续物理页分配

**负责人：** 2511565－闻鹏杰完成前期阅读与问答准备；2511057－祝安毅负责本轮复核和报告整理；2511955－洪亮审核示例讲解与问答记录。

```c
static void default_init(void);
static void default_init_memmap(struct Page *base, size_t n);
static struct Page *default_alloc_pages(size_t n);
static void default_free_pages(struct Page *base, size_t n);
```

`default_init()` 建立空链表并清零计数；`default_init_memmap()` 接收真正的可用区间，清除保留状态，将首描述符标为块头，记录连续页数并按地址插入链表。

分配时从链首找到第一个足够大的块。若块比请求大，就拆成“已分配前段”和“剩余空闲尾段”，更新块头与链表，空闲页计数只减去实际申请页数。释放时归还页面、按地址插入，然后检查前后物理连续块是否可以合并；合并只改变块形态，不重复增加空闲页总数。

**改进空间：** 线性搜索在空闲块多时开销较高；可以考虑大小索引或分级链表，但需维护与地址顺序的一致性。Next-Fit 可减少总从链首扫描的情况，却改变了选择策略。应同时关注搜索成本和碎片，不能认为某种算法在所有负载下都最好。

该任务是阅读和思考题，本轮没有改写课程给出的 First-Fit。提示词和分析规格见 `prompt.md` 第 1 节及历史 `first_fit.md`。

### 功能模块二／任务二：Best-Fit 连续物理页分配

**负责人：** 2511565－闻鹏杰完成初版 Best-Fit 模块及接入；2511057－祝安毅负责本轮复核和精确匹配搜索优化；2511955－洪亮审核评分结果与测试输出。

#### 模块功能描述

```c
static void best_fit_init(void);
static void best_fit_init_memmap(struct Page *base, size_t n);
static struct Page *best_fit_alloc_pages(size_t n);
static void best_fit_free_pages(struct Page *base, size_t n);
static size_t best_fit_nr_free_pages(void);
```

通过 `best_fit_pmm_manager` 注册接口，`init_pmm_manager()` 默认选择该管理器。所有状态保存在 `free_area` 中，兼容原测试临时保存、清空和恢复 `free_list/nr_free` 的做法。`PageProperty=0` 不一定表示已分配，也可能是空闲块内部页，因此算法只能用块头标记解释空闲链表。

例如按地址有 6 页块和 3 页块，请求 3 页，First-Fit 会拆前一个块，Best-Fit 会选择现成的 3 页块，保留完整 6 页块。当前实现仍按地址维护链表，遍历候选取最小长度，同长时取低地址。

#### 最终提示词

```text
[PROMPT] 保持地址有序、拆分和合并语义，优化精确匹配搜索。
[RELY] pmm_manager、Page/list、free_area、原 First-Fit 和原测试。
[GUARANTEE] 完整 Best-Fit 接口与默认接入，精确申请 n 页。
[SPECIFICATION] 最小足够块、同长取低地址；精确匹配可提前退出；
释放正确双向合并；不得改 basic_check/best_fit_check 或官方测试。
```

#### 实现迭代过程

本轮 **1 次代码优化**。原模块正确选择最小候选，但即使已经找到 `property==n` 的精确匹配，也继续扫描剩余链表。精确匹配不可能被更优候选替代，因此记录候选后直接 `break`。由于按地址遍历，提前退出仍保留同长选低地址的约定。

这不是把一次正确实现描述成“原先无法运行”的 Bug。改动目的在于消除不必要遍历，最坏搜索仍为 `O(F)`（F 为空闲块数）。原测试、保护检查、目标启动及官方 Best-Fit 检查均通过。

**进一步改进：** 可额外维护按大小排序的树或分级索引以降低查找成本，但双索引更新更复杂，还需考虑现有测试的状态恢复约定；Best-Fit 也可能产生很多难利用的小碎片，不能只比较本次搜索是否最紧凑。

### 功能模块二／任务三：Buddy System

**负责人：** 2511565－闻鹏杰完成 Buddy 核心、初版独立测试和实现/测试提示词；2511057－祝安毅负责本轮核心复核与测试加固；2511955－洪亮审核测试覆盖与运行记录。

#### 模块功能描述

```c
void buddy_core_init(struct buddy_context *, struct Page *,
                     struct buddy_meta *, size_t capacity);
void buddy_core_register(struct buddy_context *, size_t start, size_t n);
struct Page *buddy_core_alloc(struct buddy_context *, size_t n);
void buddy_core_free(struct buddy_context *, struct Page *, size_t n);
void buddy_check(void);
```

最大 32768 页，对应阶 0～15。每阶一个空闲链表，申请向上取整到 2 的幂；拆分大块时将另一半放回低一阶链表。释放时使用 `i XOR (1<<order)` 找伙伴，只有同阶、空闲、同注册域且在界内才能合并。

每个描述符之外另有 16 字节元数据，记录原请求、注册域、阶与状态，总计 512KiB，属于内核 BSS，已由 `page_init()` 保留。每个注册区间独立成域，即使两个区间相邻也不跨域合并，这是明确的碎片权衡。

**接口例子：** 请求 3 页实际占 4 页，计数减 4；释放时传原请求 3，由元数据回收完整 4 页。不能把其中一页独立释放。SLUB 大对象同样需要保留原页请求。

#### 最终提示词

实现与测试分别使用两份四段式提示词，完整内容见 `prompt.md` 第 3、4 节；历史起始版也保留在提示词汇总中。实现规格关注对齐、域、状态和计数；测试规格只按接口契约检查，不复制分配器内部选块逻辑。

```text
实现提示词：
[PROMPT] 复核并接入 ucore Buddy 页管理模块。
[RELY] Page、pmm_manager、每阶链表与独立元数据。
[GUARANTEE] 初始化、区间注册、分配、释放、统计接口。
[SPECIFICATION] 请求向上取整；仅同域同阶空闲伙伴合并；
释放传原请求；失败不改状态；元数据保持在内核保留区。

测试提示词：
[PROMPT] 独立验证拆分、合并、碎片及随机交错行为。
[RELY] 公共接口、隔离实例、静态所有权和数据模式数组。
[GUARANTEE] 多种子、打乱释放、大块重申请、耗尽与恢复测试。
[SPECIFICATION] 每步检查非重叠、内容、对齐和计数；
回收后重申请原可分配大块；不修改原测试或让实现迎合固定地址。
```

#### 实现迭代过程

本轮 **1 轮实现复核、1 轮测试改进**。核心拆分和合并未发现合法调用下的确定错误，故没有为制造改动而重写。

发现的真实问题是测试负载过于规律：旧 LCG 直接取最低 6 位选择槽位，且仅申请分支额外抽随机数。复现 512 步可得到 128 步固定模式反复出现，削弱了交错碎片测试。

修正方法：使用非零种子的 xorshift32，每一步都独立抽取槽位和请求，运行 `2511057`、`0x9e3779b9`、`0xa5a5f00d` 三个固定种子，便于复现。逐步核查内容、所有权、保留页、对齐和计数。在隔离 64 页实例中把单页分配后打乱释放，最后重新申请整块 64 页；真实页管理器则先测得可分配的大块，随机回收及耗尽回收后再次申请该块。

三种种子的实际申请/释放次数分别为 `270/242`、`272/240`、`270/242`，残余活动块在每轮末尾全部回收。计数恢复和 16384 页大块恢复均通过。

#### 测试为何有效

| 用例 | 检验目标 |
|------|----------|
| 3 页、5 页申请与 16 页重申请 | 向上取整、拆分与递归合并 |
| 相邻但非伙伴的两页 | 防止错误地仅按物理相邻合并 |
| 不规则注册起止、洞和不同域 | 防止扩展越界、丢尾页或跨域合并 |
| 三种种子、活动块写入与非重叠检查 | 防止中途重复分配或覆盖仍在使用的数据 |
| 64 页打乱释放后整块重申请 | 检验复杂顺序下的合并，而不仅看空闲计数 |
| 真正耗尽后恢复大块 | 检验失败路径和集成环境中的完整回收 |

### Challenge：简化 SLUB 任意大小对象分配

**负责人：** 2511565－闻鹏杰完成简化 SLUB、初版独立测试和实现/测试提示词；2511057－祝安毅负责本轮位图优化、接口文档和测试加固；2511955－洪亮审核容量说明与测试记录。

#### 模块功能描述

```c
void slub_init(void);
void *kmalloc(size_t size);
void kfree(void *ptr);
void slub_check(void);
```

小对象使用 16、32、64、128、256、512、1024、2048 八个尺寸类别，每个 slab 占一物理页，维护尚有空槽的 `partial` 链表。满 slab 从链表移除，释放第一个对象后重新加入；最后一个对象释放后整页归还。

大于 2048 字节的对象走连续页后端，必须把头部也算入页数，例如申请 4096 字节需 2 页。头部记录原页请求，释放时将原请求交给后端，因此同时支持 Best-Fit 和 Buddy。

本实现保证至少 16 字节对齐，不保证清零；`kmalloc(0)=NULL`，`kfree(NULL)` 无操作；仅支持单核串行调用和存活对象的原始返回指针，不承诺对任意无效地址提供全面防护。

#### 最终提示词

实现和独立测试分别见 `prompt.md` 第 5、6 节。实现规格强调“位图与空链一致、大对象原请求、空页回收”；测试规格强调“全类别状态转换、内容保持、后端耗尽但已有槽可用、两种后端验证”。

```text
实现提示词：
[PROMPT] 在页分配之上复核并优化简化 SLUB。
[RELY] 两种页后端、八个尺寸类别、partial 链表和槽分配位图。
[GUARANTEE] slub_init、kmalloc、kfree 及公开调用契约。
[SPECIFICATION] 至少16字节对齐；位图与空链一致；空页立即归还；
大对象保存原页请求；失败不泄漏；元数据增加后重新计算容量。

测试提示词：
[PROMPT] 独立检验任意大小对象分配及状态转换。
[RELY] kmalloc/kfree、页计数、静态追踪数组，不依赖内部选槽算法。
[GUARANTEE] 边界、内容、非重叠、全类别复用、随机和耗尽测试。
[SPECIFICATION] 兼容一页仅一个槽的类别；物理页耗尽时仍可使用已有槽；
清理恢复基线；分别使用 Best-Fit/Buddy 后端。
```

#### 实现迭代过程

本轮 **1 轮实现优化和 1 轮测试扩展**。原 `kfree()` 每次遍历整个空槽链表检测重复释放，16 字节类一页批量释放会产生数万次额外节点检查。改为 256 位分配位图：申请时按槽索引置位，释放时验证并清位，使诊断成为常数时间操作。

位图增加 32 字节元数据，头部从 80 字节变为 112 字节。容量必须重新计算，不能沿用旧值：16 字节类现为 `(4096-112)/16=249` 个对象，600 个对象仍只需 3 页。位图中未用的尾位不作为可分配对象。

原复用测试主要覆盖 16 字节类。新测试对八类分别执行 600 个对象的满/部分/空状态转换，写满并核对请求区。2048 类一页仅 1 槽，其交错释放会直接归还整页，因此不能错误要求它像多槽 slab 一样保留部分空闲页。

另新增“物理页完全耗尽时，从已经存在的 32 字节 slab 再申请对象”的测试：同类槽申请成功且不占新页；新类别申请失败且计数不变；全部清理恢复基线。Best-Fit 与 Buddy 两种后端全部通过。

### 构建与测试基础设施

**负责人：** 2511565－闻鹏杰完成初版多配置开关；2511057－祝安毅修正配置戳并完成增量构建复核；2511955－洪亮审核配置切换记录。

构建参数为 `PMM=best_fit|buddy`、`SLUB=0|1`、`EXT_TEST=0|1`。默认 Best-Fit，不进行运行中切换。原配置戳在最终包含路径追加前计算，未来只改包含路径可能复用旧目标；本轮将戳移到最终 `CFLAGS/CFLAGS2/KCFLAGS` 确定之后。

新增不 `clean` 的配置切换验证：Best-Fit → Buddy → Best-Fit+SLUB → Buddy+SLUB → 默认 Best-Fit。每次检查输出管理器与功能标记，并拒绝已关闭功能的残余输出，五次全部通过。常规四配置矩阵仍逐项干净构建，用于区分功能验证与增量构建验证。

所有 12 项课程保护检查通过，原 `basic_check/best_fit_check`、注入脚本、评分脚本、DTB 解析器及保护头文件保持原内容。

### 分支任务：GDB 调试页表查询与 TLB

**负责人：** 2511565－闻鹏杰完成前期双 GDB 环境搭建及一次内核取指地址翻译观察；2511057－祝安毅完成本轮系统化页表、TLB 与 Bare 对比调试记录；2511955－洪亮审核调试记录与截图。

#### 实际执行方式

已有常规 QEMU 可运行内核，但安装后的二进制没有本次所需的源码调试符号；工具链中的 GDB 只支持 RISC-V，尝试设置宿主 `i386:x86-64` 架构时返回 `Undefined item`，因此不能拿它调试 x86_64 的 QEMU 进程。

本轮从本机已有 QEMU 4.1.1 源码包独立构建调试版：

```bash
/qemu-4.1.1/configure --target-list=riscv64-softmmu \
  --enable-debug --disable-werror --disable-docs \
  --disable-gtk --disable-sdl --disable-vnc \
  --extra-cflags='-O0 -g3'
make -j8
```

没有执行 `make install`，也没有替换原来可用的 QEMU。Ubuntu 官方 GDB 17.1 及缺少的官方动态库下载后在独立目录解包，以 `LD_LIBRARY_PATH` 指向该目录运行，未要求系统级安装。实际使用的配置参数见本节，最终调试记录见附录 A。

实际采集由 `code/debug/capture_runtime.py` 组织。宿主 GDB 启动带 `-S` 与 GDB stub 的 QEMU；RISC-V GDB 连接，停在 `kern_init`，读取客体寄存器与根页表后 detach，随后宿主 GDB 捕获真实数据访问。最先设置的宿主条件断点位于 `riscv_cpu_tlb_fill`，而不是所有 `get_physical_address` 调用，避免将客体 GDB 读内存触发的调试器查询混作程序实际访存。

完整规格见 `prompt.md` 第 8 节。两个 GDB 分工为：宿主 GDB 观察 QEMU 的 C 变量、页表遍历和宿主指令；客体 GDB 观察 RISC-V 寄存器、指令和符号，不能互换。

#### 客体入口的实际观察

附录 A.12 中在 `kern_init` 硬件断点处观察到：

```text
pc    = 0xffffffffc02000d8
sp    = 0xffffffffc0205000
satp  = 0x8000000000080205
boot_page_table_sv39 的虚拟地址 = 0xffffffffc0205000
根表第511项 = 0x200000cf
```

`satp.MODE=8` 表示 Sv39，低 44 位 PPN 为 `0x80205`，左移 12 位得到根表物理地址 `0x80205000`。这与内核打印的页表物理地址一致。

#### 一次真实数据访存的页表查询

附录 A.13 捕获了一次 S 模式的 4 字节读访问，调用栈是：

```text
code_gen_buffer（实际执行的宿主生成代码）
 → helper_le_ldul_mmu / full_le_ldul_mmu
 → load_helper
 → tlb_fill
 → riscv_cpu_tlb_fill
 → get_physical_address
```

该栈不是 `riscv_cpu_get_phys_page_debug` 的调试器读内存路径。以下各值均为实际断点输出：

| 项目 | 实际值 |
|------|--------|
| 请求 VA | `0xffffffffc0202240` |
| `access_type / mmu_idx` | `0 / 1`，即数据读、S 模式 |
| `satp` | `0x8000000000080205` |
| `levels / ptshift` | `3 / 18` |
| 根表 PA | `0x80205000` |
| 根索引 `idx` | `0x1ff`，即 511 |
| PTE 物理地址 | `0x80205ff8 = 0x80205000 + 511×8` |
| PTE | `0x200000cf` |
| PPN | `0x80000` |
| 转换函数给出的 4KiB 页基址 | `0x80202000` |
| 最终物理字节地址 | **`0x80202240`** |
| 完成赋值后的转换返回码 | `0`，成功 |

查询流程先判断有效访问模式；Sv39 路径确定 3 级、每级 9 位索引、每项 8 字节，并检查虚拟地址符号扩展。根项的 V、R、W、X、A、D 位有效且 U=0，符合本次 S 模式读访问。R/X 有效说明它已是叶子，并非下一层页表指针；PPN 的低 18 位为零，满足 1GiB 大页对齐要求，因此本次根层即结束，不再读取下两层。

大页把虚拟页号的低 18 位补入物理页号，函数返回页基址 `0x80202000`，再加页内偏移 `0x240`，得到 `0x80202240`。也可按启动映射核对：`0x80000000 + (VA - 0xffffffffc0000000)` 得到相同地址。这个算术核对是对实际观察的验证，不是用事先示例代替调试。

#### 软件 TLB 的填充与实际命中观察

成功翻译后，实际进入 `tlb_set_page`，填入 `vaddr=0xffffffffc0202000`、`paddr=0x80202000`、`prot=7`、`mmu_idx=1`、`size=4096`。因此根层 1GiB 叶子并不意味着本次软件 TLB 一定存入一条 1GiB 大项：本版本在这里为 TLB 构造了 4KiB 页映射。

读取对应软件项，索引为 2：

```text
addr_read  = 0xffffffffc0202000
addr_write = 0xffffffffc0202000
addr_code  = 0xffffffffc0202000
addend     = 0x80001fe00000
addr_read 与请求虚拟页相等 = 1
```

在该项 `addr_read` 上设置硬件读观察点后，第一次停在 `load_helper` 的填充后标签重读。仅凭这次停顿不能声称看到后续快速命中，于是继续运行到观察点再次在 `code_gen_buffer` 中触发。该次实际执行位置附近的宿主指令为：

```text
mov    %rbx,%rsi
jne    ...slow_path...
add    0x18(%rdi),%rsi
movslq (%rsi),%rbx
```

实测 `eflags=0x246`、ZF=1；按 `jne` 的语义，标签相等时满足命中条件，后续直接使用 `addend` 形成宿主地址。实际观察证明查找不一定体现为每次进入一个 C 函数：TCG 会把比较、条件跳转与地址加法生成到宿主机器码里。`tcg_out_tlb_load` 是生成这些指令的函数，不是每次访存都调用的 C 查找入口。

#### Bare 对比与真实 CPU 的区别

另一轮运行在 S 模式、`satp=0`、内核入口 `0x80200000` 的取指处停下。`get_physical_address` 不遍历 Sv39 页表，直接返回 `0x80200000`，返回码为 0；随后仍进入 `tlb_set_page`，其虚拟/物理参数同为 `0x80200000`，大小 4096。这些值见 附录 A.14。

这里的 Bare 样本是取指，Sv39 样本是数据读；我们比较的是是否进行分页转换和是否填充软件缓存，不把两种访存类型的栈差异都归因于模式改变。真实 CPU 在 Bare 下不进行 Sv39 页表翻译，而 QEMU 仍要将客体物理地址快速定位到宿主 RAM，因此其软件 TLB 兼有模拟执行加速作用。

#### 实际迭代与问题解决

1. **首次联调失败：** 通用前导脚本包含 `set debuginfod enabled off`，目标 GDB 10.1 不支持该配置，在装载符号前报 `No symbol table is loaded`。失败输出摘自原始记录，见附录 A.15，删除不兼容的公共命令，改用宿主环境变量控制联网符号服务，两个 GDB 随后能正常工作。
2. **采集语义修正：** 第一版完整采集在 `finish` 返回但调用者赋值尚未执行时打印 `ret`，得到的是旧值；同时首次标签观察停在填充后的 C 慢路径，不能直接称为快速命中。该版记录见附录 A.16，改为在赋值完成后记录返回码，并继续观察直到实际生成代码读取标签。
3. **最终结果：** 宿主 Sv39、客体入口、Bare 对比均完成，最终日志见附录 A.12～A.14。调试工具按版本区分；程序实际访存、调试器读内存、源码解释和算术核对分别标记，没有把准备教程当成已完成实验。

---

## 五、测试与验证

### 5.1 复现方式

在具备工具链的 Ubuntu 中进入 `code/`，确认工具链目录已加入 PATH：

```bash
python3 tests/check_protected.py
python3 tests/run_host_tests.py
python3 tests/page_init_host_check.py kern/mm/pmm.c
python3 tests/run_qemu_matrix.py --timeout 180 --log-dir test-results/target
python3 tests/run_qemu_matrix.py --timeout 180 --log-dir test-results/switch --reuse-build
make grade PMM=best_fit SLUB=0 EXT_TEST=0
```

也可分别使用 `make qemu`、`make qemu PMM=buddy EXT_TEST=1`、`make qemu PMM=best_fit SLUB=1 EXT_TEST=1`、`make qemu PMM=buddy SLUB=1 EXT_TEST=1`。内核最终无限循环是原框架行为，看到预期完成标记后用 `Ctrl+A` 再 `X` 退出。仅看到 OpenSBI 输出不代表实验通过。

### 5.2 实际结果

| 验证项 | 实际结果 | 原始证据 |
|--------|----------|----------|
| 官方 page_init / Best-Fit 评分 | **20/20** | 附录 A.2 |
| 真实 QEMU 四配置 | 全部构建与运行通过 | 附录 A.3、A.8～A.11 |
| 不 clean 的五次配置切换 | 全部通过，包含切回默认 | 附录 A.4 |
| 实际算法的宿主四配置 | ASan/UBSan 通过 | 附录 A.5 |
| page_init 宿主边界 | **15/15** | 附录 A.6 |
| 保护文件及原测试 | **12 项通过** | 附录 A.7 |

默认 Best-Fit 目标运行实际获得 31929 个初始空闲页；Buddy+SLUB 完整测试配置为 31661 页，并在测试后恢复 31661 页。宿主适配层固定使用 31744 页，这些数字来自不同布局，不能互相替代。默认 `Page` 描述符物理区间为 `[0x80207000,0x80347000)`；启用更多静态元数据后地址随内核 `end` 改变。

### 5.3 测试截图

下图均由本轮真实原始日志的展示页面截取，明确标注日志来源，不伪装成手工终端操作。与截图对应的原始运行记录汇入附录 A，便于复核。

**默认构建和运行：**

![默认 Best-Fit 构建与 QEMU 运行](./images/01_best_fit.jpg)

**官方评分：**

![官方评分20分](./images/02_grade.jpg)

**Buddy 三种子、合并与耗尽恢复：**

![Buddy测试](./images/03_buddy.jpg)

**Best-Fit 后端的 SLUB：**

![Best-Fit和SLUB测试](./images/04_slub_best_fit.jpg)

**Buddy 后端的 SLUB：**

![Buddy和SLUB测试](./images/05_slub_buddy.jpg)

**配置切换与宿主边界检查：**

![配置切换和初始化边界](./images/06_validation.jpg)

**实际页表与 TLB 调试：**

![实际地址翻译调试](./images/07_debug.jpg)

### 5.4 验证边界

官方 20 分脚本只检查其规定的 page_init 与 Best-Fit，不等于 Buddy、SLUB 和报告整体获得课程分数。扩展项由独立测试与实际目标运行提供证据。未进行多核并发、NUMA、通用多段 RAM、全部设备树保留区及形式化正确性验证，不把测试通过写成“所有输入均已证明正确”。

---

## 六、实验总结与收获

### 闻鹏杰个人完成内容

本人先根据实验要求设计四段式提示词，完成了 `page_init`、Best-Fit、Buddy 和简化 SLUB 的初版代码，并分别准备 Buddy 与 SLUB 的实现提示词和独立测试提示词。在 WSL 中完成交叉编译、QEMU 启动、官方 `make grade` 以及 Best-Fit、Buddy、Best-Fit＋SLUB、Buddy＋SLUB 四种配置的运行验证；同时搭建宿主 GDB 与 RISC-V GDB 的双调试环境，观察到内核高地址取指进入 QEMU 的 `get_physical_address()` 地址翻译路径。

这部分工作的重点不只是“让程序跑起来”，而是明确区分物理地址、内核虚拟地址、物理页号和 `Page` 描述符，理解页初始化如何排除内核与元数据占用；比较 First-Fit 与 Best-Fit 的选块差异；理解 Buddy 的 2 的幂拆分/合并以及 SLUB 在页分配器之上的对象复用。后续复核者对搜索、测试负载、SLUB 位图和构建配置作了进一步加固，最终结果以共同验证记录为准。

### 对操作系统的理解

| 实验知识点 | 对应 OS 原理 | 含义、关系和差异 |
|------------|--------------|------------------|
| `page_init`、保留页和描述符 | 物理资源管理与启动内存分配 | 原理强调资源状态与保护；实验用固定框架、DTB 单段信息和链接符号实现，范围比通用 OS 小。 |
| `pmm_manager` 函数指针 | 机制与策略分离 | 上层统一接口、下层更换策略；C 语言通过函数指针组织，并非必须依赖面向对象语言。 |
| First-Fit / Best-Fit | 连续分配、外部碎片 | 页总数足够仍可能缺少连续块；Best-Fit 的局部紧凑不保证全局碎片最少。 |
| Buddy 阶与 XOR 合并 | 分级内存管理、内外部碎片权衡 | 快速定位伙伴有利于合并；请求取整产生内部碎片，3 页占 4 页就是例子。 |
| SLUB 类别和槽复用 | 对象缓存、分层分配 | 小对象不必每次占整页；本实现是单页 slab、立即释放空页的简化方案，不等同完整 Linux SLUB。 |
| Sv39、页表项与大页叶子 | 虚拟地址翻译、权限保护 | 概念上的多级页表可提前在大页叶子结束；当前启动映射使用根层 1GiB 叶子。 |
| QEMU TLB 与 TCG | 地址翻译缓存与模拟执行 | 真实 CPU 的 TLB 缓存硬件转换；QEMU 还需把客体地址高效定位到宿主 RAM，命中路径可能是生成的机器码。 |
| 多种子、所有权与数据模式检查 | 不变量与系统验证 | 最终空闲计数恢复不代表期间没有覆盖，必须同时验证活动对象内容、非重叠以及大块恢复。 |

**OS 原理中重要、但本实验尚未对应实现的内容：**

1. 进程独立地址空间及完整的用户/内核访问隔离。
2. 缺页处理、按需分配、换入换出和页面置换策略。
3. 写时复制、共享内存与文件映射的完整生命周期。
4. 多核下分配器锁、每 CPU 缓存、TLB shootdown 和内存一致性。
5. NUMA、内存热插拔、内存压缩及通用固件保留映射。
6. 调度、进程通信、文件系统、持久化及权限模型。

### AI 协作开发的经验

1. **先明确不变量。** “实现分配器”过于宽泛；必须说清地址、页数、块头、原始请求长度和失败时能否改状态。Buddy 与 SLUB 的组合尤其依赖原页请求约定。
2. **先审查再修改。** 收到的代码不一定错误，也不一定完整。此次保留通过规格复核的核心，修改有证据的测试弱点和性能开销，避免无目的重写。
3. **让测试成为独立约束。** 原 Best-Fit 测试和评分保持不动，新增测试按契约检查，不按生成算法的内部选择重新写“答案”。
4. **区分代码问题和环境问题。** 交叉工具链不在 PATH、宿主 GDB 缺失和旧 QEMU 的构建兼容性应分别定位，不能通过删测试或编造运行结果绕过。
5. **规格与实现同步。** SLUB 加位图后头部和容量一起改变，提示词、设计说明与测试不能继续使用原来的 80 字节和 251 槽假设。
6. **证据需要分层。** 宿主检查、真实目标启动、官方评分、调试观察、源码推导分别记录；保留原始日志，截图只是阅读入口。

### 参考资料与来源

- [2026 实验指导书：Lab2 练习](http://oslab.mobisys.top/lab2026/_book/lab2/lab2_2_1_exercise.html)
- [Lab2 实验报告要求](http://oslab.mobisys.top/lab2026/_book/lab2/lab2_5_labs_requirement.html)
- [页表查询调试分支任务](http://oslab.mobisys.top/lab2026/_book/lab2/lab2_4_qemu_mmu_debug.html)
- [2026-10-15 课堂 Lab2 纪要](https://nankai.feishu.cn/docx/JQhSd6YaPoO0qExzbLXcnZHpnZf?dcuId=6838189938572492804)
- 工作区《实验报告模板.md》；用户提供的组内 Lab2 代码包。
- QEMU 4.1.1 源码：`target/riscv/cpu_helper.c`、`accel/tcg/cputlb.c`、`tcg/i386/tcg-target.inc.c`。


---

## 附录 A：实际测试与调试记录

以下为本轮实际运行的原始输出，直接并入报告，不另附日志目录。文件名沿用截图中的采集记录名称，SHA-256 用于核对原始文本。

### A.1 运行环境

原始记录：`environment.log`；SHA-256：`ded7b41c3c5c988f1637be0fbd1906bb7b0b47160a9458a3fc905313ffe8c69b`。

```text
$ uname -a
Linux LAPTOP-8V6CL7Q6 6.6.114.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Mon Dec  1 20:46:23 UTC 2025 x86_64 GNU/Linux
$ cat /etc/os-release
PRETTY_NAME="Ubuntu 26.04.1 LTS"
NAME="Ubuntu"
VERSION_ID="26.04"
VERSION="26.04.1 LTS (Resolute Raccoon)"
VERSION_CODENAME=resolute
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=resolute
LOGO=ubuntu-logo
$ gcc --version
gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0
Copyright (C) 2025 Free Software Foundation, Inc.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

$ python3 --version
Python 3.14.4
$ make --version
GNU Make 4.4.1
Built for x86_64-pc-linux-gnu
Copyright (C) 1988-2023 Free Software Foundation, Inc.
License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.
$ /mnt/d/软件基础/RISC-V/toolchain/bin/riscv64-unknown-elf-gcc --version
riscv64-unknown-elf-gcc (SiFive GCC-Metal 10.2.0-2020.12.8) 10.2.0
Copyright (C) 2020 Free Software Foundation, Inc.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

$ qemu-system-riscv64 --version
QEMU emulator version 4.1.1
Copyright (c) 2003-2019 Fabrice Bellard and the QEMU Project developers
$ /mnt/d/软件基础/RISC-V/toolchain/bin/riscv64-unknown-elf-gdb --version
GNU gdb (SiFive GDB-Metal 10.1.0-2020.12.7) 10.1
Copyright (C) 2020 Free Software Foundation, Inc.
License GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.
```

### A.2 官方评分

原始记录：`official-grade.log`；SHA-256：`8a6f4679da8dcd0ce49335df33b1b0c00b3d53e6f06cb0f0f671b3f134f23dfe`。

```text
lab2 injection complete
gmake[1]: Entering directory '/tmp/lab2-2511057-grade-20261022' + cc kern/init/entry.S + cc kern/init/init.c + cc kern/libs/stdio.c + cc kern/debug/panic.c + cc kern/driver/console.c + cc kern/driver/dtb.c + cc kern/mm/best_fit_pmm.c + cc kern/mm/buddy_check.c + cc kern/mm/buddy_pmm.c + cc kern/mm/default_pmm.c + cc kern/mm/pmm.c + cc kern/mm/slub.c + cc kern/mm/slub_check.c + cc kern/test/test_lab2.c + cc libs/printfmt.c + cc libs/readline.c + cc libs/sbi.c + cc libs/string.c + ld bin/kernel /mnt/d/软件基础/RISC-V/toolchain/bin/riscv64-unknown-elf-objcopy bin/kernel --strip-all -O binary bin/ucore.img gmake[1]: Leaving directory '/tmp/lab2-2511057-grade-20261022'
  -check page init:                          OK
  -check best fit:                           OK
Total Score: 20/20
```

### A.3 QEMU 四配置结果

原始记录：`target-matrix.log`；SHA-256：`278eb8aed81213e21af71c8621f3cd52c5ec186bd311fa6f75314115aa589f33`。

```text
QEMU emulator version 4.1.1
Copyright (c) 2003-2019 Fabrice Bellard and the QEMU Project developers
BUILD + BOOT best_fit
TARGET PASS best_fit log: /mnt/d/软件基础/Lab2_2511057_祝安毅/report/logs/target/best_fit-qemu.log
BUILD + BOOT buddy
TARGET PASS buddy log: /mnt/d/软件基础/Lab2_2511057_祝安毅/report/logs/target/buddy-qemu.log
BUILD + BOOT best_fit-slub
TARGET PASS best_fit-slub log: /mnt/d/软件基础/Lab2_2511057_祝安毅/report/logs/target/best_fit-slub-qemu.log
BUILD + BOOT buddy-slub
TARGET PASS buddy-slub log: /mnt/d/软件基础/Lab2_2511057_祝安毅/report/logs/target/buddy-slub-qemu.log
Four target configurations passed. Run default `make grade` separately for official scoring.
```

### A.4 五次配置切换

原始记录：`config-switch.log`；SHA-256：`c09649006cc59f89a3c1cf55f2a6a586fdb0f2a5b6966d82dc1084431d860cb2`。

```text
QEMU emulator version 4.1.1
Copyright (c) 2003-2019 Fabrice Bellard and the QEMU Project developers
BUILD + BOOT 1-best_fit
TARGET PASS 1-best_fit log: /mnt/d/软件基础/Lab2_2511057_祝安毅/report/logs/switch/1-best_fit-qemu.log
BUILD + BOOT 2-buddy
TARGET PASS 2-buddy log: /mnt/d/软件基础/Lab2_2511057_祝安毅/report/logs/switch/2-buddy-qemu.log
BUILD + BOOT 3-best_fit-slub
TARGET PASS 3-best_fit-slub log: /mnt/d/软件基础/Lab2_2511057_祝安毅/report/logs/switch/3-best_fit-slub-qemu.log
BUILD + BOOT 4-buddy-slub
TARGET PASS 4-buddy-slub log: /mnt/d/软件基础/Lab2_2511057_祝安毅/report/logs/switch/4-buddy-slub-qemu.log
BUILD + BOOT 5-best_fit
TARGET PASS 5-best_fit log: /mnt/d/软件基础/Lab2_2511057_祝安毅/report/logs/switch/5-best_fit-qemu.log
Five configuration switches passed. Run default `make grade` separately for official scoring.
```

### A.5 宿主测试

原始记录：`host-tests.log`；SHA-256：`51907527e261ac123b69e6a474a515ca67bfbe16d9b96b570cc819ed0681ad20`。

```text

BUILD best-fit
HOST algorithm check: best_fit_pmm_manager, 31744 free pages
[PMM] check and baseline restoration PASS
HOST PASS (not a RISC-V boot test)

BUILD buddy
HOST algorithm check: buddy_pmm_manager, 31744 free pages
[Buddy] split and recursive merge: PASS
[Buddy] adjacent non-buddies: PASS
[Buddy] irregular ranges, holes, domains, invalid sizes: PASS
[Buddy] shuffled 64-page merge, three seeds: PASS
[Buddy] seed=2511057 alloc=270 free=242, contents/non-overlap/large-block: PASS
[Buddy] seed=2654435769 alloc=272 free=240, contents/non-overlap/large-block: PASS
[Buddy] seed=2779115533 alloc=270 free=242, contents/non-overlap/large-block: PASS
[Buddy] exhaustion and recovery (largest=16384 pages): PASS
[Buddy] ALL TESTS PASS; baseline=31744 restored=31744
[PMM] check and baseline restoration PASS
HOST PASS (not a RISC-V boot test)

BUILD best-fit-slub
HOST algorithm check: best_fit_pmm_manager, 31744 free pages
[PMM] check and baseline restoration PASS
[SLUB] class/page boundaries, alignment, contents: PASS
[SLUB] class=16 full/partial/empty reuse: PASS
[SLUB] class=32 full/partial/empty reuse: PASS
[SLUB] class=64 full/partial/empty reuse: PASS
[SLUB] class=128 full/partial/empty reuse: PASS
[SLUB] class=256 full/partial/empty reuse: PASS
[SLUB] class=512 full/partial/empty reuse: PASS
[SLUB] class=1024 full/partial/empty reuse: PASS
[SLUB] class=2048 full/partial/empty reuse: PASS
[SLUB] seeded mixed allocation/free: PASS
[SLUB] backend exhaustion, rollback and recovery: PASS
[SLUB] existing slab usable with zero free physical pages: PASS
[SLUB] ALL TESTS PASS; baseline=31744 restored=31744
HOST PASS (not a RISC-V boot test)

BUILD buddy-slub
HOST algorithm check: buddy_pmm_manager, 31744 free pages
[Buddy] split and recursive merge: PASS
[Buddy] adjacent non-buddies: PASS
[Buddy] irregular ranges, holes, domains, invalid sizes: PASS
[Buddy] shuffled 64-page merge, three seeds: PASS
[Buddy] seed=2511057 alloc=270 free=242, contents/non-overlap/large-block: PASS
[Buddy] seed=2654435769 alloc=272 free=240, contents/non-overlap/large-block: PASS
[Buddy] seed=2779115533 alloc=270 free=242, contents/non-overlap/large-block: PASS
[Buddy] exhaustion and recovery (largest=16384 pages): PASS
[Buddy] ALL TESTS PASS; baseline=31744 restored=31744
[PMM] check and baseline restoration PASS
[SLUB] class/page boundaries, alignment, contents: PASS
[SLUB] class=16 full/partial/empty reuse: PASS
[SLUB] class=32 full/partial/empty reuse: PASS
[SLUB] class=64 full/partial/empty reuse: PASS
[SLUB] class=128 full/partial/empty reuse: PASS
[SLUB] class=256 full/partial/empty reuse: PASS
[SLUB] class=512 full/partial/empty reuse: PASS
[SLUB] class=1024 full/partial/empty reuse: PASS
[SLUB] class=2048 full/partial/empty reuse: PASS
[SLUB] seeded mixed allocation/free: PASS
[SLUB] backend exhaustion, rollback and recovery: PASS
[SLUB] existing slab usable with zero free physical pages: PASS
[SLUB] ALL TESTS PASS; baseline=31744 restored=31744
HOST PASS (not a RISC-V boot test)

All four HOST configurations passed. Target/QEMU verification is separate.
```

### A.6 页初始化边界测试

原始记录：`page-init-tests.log`；SHA-256：`fae76dfae91b16253aa7aea03f236ff66dd1eb49275c2b1ca86277aab69e826a`。

```text
PASS normal_128MiB_unaligned_end      descriptors=32768 free=31919 registrations=1
PASS already_aligned_kernel_end       descriptors=32768 free=31919 registrations=1
PASS truncate_256MiB_to_cap           descriptors=32768 free=31919 registrations=1
PASS unaligned_RAM_end                descriptors=32767 free=31918 registrations=1
PASS zero_free_exact_array_end        descriptors=1024 free=0 registrations=0
PASS less_than_one_free_page          descriptors=1023 free=0 registrations=0
PASS exactly_one_free_page            descriptors=1024 free=1 registrations=1
PASS zero_size                        expected panic: page_init: invalid or unsupported DTB memory range
PASS zero_base                        expected panic: page_init: invalid or unsupported DTB memory range
PASS unsupported_DRAM_base            expected panic: page_init: invalid or unsupported DTB memory range
PASS DTB_end_overflow                 expected panic: page_init: invalid or unsupported DTB memory range
PASS no_complete_DRAM_page            expected panic: page_init: no manageable physical pages
PASS kernel_exceeds_RAM               expected panic: page_init: kernel end is outside manageable memory
PASS descriptor_array_cannot_fit      expected panic: page_init: insufficient memory for Page descriptors
PASS kernel_below_link_base           expected panic: invalid kva
15/15 host contract scenarios passed (NOT a QEMU boot test).
```

### A.7 保护检查

原始记录：`protected-check.log`；SHA-256：`d2f9e7d10bee894d8c4e6ed7113ba4c59794c5032616d33f371782ac15dd2505`。

```text
UNCHANGED kern/mm/default_pmm.c
UNCHANGED kern/mm/pmm.h
UNCHANGED kern/mm/memlayout.h
UNCHANGED kern/driver/dtb.c
UNCHANGED kern/driver/dtb.h
UNCHANGED tools/test_lab2.c
UNCHANGED tools/test_lab2.h
UNCHANGED tools/inject.py
UNCHANGED tools/grade.sh
UNCHANGED kern/init/entry.S
UNCHANGED tools/kernel.ld
UNCHANGED best_fit_original_test_suffix
Protected framework and official tests: PASS
```

### A.8 Best-Fit 目标运行

原始记录：`target/best_fit-qemu.log`；SHA-256：`571cfb82c501b16ee679653fd61cd72548ed9eaedd2111ace25de5a8ccc7d780`。

```text

OpenSBI v0.4 (Jul  2 2019 11:53:53)
   ____                    _____ ____ _____
  / __ \                  / ____|  _ \_   _|
 | |  | |_ __   ___ _ __ | (___ | |_) || |
 | |  | | '_ \ / _ \ '_ \ \___ \|  _ < | |
 | |__| | |_) |  __/ | | |____) | |_) || |_
  \____/| .__/ \___|_| |_|_____/|____/_____|
        | |
        |_|

Platform Name          : QEMU Virt Machine
Platform HART Features : RV64ACDFIMSU
Platform Max HARTs     : 8
Current Hart           : 0
Firmware Base          : 0x80000000
Firmware Size          : 112 KB
Runtime SBI Version    : 0.1

PMP0: 0x0000000080000000-0x000000008001ffff (A)
PMP1: 0x0000000000000000-0xffffffffffffffff (A,R,W,X)
DTB Init
HartID: 0
DTB Address: 0x82200000
Physical Memory from DTB:
  Base: 0x0000000080000000
  Size: 0x0000000008000000 (128 MB)
  End:  0x0000000087ffffff
DTB init completed
(THU.CST) os is loading ...
Special kernel symbols:
  entry  0xffffffffc02000d8 (virtual)
  etext  0xffffffffc020177c (virtual)
  edata  0xffffffffc0206018 (virtual)
  end    0xffffffffc0206078 (virtual)
Kernel executable memory footprint: 24KB
memory management: best_fit_pmm_manager
Physical memory from DTB: [0x0000000080000000, 0x0000000088000000)
Managed physical memory: [0x0000000080000000, 0x0000000088000000)
Page descriptors: VA 0xffffffffc0207000, PA [0x0000000080207000, 0x0000000080347000), 32768 entries
Initial free memory: [0x0000000080347000, 0x0000000088000000), 31929 pages
check_alloc_page() succeeded!
satp virtual address: 0xffffffffc0205000
satp physical address: 0x0000000080205000
qemu-system-riscv64: terminating on signal 15 from pid 560 (python3)
```

### A.9 Buddy 目标运行

原始记录：`target/buddy-qemu.log`；SHA-256：`b22ecd38b7d9961eeb7080474c27f90a4d7d243e15a769917ad6ee8b1a55687c`。

```text

OpenSBI v0.4 (Jul  2 2019 11:53:53)
   ____                    _____ ____ _____
  / __ \                  / ____|  _ \_   _|
 | |  | |_ __   ___ _ __ | (___ | |_) || |
 | |  | | '_ \ / _ \ '_ \ \___ \|  _ < | |
 | |__| | |_) |  __/ | | |____) | |_) || |_
  \____/| .__/ \___|_| |_|_____/|____/_____|
        | |
        |_|

Platform Name          : QEMU Virt Machine
Platform HART Features : RV64ACDFIMSU
Platform Max HARTs     : 8
Current Hart           : 0
Firmware Base          : 0x80000000
Firmware Size          : 112 KB
Runtime SBI Version    : 0.1

PMP0: 0x0000000080000000-0x000000008001ffff (A)
PMP1: 0x0000000000000000-0xffffffffffffffff (A,R,W,X)
DTB Init
HartID: 0
DTB Address: 0x82200000
Physical Memory from DTB:
  Base: 0x0000000080000000
  Size: 0x0000000008000000 (128 MB)
  End:  0x0000000087ffffff
DTB init completed
(THU.CST) os is loading ...
Special kernel symbols:
  entry  0xffffffffc02000d8 (virtual)
  etext  0xffffffffc0202422 (virtual)
  edata  0xffffffffc0207020 (virtual)
  end    0xffffffffc02d04f8 (virtual)
Kernel executable memory footprint: 834KB
memory management: buddy_pmm_manager
Physical memory from DTB: [0x0000000080000000, 0x0000000088000000)
Managed physical memory: [0x0000000080000000, 0x0000000088000000)
Page descriptors: VA 0xffffffffc02d1000, PA [0x00000000802d1000, 0x0000000080411000), 32768 entries
Initial free memory: [0x0000000080411000, 0x0000000088000000), 31727 pages
[Buddy] split and recursive merge: PASS
[Buddy] adjacent non-buddies: PASS
[Buddy] irregular ranges, holes, domains, invalid sizes: PASS
[Buddy] shuffled 64-page merge, three seeds: PASS
[Buddy] seed=2511057 alloc=270 free=242, contents/non-overlap/large-block: PASS
[Buddy] seed=2654435769 alloc=272 free=240, contents/non-overlap/large-block: PASS
[Buddy] seed=2779115533 alloc=270 free=242, contents/non-overlap/large-block: PASS
[Buddy] exhaustion and recovery (largest=16384 pages): PASS
[Buddy] ALL TESTS PASS; baseline=31727 restored=31727
check_alloc_page() succeeded!
satp virtual address: 0xffffffffc0206000
satp physical address: 0x0000000080206000
qemu-system-riscv64: terminating on signal 15 from pid 560 (python3)
```

### A.10 Best-Fit 与 SLUB 目标运行

原始记录：`target/best_fit-slub-qemu.log`；SHA-256：`8059f90c61af7601ec468c7d563ee332d9ae92358b540f600c6310a7e1a83522`。

```text

OpenSBI v0.4 (Jul  2 2019 11:53:53)
   ____                    _____ ____ _____
  / __ \                  / ____|  _ \_   _|
 | |  | |_ __   ___ _ __ | (___ | |_) || |
 | |  | | '_ \ / _ \ '_ \ \___ \|  _ < | |
 | |__| | |_) |  __/ | | |____) | |_) || |_
  \____/| .__/ \___|_| |_|_____/|____/_____|
        | |
        |_|

Platform Name          : QEMU Virt Machine
Platform HART Features : RV64ACDFIMSU
Platform Max HARTs     : 8
Current Hart           : 0
Firmware Base          : 0x80000000
Firmware Size          : 112 KB
Runtime SBI Version    : 0.1

PMP0: 0x0000000080000000-0x000000008001ffff (A)
PMP1: 0x0000000000000000-0xffffffffffffffff (A,R,W,X)
DTB Init
HartID: 0
DTB Address: 0x82200000
Physical Memory from DTB:
  Base: 0x0000000080000000
  Size: 0x0000000008000000 (128 MB)
  End:  0x0000000087ffffff
DTB init completed
(THU.CST) os is loading ...
Special kernel symbols:
  entry  0xffffffffc02000d8 (virtual)
  etext  0xffffffffc0202726 (virtual)
  edata  0xffffffffc0207020 (virtual)
  end    0xffffffffc02487d0 (virtual)
Kernel executable memory footprint: 290KB
memory management: best_fit_pmm_manager
Physical memory from DTB: [0x0000000080000000, 0x0000000088000000)
Managed physical memory: [0x0000000080000000, 0x0000000088000000)
Page descriptors: VA 0xffffffffc0249000, PA [0x0000000080249000, 0x0000000080389000), 32768 entries
Initial free memory: [0x0000000080389000, 0x0000000088000000), 31863 pages
check_alloc_page() succeeded!
satp virtual address: 0xffffffffc0206000
satp physical address: 0x0000000080206000
[SLUB] class/page boundaries, alignment, contents: PASS
[SLUB] class=16 full/partial/empty reuse: PASS
[SLUB] class=32 full/partial/empty reuse: PASS
[SLUB] class=64 full/partial/empty reuse: PASS
[SLUB] class=128 full/partial/empty reuse: PASS
[SLUB] class=256 full/partial/empty reuse: PASS
[SLUB] class=512 full/partial/empty reuse: PASS
[SLUB] class=1024 full/partial/empty reuse: PASS
[SLUB] class=2048 full/partial/empty reuse: PASS
[SLUB] seeded mixed allocation/free: PASS
[SLUB] backend exhaustion, rollback and recovery: PASS
[SLUB] existing slab usable with zero free physical pages: PASS
[SLUB] ALL TESTS PASS; baseline=31863 restored=31863
qemu-system-riscv64: terminating on signal 15 from pid 560 (python3)
```

### A.11 Buddy 与 SLUB 目标运行

原始记录：`target/buddy-slub-qemu.log`；SHA-256：`aa2e485392ab89eef6941ec3e0bceb4b3bc402a680bb504178d6f52ec3a3225e`。

```text

OpenSBI v0.4 (Jul  2 2019 11:53:53)
   ____                    _____ ____ _____
  / __ \                  / ____|  _ \_   _|
 | |  | |_ __   ___ _ __ | (___ | |_) || |
 | |  | | '_ \ / _ \ '_ \ \___ \|  _ < | |
 | |__| | |_) |  __/ | | |____) | |_) || |_
  \____/| .__/ \___|_| |_|_____/|____/_____|
        | |
        |_|

Platform Name          : QEMU Virt Machine
Platform HART Features : RV64ACDFIMSU
Platform Max HARTs     : 8
Current Hart           : 0
Firmware Base          : 0x80000000
Firmware Size          : 112 KB
Runtime SBI Version    : 0.1

PMP0: 0x0000000080000000-0x000000008001ffff (A)
PMP1: 0x0000000000000000-0xffffffffffffffff (A,R,W,X)
DTB Init
HartID: 0
DTB Address: 0x82200000
Physical Memory from DTB:
  Base: 0x0000000080000000
  Size: 0x0000000008000000 (128 MB)
  End:  0x0000000087ffffff
DTB init completed
(THU.CST) os is loading ...
Special kernel symbols:
  entry  0xffffffffc02000d8 (virtual)
  etext  0xffffffffc02033cc (virtual)
  edata  0xffffffffc0208020 (virtual)
  end    0xffffffffc0312c48 (virtual)
Kernel executable memory footprint: 1099KB
memory management: buddy_pmm_manager
Physical memory from DTB: [0x0000000080000000, 0x0000000088000000)
Managed physical memory: [0x0000000080000000, 0x0000000088000000)
Page descriptors: VA 0xffffffffc0313000, PA [0x0000000080313000, 0x0000000080453000), 32768 entries
Initial free memory: [0x0000000080453000, 0x0000000088000000), 31661 pages
[Buddy] split and recursive merge: PASS
[Buddy] adjacent non-buddies: PASS
[Buddy] irregular ranges, holes, domains, invalid sizes: PASS
[Buddy] shuffled 64-page merge, three seeds: PASS
[Buddy] seed=2511057 alloc=270 free=242, contents/non-overlap/large-block: PASS
[Buddy] seed=2654435769 alloc=272 free=240, contents/non-overlap/large-block: PASS
[Buddy] seed=2779115533 alloc=270 free=242, contents/non-overlap/large-block: PASS
[Buddy] exhaustion and recovery (largest=16384 pages): PASS
[Buddy] ALL TESTS PASS; baseline=31661 restored=31661
check_alloc_page() succeeded!
satp virtual address: 0xffffffffc0207000
satp physical address: 0x0000000080207000
[SLUB] class/page boundaries, alignment, contents: PASS
[SLUB] class=16 full/partial/empty reuse: PASS
[SLUB] class=32 full/partial/empty reuse: PASS
[SLUB] class=64 full/partial/empty reuse: PASS
[SLUB] class=128 full/partial/empty reuse: PASS
[SLUB] class=256 full/partial/empty reuse: PASS
[SLUB] class=512 full/partial/empty reuse: PASS
[SLUB] class=1024 full/partial/empty reuse: PASS
[SLUB] class=2048 full/partial/empty reuse: PASS
[SLUB] seeded mixed allocation/free: PASS
[SLUB] backend exhaustion, rollback and recovery: PASS
[SLUB] existing slab usable with zero free physical pages: PASS
[SLUB] ALL TESTS PASS; baseline=31661 restored=31661
qemu-system-riscv64: terminating on signal 15 from pid 560 (python3)
```

### A.12 客体入口调试

原始记录：`debug/guest.log`；SHA-256：`33195737a98279c2512e47949a33bc29438d0a143d8ecb3d3798964b50c002bb`。

```text
The target architecture is set to "riscv:rv64".
0x0000000000001000 in ?? ()
Hardware assisted breakpoint 1 at 0xffffffffc02000d8: file kern/init/init.c, line 33.

Breakpoint 1, kern_init () at kern/init/init.c:33
33	    memset(edata, 0, end - edata);

=== REAL GUEST KERNEL ENTRY ===
pc             0xffffffffc02000d8	0xffffffffc02000d8 <kern_init>
sp             0xffffffffc0205000	0xffffffffc0205000
satp           0x8000000000080205	-9223372036854251003
=> 0xffffffffc02000d8 <kern_init>:	auipc	a0,0x6
   0xffffffffc02000dc <kern_init+4>:	addi	a0,a0,-192
   0xffffffffc02000e0 <kern_init+8>:	auipc	a2,0x6
   0xffffffffc02000e4 <kern_init+12>:	addi	a2,a2,-104
   0xffffffffc02000e8 <kern_init+16>:	addi	sp,sp,-16
   0xffffffffc02000ea <kern_init+18>:	sub	a2,a2,a0
   0xffffffffc02000ec <kern_init+20>:	li	a1,0
   0xffffffffc02000ee <kern_init+22>:	sd	ra,8(sp)
$1 = 0xffffffffc0205000
$2 = 0x200000cf

=== GUEST CAPTURE COMPLETE ===
[Inferior 1 (process 1) detached]
```

### A.13 Sv39 与 TLB 调试

原始记录：`debug/host-sv39.log`；SHA-256：`42dd8ded5e6baa8b2cb0e7e05f6d1ea270702c766cee6197e8c84abe56124af2`。

```text
Breakpoint 1 at 0x3c72d4: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c, line 438.
[Thread debugging using libthread_db enabled]
Using host libthread_db library "/usr/lib/x86_64-linux-gnu/libthread_db.so.1".
[New Thread 0x7ffff77ff6c0 (LWP 458)]
[New Thread 0x7ffff4ffe6c0 (LWP 459)]

OpenSBI v0.4 (Jul  2 2019 11:53:53)
   ____                    _____ ____ _____
  / __ \                  / ____|  _ \_   _|
 | |  | |_ __   ___ _ __ | (___ | |_) || |
 | |  | | '_ \ / _ \ '_ \ \___ \|  _ < | |
 | |__| | |_) |  __/ | | |____) | |_) || |_
  \____/| .__/ \___|_| |_|_____/|____/_____|
        | |
        |_|

Platform Name          : QEMU Virt Machine
Platform HART Features : RV64ACDFIMSU
Platform Max HARTs     : 8
Current Hart           : 0
Firmware Base          : 0x80000000
Firmware Size          : 112 KB
Runtime SBI Version    : 0.1

PMP0: 0x0000000080000000-0x000000008001ffff (A)
PMP1: 0x0000000000000000-0xffffffffffffffff (A,R,W,X)
DTB Init
HartID: [Switching to Thread 0x7ffff4ffe6c0 (LWP 459)]

Thread 3 "qemu-system-ris" hit Breakpoint 1, riscv_cpu_tlb_fill (cs=0x5555564daf50, address=18446744072637915712, size=4, access_type=MMU_DATA_LOAD, mmu_idx=1, probe=false, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:438
438	{
Temporary breakpoint 2 at 0x55555591a686: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c, line 158.

Thread 3 "qemu-system-ris" hit Temporary breakpoint 2, get_physical_address (env=0x5555564e3960, physical=0x7ffff4ffd280, prot=0x7ffff4ffd274, addr=18446744072637915712, access_type=0, mmu_idx=1) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:158
158	{

=== REAL SV39 DATA LOAD ===
#0  get_physical_address (env=0x5555564e3960, physical=0x7ffff4ffd280, prot=0x7ffff4ffd274, addr=18446744072637915712, access_type=0, mmu_idx=1) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:158
#1  0x000055555591b398 in riscv_cpu_tlb_fill (cs=0x5555564daf50, address=18446744072637915712, size=4, access_type=MMU_DATA_LOAD, mmu_idx=1, probe=false, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:451
#2  0x00005555558608f8 in tlb_fill (cpu=0x5555564daf50, addr=18446744072637915712, size=4, access_type=MMU_DATA_LOAD, mmu_idx=1, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:878
#3  0x0000555555862e59 in load_helper (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478, size=4, big_endian=false, code_read=false, full_load=0x555555862c19 <full_le_ldul_mmu>) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1274
#4  full_le_ldul_mmu (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1423
#5  0x0000555555863312 in helper_le_ldul_mmu (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1430
#6  0x00007ffff5009e8c in code_gen_buffer ()
#7  0x00005555558854f0 in cpu_tb_exec (cpu=0x5555564daf50, itb=0x7ffff5009d40 <code_gen_buffer+44307>) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cpu-exec.c:173
env = 0x5555564e3960
physical = 0x7ffff4ffd280
prot = 0x7ffff4ffd274
addr = 18446744072637915712
access_type = 0
mmu_idx = 1
$1 = 0x8000000000080205
VA=0xffffffffc0202240 SATP=0x8000000000080205 ACCESS=0 MMU=1
Temporary breakpoint 3 at 0x55555591abc7: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c, line 254.

Thread 3 "qemu-system-ris" hit Temporary breakpoint 3, get_physical_address (env=0x5555564e3960, physical=0x7ffff4ffd280, prot=0x7ffff4ffd274, addr=18446744072637915712, access_type=0, mmu_idx=1) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:254
254	        target_ulong ppn = pte >> PTE_PPN_SHIFT;

=== PAGE TABLE WALK ===
$2 = 3
$3 = 18
$4 = 0x80205000
$5 = 0x1ff
$6 = 0x80205ff8
$7 = 0x200000cf
ROOT_PA=0x80205000 LEVELS=3 PTSHIFT=18 INDEX=511 PTE_ADDR=0x80205ff8 PTE=0x200000cf
256	        if (!(pte & PTE_V)) {
$8 = 0x80000
Temporary breakpoint 4 at 0x55555591ae1a: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c, line 334.

Thread 3 "qemu-system-ris" hit Temporary breakpoint 4, get_physical_address (env=0x5555564e3960, physical=0x7ffff4ffd280, prot=0x7ffff4ffd274, addr=18446744072637915712, access_type=0, mmu_idx=1) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:334
334	            *physical = (ppn | (vpn & ((1L << ptshift) - 1))) << PGSHIFT;
337	            if ((pte & PTE_R) || ((pte & PTE_X) && mxr)) {
$9 = 0x80202000
$10 = 0x80202240
PHYSICAL_PAGE=0x80202000 FINAL_PA=0x80202240
0x000055555591b398 in riscv_cpu_tlb_fill (cs=0x5555564daf50, address=18446744072637915712, size=4, access_type=MMU_DATA_LOAD, mmu_idx=1, probe=false, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:451
451	    ret = get_physical_address(env, &pa, &prot, address, access_type, mmu_idx);
Value returned is $11 = 0
453	    if (mode == PRV_M && access_type != MMU_INST_FETCH) {

=== TRANSLATION RETURN ===
$12 = 0
$13 = 0x80202000
Temporary breakpoint 5 at 0x5555558607ed: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c, line 847.

Thread 3 "qemu-system-ris" hit Temporary breakpoint 5, tlb_set_page (cpu=0x5555564daf50, vaddr=18446744072637915136, paddr=2149588992, prot=7, mmu_idx=1, size=4096) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:847
847	    tlb_set_page_with_attrs(cpu, vaddr, paddr, MEMTXATTRS_UNSPECIFIED,

=== SOFTWARE TLB FILL ===
cpu = 0x5555564daf50
vaddr = 18446744072637915136
paddr = 2149588992
prot = 7
mmu_idx = 1
size = 4096
riscv_cpu_tlb_fill (cs=0x5555564daf50, address=18446744072637915712, size=4, access_type=MMU_DATA_LOAD, mmu_idx=1, probe=false, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:474
474	        return true;
$14 = 0x2
$15 = {
  {
    {
      addr_read = 0xffffffffc0202000,
      addr_write = 0xffffffffc0202000,
      addr_code = 0xffffffffc0202000,
      addend = 0x80001fe00000
    },
    dummy = {0x0, 0x20, 0x20, 0xc0, 0xff, 0xff, 0xff, 0xff...}
  }
}
$16 = 1
Hardware read watchpoint 6: -location $saved_entry->addr_read

Thread 3 "qemu-system-ris" hit Hardware read watchpoint 6: -location $saved_entry->addr_read

Value = 18446744072637915136
0x0000555555862eb9 in load_helper (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478, size=4, big_endian=false, code_read=false, full_load=0x555555862c19 <full_le_ldul_mmu>) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1279
1279	        tlb_addr = code_read ? entry->addr_code : entry->addr_read;

=== POST-FILL TAG RELOAD IN C SLOW PATH ===
#0  0x0000555555862eb9 in load_helper (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478, size=4, big_endian=false, code_read=false, full_load=0x555555862c19 <full_le_ldul_mmu>) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1279
#1  full_le_ldul_mmu (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1423
#2  0x0000555555863312 in helper_le_ldul_mmu (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1430
#3  0x00007ffff5009e8c in code_gen_buffer ()

Thread 3 "qemu-system-ris" hit Hardware read watchpoint 6: -location $saved_entry->addr_read

Value = 18446744072637915136
0x00007ffff5009e3e in code_gen_buffer ()

=== EXECUTED GENERATED TCG TLB HIT ===
#0  0x00007ffff5009e3e in code_gen_buffer ()
#1  0x00005555558854f0 in cpu_tb_exec (cpu=0x5555564daf50, itb=0x7ffff5009d40 <code_gen_buffer+44307>) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cpu-exec.c:173
#2  0x0000555555886327 in cpu_loop_exec_tb (cpu=0x5555564daf50, tb=0x7ffff5009d40 <code_gen_buffer+44307>, last_tb=0x7ffff4ffd998, tb_exit=0x7ffff4ffd990) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cpu-exec.c:621
#3  0x0000555555886650 in cpu_exec (cpu=0x5555564daf50) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cpu-exec.c:732
=> 0x7ffff5009e3e <code_gen_buffer+44561>:	mov    %rbx,%rsi
   0x7ffff5009e41 <code_gen_buffer+44564>:	jne    0x7ffff5009e77 <code_gen_buffer+44618>
   0x7ffff5009e47 <code_gen_buffer+44570>:	add    0x18(%rdi),%rsi
   0x7ffff5009e4b <code_gen_buffer+44574>:	movslq (%rsi),%rbx
   0x7ffff5009e4e <code_gen_buffer+44577>:	add    %r12,%rbx
   0x7ffff5009e51 <code_gen_buffer+44580>:	mov    %rbx,0x68(%rbp)
   0x7ffff5009e55 <code_gen_buffer+44584>:	and    $0xfffffffffffffffe,%rbx
   0x7ffff5009e59 <code_gen_buffer+44588>:	mov    %rbx,0x200(%rbp)
$17 = 0x246
$18 = 1
0x00007ffff5009e41 in code_gen_buffer ()
=> 0x7ffff5009e41 <code_gen_buffer+44564>:	jne    0x7ffff5009e77 <code_gen_buffer+44618>

=== SV39 CAPTURE COMPLETE ===
[Inferior 1 (process 455) killed]
```

### A.14 Bare 模式调试

原始记录：`debug/host-bare.log`；SHA-256：`54ef04b4b3562725986d1371d8efe5e81142f4a8432b66312feeeb1e898bec42`。

```text
Breakpoint 1 at 0x3c6686: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c, line 158.
[Thread debugging using libthread_db enabled]
Using host libthread_db library "/usr/lib/x86_64-linux-gnu/libthread_db.so.1".
[New Thread 0x7ffff77ff6c0 (LWP 475)]
[New Thread 0x7ffff4ffe6c0 (LWP 476)]

OpenSBI v0.4 (Jul  2 2019 11:53:53)
   ____                    _____ ____ _____
  / __ \                  / ____|  _ \_   _|
 | |  | |_ __   ___ _ __ | (___ | |_) || |
 | |  | | '_ \ / _ \ '_ \ \___ \|  _ < | |
 | |__| | |_) |  __/ | | |____) | |_) || |_
  \____/| .__/ \___|_| |_|_____/|____/_____|
        | |
        |_|

Platform Name          : QEMU Virt Machine
Platform HART Features : RV64ACDFIMSU
Platform Max HARTs     : 8
Current Hart           : 0
Firmware Base          : 0x80000000
Firmware Size          : 112 KB
Runtime SBI Version    : 0.1

PMP0: 0x0000000080000000-0x000000008001ffff (A)
PMP1: 0x0000000000000000-0xffffffffffffffff (A,R,W,X)
[Switching to Thread 0x7ffff4ffe6c0 (LWP 476)]

Thread 3 "qemu-system-ris" hit Breakpoint 1, get_physical_address (env=0x5555564e3920, physical=0x7ffff4ffd730, prot=0x7ffff4ffd724, addr=2149580800, access_type=2, mmu_idx=1) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:158
158	{

=== REAL S-MODE BARE ACCESS ===
#0  get_physical_address (env=0x5555564e3920, physical=0x7ffff4ffd730, prot=0x7ffff4ffd724, addr=2149580800, access_type=2, mmu_idx=1) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:158
#1  0x000055555591b398 in riscv_cpu_tlb_fill (cs=0x5555564daf10, address=2149580800, size=0, access_type=MMU_INST_FETCH, mmu_idx=1, probe=false, retaddr=0) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:451
#2  0x00005555558608f8 in tlb_fill (cpu=0x5555564daf10, addr=2149580800, size=0, access_type=MMU_INST_FETCH, mmu_idx=1, retaddr=0) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:878
#3  0x0000555555860f9f in get_page_addr_code (env=0x5555564e3920, addr=2149580800) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1032
#4  0x0000555555885a40 in tb_htable_lookup (cpu=0x5555564daf10, pc=2149580800, cs_base=0, flags=24577, cf_mask=4278714368) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cpu-exec.c:339
#5  0x0000555555884f8d in tb_lookup__cpu_state (cpu=0x5555564daf10, pc=0x7ffff4ffd938, cs_base=0x7ffff4ffd930, flags=0x7ffff4ffd92c, cf_mask=4278714368) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/include/exec/tb-lookup.h:43
#6  0x0000555555885d0a in tb_find (cpu=0x5555564daf10, last_tb=0x0, tb_exit=0, cf_mask=524288) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cpu-exec.c:406
#7  0x0000555555886634 in cpu_exec (cpu=0x5555564daf10) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cpu-exec.c:731
env = 0x5555564e3920
physical = 0x7ffff4ffd730
prot = 0x7ffff4ffd724
addr = 2149580800
access_type = 2
mmu_idx = 1
$1 = 0x0
0x000055555591b398 in riscv_cpu_tlb_fill (cs=0x5555564daf10, address=2149580800, size=0, access_type=MMU_INST_FETCH, mmu_idx=1, probe=false, retaddr=0) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:451
451	    ret = get_physical_address(env, &pa, &prot, address, access_type, mmu_idx);
Value returned is $2 = 0
453	    if (mode == PRV_M && access_type != MMU_INST_FETCH) {
$3 = 0x80200000
$4 = 0
Temporary breakpoint 2 at 0x5555558607ed: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c, line 847.

Thread 3 "qemu-system-ris" hit Temporary breakpoint 2, tlb_set_page (cpu=0x5555564daf10, vaddr=2149580800, paddr=2149580800, prot=7, mmu_idx=1, size=4096) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:847
847	    tlb_set_page_with_attrs(cpu, vaddr, paddr, MEMTXATTRS_UNSPECIFIED,

=== BARE ALSO FILLS QEMU SOFTWARE TLB ===
cpu = 0x5555564daf10
vaddr = 2149580800
paddr = 2149580800
prot = 7
mmu_idx = 1
size = 4096

=== BARE CAPTURE COMPLETE ===
[Inferior 1 (process 472) killed]
```

### A.15 首次调试的兼容性错误

原始记录：`debug-attempt1/guest.log`；SHA-256：`550c1bcce730649e0deb1b4e3d2efc13613c5157b01f6c1653aa8dd10c754f1d`。

```text
/mnt/d/软件基础/Lab2_2511057_祝安毅/report/logs/debug/guest.gdb:5: Error in sourced command file:
No symbol table is loaded.  Use the "file" command.
```

### A.16 修正前的采集记录

原始记录：`debug-attempt2/host-sv39.log`；SHA-256：`6c38c4717e23efdd5e67080114cf7d0420970bee379bb67666db1357481c2be8`。

```text
Breakpoint 1 at 0x3c72d4: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c, line 438.
[Thread debugging using libthread_db enabled]
Using host libthread_db library "/usr/lib/x86_64-linux-gnu/libthread_db.so.1".
[New Thread 0x7ffff77ff6c0 (LWP 454)]
[New Thread 0x7ffff4ffe6c0 (LWP 455)]

OpenSBI v0.4 (Jul  2 2019 11:53:53)
   ____                    _____ ____ _____
  / __ \                  / ____|  _ \_   _|
 | |  | |_ __   ___ _ __ | (___ | |_) || |
 | |  | | '_ \ / _ \ '_ \ \___ \|  _ < | |
 | |__| | |_) |  __/ | | |____) | |_) || |_
  \____/| .__/ \___|_| |_|_____/|____/_____|
        | |
        |_|

Platform Name          : QEMU Virt Machine
Platform HART Features : RV64ACDFIMSU
Platform Max HARTs     : 8
Current Hart           : 0
Firmware Base          : 0x80000000
Firmware Size          : 112 KB
Runtime SBI Version    : 0.1

PMP0: 0x0000000080000000-0x000000008001ffff (A)
PMP1: 0x0000000000000000-0xffffffffffffffff (A,R,W,X)
DTB Init
HartID: [Switching to Thread 0x7ffff4ffe6c0 (LWP 455)]

Thread 3 "qemu-system-ris" hit Breakpoint 1, riscv_cpu_tlb_fill (cs=0x5555564daf50, address=18446744072637915712, size=4, access_type=MMU_DATA_LOAD, mmu_idx=1, probe=false, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:438
438	{
Temporary breakpoint 2 at 0x55555591a686: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c, line 158.

Thread 3 "qemu-system-ris" hit Temporary breakpoint 2, get_physical_address (env=0x5555564e3960, physical=0x7ffff4ffd280, prot=0x7ffff4ffd274, addr=18446744072637915712, access_type=0, mmu_idx=1) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:158
158	{

=== REAL SV39 DATA LOAD ===
#0  get_physical_address (env=0x5555564e3960, physical=0x7ffff4ffd280, prot=0x7ffff4ffd274, addr=18446744072637915712, access_type=0, mmu_idx=1) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:158
#1  0x000055555591b398 in riscv_cpu_tlb_fill (cs=0x5555564daf50, address=18446744072637915712, size=4, access_type=MMU_DATA_LOAD, mmu_idx=1, probe=false, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:451
#2  0x00005555558608f8 in tlb_fill (cpu=0x5555564daf50, addr=18446744072637915712, size=4, access_type=MMU_DATA_LOAD, mmu_idx=1, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:878
#3  0x0000555555862e59 in load_helper (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478, size=4, big_endian=false, code_read=false, full_load=0x555555862c19 <full_le_ldul_mmu>) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1274
#4  full_le_ldul_mmu (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1423
#5  0x0000555555863312 in helper_le_ldul_mmu (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1430
#6  0x00007ffff5009e8c in code_gen_buffer ()
#7  0x00005555558854f0 in cpu_tb_exec (cpu=0x5555564daf50, itb=0x7ffff5009d40 <code_gen_buffer+44307>) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cpu-exec.c:173
env = 0x5555564e3960
physical = 0x7ffff4ffd280
prot = 0x7ffff4ffd274
addr = 18446744072637915712
access_type = 0
mmu_idx = 1
$1 = 0x8000000000080205
VA=0xffffffffc0202240 SATP=0x8000000000080205 ACCESS=0 MMU=1
Temporary breakpoint 3 at 0x55555591abc7: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c, line 254.

Thread 3 "qemu-system-ris" hit Temporary breakpoint 3, get_physical_address (env=0x5555564e3960, physical=0x7ffff4ffd280, prot=0x7ffff4ffd274, addr=18446744072637915712, access_type=0, mmu_idx=1) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:254
254	        target_ulong ppn = pte >> PTE_PPN_SHIFT;

=== PAGE TABLE WALK ===
$2 = 3
$3 = 18
$4 = 0x80205000
$5 = 0x1ff
$6 = 0x80205ff8
$7 = 0x200000cf
ROOT_PA=0x80205000 LEVELS=3 PTSHIFT=18 INDEX=511 PTE_ADDR=0x80205ff8 PTE=0x200000cf
256	        if (!(pte & PTE_V)) {
$8 = 0x80000
Temporary breakpoint 4 at 0x55555591ae1a: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c, line 334.

Thread 3 "qemu-system-ris" hit Temporary breakpoint 4, get_physical_address (env=0x5555564e3960, physical=0x7ffff4ffd280, prot=0x7ffff4ffd274, addr=18446744072637915712, access_type=0, mmu_idx=1) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:334
334	            *physical = (ppn | (vpn & ((1L << ptshift) - 1))) << PGSHIFT;
337	            if ((pte & PTE_R) || ((pte & PTE_X) && mxr)) {
$9 = 0x80202000
$10 = 0x80202240
PHYSICAL_PAGE=0x80202000 FINAL_PA=0x80202240
0x000055555591b398 in riscv_cpu_tlb_fill (cs=0x5555564daf50, address=18446744072637915712, size=4, access_type=MMU_DATA_LOAD, mmu_idx=1, probe=false, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:451
451	    ret = get_physical_address(env, &pa, &prot, address, access_type, mmu_idx);
Value returned is $11 = 0

=== TRANSLATION RETURN ===
$12 = 1
$13 = 0x80202000
Temporary breakpoint 5 at 0x5555558607ed: file /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c, line 847.

Thread 3 "qemu-system-ris" hit Temporary breakpoint 5, tlb_set_page (cpu=0x5555564daf50, vaddr=18446744072637915136, paddr=2149588992, prot=7, mmu_idx=1, size=4096) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:847
847	    tlb_set_page_with_attrs(cpu, vaddr, paddr, MEMTXATTRS_UNSPECIFIED,

=== SOFTWARE TLB FILL ===
cpu = 0x5555564daf50
vaddr = 18446744072637915136
paddr = 2149588992
prot = 7
mmu_idx = 1
size = 4096
riscv_cpu_tlb_fill (cs=0x5555564daf50, address=18446744072637915712, size=4, access_type=MMU_DATA_LOAD, mmu_idx=1, probe=false, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/target/riscv/cpu_helper.c:474
474	        return true;
$14 = 0x2
$15 = {
  {
    {
      addr_read = 0xffffffffc0202000,
      addr_write = 0xffffffffc0202000,
      addr_code = 0xffffffffc0202000,
      addend = 0x80001fe00000
    },
    dummy = {0x0, 0x20, 0x20, 0xc0, 0xff, 0xff, 0xff, 0xff...}
  }
}
$16 = 1
Hardware read watchpoint 6: -location $saved_entry->addr_read

Thread 3 "qemu-system-ris" hit Hardware read watchpoint 6: -location $saved_entry->addr_read

Value = 18446744072637915136
0x0000555555862eb9 in load_helper (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478, size=4, big_endian=false, code_read=false, full_load=0x555555862c19 <full_le_ldul_mmu>) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1279
1279	        tlb_addr = code_read ? entry->addr_code : entry->addr_read;

=== EXECUTED TCG TLB TAG READ ===
#0  0x0000555555862eb9 in load_helper (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478, size=4, big_endian=false, code_read=false, full_load=0x555555862c19 <full_le_ldul_mmu>) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1279
#1  full_le_ldul_mmu (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1423
#2  0x0000555555863312 in helper_le_ldul_mmu (env=0x5555564e3960, addr=18446744072637915712, oi=97, retaddr=140737303846478) at /mnt/d/软件基础/Lab2验证工具_20261022/qemu-4.1.1/accel/tcg/cputlb.c:1430
#3  0x00007ffff5009e8c in code_gen_buffer ()
=> 0x555555862eb9 <full_le_ldul_mmu+672>:	mov    %rax,-0x50(%rbp)
   0x555555862ebd <full_le_ldul_mmu+676>:	mov    -0x50(%rbp),%rax
   0x555555862ec1 <full_le_ldul_mmu+680>:	and    $0xfff,%eax
   0x555555862ec6 <full_le_ldul_mmu+685>:	test   %rax,%rax
   0x555555862ec9 <full_le_ldul_mmu+688>:	setne  %al
   0x555555862ecc <full_le_ldul_mmu+691>:	movzbl %al,%eax
   0x555555862ecf <full_le_ldul_mmu+694>:	test   %rax,%rax
   0x555555862ed2 <full_le_ldul_mmu+697>:	je     0x55555586305a <full_le_ldul_mmu+1089>
$17 = 0x246
$18 = 1
1283	    if (unlikely(tlb_addr & ~TARGET_PAGE_MASK)) {
=> 0x555555862ebd <full_le_ldul_mmu+676>:	mov    -0x50(%rbp),%rax

=== SV39 CAPTURE COMPLETE ===
[Inferior 1 (process 451) killed]
```
