# D213ECV vendor Linux 5.10 firmware

Buildroot 2026.08.1 and the pinned Bootlin RV64 LP64D musl toolchain (GCC
14.3) build vendor Linux 5.10.44 and the independent BusyBox UBIFS rootfs.
The build imports committed vendor sources directly and uses the board DTB
from vendor U-Boot 2021.10. This matches the vendor kernel FIT contract:
uncompressed Image, load/entry `0x40000000`, and vendor OpenSBI 0.9. The
original board name in the vendor source is `d211_demo128_nand`. The tracked
patches under `board/artinchip/d213ecv-demo128-nand/linux510/linux/` carry
compiler and assembler compatibility changes.

The operator previously booted factory Linux 5.10.44 with a Buildroot rootfs
on D213ECV-DEMO-V4-0. The newly compiled kernel and rebuilt boot components
need their own hardware verification.

## Build

Run as a regular user with the project host dependencies, Git with `git archive
--mtime` support, GNU gzip, and an existing Luban Git checkout containing the
revision in `board/artinchip/d213ecv-demo128-nand/vendor-sources.json`.

```sh
python3 -m venv .cache/firmware-venv
. .cache/firmware-venv/bin/activate
pip install -r scripts/requirements-firmware.txt
./scripts/build-vendor-linux510.sh "$LUBAN_REFERENCE"
(cd artifacts/d213ecv-linux510-system-update && sha256sum -c SHA256SUMS)
```

`LUBAN_REFERENCE` is the existing local checkout path. An optional second
argument selects a fresh firmware output directory. The script verifies the
pinned vendor kernel archive and uses the same commands as GitHub Actions.
It exports `kernel-5.10.44.itb`, its memory layout report, the final Linux
configuration, the board DTB, source provenance, `SHA256SUMS`, and
`d213ecv-linux510-system-update.img`.

## 实板验证

适用于已保留原厂分区和 Recovery 的 D213ECV-DEMO-V4-0，128 MiB SPI NAND。
先用 `SHA256SUMS` 校验。串口使用 115200 8N1，无流控。

可先将 `kernel-5.10.44.itb` 放到 FAT 格式 microSD 的根目录。进入原厂
U-Boot，使用以下命令从 RAM 启动并挂载现有的 NAND 根文件系统：

```text
run set_nand_bootargs
fatload mmc 0:1 0x41200000 kernel-5.10.44.itb
iminfo 0x41200000
bootm 0x41200000#conf-1
```

命令只使用临时环境。`iminfo` 校验三项 FIT 载荷后再启动。进入 Shell 后记录
`uname -a`、`cat /proc/cmdline`、`cat /proc/mtd`、`mount` 和 `ubinfo -a`，
确认 Linux 5.10.44 与 `ubi0:rootfs`，并保留从复位开始的串口日志。

完整更新时在 AiBurn 选择 `d213ecv-linux510-system-update.img`。核对写入目标为
SPL、U-Boot（含 OpenSBI）、env、env_r、logo、kernel 与 `ubiroot:rootfs`。
保留 Recovery、BBT、userid、Falcon 及 `ubisystem:user`，禁止整片擦除或重新分区。
请备份自定义 U-Boot 环境，并备好原厂镜像。更新环境默认使用正常 U-Boot 启动路径，
支持进入原有 Recovery。失败时先复位保存完整串口日志，再按原厂流程恢复。

### AiBurn loses the device after `image.updater.spl`

The USB Boot ROM passes execution to the downloaded SPL. AiBurn then waits
for the U-Boot USB gadget to enumerate. The handoff can interrupt the final
USB response. `Dev ... lost` means the host timed out waiting for the gadget.
A log containing only `image.updater.*` shows RAM transfers. The updated
package uses the original vendor RAM environment, including `bootdelay=-3`,
and applies the normal boot settings to the NAND `env` and `env_r` payload.

若在 `Wait to reconnect` 后约 10 秒出现 `Dev ... lost`，先结束本次烧录，断电重进
USB 下载模式。将新 `.img` 复制到 Windows 本地磁盘，核对 SHA256，使用直连
USB 数据线重试。串口从开始烧录前就记录。观察是否打印
`Run USB upgrade program`，并查看设备管理器是否出现 `USB\VID_33C3&PID_6677`。

如果仍然掉线，用已验证的原厂 AiBurn 镜像对照。若原系统还能正常进入 U-Boot，
也可先按上面的 microSD 流程验证内核。请保留完整的 UART 和 AiBurn 日志、AiBurn
版本及观察到的 USB 设备 ID。若串口进入 USB 升级程序且设备已枚举，优先检查
Windows 驱动、设备绑定或虚拟机 USB 直通。若串口停在更早的位置，最后一行可用于
定位 SPL、OpenSBI 或 U-Boot 的启动阶段。
