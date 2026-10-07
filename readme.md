Распаковка/упаковка прошивки v3_analog.upt

Инструкция v3_analog.upt это ISO файл. Разобрать его можно просто в 7-zip

```
7z x v3_analog.upt
```

После распаковки имеем образ системного раздела SYSTEM.UBI, упакованное ядро
UIMAGE.BIN (которое никто из кастомизаторов не трогает), загрузчик UBOOT.BIN, и
"служебные" файлы UPDATE.TXT, VERSION.TXT, \_GITIGNO. Если какие-то из файлов
менялись при кастомизации (ядро и загрузчик обычно никто не трогает, потому речь
только о SYSTEM.UBI), то нужно пересчитать и изменить MD5 для нового SYSTEM.UBI
в файле UPDATE.TXT. Отредактировать файл можно вручную или командой

```
sed -i '7,$s/md5=.*/md5='"$(md5sum unpacked_fw/SYSTEM.UBI | cut -d\  -f1)/" unpacked_fw/UPDATE.TXT
```

Запаковать файлы обратно в v3.upt можно с помощью mkisofs / genisoimage :

```
genisoimage -l -o v3_analog.upt unpacked_fw/{SYSTEM.UBI,UIMAGE.BIN,UBOOT.BIN,UPDATE.TXT,VERSION.TXT,_GITIGNO}
```

Распаковка образа системного раздела SYSTEM.UBI в Linux (Владелец/группа файлов
и директорий 1004:1004 , я всегда правлю для замененных файлов. А может не
обязательно...) (для плееров HiBy 1009:1009)

```
sudo ubireader_extract_files SYSTEM.UBI -o SYSTEM -k
```

Упаковка SYSTEM в SYSTEM.UBI в Linux

```
mkfs.ubifs -x lzo -d SYSTEM -e 0x1F000 -c 480 -m 0x800 -o SYSTEM.UBI
```

где LEB Size: 126976 | max_leb_cnt: 480 | min_io_size: 2048

Чтобы просто поковыряться в \*.upt прошивках плееров на HiBy OS, сравнить
изменения в прошивках, можно не ходить в Linux/вирт. машину, а распаковывать
прошивки в Windows известным "редактором тем" (содержит портативные сборки
ubireader_extract_files и mkfs.ubifs) и сравнивать содержимое папок system
(различия файлов) разных прошивок в программе WinMerge. Я так делаю.

Сборка/разборка в этом каталоге (весь софт в docker, в систему ничего не
ставится — образ собран из `docker/Dockerfile`):

```
./tools/make.sh unpack   # v3_analog.upt.txt -> fw/unpacked (ISO) + fw/SYSTEM (UBIFS)
./tools/make.sh patch    # правки бинарей (tools/patch_player.py)
./tools/make.sh build    # fw/SYSTEM -> SYSTEM.UBI -> md5 в UPDATE.TXT -> out/v3_analog_patched.upt
./tools/make.sh verify   # распаковать результат и сверить дерево и md5
./tools/make.sh all      # всё подряд
```

`make.sh build` перед упаковкой: копирует `overlay/` в дерево (так в сборке
оказывается `etc/init.d/S98adb_debug` — adb по маркеру), схлопывает дубликаты
файлов (`tools/dedupe_rootfs.py`) и выставляет права `775` на `hiby_player`
(иначе плеер не запустится — бутлуп).

Проверки ДО флеша: `python3 tools/verify_build.py <bin> [--image out/x.upt]
[--db <копия базы>]` — права дерева, все `--check` патчей, целостность образа и
offline-симуляция правок БД. Самодостаточная медиатека: SQL-фикс генерируется
`tools/make_db_fix_sql.py`, выполняется бинарём (хук `tools/exp_db_autofix.py`).

Готовые образы (подробно — в `CHANGELOG.md`):
- `out/v3_analog_selfdb5.upt` — **релиз**: всё из `v3_analog_artist_stock.upt`
  плюс **самодостаточная медиатека** (после «обновления медиатеки» прошивка сама
  расставляет буквы, разбирает совместных исполнителей по `;` и пересобирает
  списки — без компьютера) и adb по маркеру `/mnt/sd_0/enable_adb`; ISO
  `38e4c70f…`, UBI `18d3dff3…`;
- `out/v3_analog_artist_stock.upt` — предыдущий релиз: всё из
  `v3_analog_artist_toggle.upt` плюс Artists по тегу `artist` (как в стоке) и
  постоянный фикс сортировки списка «All»;
- `out/v3_analog_artist_toggle.upt` — предыдущий релиз: всё из
  `v3_analog_shuffle.upt` плюс переключатель «список альбомов ⇄ список треков»
  в Artists (и обложки в «исполнителе альбома»);
- `out/v3_analog_artist_stock_adb.upt` — то же + отладочный `S98adb_debug`
  (гаджет `adb` без `mass_storage`, поэтому карта не отваливается от USB);
  ISO `3851f6c6…`, UBI `1381a479…`;
- `out/v3_analog_artist_toggle_adb.upt` — старый отладочный образ (на базе
  `artist_toggle`, без правок «Artists по тегу»/«All»);
- `out/v3_analog_shuffle.upt` — предыдущий релиз: всё из `v3_analog_coverid.upt`
  плюс обратимый случайный порядок («назад → вперёд» возвращает тот же трек);
- `out/v3_analog_coverid.upt` — предыдущий релиз: обложки альбомов в разделе
  «Artists → артист» (по одной своей на альбом) и фильтр альбомов по `album_artist`;
- `out/v3_analog_artists.upt` — предыдущий релиз (без обложек в Artists): альбом
  показывает все треки; у «исполнителя альбома» есть уровень «альбомы»; таблицы
  списков сортируются по букве, а «Артисты» показывают авторов альбомов — поэтому
  поиск по алфавиту находит русские имена;
- `out/v3_analog_artists_with_adb.upt` — то же, но с отладочным adb-скриптом;
- `out/v3_analog_patched.upt` — только правка списка треков альбома;
- `out/v3_analog_patched_albumlevel.upt` — то же плюс уровень «альбомы».

SQL-правки списков лежат в `tools/patch_sql.py` (слоты таблицы запросов),
правки кода — в `tools/patch_player.py`; проверить состав:
`./docker/fw.sh python3 tools/patch_sql.py --check <hiby_player>`.

Произвольная команда внутри контейнера с инструментами: `./docker/fw.sh <команда>`.

Дополнительные полезные ссылки/инструменты/скрипты скрипты
https://github.com/SuperTaiyaki/hiby-firmware-tools утилита ubireader
https://github.com/jrspruitt/ubi_reader для распаковки system.ubi вместо
монтирования UBI image. скрипты на python от snoopy112
https://github.com/snoopy112/FW-tool
