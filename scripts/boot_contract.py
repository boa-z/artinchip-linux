#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Static board checks; these cannot establish a physical boot result."""
import subprocess
from riscv_image import require


def prop(path, node, key, kind='s'):
    return subprocess.check_output(['fdtget', '-t', kind, str(path), node, key], text=True).strip()


def cells(path, node, key):
    return [int(x, 16) for x in prop(path, node, key, 'x').split()]


def check_dtb(path):
    cpu = '/cpus/cpu@0'
    uart = prop(path, '/aliases', 'serial0')
    require(cells(path, '/memory@40000000', 'reg') == [0, 0x40000000, 0, 0x8000000], 'DTB DDR mismatch')
    require(cells(path, cpu, 'reg') == [0], 'DTB boot hart must be 0')
    require(prop(path, cpu, 'status') == 'okay', 'DTB CPU disabled')
    require(prop(path, cpu, 'mmu-type') == 'riscv,sv39', 'DTB MMU mismatch')
    isa = prop(path, cpu, 'riscv,isa')
    require(isa.startswith('rv64'), 'DTB CPU ISA is not RV64')
    require(cells(path, '/cpus', 'timebase-frequency')[0] > 0, 'DTB timer frequency invalid')
    require(prop(path, uart, 'compatible') == 'artinchip,aic-uart-v1.0', 'DTB UART match mismatch')
    require(cells(path, uart, 'reg')[:2] == [0, 0x18710000], 'DTB UART address mismatch')
    require(cells(path, uart, 'reg-shift') == [2] and cells(path, uart, 'reg-io-width') == [4], 'DTB UART access mismatch')
    require(prop(path, uart, 'status') == 'okay', 'DTB console UART disabled')
    require(prop(path, '/chosen', 'stdout-path') == 'serial0:115200n8', 'DTB stdout mismatch')
    for node, compat in [('/soc/clint@24000000', 'riscv,clint0'),
                         ('/soc/interrupt-controller@20000000', 'riscv,plic0')]:
        require(prop(path, node, 'compatible') == compat, 'DTB interrupt/timer compatible mismatch')
        require(bool(cells(path, node, 'interrupts-extended')), 'DTB interrupt routing absent')
    intc = cells(path, cpu + '/interrupt-controller', 'phandle')[0]
    require(cells(path, cpu + '/interrupt-controller', '#interrupt-cells') == [1], 'DTB CPU interrupt cells mismatch')
    require(cells(path, '/soc/clint@24000000', 'interrupts-extended') == [intc, 3, intc, 7],
            'DTB CLINT hart routing mismatch')
    require(cells(path, '/soc/interrupt-controller@20000000', 'interrupts-extended') ==
            [intc, 0xffffffff, intc, 9], 'DTB PLIC hart routing mismatch')
    reserved = []
    nodes = subprocess.check_output(['fdtget', '-l', str(path), '/reserved-memory'], text=True).split()
    for name in nodes:
        node = '/reserved-memory/' + name
        keys = subprocess.check_output(['fdtget', '-p', str(path), node], text=True).split()
        require('reg' in keys, 'Dynamic DTB reserved-memory requires explicit RAM plan')
        values = cells(path, node, 'reg')
        require(len(values) % 4 == 0, 'Unsupported reserved-memory address/size cells')
        for i in range(0, len(values), 4):
            start = (values[i] << 32) | values[i + 1]
            size = (values[i + 2] << 32) | values[i + 3]
            reserved.append((name, start, start + size))
    return {'cpu_isa': isa, 'uart': uart, 'bootargs_in_file': prop(path, '/chosen', 'bootargs'),
            'reserved': reserved, 'runtime_bootargs': 'must inspect U-Boot fixed-up DTB on board'}


def check_config(path, diagnostic=False):
    values = {}
    for line in path.read_text().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
            values[key] = value
    required = ['ARCH_ARTINCHIP', 'MACH_D211', 'RISCV_SBI', 'MMU', 'PRINTK', 'SERIAL_EARLYCON',
                'SERIAL_EARLYCON_RISCV_SBI', 'SERIAL_8250', 'SERIAL_8250_CONSOLE',
                'SERIAL_8250_ARTINCHIP', 'ERRATA_THEAD', 'ERRATA_THEAD_MAE', 'ERRATA_THEAD_CMO',
                'MTD_UBI', 'UBIFS_FS']
    if diagnostic:
        required += ['D213ECV_EARLY_DEBUG', 'RISCV_SBI_V01']
    for name in required:
        require(values.get('CONFIG_' + name) == 'y', 'Required built-in CONFIG_' + name + '=y missing')
    require(values.get('CONFIG_RISCV_M_MODE') != 'y', 'S-mode FIT cannot boot M-mode Linux')
    return {'required_builtins': required, 'code_model': 'medlow' if values.get('CONFIG_CMODEL_MEDLOW') == 'y' else 'medany',
            'sbi_v01': values.get('CONFIG_RISCV_SBI_V01', 'n'),
            'earlycon_sbi_compatible_with_vendor_0_9': values.get('CONFIG_RISCV_SBI_V01') == 'y'}
