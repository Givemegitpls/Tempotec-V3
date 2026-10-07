# ghidra-mcp — ускоритель реверса (опционально)

`github.com/bethington/ghidra-mcp` — MCP-сервер к Ghidra: Java-плагин/headless
server с HTTP API на `127.0.0.1:8089` и Python-мост `bridge-mcp-ghidra` для MCP-клиента.
250+ инструментов: декомпиляция, xref/call-graph, строки, типы/структуры, P-code
эмуляция, batch-операции, перенос документации между ревизиями бинаря.

Требования: **Java 21**, **Ghidra 12.1.3+**, **Python 3.10+** с `uv`.

## Вариант 1. На хосте (проще)

```bash
# Arch: yay -S ghidra-mcp   (или ghidra-mcp-git)
# Иначе:
git clone https://github.com/bethington/ghidra-mcp
cd ghidra-mcp
curl -LsSf https://astral.sh/uv/install.sh | sh          # если uv нет
python3 -m tools.setup preflight --ghidra-path /opt/ghidra
python3 -m tools.setup ensure-prereqs --ghidra-path /opt/ghidra
python3 -m tools.setup build
python3 -m tools.setup deploy --ghidra-path /opt/ghidra  # ставит extension, может стартовать Ghidra
```

Затем в Ghidra (CodeBrowser): **File > Configure > Configure All Plugins > GhidraMCP**
включить, **Tools > GhidraMCP > Start MCP Server**. Проверка:

```bash
curl http://127.0.0.1:8089/check_connection
curl http://127.0.0.1:8089/get_version
curl http://127.0.0.1:8089/mcp/schema      # список инструментов и групп
```

Мост к MCP-клиенту (stdio) — конфиг клиента (абсолютный путь к `uv`!):

```json
{
  "mcpServers": {
    "ghidra-mcp": {
      "command": "/home/<you>/.local/bin/uv",
      "args": ["run", "--directory", "/path/to/ghidra-mcp", "bridge-mcp-ghidra", "--transport", "stdio"],
      "env": { "GHIDRA_MCP_URL": "http://127.0.0.1:8089" }
    }
  }
}
```

## Вариант 2. Docker (headless)

`Dockerfile.ghidra-mcp` (см. рядом) собирается поверх `hiby-ghidra` и запускает
headless-сервер:

```bash
docker build -t hiby-ghidra-mcp -f docker/Dockerfile.ghidra-mcp docker
docker run --rm -p 127.0.0.1:8089:8089 -v "$PWD:/work" -w /work hiby-ghidra-mcp \
  java -jar /opt/ghidra-mcp/GhidraMCPHeadless.jar --bind 0.0.0.0 --port 8089
```
> Dockerfile **экспериментальный**: имена артефактов/шаги `tools.setup` зависят от
> версии ghidra-mcp. Если сборка не прошла — используй вариант 1 и/или сверься с
> README репозитория. Порт наружу только на loopback.

## Полезные настройки (env)

| переменная | смысл |
|---|---|
| `GHIDRA_MCP_URL` | адрес HTTP-сервера (по умолчанию `http://127.0.0.1:8089`) |
| `GHIDRA_MCP_LAZY=0` | отключить ленивую загрузку инструментов (для клиентов без `tools/list_changed`) |
| `GHIDRA_MCP_REQUIRE_PROGRAM_SELECTORS=1` | требовать явный `program=` (мультипрограммная безопасность) |
| `GHIDRA_MCP_ALLOW_SCRIPTS=1` | разрешить исполнение скриптов (по умолчанию выключено) |
| `GHIDRA_MCP_AUTH_TOKEN`, `GHIDRA_MCP_FILE_ROOT` | если сервер выставлен за loopback |

## Минимальный набор инструментов (read-only)

`get_metadata`, `list_methods`, `get_entry_points`, `decompile_function`
(+ по мере надобности `get_function_callers/callees`, `get_xrefs_to`, `list_strings`,
`search_functions`). Под `--lazy` эти группы (`listing,function,program`) уже загружены.

## Зачем нам

- Быстрые xref и call-graph без ручного `xref.py`.
- Декомпиляция пачками, перенос имён/типов между ревизиями `hiby_player`.
- P-code эмуляция — для проверки гипотез о том, что читает функция.

Не заменяет `docs/02-workflow.md`: те же инварианты (VA-конвертация, RX-запись,
кэш списков) действуют.
