# Artists vs «Исполнитель альбома»: список альбомов (СДЕЛАНО, проверено на устройстве)

Статус на 2026-10-08: **проверено пользователем на плеере — Artists→`Дэн Субботин`
= 5, «Исполнитель альбома»→`Дэн Субботин` = 2.** Читать вместе с
`.opencode/NOTES.md` (раздел «Разведение Artists / Исполнитель альбома») и
`docs/ui-queries.md`.

## Цель (достигнута правкой)

- **Artists** (тег `artist`, соавторы разбиты на отдельных) → список альбомов по
  **составляющей** тега `artist` (у `Дэн Субботин` = **5**).
- **Исполнитель альбома** (тег `album_artist`) → список альбомов по
  `album_artist` (у `Дэн Субботин` = **2**).
- Раньше оба показывали 5/5 (один вид, один источник, один запрос).

## Решение (реализовано, `tools/exp_albums_artist_album_artist.py`)

Разделы различимы по **ключу дочернего вида** — он есть, но раньше терялся.

1. **Ключ вида хранит префикс.** Открыватель Artists `FUN_004a8b20` передаёт
   префикс ключа `L"artist"` (@0x960b3c), открыватель «Исполнителя альбома»
   `FUN_004aa1a0` — `L"album_artist"` (@0x960b30). Ключ дочернего вида =
   `<префикс>\<имя>` (`FUN_004a7500`+`FUN_0049d6e0`): `artist\Дэн` /
   `album_artist\Дэн`. Подтверждено heap-дампом (`hdv2.bin`): у живого
   `vg_listview_album` `view+0x3de0 = L"artist\Anacondaz"`.
2. **Источник списка `FUN_004a9180`.** `param_1` — виджет (не вид);
   `FUN_004627e0(widget)=widget+0x7c=вид`; ключ `= view+0x3de0`. Далее:
   - `FUN_0049d760` (@0x4a9214) **обрезал** ключ после `\` и клал голое имя в
     `rec+0x52c`;
   - `FUN_0070a3a0(9,…)` → `FUN_00708d20` **case 9** биндит `rec+0x52c` к слоту
     182 (`SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ?`).
   Отсюда оба раздела получали одинаковый фильтр → 5/5.

**Правка (2 точки):**
1. `0x4a9214`: `jal FUN_0049d760` (0x0C1275D8, обрезка) → `jal FUN_00420f20`
   (0x0C1083C8, bounded wide-копия; `a2=0x80` уже выставлен). Теперь `rec+0x52c`
   = ПОЛНЫЙ ключ `artist\ИМЯ` / `album_artist\ИМЯ`.
2. Слот 182 (SQL) → строка в `.rodata` @0x93fb00: при ключе `album_artist\%` —
   фильтр по составляющей `album_artist`, при `artist\%` — по `artist`
   (обе через `(';'||substr(x,1,length(x))||';') LIKE '%;'||…||';%'`).
   Верхние «Альбомы» (ключ `album`) дают 0 строк в `list_tb`, но берут данные из
   `ALBUM_TABLE` через ветку `FUN_0070b020` — поведение не меняется.

Проверено offline на копии реальной БД (3798 треков): `artist\Дэн Субботин`→5,
`album_artist\Дэн Субботин`→2, `artist\Anacondaz`→16, `album`→0 (в т.ч. с
хвостовым NUL, как биндит плеер).

## Переключатель «треки» в «Исполнителе альбома» (`tools/exp_toggle_album_artist.py`)

Отдельный фикс: кнопка `sub_back_iv_list_type` (обработчик `FUN_004c7ba0`) общая
для Artists и «Исполнителя альбома», и для вида `vg_listview_album` строила ключ
`artist_all\<имя>` → открывала `vg_listview_songs_of_artist_all` (kind 5,
`WHERE artist like ?`). Поэтому в Album Artist переключатель показывал 13 треков
по `artist` вместо 2 по `album_artist`.

Патч (3 точки, без RX — заглушка в `.text`-пещере `0x419328`):
1. `0x4c7c40`: `jal 0xa7d710`(`0x0C29F5C4`, strlen) → `jal 0x419328`(`0x0C1064CA`);
2. заглушка: вид `vg_listview_songs_of_an_album_artist` → назад в
   `vg_listview_album`; вид `vg_listview_album` + ключ начинается с
   `album_artist\` → открыть `vg_listview_songs_of_an_album_artist` (type 0x63,
   kind 0x21, `WHERE album_artist = ?`) с тем же ключом; иначе `fallback`
   (воспроизвести `strlen` и вернуться в `0x4c7c48`) — Artists/жанры без изменений;
3. jump-таблица панели `0x96429c`, idx `0x63` @`0x964428`: `0x4c7618` → `0x4c74f0`
   (показать кнопку на трек-списке для возврата).

## Что НЕ сработало (НЕ повторять — теперь понятно почему)

1. `exp_albums_by_section.py` (удалён) — патчил **не тот буфер**: `0x4a9274`
   пишет полный ключ в `sp+0x24` (для `FUN_0070b020`), а слот 182 питается из
   `rec+0x52c` (`0x4a9214`). CASE не видел префикса → 5/5.
2. `exp_albums_album_artist.py` (удалён) — флаг от обёрток + подмена стейтмента
   `manager+0x4ac`: `manager+0x4ac` — это поиск ИНДЕКСА списка по ключу, а не
   запрос альбомов.
3. Правка `0x4a9278` (`move a1,s6` → `addiu a1,s0,0x3de0`): пустые списки.
4. Стаб на `0x4a9274` (склейка `категория\имя` в `sp+0x24`): 5/5 (см. п.1).

## Адреса и грабли (шпаргалка)

- Менеджер: `*(0xbc18f0)`; поле 0 = `sqlite3*`. `FUN_005f0be0` = exec,
  `FUN_00606140` = prepare, `FUN_005b2fa0` = bind, `FUN_005efe80` = step,
  `FUN_005a1240` = column, `FUN_005d35c0` = reset, `FUN_005d34e0` = finalize.
- Слоты SQL: база `0x9b7730` (199 × 4). Слот 182 — список альбомов артиста,
  183 — по жанру. Дамп: `tools/dump_sql_slots.py` → `work/sql_slots*.txt`.
- `FUN_00420f20(dst,src,n)` — bounded wide-копия (n символов, NUL-terminate);
  `FUN_00420ee0(dst,src)` — без ограничения; `FUN_0049d760(dst,src,n)` — копия
  после первого `\`.
- `FUN_0070a3a0` — сборка подсписков; jump-таблица kind→handler `0x9b70c8`
  (kind 5..0x21), kind 9 → `0x70a57c`.
- Свободный код: `.text`-пещера `0x419327..0x41bae0` (~10 КБ нулей, ссылок нет,
  R+X). `.rodata`: `0x93fa00` (All), `0x93fb00` (слот 182), до `0x93fd00`.
- `jal`/`j` из RX/пещеры — только через `jalr`; из обычного `.text` — можно `jal`.
- Флаги `open` MIPS o32: `O_WRONLY=0x1`, `O_CREAT=0x100`, `O_APPEND=0x8`.
- Права `usr/bin/hiby_player` — `775` (иначе бутлуп); `make.sh build` это делает.
- adb: поднимается `overlay/etc/init.d/S98adb_debug` только при маркере
  `/mnt/sd_0/enable_adb` в момент загрузки.

## Сборка и проверка

Образ: `out/v3_analog_aa_toggle.upt` (ISO md5 `7eba4824f28db0f91ec00e769ba3419b`,
SYSTEM.UBI `7996b273b6b2e5709503c5289d66fa9a`, бинарь `c77cc2703ca95f7a1deab566d65b1ad7`);
предыдущая (без переключателя) — `out/v3_analog_aa_split.upt`.
Цепочка: `patch_player --album-level → patch_sql → exp_album_view →
exp_flags_view21 → exp_coverpath_combo → exp_cover_kind9col → exp_cover_kind9id →
exp_shuffle_linear → exp_shuffle_guard → exp_artist_toggle →
exp_toggle_album_artist → exp_all_sort → exp_albums_artist_album_artist →
exp_artist_tracks_component → exp_db_autofix`
(`exp_albums_by_component` заменён новым скриптом; `exp_albums_by_section` и
`exp_albums_album_artist` удалены). Проверка: `python3 tools/verify_build.py <bin>
[--image out/x.upt] [--db <копия>]` → ИТОГ: OK.

## Проверка на устройстве (ПРОЙДЕНА 2026-10-08)

1. `adb push fw/SYSTEM/usr/bin/hiby_player /usr/bin/hiby_player` → `chmod 755` →
   `sync` → `reboot` (или прошить `out/v3_analog_aa_toggle.upt`).
2. Artists → `Дэн Субботин` = **5** альбомов. ✓
3. Исполнитель альбома → `Дэн Субботин` = **2** альбома. ✓
4. Переключатель в «Исполнителе альбома» → **2 трека** (по `album_artist`); ещё
   раз → назад к 2 альбомам. ✓
5. Artists → переключатель → **13 треков** (не сломано). ✓
6. Albums / Genres — без изменений. ✓
7. Перед первым тестом очищен кэш списков (`tools/clear_list_cache.py`), иначе
   старый `list_tb` под ключом `album_artist\Дэн` показывал бы 5.
