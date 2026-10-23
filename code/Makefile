PROJ	:= lab2
EMPTY	:=
SPACE	:= $(EMPTY) $(EMPTY)
SLASH	:= /

V       := @

#ifndef GCCPREFIX
GCCPREFIX := riscv64-unknown-elf-
#endif

ifndef QEMU
QEMU := qemu-system-riscv64
endif

ifndef SPIKE
SPIKE := spike
endif

# eliminate default suffix rules
.SUFFIXES: .c .S .h

# delete target files if there is an error (or make is interrupted)
.DELETE_ON_ERROR:

# lab2 2511565: isolated build-time choices, no live manager switching.
PMM ?= best_fit
SLUB ?= 0
EXT_TEST ?= 0
ifeq ($(filter $(PMM),best_fit buddy),)
$(error PMM must be best_fit or buddy)
endif
ifeq ($(filter $(SLUB),0 1),)
$(error SLUB must be 0 or 1)
endif
ifeq ($(filter $(EXT_TEST),0 1),)
$(error EXT_TEST must be 0 or 1)
endif
LAB2_FLAGS :=
ifeq ($(PMM),buddy)
LAB2_FLAGS += -DLAB2_PMM_BUDDY
endif
ifeq ($(SLUB),1)
LAB2_FLAGS += -DLAB2_ENABLE_SLUB
endif
ifeq ($(EXT_TEST),1)
LAB2_FLAGS += -DLAB2_EXT_TEST
endif
# Optional isolated debug QEMU, without overwriting installed QEMU.
ifneq ($(strip $(QEMU_DEBUG)),)
QEMU := $(QEMU_DEBUG)
endif

# define compiler and flags
HOSTCC		:= gcc
HOSTCFLAGS	:= -Wall -O2

GDB		= $(GCCPREFIX)gdb

CC		:= $(GCCPREFIX)gcc
CFLAGS  := -mcmodel=medany -std=gnu99 -Wno-unused -Werror 
CFLAGS	+= -fno-builtin -Wall -O2 -nostdinc $(DEFS)
CFLAGS	+= -fno-stack-protector -ffunction-sections -fdata-sections
CFLAGS	+= -g $(LAB2_FLAGS)
CFLAGS2 = $(CFLAGS) -D ucore_test
CTYPE	:= c S
LD      := $(GCCPREFIX)ld
LDFLAGS	:= -m elf64lriscv
LDFLAGS	+= -nostdlib --gc-sections

OBJCOPY := $(GCCPREFIX)objcopy
OBJDUMP := $(GCCPREFIX)objdump

COPY	:= cp
MKDIR   := mkdir -p
MV		:= mv
RM		:= rm -f
AWK		:= awk
SED		:= sed
SH		:= sh
TR		:= tr
TOUCH	:= touch -c

OBJDIR	:= obj
BINDIR	:= bin

ALLOBJS	:=
ALLDEPS	:=
TARGETS	:=

include tools/function.mk

listf_cc = $(call listf,$(1),$(CTYPE))

# for cc
add_files_cc = $(call add_files,$(1),$(CC),$(CFLAGS) $(3),$(2),$(4))
add_files_cc2 = $(call add_files,$(1),$(CC),$(CFLAGS2) $(3),$(2),$(4))
create_target_cc = $(call create_target,$(1),$(2),$(3),$(CC),$(CFLAGS))

# for hostcc
add_files_host = $(call add_files,$(1),$(HOSTCC),$(HOSTCFLAGS),$(2),$(3))
create_target_host = $(call create_target,$(1),$(2),$(3),$(HOSTCC),$(HOSTCFLAGS))

cgtype = $(patsubst %.$(2),%.$(3),$(1))
objfile = $(call toobj,$(1))
asmfile = $(call cgtype,$(call toobj,$(1)),o,asm)
outfile = $(call cgtype,$(call toobj,$(1)),o,out)
symfile = $(call cgtype,$(call toobj,$(1)),o,sym)

# for match pattern
match = $(shell echo $(2) | $(AWK) '{for(i=1;i<=NF;i++){if(match("$(1)","^"$$(i)"$$")){exit 1;}}}'; echo $$?)

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# include kernel/user

INCLUDE	+= libs/

CFLAGS	+= $(addprefix -I,$(INCLUDE))

LIBDIR	+= libs

$(call add_files_cc,$(call listf_cc,$(LIBDIR)),libs,)

# -------------------------------------------------------------------
# kernel

KINCLUDE	+= kern/debug/ \
			   kern/driver/ \
			   kern/mm/ \
			   kern/arch/

KSRCDIR		+= kern/init \
			   kern/libs \
			   kern/debug \
			   kern/driver \
			   kern/mm

KCFLAGS		+= $(addprefix -I,$(KINCLUDE))

# lab2 2511057: capture FINAL flags, including all include paths.
# Unchanged content keeps its mtime; administrative targets need no stamp.
ifneq ($(filter-out clean dist-clean grade host-test print-%,$(MAKECMDGOALS)),)
LAB2_NEED_STAMP := 1
endif
ifeq ($(strip $(MAKECMDGOALS)),)
LAB2_NEED_STAMP := 1
endif
ifeq ($(LAB2_NEED_STAMP),1)
LAB2_STAMP := $(OBJDIR)/.lab2-config
LAB2_STAMP_UPDATE := $(shell mkdir -p $(OBJDIR); \
 printf '%s\n' '$(CC)|$(CFLAGS)|$(CFLAGS2)|$(KCFLAGS)|$(PMM)|$(SLUB)|$(EXT_TEST)|$(filter test,$(MAKECMDGOALS))' > $(LAB2_STAMP).tmp; \
 cmp -s $(LAB2_STAMP).tmp $(LAB2_STAMP) && rm -f $(LAB2_STAMP).tmp || mv $(LAB2_STAMP).tmp $(LAB2_STAMP))
endif

ifeq ($(MAKECMDGOALS),test)
$(call add_files_cc2,$(call listf_cc,$(KSRCDIR)),kernel,$(KCFLAGS))
else
$(call add_files_cc,$(call listf_cc,$(KSRCDIR)),kernel,$(KCFLAGS))
endif
KOBJS	= $(call read_packet,kernel libs)

# create kernel target
kernel = $(call totarget,kernel)

$(kernel): tools/kernel.ld

$(kernel): $(KOBJS)
	@echo + ld $@
	$(V)$(LD) $(LDFLAGS) -T tools/kernel.ld -o $@ $(KOBJS)
	@$(OBJDUMP) -S $@ > $(call asmfile,kernel)
	@$(OBJDUMP) -t $@ | $(SED) '1,/SYMBOL TABLE/d; s/ .* / /; /^$$/d' > $(call symfile,kernel)

$(call create_target,kernel)

# -------------------------------------------------------------------
# create ucore.img
UCOREIMG	:= $(call totarget,ucore.img)


$(UCOREIMG): $(kernel)
	$(OBJCOPY) $(kernel) --strip-all -O binary $@

$(call create_target,ucore.img)

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

$(call finish_all)
ifeq ($(LAB2_NEED_STAMP),1)
$(ALLOBJS) $(ALLDEPS): $(LAB2_STAMP)
endif

IGNORE_ALLDEPS	= host-test \
				  clean \
				  dist-clean \
				  grade \
				  touch \
				  print-.+ \
				  handin

ifeq ($(call match,$(MAKECMDGOALS),$(IGNORE_ALLDEPS)),0)
-include $(ALLDEPS)
endif

# files for grade script

TARGETS: $(TARGETS)

.DEFAULT_GOAL := TARGETS
.PHONY: qemu spike test
qemu: $(UCOREIMG) $(SWAPIMG) $(SFSIMG)
	$(V)$(QEMU) \
		-machine virt \
		-nographic \
		-bios default \
		-device loader,file=$(UCOREIMG),addr=0x80200000

debug: $(UCOREIMG) $(SWAPIMG) $(SFSIMG)
	$(V)$(QEMU) \
		-machine virt \
		-nographic \
		-bios default \
		-device loader,file=$(UCOREIMG),addr=0x80200000\
		-s -S

gdb:
	$(GDB) \
    -ex 'file bin/kernel' \
    -ex 'set arch riscv:rv64' \
    -ex 'target remote localhost:1234'

test: $(UCOREIMG) $(SWAPIMG) $(SFSIMG)
	$(V)$(QEMU) \
		-machine virt \
		-nographic \
		-bios default \
		-device loader,file=$(UCOREIMG),addr=0x80200000
spike: $(UCOREIMG) $(SWAPIMG) $(SFSIMG)
	$(V)$(SPIKE) $(UCOREIMG)

.PHONY: grade touch

GRADE_GDB_IN	:= .gdb.in
GRADE_QEMU_OUT	:= .qemu.out
HANDIN			:= proj$(PROJ)-handin.tar.gz

TOUCH_FILES		:=

MAKEOPTS		:= --quiet --no-print-directory

GRADE_TMP	:= /tmp/lab2_grade

grade:
	@test "$(PMM):$(SLUB):$(EXT_TEST)" = "best_fit:0:0" || { echo 'grade requires PMM=best_fit SLUB=0 EXT_TEST=0'; exit 1; }
	$(V)$(MAKE) $(MAKEOPTS) clean
	$(V)$(RM) -rf $(GRADE_TMP)
	$(V)$(MKDIR) $(GRADE_TMP)
	$(V)tar -C . --exclude=.git --exclude=.vscode --exclude=vcs -cf - . | tar -C $(GRADE_TMP) -xf -
	$(V)python3 tools/inject.py $(GRADE_TMP)
	$(V)cd $(GRADE_TMP) && $(SH) tools/grade.sh
	$(V)$(RM) -rf $(GRADE_TMP)

touch:
	$(V)$(foreach f,$(TOUCH_FILES),$(TOUCH) $(f))

print-%:
	@echo $($(shell echo $(patsubst print-%,%,$@) | $(TR) [a-z] [A-Z]))

.PHONY: clean dist-clean handin packall tags
clean:
	$(V)$(RM) $(GRADE_GDB_IN) $(GRADE_QEMU_OUT) cscope* tags
	-$(RM) -r $(OBJDIR) $(BINDIR)

dist-clean: clean
	-$(RM) $(HANDIN)

handin: packall
	@echo Please visit http://learn.tsinghua.edu.cn and upload $(HANDIN). Thanks!

packall: clean
	@$(RM) -f $(HANDIN)
	@tar -czf $(HANDIN) `find . -type f -o -type d | grep -v '^\.*$$' | grep -vF '$(HANDIN)'`

tags:
	@echo TAGS ALL
	$(V)rm -f cscope.files cscope.in.out cscope.out cscope.po.out tags
	$(V)find . -type f -name "*.[chS]" >cscope.files
	$(V)cscope -bq 
	$(V)ctags -L cscope.files

# lab2 2511955: final wrap-up, environment setup and verification review.
.PHONY: host-test
host-test:
	python3 tests/run_host_tests.py
