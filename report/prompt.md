# Lab2 提示词汇总

成员：2511565 闻鹏杰、2511057 祝安毅、2511955 洪亮。整理日期：2026-10-22。

## 记录范围与来源

本轮以闻鹏杰完成的前期 Lab2 代码为起点，进行复核、修正、测试加固、真实目标验证和报告整理。下列本轮规格在修改代码前保存，并据此执行。闻鹏杰阶段的提示词原文汇总在本文附录中；它们描述此前真实开发阶段，不改写为本轮重新生成的历史。

## 0. 后续复核轮次的原始任务摘要

按照工作区的实验报告模板以及本次 Lab2 的内容完成作业。检查组内已有实验二代码，不能假定其正确；按实际问题修改并验证。输出源代码和 Markdown 报告，目录为 code、report；report 中包含 report.md、prompt.md 和 images 测试结果截图。报告使用 2511057 祝安毅、2511955 洪亮。用户负责把文件交给组员提交，本轮只生成文件。

> 该段保留后续复核轮次收到的原始要求，因此当时仅列两名成员。最终交付经贡献核对后补入 2511565 闻鹏杰；其前期提示词和初版实现记录见本文附录。

## 1. page_init 复核与 First-Fit 分析

```text
[PROMPT]
复核 kern/mm/pmm.c 的 page_init 与原框架地址转换契约，阅读 default_pmm.c 解释 First-Fit；修复确证问题，保留正确实现，不修改课程测试和设备树解析器。
[RELY]
get_memory_base/get_memory_size、end、Page、nbase/npage/pages/va_pa_offset、memlayout.h、pmm.h、mmu.h、原始 test_lab2.c。
[GUARANTEE]
page_init(void) 必须建立描述符布局并仅注册合法完整空闲页；解释 default_init/init_memmap/alloc_pages/free_pages 的职责。
[SPECIFICATION]
设备树基址和大小无效、加法溢出、内核或描述符放不下时在写入描述符前失败。物理管理上界同时受设备树、框架上界和映射范围约束。描述符覆盖 [nbase,npage)，内核、固件、描述符及对齐间隙保持保留。没有完整空闲页时不调用 init_memmap。宿主边界用例与真实 QEMU 启动分别验证，不把二者混同。
```

## 2. Best-Fit 实现复核与优化

```text
[PROMPT]
检查 Best-Fit 的地址有序空闲链表、最小合适块选择、拆分和双向合并；在语义不变的前提下优化精确匹配搜索。
[RELY]
struct pmm_manager、default_pmm.c、best_fit_pmm.c；free_area 为兼容原测试的唯一状态根。
[GUARANTEE]
完整 best_fit_pmm_manager；初始化、注册、分配、释放、统计接口；默认管理器选 Best-Fit。
[SPECIFICATION]
申请 n 页返回至少 n 个连续页，此实现恰好返回 n 页；选择最小足够块，同长取低地址。找到 property==n 的候选即可提前退出。释放正确恢复计数并合并物理相邻块。不得修改 basic_check/best_fit_check 或任何课程保护文件，必须通过原保护哈希、宿主检查、目标检查与官方评分。
```

## 3. Buddy 实现规格（继承实现的复核依据）

```text
[PROMPT]
以既有 ucore 页管理接口复核 Buddy 模块，重点检查不规则注册区间、非伙伴相邻块、拆分、递归合并及原请求长度约定；不为追求改动量重写已正确的核心。
[RELY]
pmm_manager、Page/list 接口、buddy_context、每阶空闲链表、现有固定128MiB管理上界。
[GUARANTEE]
buddy_pmm_manager 及 init/register/alloc/free/nr_free 接口。
[SPECIFICATION]
将请求向上取整为2的幂；每个注册区间独立合并域，不跨洞和域合并。伙伴索引 XOR 2^order，必须同域、同阶且空闲。申请3页占用4页、free仍传原请求3；计数按实际块大小变化。元数据位于内核保留区。零请求和超大请求失败，失败不改状态。保持默认单核串行约定。
```

## 4. Buddy 独立测试与修正提示词

```text
[PROMPT]
独立于分配器的选择逻辑加强 buddy_check.c，修复LCG低位及分支抽样造成的固定申请/释放节奏，补复杂释放顺序后的大块恢复证据。
[RELY]
公共分配接口与隔离 buddy_context；可用固定数组追踪所有权和数据模式，不能改变分配器使测试通过。
[GUARANTEE]
多固定种子随机测试、隔离64页打乱释放合并测试、真实内存耗尽及恢复测试。
[SPECIFICATION]
使用非零种子的xorshift32；每步独立抽取槽位和请求，不因分支额外消耗随机序列。逐步检查活动块内容、区间不重叠、对齐、保留页及计数变化。随机回收和耗尽回收后都重新申请测试前能够分配的大块，不仅断言页数。打印实际种子和申请/释放计数，保留可复现性。不得修改任何原Best-Fit/官方测试。
```

## 5. SLUB 实现与性能改进提示词

```text
[PROMPT]
复核并优化简化SLUB的小对象及大对象分配，用每slab分配位图替换kfree的空槽链表线性重复释放诊断，维持原接口和两种页后端兼容性。
[RELY]
kmalloc/kfree、alloc_pages/free_pages、partial链表；16至2048字节八类，较大对象走连续页。
[GUARANTEE]
slub_init、kmalloc、kfree；小对象位图和空闲链表状态一致；公开头文件记录调用契约。
[SPECIFICATION]
返回至少16字节对齐；0请求返回NULL、kfree(NULL)无操作、不承诺清零、调用须单核串行。位图按槽索引置位/清位，重复释放在仍存活的slab上断言失败。头部增大后重新计算对象容量，不硬编码旧容量。满页释放首个对象重新入partial，空slab立即归还。大对象记录原页请求，free传原值以兼容Buddy取整。合法调用不得泄漏、越界或重叠；无效任意指针不在支持契约内。
```

## 6. SLUB 独立测试提示词

```text
[PROMPT]
扩展SLUB的独立测试，对全部八类验证满/部分/空状态转换，并增加页后端耗尽但现有slab有槽时仍能分配的测试。
[RELY]
仅依赖kmalloc/kfree与页计数，不复制分配器内部容量和选择算法；静态测试数组属于内核映像。
[GUARANTEE]
边界、对齐、内容、非重叠、多类别复用、随机混合、大对象、耗尽及恢复检查，分别在Best-Fit/Buddy后端运行。
[SPECIFICATION]
600个同类对象写满请求区，交错释放并重分配后检查内容与占用页恢复；2048类每页可能只有1槽，允许其空页返还再申请，不能错误要求每类释放后都保留同样的partial页。耗尽物理页后从已存在的32字节slab分配，必须成功且不新占页。清理后恢复基线，申请失败不能泄漏。
```

## 7. 构建和验证提示词

```text
[PROMPT]
复核配置切换、测试保护、宿主与目标矩阵。把配置戳放到最终编译参数确定之后，默认构建保留Best-Fit，日志输出到report/logs。
[RELY]
原Makefile、官方grade/inject、交叉GCC10.2、QEMU4.1.1、现有宿主ASan/UBSan脚本。
[GUARANTEE]
默认官方20分检查、四配置目标运行、不clean切换配置验证、15个page_init边界用例和12项保护检查。
[SPECIFICATION]
不篡改官方测试。缺工具/超时/缺成功标记即失败。每次记录实际命令、工具版本、退出码和原始输出。截图展示真实日志，注明其来源，不将模拟/推导当运行证据。不要提交bin/obj、临时评分副本和QEMU构建目录。
```

## 8. 页表、TLB真实调试提示词

```text
[PROMPT]
使用带调试信息的QEMU4.1.1及适合x86_64宿主的GDB，真实跟踪RISC-V ucore的地址翻译、页表叶子与软件TLB，补齐原先只有教程的分支任务。
[RELY]
entry.S的Sv39根叶子映射、kernel符号、QEMU target/riscv/cpu_helper.c和accel/tcg/cputlb.c、TCG快速路径；已有跨架构GDB只能调RISC-V，不能冒充宿主GDB。
[GUARANTEE]
保存宿主断点调用栈、真实VA/SATP/PTE/PA与关键分支，区分程序实际访存与调试器读内存；记录Bare对比和TLB填充/命中相关证据。
[SPECIFICATION]
调试工具在独立目录构建/解包，不覆盖可用QEMU。先核对符号和函数，再设置有针对性的断点。根层1GiB叶子可能一步结束，不能编造三级遍历。QEMU软件TLB含客体物理到宿主地址映射，Bare也可能经过它；TCG命中可直接在生成的宿主机器码里完成。实际观察、源码推导与算术核对分别标记。全部输出保存，遇到真实兼容问题记录解决过程。
```

## 9. 报告与打包提示词

```text
[PROMPT]
遵循工作区实验报告模板的章节顺序完成report.md，汇总上述prompt，加入实际验证截图和原始日志，输出可交给组员提交的code/report文件包。
[RELY]
实验报告模板.md、课堂Lab2纪要、2026指导书、实际代码和本轮日志；成员为2511057祝安毅、2511955洪亮。
[GUARANTEE]
report/report.md、report/prompt.md、report/images、可复现code，根目录仅code和report。
[SPECIFICATION]
按练习顺序写目的、环境、整体逻辑、核心函数、规格、实际迭代、思考题、Challenge、调试、验证和理论联系。真实区分继承成果与本轮修改，不伪造旧prompt/未出现的bug/成员独立完成记录。不填写未知模型版本和未经确认的个人明细。截图来自本轮真实运行日志的展示页面，并保留原始文本对应。用户自行提交，不创建或推送远端仓库。
```

## 10. 闻鹏杰前期提示词索引

闻鹏杰初版代码阶段的完整提示词已逐份收录在本文附录中，包含 master、page_init、first_fit、best_fit_impl、buddy_impl、buddy_test、slub_impl、slub_test 和 EXECUTION。它们与后续复核/修改提示词共同覆盖本实验的实现与测试过程；报告按实际采用的阶段引用，不虚构重新生成次数。


## 11. 本轮调试反馈后的追加约束

1. 目标 GDB 10.1 不支持宿主 GDB 17.1 的 `set debuginfod enabled off`。移除公共配置中的新版本专有命令，使用环境变量约束宿主联网符号服务，保留首次失败日志。
2. 在 GDB 中 `finish` 刚返回时，调用者源行上的赋值可能尚未执行。需再 `next` 后读取 `ret`，同时保留转换函数的真实返回值。
3. TLB 填充后的 C 慢路径会再次读取标签；这不是后续生成代码快速命中的证据。观察点继续执行到 `code_gen_buffer` 中触发，记录真实宿主指令、标签和标志位，明确区分观察与条件分支语义推导。
4. 图像使用浏览器对真实日志展示页截图，保留原文本与哈希；不拼造交互式终端界面。报告中据实注明截图方式。

## 附录：收到的代码包内历史提示词原文

以下保留收到内容；其日期、旧署名与历史验证范围属于原包记录，不代表本轮重新执行的结果。

### 历史文件：best_fit_impl.md

`````markdown
[PROMPT]
任务：参考当前 First-Fit 实现，在 kern/mm/best_fit_pmm.c 中从零补全 Best-Fit 连续物理页管理模块，并在 pmm.c 的 init_pmm_manager() 中将默认管理器切换为 best_fit_pmm_manager。学号2511565。

操作要求：
1. 先阅读真实代码，再修改可访问的实际工程文件，不只给代码片段。
2. 在 lab2 function2-2 标记位置实现，保留 lab2 注释，将对应 YOUR CODE 替换为2511565。
3. 允许修改 best_fit_pmm.c、为接口一致性必要的 best_fit_pmm.h，以及 pmm.c 中管理器声明/选择所需的最小位置。保留已实现的 page_init；不改 First-Fit、设备树解析、官方测试和评分脚本。
4. basic_check() 和 best_fit_check() 的函数内容必须保持原样。不得删除、跳过或弱化断言。
5. 若只访问附件副本，明确它不是我电脑的 WSL 目录，提供补丁和同步方法。不要覆盖我未授权修改的文件，不自动提交 Git。

输出要求：说明修改文件、算法和关键状态变化；列出实际执行的验证、结果、未执行项目和阻碍；给出可核对的报告段落及改进思考。需要我本机执行时，每次只给一组命令，标明终端、目录、作用、预期结果和失败时应反馈的输出。

[RELY]
先阅读：kern/mm/default_pmm.c、best_fit_pmm.c、best_fit_pmm.h、pmm.h、pmm.c、memlayout.h、libs/list.h、defs.h、Makefile、tools/test_lab2.c、inject.py、grade.sh。

可信依赖以实际文件为准：
- struct pmm_manager 的 init、init_memmap、alloc_pages、free_pages、nr_free_pages、check 接口。
- struct Page 的 flags、property、ref、page_link；free_area_t 和相关页状态/引用计数宏。
- alloc_pages、free_pages 等包装函数由框架提供，不是本次需要重新实现的模块。

特别核对原测试约定：
- 两个现有测试直接读写 free_list 和 nr_free，并保存、清空、恢复它们；实现必须提供兼容的可赋值状态。
- 测试可能在链表已清空、nr_free 尚未清零的临时状态调用 alloc_pages；空链表必须安全返回 NULL。
- 测试会拆分释放、分批重新分配，再统一释放连续页面，不能要求每次释放长度必须等于某一次原始分配长度。
- 存在请求1页时必须选择1页空闲块、而不是前面的2页块的测试。

[GUARANTEE]
实现并注册下列接口（内部函数可用 static）：
static void best_fit_init(void);
static void best_fit_init_memmap(struct Page *base, size_t n);
static struct Page *best_fit_alloc_pages(size_t n);
static void best_fit_free_pages(struct Page *base, size_t n);
static size_t best_fit_nr_free_pages(void);
const struct pmm_manager best_fit_pmm_manager;

已有 static void best_fit_check(void) 作为 check 回调；若注册结构位于测试函数之前，添加必要的前置声明，不重复定义测试。
保留 basic_check 和 best_fit_check，不把它们当成待实现函数。

[SPECIFICATION]
1. best_fit_init
Pre-Condition：启动阶段，尚无该管理器的活动分配。
Post-Condition：空闲链表为空，nr_free为0，状态可供 init_memmap 注册区域。

2. best_fit_init_memmap
Pre-Condition：n>0；base起的n个描述符属于真实、连续、尚未注册且被标记保留的可用物理页。
Post-Condition：各页引用计数/标志按框架初始化；形成合法空闲块，块头记录长度并入链；nr_free增加n；不把内核或描述符占用页变为空闲。

3. best_fit_alloc_pages
Pre-Condition：n>0，遵循原框架对非法零请求的处理约定。
Post-Condition：成功返回至少满足请求且本次按n页划出的连续页区间首描述符；从所有足够大的空闲块中选择长度最小者，nr_free恰好减少n。失败返回NULL，不破坏状态。
Case A 精确匹配：移除整个空闲块。
Case B 需要拆分：返回前n页，剩余页面形成正确空闲块。
Case C 多个候选：必须比较大小；相同大小时选较低物理地址作为本实现的确定性约定。
Case D 无合适连续块、总页数不足或空链表：返回NULL，不能将总空闲页足够误判为存在连续区间。

4. best_fit_free_pages
Pre-Condition：n>0；传入区间内所有页均为本管理器管理的有效已分配页。允许释放原分配的一部分，也允许合并释放多个相邻已分配区间。
Post-Condition：nr_free增加n，区间重新成为空闲页；与相邻物理空闲块合并，不留下重复节点；消失的块头不再保留有效 PageProperty 标记。
Case A 无邻块；Case B 仅前邻；Case C 仅后邻；Case D 前后同时相邻：均需正确维护链表、块长和页标志。

5. best_fit_nr_free_pages 与注册
Post-Condition：返回空闲物理页总数，而非块数；注册结构各回调类型正确，check指向原 best_fit_check；默认启动选择Best-Fit。

Requirements：
- 优先使用按地址排序的空闲块链表配合完整搜索，便于合并并兼容测试；如采用其他结构，必须证明测试保存/恢复 free_list、nr_free 时不会遗留隐藏状态。
- 不要求优化复杂度，不通过硬编码测试请求大小或地址通过测试。
- 保留所有既有测试和任务一实现。若 page_init 仍缺失，明确报告依赖阻碍，不能删除测试绕过。
- 比较修改前后官方测试内容，确认未被修改。
- 实际运行当前工程支持的构建、QEMU检查及评分流程；没有目标工具链时只报告已做的静态/宿主验证，不能声称内核运行通过。
- 核对 tools/inject.py 的评分注入机制；不能提前加入会导致注入冲突的官方测试代码。官方默认验收保持Best-Fit。
- 对开关或编译宏变化进行干净重编译，避免旧目标文件造成假象。
- 在报告中说明：Best-Fit可通过大小索引等方式降低查找成本，但可能产生很小的剩余块；不保证所有负载下都优于First-Fit。区分算法语义和具体实现优化。
`````

### 历史文件：buddy_impl.md

`````markdown
[PROMPT]
任务：参考当前 ucore 页管理框架，从零实现 Buddy System 物理页分配模块并接入内核。没有现成的Buddy骨架。本次完成实现及最小运行检查，完整独立测试由下一份提示词完成。学号2511565。

操作要求：
1. 先读取工程并确认Best-Fit基础版本状态，再修改实际文件。
2. 新增 kern/mm/buddy_pmm.c、buddy_pmm.h；仅在pmm.c增加管理器选择和必要声明，在Makefile增加确有必要的构建开关。其他文件如确需修改，先说明具体依赖，避免扩大范围。
3. 默认仍选择Best-Fit；用显式编译开关 LAB2_PMM_BUDDY 选择Buddy，启动时打印实际管理器名称。切换必须退出QEMU并重新构建启动，禁止有活动分配时切换全局管理器。
4. 保留page_init、First-Fit、Best-Fit原测试和评分代码；不把Best-Fit的专属测试强行用于Buddy。
5. 只访问附件时说明副本位置及补丁同步方式，不声称已改动我的WSL文件。

输出要求：给出实现、设计说明、准确接口契约、最小真实验证和待测项。用申请3页的例子解释实际占用4页及释放方式。记录真实提示词和问题修复，不伪造QEMU成功日志。

[RELY]
首先阅读 pmm.h、pmm.c、memlayout.h、default_pmm.c、best_fit_pmm.c、libs/list.h、defs.h、Makefile、tools/inject.py、grade.sh。
依赖现有pmm_manager回调、Page描述符、pages/npage/nbase、page2pa、pa2page、页标志和断言。KADDR在当前框架中被注释，不能直接调用。
page_init已负责排除OpenSBI、内核和描述符空间；传给init_memmap的起点和长度不保证是二次幂对齐的完整大块。
不修改struct Page布局，不假设操作系统已有malloc/kmalloc，不假设虚拟地址就是物理地址。
Buddy参考材料可辅助理解，但不得照搬与本工程接口不兼容的代码。

[GUARANTEE]
实现以下模块接口：
static void buddy_init(void);
static void buddy_init_memmap(struct Page *base, size_t n);
static struct Page *buddy_alloc_pages(size_t n);
static void buddy_free_pages(struct Page *base, size_t n);
static size_t buddy_nr_free_pages(void);
void buddy_check(void);
const struct pmm_manager buddy_pmm_manager;

buddy_check在本阶段提供可运行的最小检查，下一阶段扩展成独立测试；不能注册未定义函数，不能把空函数说成测试通过。最终只能有一个buddy_check定义。

[SPECIFICATION]
设计约定（本prompt选择，不冒充课程硬性要求）：
- 页数请求n向上取到最小的2^k，整个2^k页块归调用者独占。
- free_pages(base,n)传回原始请求n，释放整个对应块。例如申请3页占4页，释放时传3，空闲页数恢复4。
- 不支持对Buddy块进行部分释放；调用者必须传原块头及匹配的原请求大小。不得沿用Best-Fit的部分释放假设。

1. buddy_init
Pre-Condition：启动阶段，无活动分配。
Post-Condition：各阶空闲状态、分配元数据和计数正确初始化，不依赖尚未可用的动态分配器。

2. buddy_init_memmap
Pre-Condition：n>0，base起的n页真实有效、未注册、不重叠，均可交给本管理器。
Post-Condition：将整个区间分解为合法对齐的二次幂块，无遗漏、无重叠，不向区间外取整扩展。
说明采用的伙伴编号坐标系和管理域。多次注册时不能清空已有状态；禁止越过未注册洞、保留页或域边界合并。

3. buddy_alloc_pages
Pre-Condition：初始化完成。
Post-Condition：成功返回一个符合所属阶对齐规则的连续块；不足时逐级拆分大块，未分配半块回到正确阶；nr_free减少实际块页数2^k。
Case A n=0：返回NULL，状态不变。
Case B n非二次幂：向上取整，记录足够元数据供正确释放。
Case C 大小取整可能溢出、阶数超出范围或无足够连续块：返回NULL，状态不变。

4. buddy_free_pages
Pre-Condition：base是合法活动分配块头，n为该次分配的原始请求。
Post-Condition：释放实际占用页数；仅与同阶、空闲、同管理域且互为伙伴的块合并，递归到不能合并为止。nr_free增加实际释放页数，合并本身不再次增加计数。
解释“物理相邻”与“互为伙伴”的区别。非法释放不在正常API前置条件内；如额外提供诊断，说明支持的错误类型，并保证检查先于破坏状态。

5. buddy_nr_free_pages、注册与最小检查
Post-Condition：返回可分配物理页总量；元数据实际占用的页不能重复算为空闲。注册回调类型正确，启动选择逻辑可复现。
最小检查至少实际执行一次分配、释放及计数恢复，但明确它不代替下一阶段全面测试。

Requirements：
- 不假设初始空闲区长度为二次幂，不丢弃尾部小块。
- 给出伙伴地址计算公式、对齐原点、每阶链表和元数据含义；不能在物理页号与Page数组索引间混用坐标。
- 元数据用静态存储或明确预留的已知空间，不在自身初始化时递归调用自身分配。检查容量；不得把元数据占用区又分配出去。
- 对阶数移位、向上取整、计数与索引做边界检查。
- 不把PageProperty为0单独当作“已分配”的充分证明。
- 明确单核/调用串行化假设；不要声称未经实现的SMP安全。
- 不要求达到特定时空复杂度，首先保证契约一致和可验证。
- 当前评分注入器对kern/test有特殊处理：自编测试不要提前占用官方注入目录或改写其脚本。
- 分别列出默认Best-Fit构建和Buddy构建的方式，核对宏变更是否需要make clean。只运行已有条件支持的检查，未运行项如实说明。
`````

### 历史文件：buddy_test.md

`````markdown
[PROMPT]
任务：为当前工程已经实现的Buddy System设计并编写独立测试，检验实现是否满足接口约定，而不是根据它当前输出反推“正确答案”。学号2511565。

操作要求：
1. 先阅读Buddy实现、头文件、接口说明及集成位置；如果实现缺失，先指出缺失，不能假装已测试。
2. 新增 kern/mm/buddy_check.c（或经核实不会重复编译的等效位置），将buddy_check完整测试集中到一处，并删除或替换上一阶段同名最小检查，避免重复定义。
3. 保留官方测试和评分脚本，不改Best-Fit语义，不在kern/test中放自编测试。
4. 若测试发现实现缺陷，先记录最小复现、期望值和实际值，再对buddy_pmm.c进行必要修复；不得降低断言适应错误实现。

输出要求：交付实际测试代码、每个用例的目的、真实运行证据与未覆盖项；给出报告可用的“测试覆盖及有效性”说明，不虚构通过情况。

[RELY]
读取buddy_pmm.c/.h、pmm.h、pmm.c、memlayout.h、Makefile及上一阶段接口说明。
约定：申请n页实际占用最小的2^k>=n；释放传原请求n；n=0及不能表示的请求返回NULL；不支持部分释放。
依赖alloc_pages、free_pages、nr_free_pages、page2pa、页大小和有效地址转换；不能直接调用被注释的KADDR。
Tests应依据契约独立推导结果，不复制分配器内部搜索/伙伴合并函数作为判定器。

[GUARANTEE]
提供 void buddy_check(void) 并确保buddy_pmm_manager.check指向它。
测试辅助函数用static；仅为测试确有必要时增加条件编译下的只读状态检查接口，不能暴露任意修改生产状态的接口。

[SPECIFICATION]
Pre-Condition：Buddy已被显式选为启动管理器，page_init完成注册；测试运行期间无其他并发分配者。
Post-Condition：正常测试退出后，所有测试持有页均已释放，空闲页数恢复进入测试时的基线；测试不能重置或丢弃内核管理的真实空闲区。

必须覆盖：
1. 单页和多页：1、2、4等请求，检查连续性、对齐、计数和写入后内容。
2. 非二次幂：3、5等请求分别占4、8页；释放传3、5后对应计数恢复。
3. 拆分：用可控前置状态证明大块能够拆出所需小块；不能仅凭一次alloc成功就认定发生了拆分。
4. 伙伴合并：以地址确认真正伙伴，释放后检验更大块可重新获得；增加连续多阶合并用例。
5. 不能合并的相邻块：构造相邻但不满足伙伴关系的区间，验证不会错误形成更大块。
6. 不规则初始区间：非二次幂长度、非大块对齐起点；若实现支持多次注册，测试多段及有洞的注册，确认不跨洞合并、不遗漏尾页。
7. 边界与失败：n=0、超过最大阶/管理容量、向上取整溢出、无可用连续块；失败不得改变页数、已有分配或数据。
8. 耗尽与恢复：用有界方法分配到失败，再以不同次序释放，检查无重叠、无重复分配和页数恢复。
9. 固定随机种子的有界分配/释放序列：独立记录活动区间与数据模式，检查重叠、内容破坏和泄漏。

Requirements：
- 可用独立位图/区间记录检查实际分配页的归属；它不应调用Buddy内部判断函数来决定预期结果。
- 对需要精确布局的用例，采用隔离测试实例、合法独立测试区域或独立启动配置；说明隔离方式。不得在存在活动分配时重新init全局管理器，也不得用假的Page数组冒充真实物理页调用page2pa写内存。
- 如果无法安全构造某个用例，明确标为待测并给出可执行方案，不能以普通用例替代却宣称已覆盖。
- 如果测试到非法释放：只有实现明确承诺诊断时才检查；预期panic用例单独启动，不能让正常测试在中途panic后被当作全通过。
- 控制随机次数及耗尽测试的记录容量，避免内核栈溢出；较大跟踪数组用静态存储等明确方式分配，不能递归依赖正在测试的分配器。
- 不要求固定返回地址，除非该用例前置状态确实决定地址；按契约验证对齐、范围、归属和占用量。
- 每个PASS输出必须由实际断言支撑；宿主测试与真实RISC-V/QEMU测试分别报告。
- 完成后说明为何只有“分配后再释放、总数不变”不足以证明无重叠或合并正确。
`````

### 历史文件：EXECUTION.md

`````markdown
# 真实执行记录
2026-10-17：用户提交总任务授权后，在修改模块二源码之前从此前六份四段式提示词保存上述阶段文件，按总提示词及阶段约束执行。
page_init.md为本轮核实提示词，不追溯伪造上轮的使用记录。Buddy/SLUB的实现与测试分阶段执行，未使用独立AI代理；独立测试指契约和判定逻辑独立。

实际阶段设计补充：Buddy核心实例化供元数据隔离测试，正常页接口仍由pmm_manager封装；同一注册区间为合并域。SLUB小对象类别16～2048、头部对齐80字节，空slab立即归还。独立测试与实现分别落文件，允许测试读取私有核心接口，不触碰官方测试。
本轮 master.md 保存用户在会话中提交的总任务内容；用户提交发生在实现之前，文件整理发生在交付阶段。阶段提示词在源码修改之前保存。
宿主验证中的LSan因进程跟踪限制默认关闭，ASan/UBSan保留；这不是改变分配器功能契约。
`````

### 历史文件：first_fit.md

`````markdown
[PROMPT]
任务：作为我的操作系统实验老师，阅读当前工程的 First-Fit 实现，帮助我完成“理解 First-Fit 连续物理内存分配算法”的思考题。姓名闻鹏杰，学号2511565。

操作要求：
1. 先读取实际文件；本次只分析，不修改分配器或测试。
2. 按“一个小例子→真实代码→状态变化→改进思考”讲解。说明首个满足条件的空闲块为什么未必是最小的合适块。
3. 不重复环境安装，不凭空补充截图和运行结果。若文件不可读，索取所缺文件。

输出要求：先用简短例子说明算法，再逐函数解释，最后给出可供我核对和改写的报告草稿。不要虚构我的学习体会。最多提出两个理解问题，不用连续问答阻止我进入实现阶段。

[RELY]
首先阅读 kern/mm/default_pmm.c、pmm.h、memlayout.h、pmm.c 与 libs/list.h；指导书可读取时核对对应章节。
依赖实际的 struct Page、free_area_t、PageReserved、PageProperty、property、nr_free、链表操作及 pmm_manager 接口。
page_init 负责识别、预留并注册初始空闲物理页；default_init_memmap 负责把传入区域交给 First-Fit 管理。两者职责不同。
不要将 npage 解释为空闲页数，不要将 Page 描述符地址解释为其管理的物理页地址。

[GUARANTEE]
本任务不新增函数；必须解释以下现有函数的输入、前后状态和调用关系：
- default_init(void)
- default_init_memmap(struct Page *base, size_t n)
- default_alloc_pages(size_t n)
- default_free_pages(struct Page *base, size_t n)
- default_nr_free_pages(void)
补充说明 default_pmm_manager 注册结构与 check 的作用。

[SPECIFICATION]
Pre-Condition：实际源码可读取，学习者已经初步理解页、Page 描述符和空闲链表。
Post-Condition：我能说明初始化、寻找、拆分、回收和相邻合并，并能根据例子计算 nr_free 的变化。

Case 1 初始化：解释空链表初始化和空闲区注册的区别；说明哪些页状态被清除、哪些节点进入空闲链表、property 在哪个页面上有效。
Case 2 分配：用按地址排列、大小依次为6页和3页的两个空闲块，演示请求3页时选择哪块、是否拆分、剩余块如何入链、nr_free 如何变化。
Case 3 回收：分别说明没有相邻块、只有前邻、只有后邻、同时有前后邻时的行为。强调物理地址连续才可合并，链表相邻不足以证明物理连续。
Case 4 失败：解释无足够连续块但总空闲页数仍较多时为何会失败；以源码为准说明 n=0 的处理。

Requirements：
- 区分空闲块头、块内页、已分配页；不能仅凭某页 PageProperty 为0就断言它已分配。
- 解释按地址排序便于合并，但不等于按块大小排序。
- 解释 allocated/free 状态变化时 PageProperty、property、ref 和 nr_free 的各自含义。
- 说明检查函数为什么能发现重复分配、丢页或错误拆分；不把测试通过说成所有输入均已证明正确。
- 回答是否有改进空间，至少讨论搜索开销、外部碎片和合并维护。区分保持 First-Fit 语义的数据结构优化与 Next-Fit、Best-Fit 等策略改变，说明收益和代价。
- 分析复杂度时区分遍历空闲块与逐页初始化/清理的成本。
`````

### 历史文件：master.md

`````markdown
[PROMPT]

你是我的操作系统实验编程协作者。请依据当前 Lab2 工程、Lab2 指导书和《AI使用范式》，完成本实验全部代码任务，包括附加的简化 SLUB，实现、接入、测试、修复和交付。

姓名：闻鹏杰
学号：2511565

一、工作目标

按依赖顺序完成：
1. 核对工程及环境，检查或补全 page_init。
2. 阅读 First-Fit，理解其状态和接口，作为后续实现依据。
3. 实现并接入 Best-Fit，作为默认物理页管理器。
4. 从零实现 Buddy，并编写独立测试。
5. 从零实现简化 SLUB，并编写独立测试。
6. 完成构建配置、原有测试、必要回归验证。
7. 根据指导书准备 QEMU 页表查询调试所需的构建配置、脚本和操作说明。
8. 保存真实提示词、修改说明、测试记录及待完成事项。

二、执行方式

- 先读取当前实际工程，再修改文件；不能只展示代码片段。
- 已正确完成的代码应保留，只修复有证据的问题，不重复重写。
- 我已授权本任务范围内的实现、测试和常规修复，无须反复询问是否继续。
- 分阶段连续推进；不要在只给出方案或完成一个模块后就结束整个任务。
- 不要求我先回答一系列知识问题才能进入代码阶段。
- 每阶段用简短例子解释关键设计和状态变化，再实施修改并验证。
- 遇到必须由我本机执行的操作，完成你能够完成的工作后，给出一组明确步骤，等待真实反馈；不得猜测结果。
- 若只能访问附件副本，明确该副本不是我的 WSL 工程，提供补丁及安全同步方法。
- 缺少源码时只索取必要文件，不凭提示词自行编造整个课程框架。
- 不自动提交或推送 Git，不覆盖无关改动。

三、修改范围

允许：
- kern/mm/pmm.c 中 page_init 和管理器选择所需位置。
- kern/mm/best_fit_pmm.c 及必要的头文件声明。
- 新增 Buddy、SLUB 实现、头文件和自编测试。
- kern/init/init.c 中确有必要的初始化调用。
- Makefile 中管理器选择、测试开关和调试程序路径配置。
- 新增 prompts、docs 及独立验证脚本。

约束：
- 保留 lab2 注释，将本人实现位置的 YOUR CODE 替换为2511565。
- 不改写已有 First-Fit 实现。
- 不删除或修改 Best-Fit 的 basic_check、best_fit_check。
- 不修改官方 test_lab2、inject.py、grade.sh 以制造通过。
- 不重写设备树解析器，不随意改变 struct Page 或公开接口。
- 不将未实施的扩展功能混入本次修改。

四、输出方式

维护“已完成、已验证、待验证、阻塞项”清单，区分代码完成与运行验证完成。

每组需要我执行的命令必须说明：
执行环境、终端、工作目录、作用、预期现象、失败时需提供的输出。

最终交付：
- 实际修改后的代码及补丁；
- 各配置的构建和启动方法；
- 真实测试结果、已知限制；
- 模块设计与关键函数说明；
- 实际使用的提示词及修复记录；
- 报告所需证据清单。

不能虚构截图、日志、测试通过、调试观察或我的个人学习体会。


[RELY]

一、环境与源码

我使用 Windows＋WSL2 Ubuntu＋VS Code，曾使用 QEMU 4.1.1 和 riscv64-unknown-elf 工具链。

历史 WSL 工程路径为 ~/os-lab/src/lab2，但必须重新核对。
附件曾以 lab2_new 为根目录，不能把附件路径当作我的本机路径。
不重装已经可用的工具。

先读取：
- Makefile
- tools/kernel.ld
- kern/init/entry.S、init.c
- kern/driver/dtb.c、dtb.h
- kern/mm/pmm.c、pmm.h
- kern/mm/memlayout.h、mmu.h
- kern/mm/default_pmm.c
- kern/mm/best_fit_pmm.c、best_fit_pmm.h
- libs/list.h、defs.h
- tools/test_lab2.c、相关头文件、inject.py、grade.sh
- 已存在的 Buddy、SLUB、测试、提示词和说明文件

以上与真实文件不一致时，指出差异，以当前源码和课程要求核实后的结果为准。

二、现有框架

pmm_manager 提供：
init、init_memmap、alloc_pages、free_pages、
nr_free_pages、check。

依赖现有：
get_memory_base、get_memory_size、
init_memmap、pa2page、page2pa、
PADDR、PPN、ROUNDUP、ROUNDDOWN、
页状态宏、引用计数接口和链表操作。

当前框架中的 KADDR 被注释，不能假定可以调用。
不能假定内核已经存在 malloc、kmalloc 或标准库运行环境。

重要约定：
- end 是内核镜像末端虚拟地址。
- pages 是 Page 描述符数组的虚拟地址。
- npage 是物理页号上界，不是空闲页数量。
- nbase 对应固定 DRAM 基址的物理页号。
- 描述符数量为 npage-nbase。
- pa2page 返回描述符指针，不是物理页内容地址。
- PADDR 依赖正确的 va_pa_offset。
- page_init 在当前管理器 init 之后执行。

三、现有测试约定

Best-Fit 原测试会：
- 直接保存、清空、恢复 free_list 和 nr_free。
- 在链表已经清空但 nr_free 尚未同步清零的临时状态请求分配。
- 拆分释放和重新分配后，统一释放一段连续页面。
- 检查分配器是否真正选择最小的合适块。

因此不能：
- 增加无法随测试状态一起恢复的隐藏索引；
- 只检查 nr_free 就假定一定能找到空闲块；
- 要求 Best-Fit 的释放长度必须匹配某一次完整分配。

先阅读评分注入机制。自编测试不要占用官方注入的 kern/test 位置，不提前加入会导致重复注入的官方测试代码。


[GUARANTEE]

一、必须实现或核实的接口

1. 物理内存初始化：
static void page_init(void);

2. Best-Fit：
static void best_fit_init(void);
static void best_fit_init_memmap(struct Page *base, size_t n);
static struct Page *best_fit_alloc_pages(size_t n);
static void best_fit_free_pages(struct Page *base, size_t n);
static size_t best_fit_nr_free_pages(void);
const struct pmm_manager best_fit_pmm_manager;

使用已有 best_fit_check 作为检查回调。

3. Buddy：
static void buddy_init(void);
static void buddy_init_memmap(struct Page *base, size_t n);
static struct Page *buddy_alloc_pages(size_t n);
static void buddy_free_pages(struct Page *base, size_t n);
static size_t buddy_nr_free_pages(void);
void buddy_check(void);
const struct pmm_manager buddy_pmm_manager;

4. 简化 SLUB：
void slub_init(void);
void *kmalloc(size_t size);
void kfree(void *ptr);
void slub_check(void);

已有正确实现或已公开的等价接口应优先复用，不为统一命名进行无必要重构。
内部辅助函数优先使用 static。

二、必须保存的提示词

在对应阶段执行前，依据当前代码生成并保存四段式任务提示词，再依照它完成工作：

prompts/page_init.md
prompts/best_fit_impl.md
prompts/buddy_impl.md
prompts/buddy_test.md
prompts/slub_impl.md
prompts/slub_test.md

保存本总提示词作为总任务记录。

实现与测试必须分别明确目标、接口、修改范围、前置条件和验收条件；不能事后伪造使用历史。
修订提示词时记录修订原因。

三、构建配置

至少支持：
- 默认 Best-Fit；
- Buddy 独立运行；
- Best-Fit＋SLUB；
- Buddy＋SLUB。

默认基础评分仍使用 Best-Fit，扩展检查默认关闭。
配置切换通过明确的构建开关完成，必要时清理旧目标文件并重启。
禁止在有活动分配时切换管理器。


[SPECIFICATION]

一、page_init

Pre-Condition：
设备树解析已执行，管理器已初始化；设备树信息可能无效。

Post-Condition：
正确设置 va_pa_offset、npage、pages，初始化描述符，并仅注册合法、完整的空闲页。

要求：
1. 核对设备树内存基址、大小、末端加法溢出，以及与当前固定 DRAM 基址和映射的兼容性。
2. 管理上界不得超过设备树范围、框架物理上界和实际映射范围。
3. npage 取管理末端向下按页对齐后的页号。
4. pages 位于 end 之后或恰好位于 end，按页对齐，包含 npage-nbase 个描述符。
5. 写入描述符之前，检查内核、数组和全部地址计算是否有效；不能越界写完再检查。
6. 描述符先有确定初始状态并标记保留，再注册空闲区。
7. OpenSBI、内核、描述符及必要对齐空隙不得进入空闲区。
8. 空闲起点向上对齐，末端向下对齐；没有完整空闲页时不调用 init_memmap。
9. 使用 pa2page 前同时核对下界和上界。
10. 无效设备树信息或无法容纳内核、描述符时 panic，不能用默认内存大小掩盖失败。

验证正常范围、非法信息、截断和零完整空闲页。
官方测试对 npage 的期望可能未考虑超过管理上界的内存；必须指出这一差异，独立验证截断行为，不修改官方测试。


二、First-Fit 阅读

不重写实现。结合真实函数解释：
- 初始化空链表与注册空闲区的区别；
- 首个满足条件的块如何选中；
- 拆分、释放、前后合并；
- free_list、nr_free、property、PageProperty 的作用。

给出一个“6页块和3页块，请求3页”的例子，比较 First-Fit 与 Best-Fit。

改进思考放入说明文档；区分优化数据结构和改变分配策略，不声称某种策略在所有情况下都更好。


三、Best-Fit

Pre-Condition：
按框架注册有效空闲区；分配请求 n>0；释放区间全部为有效已分配页。

Post-Condition：
成功分配恰好 n 页，选择所有候选中最小的合适块；失败不改变状态；释放后正确合并相邻空闲块。

要求：
1. 完整实现状态、管理函数和注册结构，不只补 alloc_pages。
2. 同样大小的候选块选较低地址，作为本实现确定性约定。
3. 精确匹配移除整块；较大块拆分后保留剩余空闲区。
4. 释放支持原测试要求的部分释放和连续区间统一释放。
5. 处理无邻块、仅前邻、仅后邻、前后同时相邻。
6. 合并后清理失效块头标志和节点，不重复增加 nr_free。
7. 空闲页总数足够但不存在连续块时仍应失败。
8. 兼容原测试直接保存、恢复 free_list 和 nr_free 的行为。
9. 原 basic_check、best_fit_check 保持不变。
10. 默认 init_pmm_manager 选择 best_fit_pmm_manager。

验证原测试、可用评分流程及默认启动输出，说明搜索成本和碎片方面的改进空间。


四、Buddy 实现

以下是本次设计约定，不冒充课程唯一要求：

- 请求 n 页，实际占用最小的 2^k>=n 页。
- free_pages(base,n) 传原始请求 n，释放整个对应块。
- 例如申请3页实际占4页，释放传3，空闲页数恢复4。
- 不支持部分释放。
- n=0、取整溢出或无法满足的请求返回 NULL，状态不变。

Pre-Condition：
初始化阶段无活动分配；注册区间真实有效、未重叠。

Post-Condition：
每次分配返回合法连续块；释放仅与合法伙伴递归合并；计数按实际块大小维护。

要求：
1. 明确阶数、伙伴编号坐标系、对齐原点和管理域。
2. 正确拆分非二次幂长度、非大块对齐的初始区域，不遗漏尾页，不越界扩展。
3. 支持多次注册互不重叠区间，不清空已有注册状态。
4. 禁止跨保留页、未注册洞或管理域边界合并。
5. 只有同阶、空闲且互为伙伴的块才能合并；物理相邻本身不足以合并。
6. 元数据来源明确，不递归调用尚未初始化的自身分配器。
7. 元数据占用不得重复算作空闲资源；检查容量、索引、移位和取整溢出。
8. 声明单核/串行调用假设，不宣称未实现的并发安全。
9. 非法释放不属于正常接口前置条件；若提供诊断，明确支持范围。

不要求特定复杂度，优先正确、清晰、可验证。


五、Buddy 独立测试

Pre-Condition：
Buddy 已选定，注册完成，无并发分配者。

Post-Condition：
正常测试结束时所有测试分配均已释放，空闲页数恢复基线。

覆盖：
- 1、2、4页分配；
- 3、5页请求的向上取整及对应释放；
- 大块拆分、真正伙伴合并、多阶合并；
- 相邻但非伙伴的块不能错误合并；
- 不规则注册区间、多段注册和保留洞；
- 零请求、超大请求、溢出、内存不足；
- 无重叠、无重复分配、内容不被破坏；
- 耗尽后释放恢复；
- 固定种子的有界随机分配/释放。

测试判定独立于实现，不复制内部伙伴判断函数作为唯一预期结果。

需要精确布局的测试使用隔离实例、合法测试区域或独立启动配置；不得重置有活动分配的全局管理器，不使用假的 Page 数组冒充真实物理内存进行写入。

无法真实构造的用例标明待测，不用普通分配成功冒充拆分、合并已验证。


六、简化 SLUB 实现

设计约定：
- kmalloc(0) 返回 NULL。
- kfree(NULL) 无副作用。
- 成功对象至少有 size 字节可读写，起始地址至少16字节对齐。
- 小对象按尺寸类别共享 slab 页面。
- 超过最大小对象类别的请求使用连续页后端，支持跨页对象。
- 空 slab 及时归还底层；不保留未说明的空页缓存。
- 不保证新内存清零。
- kfree 接受尚未释放的原始返回指针。

Pre-Condition：
pmm_init 已完成，底层页分配器可用；slub_init 只在无活动对象时初始化。

Post-Condition：
活动对象彼此不重叠、不覆盖元数据；失败不泄漏资源；释放能正确回收对象及底层页面。

要求：
1. 明确尺寸类别、slab元数据、对象槽、空闲对象结构及状态转换。
2. 多个小对象实际共享页面，不能把每个小请求直接包装成单页申请。
3. 计算容量时包括元数据、对齐空隙和大对象头部。
4. 检查大小相加、对齐和页数取整溢出。
5. 能可靠识别对象归属，正确处理满、部分空闲、全空状态。
6. 最后一个对象释放后，先安全脱链再归还页面。
7. 大对象记录块头和原始页请求，按底层契约释放。
8. 在Buddy后端下考虑实际向上取整占用，禁止部分释放。
9. 不使用不存在的KADDR，不混淆物理地址、内核虚拟地址和Page指针。
10. 不递归依赖自身kmalloc来完成初始化。
11. SLUB不是pmm_manager的替代品，应在pmm_init之后初始化。
12. 不要求实现Linux完整SLUB、NUMA或每CPU缓存。


七、SLUB 独立测试

Pre-Condition：
SLUB已初始化，无并发分配者；记录初始化之后的页数基线。

Post-Condition：
所有测试对象释放后，页数恢复基线，无对象或页面泄漏。

覆盖：
- 0、1字节和 kfree(NULL)；
- 每个实际尺寸类别边界的前1、边界、后1；
- 4095、4096、4097字节及多页请求；
- 对齐、请求范围可写、活动对象不重叠；
- 多个小对象确实共享slab；
- slab填满、申请新slab、部分释放、重新使用、整页回收；
- 混合尺寸、乱序释放、大对象回收；
- 超大请求和算术溢出；
- 内存不足后的状态保持；
- 固定种子的有界随机测试；
- Best-Fit和Buddy两种后端分别运行。

测试使用不同数据模式检查活动对象内容。
不在释放后继续读写，不假定分配结果已清零。
测试记录不能依赖正在测试的kmalloc，避免递归依赖和内核栈溢出。
耗尽测试若只达到记录容量，明确未证实耗尽。
仅在实现明确承诺非法释放诊断时测试它；预期panic单独启动。


八、QEMU 调试配置与辅助文件

这一阶段依据当前指导书核实，不擅自增加内核功能或修改QEMU算法。

需要完成：
1. 核对实际QEMU版本、源码路径、宿主架构及调试工具。
2. 如需重新构建，生成独立的带调试信息QEMU，不替换已安装的可用版本。
3. 提供可覆盖的调试QEMU路径配置，不把临时绝对路径硬编码成通用工程配置。
4. 区分宿主GDB调试QEMU进程、RISC-V GDB调试内核。
5. 根据实际版本定位地址翻译、页表遍历、TLB相关代码和条件断点。
6. 准备可复现的启动/调试命令或GDB脚本，注明终端、工作目录和执行顺序。
7. 使用真实访存指令、虚拟地址、satp和PTE解释地址翻译，支持中间层叶子及大页，不能假定总走到第三级页表。
8. 区分QEMU的软件TLB实现与体系结构中的TLB概念；不要凭断点未命中就声称观察到了TLB命中。

能执行的实际执行；需要我本机交互观察的步骤等待反馈。
不能把准备好脚本写成已经完成调试演示。


九、验证和交付准则

1. 先检查依赖是否完整，再构建；page_init和Best-Fit都缺失时不能期待只补一个即可通过整个工程。
2. 分别验证默认Best-Fit、Buddy、Best-Fit＋SLUB、Buddy＋SLUB。
3. 根据真实Makefile提供命令，不编造现成目标。
4. 核对构建开关变化会重新编译受影响文件，避免复用错误配置产物。
5. 保留原测试；新增测试不得通过硬编码地址、请求序列或放宽断言制造通过。
6. 测试失败记录：命令、目录、第一条关键错误、预期结果、实际结果、定位和修复。
7. 区分源码检查、宿主模拟测试、目标交叉编译、QEMU运行与人工调试；宿主通过不等于目标通过。
8. 无法验证的项目写明具体阻碍和下一步，不能标为已完成验证。
9. 测试结束释放资源，较大测试数组避免放在有限的内核栈上。
10. 原测试内容是否保持不变，须通过实际差异检查确认。

最终给出：
- 修改文件清单及用途；
- 各模块接口和关键状态变化；
- 构建、运行和配置切换方法；
- 测试覆盖表与真实结果；
- 补丁及同步方法；
- 真实提示词、问题修复记录；
- 待我本机验证的最小步骤。

物理内存发现Challenge是思考题：在说明文档中解释设备树、固件或引导程序提供内存映射的方法，区分可用RAM、保留区和MMIO，说明为何不能盲目读写探测；不要借此扩大为重写设备树模块。

现在开始读取工程、核对已有实现，并按照上述顺序持续完成任务。只有遇到确实需要我提供资料或执行本机操作的阻碍时，才暂停等待反馈。
`````

### 历史文件：page_init.md

`````markdown
[PROMPT]
核实并保留已实现的page_init，只修复发现的实际问题，不改设备树解析和评分代码。
[RELY]
pmm.c/.h、memlayout.h、mmu.h、dtb.c/.h、defs.h、kernel.ld和test_lab2.c；固定DRAM基址、物理管理上界、映射偏移以源码为准。
[GUARANTEE]
static void page_init(void)，负责va_pa_offset、npage、pages及初始空闲注册。
[SPECIFICATION]
Pre-Condition：DTB解析和管理器init已执行，DTB结果可能无效。
Post-Condition：数组覆盖[nbase,npage)，内核及描述符保留；合法完整空闲页交给管理器。
Case：非法基址/大小/溢出或布局不足panic；上界截断；合法无完整空闲页不注册。
Requirements：所有容量检查先于写入；区分VA/PA/PPN/Page；验证正常、非法、截断、空区间，宿主与目标结果分开。
记录：本阶段是对先前任务一实现的核实，不声称此前实现使用了这份新提示词。
`````

### 历史文件：slub_impl.md

`````markdown
[PROMPT]
任务：在现有ucore中从零实现简化SLUB对象分配模块，体现“底层分配物理页、上层分配任意请求大小对象”的两层结构，并接入内核。学号2511565。本次做实现和最小检查，完整独立测试由下一份提示词完成。

操作要求：
1. 先读取实际页分配框架，再修改工程。新增 kern/mm/slub.c、slub.h；只在init.c或已核实的启动位置、Makefile中进行必要接入。
2. SLUB建立在启动时已选定的页分配器之上，不作为pmm_manager的替代品。默认Best-Fit保持不变；启用SLUB不意味着热切换底层管理器。
3. 用显式编译开关LAB2_ENABLE_SLUB启用初始化和检查，默认关闭，保留基础评分路径。不得修改官方测试、page_init或已完成分配器。
4. 不照搬依赖Linux专用设施的源码。课程允许简化，本次不实现NUMA、每CPU缓存或复杂并发机制。
5. 修改附件副本时明确同步方式，不声称已经在我的WSL运行。

输出要求：给出实际实现、接口契约、对象和元数据布局图/表、分配与回收过程、最小真实验证、待测项和同步方式。说明为什么多个小对象可以共享物理页，而不是每个小对象都单独申请一页。

[RELY]
阅读 kern/mm/pmm.h、pmm.c、memlayout.h、mmu.h、libs/defs.h、list.h、kern/init/init.c、Makefile，以及实际选择的底层分配器接口。
底层可依赖 alloc_pages、free_pages、nr_free_pages、page2pa和已有映射偏移；当前KADDR被注释，不能调用不存在的接口。
若底层为Buddy，申请n页可能实际占用向上取整的块，释放仍传原请求n；不得按Best-Fit的部分释放方式释放Buddy块。
没有现成malloc/kmalloc可用于本模块初始化或管理元数据。

[GUARANTEE]
新增公开接口：
void slub_init(void);
void *kmalloc(size_t size);
void kfree(void *ptr);
void slub_check(void);

其余缓存、slab管理和链表函数优先static；公开声明放slub.h。
本阶段slub_check提供最小可运行检查，下一阶段扩展；禁止存在未定义回调或重复定义。

[SPECIFICATION]
本实现选择的契约（不是题目指定的唯一方案）：
- kmalloc(0)返回NULL；kfree(NULL)不做任何事。
- 成功返回的对象至少有size字节可读写，起始地址至少16字节对齐。
- 小对象使用有限尺寸类别和页内空闲对象结构；类别及最大小对象阈值由实现根据布局明确列出。
- 大于最大类别的请求使用连续页后端，支持跨页对象；不以“小对象类别中没有该大小”为理由拒绝本可满足的请求。
- 空slab及时退还底层页分配器，以便测试验证页数恢复；不能有未说明的空页缓存。
- 不保证新分配内存为零；kfree只接受本分配器尚未释放的原始返回指针。

1. slub_init
Pre-Condition：pmm_init已完成，底层页分配器可用，无活动SLUB对象。
Post-Condition：各尺寸缓存和管理状态初始化完成。元数据来源明确，不递归调用尚未初始化的kmalloc。

2. kmalloc
Pre-Condition：slub_init完成，按当前单核串行调用约定执行。
Post-Condition：成功对象与所有活动对象、slab元数据均不重叠，至少满足请求字节数和对齐；失败返回NULL且不泄漏页、不破坏已有对象。
Case A 当前尺寸类别有空槽：从已有slab分配。
Case B 没有空槽：向底层申请页，建立新slab后分配。
Case C 请求跨页或超过最大类别：计算包括管理信息与对齐空隙在内的页数，申请完整连续空间。
Case D size=0、计算溢出或底层内存不足：安全失败，撤销本次未完成的状态变化。

3. kfree
Pre-Condition：ptr为NULL，或本分配器返回且尚未释放的完整对象指针。
Post-Condition：小对象槽归还所属slab；从满到非满的状态可再次分配；最后一个对象释放后回收整个空slab。大对象按记录的块头和原始页请求释放，不丢页、不重复释放。
必须能可靠识别对象所属slab/大对象记录，不能只凭地址对齐猜测类型。

4. slub_check与启动接入
Post-Condition：仅在启用开关且pmm_init后初始化；最小检查验证小对象分配、写入和释放。完整测试另行补充，不将最小检查称作全面通过。

Requirements：
- 说明尺寸类别选择造成的内部碎片，区分用户请求大小、槽大小、元数据占用和底层实际页数。
- 布局计算包括页内头、空闲链表/位图、对象对齐及大对象头，不能越界写入管理信息。
- 对size加头部、向上对齐、页数取整做溢出检查。
- 物理地址到可访问内核虚拟地址的转换必须符合现有映射；不得将物理地址或Page描述符直接当对象指针。
- 所有页由统一底层接口取得和归还；记录Buddy所需原请求，不在运行中切换管理器。
- 优先避免改变Page结构或占用其他模块正在使用的页字段；如必须使用字段，明确所有权和释放时恢复规则。
- 不强制实现非法/重复释放恢复；如有诊断，写清支持范围，不能把未检测情况说成安全。
- 核对Makefile是否已经自动包含kern/mm/*.c；不要重复添加造成重复编译。自编测试不放入官方注入使用的kern/test目录。
- 分别给出静态分析、宿主验证和QEMU运行情况；没有实际运行不得输出伪造PASS。
`````

### 历史文件：slub_test.md

`````markdown
[PROMPT]
任务：为当前简化SLUB实现编写独立测试，验证不同大小对象的分配、写入、释放和底层页回收是否正确。学号2511565。

操作要求：
1. 先读取slub.c/.h和实现契约，核对实际尺寸类别、对象对齐、元数据位置及空slab回收策略。
2. 新增 kern/mm/slub_check.c，将完整slub_check放在唯一位置；替换上一阶段同名最小检查，不重复定义。
3. 保留官方评分路径、Best-Fit原测试和Buddy测试。仅对SLUB缺陷作有证据的修复，不为通过测试修改公开语义。
4. 测试通过编译开关启用；如分别验证Best-Fit和Buddy后端，必须分别重新构建、重启，不热切换。

输出要求：交付实际测试、覆盖表、真实结果、失败及修复记录、未测项；写出可纳入报告的测试有效性解释，不虚构运行或个人体会。

[RELY]
读取slub.c/.h、pmm.h、实际底层分配器、memlayout.h、init.c、Makefile。
依赖接口：slub_init、kmalloc、kfree、nr_free_pages，以及明确有效的地址转换。
契约：size=0返回NULL；kfree(NULL)无副作用；至少16字节对齐；对象至少有请求字节数可写；支持大对象；空slab归还底层；未承诺内容初始为零。
如果实际实现与上述契约不同，先指出差异，再判断是实现错误还是先前明确接受的设计变更，不能偷偷改测试期望。

[GUARANTEE]
实现 void slub_check(void) 和必要的static测试辅助函数。
测试应在SLUB初始化完成后执行，不能覆盖已有初始化逻辑。只有确有必要时增加条件编译下的只读统计接口，不依赖任意修改内部分配状态来“制造通过”。

[SPECIFICATION]
Pre-Condition：底层管理器及SLUB已初始化；测试期间无其他并发分配；记录测试前页数基线。
Post-Condition：正常退出时所有测试对象均释放，空slab与大对象占用的页全部归还，页数恢复测试前基线；不得改变其他活动对象内容。

必须覆盖：
1. 零和最小请求：kmalloc(0)、kmalloc(1)、kfree(NULL)，核对返回值与计数。
2. 尺寸边界：对实际各类别边界取边界前1、边界值、边界后1；另测4095、4096、4097字节和若干多页请求。重复尺寸可合并。
3. 对齐与容量：每个成功指针满足16字节对齐，实际写满请求字节区间；写不同数据模式，验证相邻活动对象不被破坏。
4. 页内复用：同时保留多个小对象，用页数变化、地址所在页或只读统计证明多个对象共享slab，而不是每个对象占一页。
5. 状态转换：填满一个slab，触发第二个，释放第一个中的部分对象后重新分配；验证满、部分空闲、全空之间的转换，不无条件要求重新返回同一指针。
6. 混合尺寸和乱序释放：多类别及大对象同时存在，逐次核对仍活动对象的内容和区间不重叠。
7. 大对象回收：验证包括头部和对齐空间的连续页申请/释放正确；若底层Buddy向上取整，按其真实契约判断页数变化。
8. 失败与溢出：SIZE_MAX附近等不能安全计算的请求返回NULL；以有界、可清理方式构造内存不足，确认无泄漏且旧对象数据保持。
9. 固定种子的有界随机序列：独立维护活动指针、请求大小和数据模式，逐轮检查内容、重叠和最终页数恢复。

Requirements：
- 预期结果来自接口契约和独立计算，不调用SLUB内部分类函数来同时生成实际值与期望值。
- 比较的是slub_init之后的基线；若初始化常驻元数据占页，单独解释，不能混入每次对象泄漏。
- 不测试“新对象必须清零”，因为接口未承诺；不在free后继续读写对象。
- 测试记录数组及辅助内存不能通过正在测试的kmalloc获取，避免递归依赖；控制内核栈用量。
- 空间耗尽用例必须记录所有已获对象并全部释放；达到记录容量时停止并说明未完全耗尽，不能伪称OOM已验证。
- 只有实现明确提供非法释放诊断时才增加此类测试；预期panic必须独立运行，正常成功路径不包含未定义行为。
- 用例应能发现缓冲区重叠、尺寸计算漏算元数据、对象槽未回收、空slab未归还和大对象释放长度错误。
- 若只验证一种底层管理器，明确覆盖范围；只有两种分别真实运行后才声称二者兼容。
- 输出逐项断言结果和最终基线恢复情况；区分静态检查、宿主测试和QEMU测试。
`````
