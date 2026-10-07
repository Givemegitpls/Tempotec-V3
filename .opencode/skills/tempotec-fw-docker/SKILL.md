---
name: tempotec-fw-docker
description: "Use when you need the toolchain for Tempotec V3 Analog / HiBy firmware work: building or using the docker image with 7z, ubi_reader, mkfs.ubifs, genisoimage, radare2, capstone, pyelftools. Covers building the image, running commands through docker/fw.sh, and known environment pitfalls."
---

# Docker-среда для работы с прошивкой Tempotec V3 Analog

Всё делается внутри одного docker-образа `tempotec-fw-tools`; в систему ничего
не ставится. Обёртка `docker/fw.sh` монтирует каталог проекта в `/work` и
запускает команду там.

## Сборка образа

```
docker build -t tempotec-fw-tools docker
```
Dockerfile: `docker/Dockerfile` (ubuntu 24.04 + `mtd-utils`, `genisoimage`,
`p7zip-full`, `squashfs-tools`, `cpio`, `patch`, `binutils`, `vim-common`,
`python3-pip`, `python3-lzo`, `python3-pyelftools`, `python3-capstone`,
`radare2`, плюс `pip3 install ubi_reader`).

## Запуск команд

```
./docker/fw.sh <команда> [аргументы]
```
Например:
```
./docker/fw.sh bash -c 'ls /work/fw'
./docker/fw.sh python3 tools/xref.py fw/SYSTEM/usr/bin/hiby_player "SELECT DISTINCT album"
./docker/fw.sh r2 -q -A -c 'pd 20 @ 0x4c9278' fw/SYSTEM/usr/bin/hiby_player
```

Контейнер работает **от root** — это обязательно: `ubireader_extract_files -k`
создаёт симлинки и device-ноды, а `mkfs.ubifs` записывает uid/gid (`1004:1004`)
как в оригинальной прошивке.

## Что внутри пригодится

| задача | команда |
|---|---|
| ISO (`.upt`) | `7z x -y <файл> -o<каталог>` |
| распаковать UBI/UBIFS | `ubireader_extract_files -k -o SYSTEM SYSTEM.UBI` |
| собрать UBI/UBIFS | `mkfs.ubifs -x lzo -d SYSTEM -e 0x1F000 -c 480 -m 0x800 -o SYSTEM.UBI` |
| собрать ISO | `genisoimage -l -o out.upt SYSTEM.UBI UIMAGE.BIN UBOOT.BIN UPDATE.TXT VERSION.TXT _GITIGNO` |
| md5 | `md5sum`, `python3` со `hashlib` |
| поиск ссылок в MIPS-бинарнике | `python3 tools/xref.py` (capstone) |
| дизасм/анализ | `radare2` (`r2 -q -A -c 'pd N @ addr'`), `objdump`, `strings` |

## Грабли окружения

- `/tmp` на хосте — tmpfs с `usrquota`: распаковка больших деревьев в `/tmp`
  падает с `EPERM`. Промежуточные файлы держать в каталоге проекта (`work/`, `fw/`).
- Каталог проекта монтируется в `/work`; пути внутри команды давать относительно
  него (`fw/SYSTEM/...`), а не от `/tmp`.
- `capstone` без `md.skipdata = True` декодирует только ~3% кода MIPS — для
  сканирования всего `.text` флаг обязателен (см. `tools/xref.py`).
- Образ нужно пересобирать после правки `docker/Dockerfile`
  (`docker build -t tempotec-fw-tools docker`).

Готовый пайплайн сборки самой прошивки — скилл `tempotec-fw-mod`.
