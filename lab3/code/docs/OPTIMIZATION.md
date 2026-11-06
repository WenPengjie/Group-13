# Lab3 优化审查与健壮性修复

## 结论与身份

用户闻鹏杰2511565授权本次审查。基线仅为lab3_2511057(2).zip，原始输入完整保存在包根baseline-input.zip。原实现和署名保留，本次没有Git操作，也未访问用户WSL。
内核kern、libs、官方tools、Makefile共56个原文件保持基线字节不变。本次是验证流程健壮性改进，不是新的内核提速；没有证据时不实施高风险候选。

## 基线检查

已核对指导书两个正式模块及Lab2依赖，读取实际调用关系、栈帧、时钟和异常处理、内存分配、Makefile与原官方测试；本次输入已具备时钟热路径前置、volatile单次读、异常长度共享尾部、Best-Fit精确匹配提前返回。
原测试要求35/25/40，本次未修改测试。输入附件已有100/100与六项扩展日志，仅作为历史来源保留；不是本次运行证明。
当前助手环境有宿主gcc，没有riscv64-unknown-elf-*及qemu-system-riscv64。目标编译、真实QEMU、官方评分、目标反汇编测量均被阻塞。新入口实际执行后以非零返回报告缺工具，没有报PASS。

## 候选筛选与不变量

| 候选 | 判断与证据 | 处理 |
|---|---|---|
| 继续合并异常长度处理 | 基线已经合并，不能重复算收益 | 不改 |
| 用倒计数代替ticks取模 | 增加隐藏状态，会受ticks重置/溢出等影响，无目标测量支持 | 不改 |
| 减少GPR保存或提前恢复sp | 破坏Trap契约，且不在本次修改权限范围 | 禁止 |
| 删除page_init描述符初始化/检查 | 改变元数据状态及边界保证，启动成本非热路径 | 不改 |
| 更换Best-Fit索引或默认管理器 | 改变测试状态假设与默认行为，当前无瓶颈证据 | 不改 |
| 脚本移植、日志和清理修复 | 硬编码PATH、覆盖历史、失败传播和子进程清理风险可重现 | 实施并测试 |

核心不变量由字节一致性保持；本次未改变计数、输出、阈值、时钟间隔、指令长度策略或任何CSR处理。

## 实际修改与用途

- tests/validation_tools.py：公共验证工具。继承PATH，支持TOOLCHAIN_BIN/QEMU_BIN，拒绝会悄悄改变默认构建的环境变量；预检依赖，保存命令、目录、返回码、工具版本、源码哈希。
- tests/run_required.sh：保留旧入口，改为set -euo pipefail并exec公共工具，避免tee掩盖失败。
- tests/extended_qemu.py：保留入口，仍使用原extended.c和extended_context.S；注入只在临时副本，逐条核对六项结果，未降低断言。
- tests/audit_performance.py：相同环境分别干净构建两份源码，保存nm和objdump原始输出；统计机器码符号大小和静态指令数。汇编标签没有可靠ELF大小时写null，不伪造字节数。
- tests/host_handlers.py：抽取当前真实handler，使用真实trap.h布局与宿主桩函数；24个编码/对齐组合、288字节及CSR槽位、未知异常不读取无效epc、输出格式、非时钟分支、1000次事件重设、计数与关机阈值、时钟epc不变。
- tests/test_validation_tools.py：12项宿主测试，覆盖环境配置、缺工具、构建覆盖变量、非零退出、超时进程组、结果判定、日志唯一性及临时注入。
- tests/check_baseline.py：与确切原ZIP逐字节比较56个课程文件。
- README及report头部说明：区分历史成绩和本次结果；没有补造个人学习体会、截图或分工。

## 隔离和运行风险控制

构建只复制kern/libs/tools/Makefile至本次创建的TemporaryDirectory，不clean当前用户bin/obj。官方评分仍调用原make grade，但用命令行GRADE_TMP设置本次独立临时路径，避免原固定/tmp/lab3_grade与其他验证冲突；未改评分器、注入器或构建参数。
每次日志通过mkdtemp独立创建，默认code/validation。LAB3_LOG_ROOT可改变日志父目录，但不会覆盖已有运行子目录。
所有外部命令不经过Shell字符串拼接，在独立进程组启动；超时/Ctrl+C终止本次组，必要时KILL，不使用pkill/killall。仅清理自己创建的临时目录。
输入含源码符号链接时拒绝复制，以免意外沿链接读取其他目录。
安全不等于零风险：QEMU/编译器/宿主环境自身故障仍可能发生；SIGKILL终止整个验证器时无法保证finally运行，可能遗留临时目录；不声称具备所有敌意环境防护。

## 实际验证与待验证

实际输出见code/validation/assistant-tests/。完整性52文件6保护区通过；56个课程文件与本次输入一致；宿主handler测试通过；12项工具测试通过；Shell及Python语法检查通过。
实际执行required/extended/audit入口均在依赖预检处报告阻塞，没有目标测试通过。本次没有新目标机成绩、机器码大小或动态性能数字。
宿主测试不能验证真实寄存器指令、sret、SIE硬件行为或SBI。相应原扩展用例保留，等待WSL执行。
未修改内存模块，因此未扩大为宿主模拟page_init或重新发明分配器边界测试；原内存自检仍由目标回归执行。

## 本次真实问题与修复

新宿主测试从简化结构改用真实trap.h后，首次命令python3 tests/host_handlers.py在候选code目录失败：static declaration of print_trapframe follows non-static declaration。原因是头文件已有外部声明而桩函数带static。移除桩函数static后重跑通过。只修测试桩，没有修改课程头文件/内核实现。

## 性能结论

相对于本次输入，内核源码未改，没有新增运行性能收益可报告，也不重复宣称基线历史的136→100字节收益。本次改进是可维护性、证据可靠性和隔离性。
提供的audit工具只生成静态数据，不测每次handler的周期。固定约10秒关机时间主要由定时器与输出决定，不能用来证明handler提速；本次未采用无依据的动态插桩。

## 进一步工作与回滚

先按WSL_VERIFY.md完成新目录安装与工具核对，再运行基础/扩展回归和同配置静态审计。无目标反馈前，不建议改Trap汇编或添加隐藏计数状态。
包根changes.patch以本次输入code/report为基线。使用整包无需再次打补丁；已有目录应先备份、patch -p1 --dry-run，确认无冲突后再应用。回滚可在确认没有后续个人改动时反向dry-run后patch -R -p1；更安全的是保留新旧两个目录，切回旧目录工作。
