# D213ECV-DEMO-V4-0 操作说明

唯一实板目标是 **D213ECV-DEMO-V4-0**。`d211_demo128_nand` 是原厂遗留配置名，
不能据此将实际 SoC 识别成 D211。详细构建命令、版本与分区表见
[英文主文档](m1-d213ecv.md)。

## 当前验证边界

必须分别记录“编译通过”“封装及静态校验通过”“实板启动通过”。没有从复位开始的
实板串口日志，就不能将 M1 标记为硬件验证完成。Rootfs 的 ABI、UBIFS 几何及压缩
检查不等同于已经在原厂 Linux 5.10 上挂载成功。

## 首次烧录：只更新 Rootfs

1. 保存该板可用的原厂完整固件及恢复步骤。确认板卡版本、NAND 容量和实际页/块
   参数，记录当前启动环境与分区信息。
2. 按英文文档构建 `d213ecv-demo128-nand`，编译原厂启动组件并生成
   `artifacts/d213ecv-stock510-rootfs-update/d213ecv-demo128-nand.img`。
3. 在产物目录执行 `sha256sum -c SHA256SUMS`，再用 `scripts/firmware.py verify`
   检查 `.img`。其 NAND 写入目标必须只有 `ubiroot:rootfs`。
4. 按板卡及 AiBurn 对应版本的说明进入 USB 下载模式，选择上述 `.img`。
   核对写入列表，不启用整片擦除、重新分区或覆盖 Recovery 的选项。
   如果工具不能确认分区保护，先不要烧录；先确认使用的是支持该板的原厂工具版本。
5. 完成后断开下载流程并正常复位。首轮保留 NAND 中的原厂 Linux 5.10、SPL、
   U-Boot 和 Recovery，验证新 Rootfs。镜像中的 updater 组件用于 RAM 下载运行，
   与 NAND 中的持久化写入目标不同。

禁止把 `rootfs.ubi` 或 `.ubifs` 当作全片 NAND 镜像用 `dd` 写入。UBI 的坏块处理
和卷更新应由匹配的原厂升级程序执行。

## 串口验证

依据板卡手册确认 UART 引脚与电平；使用匹配的 3.3 V TTL 串口、共地和 TX/RX，
不要猜测排针顺序或连接串口模块的供电引脚。设置为 **115200、8N1、无硬件流控**，
从复位前开始保存完整日志。

进入开发 Shell 后收集：

```sh
uname -a
cat /proc/cpuinfo
cat /proc/cmdline
cat /proc/mtd
ubinfo -a
mount
dmesg | tail -80
printf 'm1-smoke\n' > /tmp/m1-smoke
cat /tmp/m1-smoke
```

确认根文件系统为 `ubi0:rootfs`、UBIFS 正常挂载、没有几何/压缩/UBI 错误，分区表
与英文文档一致。再单独测试写入、`sync`、正常重启后的持久性。保留测试命令及返回值，
不要只保存登录提示符。

Linux 5.10 的 Rootfs 验证通过后，再评估 `d213ecv-demo128-nand-linux618`。
先记录原厂 `boot_os`、`boot_partition`、`MTD`、`UBI` 和启动命令；已有 Falcon 快速
启动快照不能直接视为适配了新内核。Linux 6.18 首次测试应走可观察的 U-Boot 路径，
不要直接复用未经验证的快速启动状态。

## 故障恢复

- UBIFS 无法挂载：保留完整错误，核对实际 NAND 页/块大小、`ubi.mtd=10`、卷名和
  原厂 5.10 内核的 UBIFS/zlib 配置；不要尝试整片擦除。
- Linux 6.18 无输出：区分 SPL、DDR、OpenSBI、U-Boot 和 Linux 阶段，核对 FIT 的
  内存地址、DTB 和 Falcon 状态。不要将 QEMU 成功当成这些阶段已经通过。
- 普通启动失败但原厂恢复功能可用：按原厂已验证的恢复方式恢复对应分区，保留
  Recovery、BBT、userid 和用户数据。恢复入口按板卡手册操作，不臆造按键或跳线步骤。
- SPL/USB 下载都不可用：停止继续写入，使用该板原厂的 ROM 下载/恢复说明和已验证
  固件处理，并保存失败前日志。

提交实板记录时标注板卡版本、固件 SHA256、测试内核、串口日志和失败点；删除凭据、
私有网络及无关主机信息。未取得这些证据前，硬件状态保持“未验证”。
