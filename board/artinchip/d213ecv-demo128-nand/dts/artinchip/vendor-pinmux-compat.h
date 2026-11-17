/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Copyright (c) 2020-2025 ArtInChip Inc.
 * AIC_PINMUX_U encoding from Luban U-Boot's aic-pinctrl.h.
 * Preserve the reference DTS's unused alternate groups without changing values.
 */
#ifndef ARTINCHIP_VENDOR_PINMUX_COMPAT_H
#define ARTINCHIP_VENDOR_PINMUX_COMPAT_H
#define AIC_PINMUX_U(port, pin, func) (((port - 'A' - 14) << 16) | (pin << 8) | func)
#endif
