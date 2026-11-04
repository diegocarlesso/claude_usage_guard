#!/usr/bin/env python3
r"""
claude_usage_guard.py — guarda de consumo para o Claude Code
=============================================================

Monitora as janelas de uso de 5 horas e de 7 dias da sua assinatura Claude
(Pro/Max) e aplica mitigações automáticas *dentro* da sua sessão do Claude
Code: /compact, /clear, troca para Haiku e failover via proxy local.

-----------------------------------------------------------------------------
POR QUE ISSO REDUZ CONSUMO
-----------------------------------------------------------------------------
A cada turno o Claude Code reenvia o histórico inteiro da conversa + CLAUDE.md
+ arquivos lidos. O custo de cada turno cresce com o tamanho do contexto, e o
custo acumulado da sessão cresce mais rápido ainda. Os limites são aplicados
pelo servidor e não podem ser desligados; o que dá para fazer legitimamente é:
  * mandar menos tokens por turno (/compact, /clear);
  * usar um modelo mais barato para trabalho rotineiro (Haiku);
  * quando a cota acaba, mandar o tráfego para outro backend que você controla
    (ex.: Ollama local/Cloud ou uma chave de API paga) via proxy local.

-----------------------------------------------------------------------------
COMO FUNCIONA (e o que o CLI do Claude Code NÃO oferece)
-----------------------------------------------------------------------------
* O CLI `claude` NÃO tem flags `--clear` / `--compact`. Comandos de barra só
  existem dentro da sessão interativa. Por isso este script roda o `claude`
  dentro de um pseudo-terminal (PTY) e "digita" `/compact`, `/clear`,
  `/model haiku` etc. no prompt, só quando é seguro.
* "Seguro" é decidido com hooks do próprio Claude Code (injetados via
  `--settings`, sem mexer no seu settings.json): o script só digita algo
  quando o último evento foi `Stop`/`SessionStart` (Claude parado no prompt),
  não há saída na tela há N segundos, você não digita há N segundos e não há
  texto pela metade no campo de entrada. Durante prompts de permissão o estado
  é "ocupado", então o script nunca aperta Enter numa caixa de permissão.
* `ANTHROPIC_BASE_URL` só vale quando o processo inicia. O failover no meio
  da sessão (opcional) envia `/exit` e reabre a mesma conversa com
  `claude --resume <id>` apontando para o proxy.
* O uso vem de `GET https://api.anthropic.com/api/oauth/usage` (o mesmo dado
  que o `/usage` mostra). É um endpoint interno, sem documentação: o formato
  pode mudar. O script lê o token OAuth de `~/.claude/.credentials.json`
  (campo `claudeAiOauth.accessToken`) ou, no macOS, do Keychain
  ("Claude Code-credentials"). O script NUNCA renova o token: renovar troca o
  refresh token e poderia deslogar o Claude Code. Se o token expirar, basta
  usar o `claude` normalmente; ele renova sozinho e o guard relê o arquivo.

-----------------------------------------------------------------------------
INSTALAÇÃO
-----------------------------------------------------------------------------
  Requisitos: Python 3.9+, Claude Code instalado e logado.
  Linux/macOS: nenhuma dependência. PyYAML é opcional (`pip install pyyaml`);
  sem ele o script usa um leitor YAML interno que cobre o config.yaml.

    chmod +x claude_usage_guard.py
    cp config.yaml ~/.claude-usage-guard/config.yaml   # ou use --config

  Windows 10 (1809+) / 11, Claude Code nativo (sem WSL):
    * `run` usa o pseudo-console do Windows (ConPTY) via pywinpty:
          py -m pip install pywinpty
    * Ou gere o .exe (já inclui o pywinpty) com build_exe.bat; o resultado
      fica em dist\claude_usage_guard\claude_usage_guard.exe, com o
      config.yaml ao lado. Use o .exe exatamente como o script:
          claude_usage_guard.exe run
    * Credenciais: %USERPROFILE%\.claude\.credentials.json
      Estado/logs: %USERPROFILE%\.claude-usage-guard\
    * Funciona com o claude.exe do instalador nativo e com o claude.cmd do
      npm (o guard lê o .cmd e chama o node direto, sem cmd.exe).
    * Prefira uma pasta sem espaços no caminho (ex.: F:\Projetos\...): o
      comando dos hooks precisa funcionar no shell que o Claude Code usa.
    * Rode no Windows Terminal ou no console padrão; o dashboard em outra aba.

-----------------------------------------------------------------------------
CONFIGURAÇÃO
-----------------------------------------------------------------------------
  Ordem de busca: --config, $CUG_CONFIG, ~/.claude-usage-guard/config.yaml,
  config.yaml ao lado deste script. Qualquer chave pode ser sobrescrita por
  variável de ambiente: CUG_ + caminho em maiúsculas, separado por "_":
      CUG_POLL_INTERVAL_SECONDS=180
      CUG_COMPACT_SESSION_THRESHOLD=55
      CUG_FAILOVER_ENABLED=true
      CUG_CLAUDE_EXTRA_ARGS='["--permission-mode","plan"]'   (listas: JSON)

-----------------------------------------------------------------------------
USO
-----------------------------------------------------------------------------
  (no Windows troque ./claude_usage_guard.py por claude_usage_guard.exe
   ou por `py claude_usage_guard.py`)
  ./claude_usage_guard.py run                 # abre o Claude Code protegido
  ./claude_usage_guard.py run -- --continue   # args após "--" vão para o claude
  ./claude_usage_guard.py dashboard           # painel ao vivo (outro terminal/tmux)
  ./claude_usage_guard.py status [--json]     # leitura única do uso
  ./claude_usage_guard.py signal clear        # pede /clear quando a tarefa
                                              #   atual terminar
  ./claude_usage_guard.py check-config        # valida config e credenciais
  ./claude_usage_guard.py install-desktop     # modo Claude Desktop (ver abaixo)
  ./claude_usage_guard.py demo                # simulação offline (sem rede)

  Dentro do próprio Claude Code dá para sinalizar "tarefa concluída" com o
  modo bash:  `! ./claude_usage_guard.py signal clear`  (a variável
  CUG_INSTANCE_ID herdada aponta para a sessão certa).

-----------------------------------------------------------------------------
CLAUDE DESKTOP (ABA CODE)
-----------------------------------------------------------------------------
  O Desktop não roda num terminal, então o `run` não serve para ele. Em vez
  disso, `install-desktop` registra hooks no ~/.claude/settings.json (só as
  entradas do guard; o resto fica intacto, com backup) e instala as skills
  economia-de-cota, ferramentas-do-projeto e pesquisar-otimizacoes:
      claude_usage_guard.exe install-desktop     # --force troca skill editada
      claude_usage_guard.exe uninstall-desktop   # tira só o que instalou
  Em cada sessão nova da aba Code, o hook `desktop-hook` mede a cota (cache
  compartilhado, rede só se velho, 2 s no máximo) e o contexto (transcript) e,
  nas viradas de nível, põe no contexto do Claude uma nota "[usage-guard]"
  pedindo economia (subagentes haiku, respostas diretas, HANDOFF.md + /clear).
  Cota alta ou crítica e contexto grande também viram toast do Windows e
  aparecem na janela (`gui`). Nenhum hook consegue rodar /compact, /clear ou
  trocar o modelo: o guard leva o Claude e você a fazer isso. O "model" do
  settings.json não é alterado (o Desktop o ignora). Limiares: seção desktop:
  do config.yaml.
  Botões na janela, por sessão (fila em desktop\pending\<sessão>.json):
  Compactar (HANDOFF.md + linha /compact pronta), Economizar (liga/desliga o
  modo econômico), Skills/MCPs (skill ferramentas-do-projeto) e Pesquisar
  (skill pesquisar-otimizacoes, grava OTIMIZACOES.md). O pedido chega ao
  Claude no fim do turno atual (hook Stop com decision:block) ou junto da sua
  próxima mensagem. Clicar de novo num pedido pendente o cancela.

-----------------------------------------------------------------------------
LIMITAÇÕES, SEGURANÇA E TERMOS DE USO
-----------------------------------------------------------------------------
* Pool / rodízio entre várias contas Anthropic (como o `shunt` faz) para
  contornar limites viola os termos de uso da Anthropic. Este script não
  implementa isso. O failover é para backends que você controla ou paga
  separadamente (Ollama, outro provedor, chave de API Anthropic paga por uso).
* O proxy recebe o token OAuth que o Claude Code envia. Use só proxies em que
  você confia. URLs http só são aceitas para localhost.
* /compact também gasta tokens (ele pede ao modelo um resumo). Vale a pena
  em contextos grandes, não em pequenos.
* Se você interromper o Claude (Esc) ou recusar um pedido de permissão, o
  hook `Stop` não dispara. O guard percebe pelo transcript (mensagem
  "[Request interrupted by user...]") quando a tela fica parada e volta a
  considerar a sessão ociosa; até lá não injeta nada (falha de forma segura).
* O endpoint de uso tem limite de requisições; o intervalo mínimo é 30 s e os
  processos compartilham um cache em ~/.claude-usage-guard/usage_cache.json.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import errno
import hashlib
import json
import logging
import logging.handlers
import os
import queue
import re
import select
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional

IS_WINDOWS = os.name == "nt"
if IS_WINDOWS:
    import ctypes
    import msvcrt
    from ctypes import wintypes
else:
    import fcntl
    import pty
    import termios
    import tty

__version__ = "1.4.0"

log = logging.getLogger("claude_usage_guard")

# --------------------------------------------------------------------------
# Caminhos e constantes
# --------------------------------------------------------------------------

STATE_DIR = Path(os.environ.get("CUG_STATE_DIR") or (Path.home() / ".claude-usage-guard"))
INSTANCES_DIR = STATE_DIR / "instances"
ACTIONS_LOG = STATE_DIR / "actions.jsonl"
DEFAULT_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
MIN_POLL_SECONDS = 30
MACOS_KEYCHAIN_SERVICE = "Claude Code-credentials"

# Eventos de hook que indicam "Claude parado no prompt, esperando você".
IDLE_EVENTS = {"Stop", "SessionStart"}
# Eventos que indicam "Claude trabalhando" (ou mostrando prompt de permissão).
BUSY_EVENTS = {"UserPromptSubmit", "PreToolUse"}

# Só deixamos digitar no TUI nomes de modelo "inofensivos" (sem espaços,
# quebras de linha, aspas): o texto vai direto para o prompt do Claude.
SAFE_MODEL_RE = re.compile(r"^[A-Za-z0-9._\-\[\]]{1,80}$")

# Tokens da entrada do teclado. No Windows, depois que o Claude Code abre, o
# ConPTY liga o "win32-input-mode" (ESC[?9001h) e o terminal passa a mandar
# cada tecla como ESC[Vk;Sc;Uc;Kd;Cs;Rc_ (Enter = ESC[13;28;13;1;0;1_). Sem
# decodificar isso, o Enter parecia uma seta e o campo ficava "sujo" para sempre.
INPUT_TOKEN_RE = re.compile(
    r"\x1b\[(?P<w32>\d*;\d*;\d*;\d*;\d*;\d*)_"   # win32-input-mode
    r"|\x1b\[200~(?P<paste>.*?)\x1b\[201~"        # colagem (bracketed paste)
    r"|\x1b(?:\[[0-9;?<>=]*[ -/]*[@-~]|O.|.)?"    # setas, foco, mouse, Esc
    r"|(?P<ch>.)", re.S)

# --------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------


class GuardError(Exception):
    """Base de todos os erros esperados do guard."""


class ConfigError(GuardError):
    """Configuração inválida."""


class CredentialsError(GuardError):
    """Credenciais ausentes, ilegíveis ou sem permissão."""


class TokenExpiredError(CredentialsError):
    """Token OAuth expirado (o Claude Code renova sozinho ao ser usado)."""


class RateLimitedError(GuardError):
    """O endpoint de uso respondeu 429."""

    def __init__(self, retry_after: Optional[float] = None):
        super().__init__("endpoint de uso limitou as requisições (HTTP 429)")
        self.retry_after = retry_after


class UsageUnavailableError(GuardError):
    """Falha de rede, timeout, 5xx ou resposta inesperada."""


# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "poll_interval_seconds": 120,
    "max_stale_seconds": 900,
    "claude": {"binary": "claude", "extra_args": []},
    "idle": {
        "output_quiet_seconds": 6,
        "input_quiet_seconds": 15,
        "min_gap_between_injections_seconds": 10,
        "allow_without_hooks": False,
    },
    "compact": {
        "enabled": True,
        "session_threshold": 60,
        "context_tokens_threshold": 0,
        "cooldown_seconds": 900,
    },
    "clear": {"enabled": True, "on_signal": True, "idle_minutes": 0},
    "model_switch": {
        "enabled": True,
        "session_threshold": 70,
        "weekly_threshold": 85,
        "model": "haiku",
        "restore": True,
        "restore_below": 50,
        "restore_model": "default",
    },
    "failover": {
        "enabled": False,
        "session_threshold": 90,
        "weekly_threshold": 95,
        "base_url": "http://127.0.0.1:8787",
        "command": [],
        "health_path": "/",
        "startup_timeout_seconds": 20,
        "relaunch_session": False,
        "stop_proxy_on_exit": True,
        "env": {},
    },
    "notifications": {"desktop": True},
    "dashboard": {"refresh_seconds": 5, "bar_width": 32},
    "gui": {"open_on_run": True},
    # Sessões da aba Code do Claude Desktop (hooks desktop-hook). Chaves planas
    # para os overrides CUG_DESKTOP_* funcionarem.
    "desktop": {
        "enabled": True,
        "attention_session": 60,
        "attention_weekly": 70,
        "high_session": 80,
        "high_weekly": 85,
        "critical_session": 92,
        "critical_weekly": 95,
        "context_tokens_threshold": 120000,
        "context_repeat_tokens": 30000,
        "toast": True,
        "session_list_hours": 2,
        "usage_fetch_timeout_seconds": 2,
        # O Desktop não renova o ~/.claude/.credentials.json; com o token
        # vencido, uma chamada mínima do `claude` (Haiku, ~500 tokens) renova.
        "refresh_auth_with_cli": True,
    },
}


def _strip_yaml_comment(line: str) -> str:
    """Remove comentários '#' que não estejam dentro de aspas."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _split_flow(inner: str) -> list[str]:
    """Divide '[a, "b, c", d]' por vírgulas fora de aspas."""
    parts, buf, quote = [], [], None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p for p in (x.strip() for x in parts) if p]


def _parse_scalar(token: str) -> Any:
    t = token.strip()
    if t == "":
        return None
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        return t[1:-1]
    low = t.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~", "none"):
        return None
    if t.startswith("[") and t.endswith("]"):
        return [_parse_scalar(x) for x in _split_flow(t[1:-1])]
    if t == "{}":
        return {}
    for cast in (int, float):
        try:
            return cast(t)
        except ValueError:
            pass
    return t


def load_simple_yaml(text: str) -> dict[str, Any]:
    """Leitor YAML mínimo (fallback quando PyYAML não está instalado).

    Suporta: mapas aninhados por indentação, escalares (str/int/float/bool/
    null), listas inline ``[a, b]``, ``{}`` e listas em bloco ``- item``.
    Não suporta âncoras, multilinha nem listas no mesmo nível da chave.
    """
    lines: list[tuple[int, str, int]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ConfigError(f"linha {lineno}: use espaços, não tabs, na indentação")
        content = _strip_yaml_comment(raw).rstrip()
        if content.strip() in ("", "---"):
            continue
        lines.append((len(content) - len(content.lstrip()), content.strip(), lineno))

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    for idx, (indent, content, lineno) in enumerate(lines):
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if content == "-" or content.startswith("- "):
            if not isinstance(parent, list):
                raise ConfigError(f"linha {lineno}: item de lista fora de uma lista")
            parent.append(_parse_scalar(content[1:]))
            continue
        key, sep, rest = content.partition(":")
        if not sep or not isinstance(parent, dict):
            raise ConfigError(f"linha {lineno}: esperado 'chave: valor'")
        key = key.strip().strip("'\"")
        rest = rest.strip()
        if rest:
            parent[key] = _parse_scalar(rest)
            continue
        nxt = lines[idx + 1] if idx + 1 < len(lines) else None
        if nxt and nxt[0] > indent:
            child: Any = [] if (nxt[1] == "-" or nxt[1].startswith("- ")) else {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = None
    return root


def _deep_merge(base: dict[str, Any], override: dict[str, Any], path: str = "") -> dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        where = f"{path}{key}"
        if key not in base:
            log.warning("config: chave desconhecida ignorada: %s", where)
            continue
        if isinstance(base[key], dict) and key != "env":
            if not isinstance(val, dict):
                raise ConfigError(f"config: '{where}' deve ser um mapa")
            out[key] = _deep_merge(base[key], val, where + ".")
        else:
            out[key] = val
    return out


def _coerce_env(raw: str, like: Any, name: str) -> Any:
    """Converte o texto de uma variável de ambiente no tipo do valor padrão."""
    if isinstance(like, bool):
        if raw.lower() in ("1", "true", "yes", "on"):
            return True
        if raw.lower() in ("0", "false", "no", "off"):
            return False
        raise ConfigError(f"{name}: esperado booleano, recebido {raw!r}")
    if isinstance(like, int):
        try:
            return int(raw)
        except ValueError:
            raise ConfigError(f"{name}: esperado inteiro, recebido {raw!r}") from None
    if isinstance(like, float):
        return float(raw)
    if isinstance(like, (list, dict)):
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            if isinstance(like, list):
                return [x.strip() for x in raw.split(",") if x.strip()]
            raise ConfigError(f"{name}: esperado JSON") from None
        if not isinstance(val, type(like)):
            raise ConfigError(f"{name}: tipo incorreto")
        return val
    return raw


def _apply_env_overrides(cfg: dict[str, Any], defaults: dict[str, Any], prefix: str = "CUG") -> None:
    for key, default in defaults.items():
        name = f"{prefix}_{key.upper()}"
        if isinstance(default, dict) and key != "env":
            _apply_env_overrides(cfg[key], default, name)
        elif name in os.environ:
            cfg[key] = _coerce_env(os.environ[name], default, name)


def find_config_path(explicit: Optional[str]) -> Optional[Path]:
    """Procura o arquivo de config. De propósito NÃO usa o diretório atual:
    o guard roda dentro de projetos que podem ter seu próprio config.yaml."""
    candidates = [explicit, os.environ.get("CUG_CONFIG"), STATE_DIR / "config.yaml",
                  app_dir() / "config.yaml"]
    for c in candidates:
        if c and Path(c).expanduser().is_file():
            return Path(c).expanduser()
    if explicit:
        raise ConfigError(f"arquivo de config não encontrado: {explicit}")
    return None


def load_config(explicit: Optional[str] = None) -> tuple[dict[str, Any], Optional[Path]]:
    """Carrega defaults <- YAML <- variáveis de ambiente e valida."""
    path = find_config_path(explicit)
    user: dict[str, Any] = {}
    if path:
        text = path.read_text(encoding="utf-8")
        try:
            if os.environ.get("CUG_FORCE_MINI_YAML"):
                raise ImportError
            import yaml  # type: ignore

            user = yaml.safe_load(text) or {}
        except ImportError:
            user = load_simple_yaml(text)
        except Exception as exc:  # erro de sintaxe do PyYAML
            raise ConfigError(f"{path}: YAML inválido: {exc}") from exc
        if not isinstance(user, dict):
            raise ConfigError(f"{path}: o topo do arquivo deve ser um mapa")
    # Cópia profunda: quem altera a config carregada não pode mudar os padrões.
    cfg = _deep_merge(json.loads(json.dumps(DEFAULT_CONFIG)), user)
    _apply_env_overrides(cfg, DEFAULT_CONFIG)
    for warning in validate_config(cfg):
        log.warning("config: %s", warning)
    return cfg, path


def _is_local_host(host: Optional[str]) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def validate_config(cfg: dict[str, Any]) -> list[str]:
    """Erros graves levantam ConfigError; avisos voltam numa lista."""
    warnings: list[str] = []

    def pct(section: str, key: str) -> float:
        val = cfg[section][key]
        if not isinstance(val, (int, float)) or isinstance(val, bool) or not 0 <= val <= 100:
            raise ConfigError(f"{section}.{key} deve ser um número entre 0 e 100 (0 desliga)")
        return float(val)

    for sec, keys in {
        "compact": ["session_threshold"],
        "model_switch": ["session_threshold", "weekly_threshold", "restore_below"],
        "failover": ["session_threshold", "weekly_threshold"],
    }.items():
        for k in keys:
            pct(sec, k)

    for win in ("session", "weekly"):
        levels = [pct("desktop", f"{lvl}_{win}") for lvl in ("attention", "high", "critical")]
        on = [x for x in levels if x > 0]  # 0 desliga o nível
        if on != sorted(on):
            raise ConfigError(f"desktop.*_{win}: esperado attention <= high <= critical")
    for key in ("context_tokens_threshold", "context_repeat_tokens", "session_list_hours",
                "usage_fetch_timeout_seconds"):
        val = cfg["desktop"][key]
        if not isinstance(val, (int, float)) or isinstance(val, bool) or val <= 0:
            raise ConfigError(f"desktop.{key} deve ser um número maior que 0")

    if cfg["poll_interval_seconds"] < MIN_POLL_SECONDS:
        warnings.append(f"poll_interval_seconds < {MIN_POLL_SECONDS}; usando {MIN_POLL_SECONDS}")
        cfg["poll_interval_seconds"] = MIN_POLL_SECONDS

    c, m, f = (cfg["compact"]["session_threshold"], cfg["model_switch"]["session_threshold"],
               cfg["failover"]["session_threshold"])
    if all(x > 0 for x in (c, m, f)) and not c <= m <= f:
        warnings.append("limiares fora de ordem (esperado compact <= model_switch <= failover)")

    for key in ("model", "restore_model"):
        if not SAFE_MODEL_RE.match(str(cfg["model_switch"][key])):
            raise ConfigError(f"model_switch.{key} contém caracteres não permitidos")

    for key, val in (("claude.extra_args", cfg["claude"]["extra_args"]),
                     ("failover.command", cfg["failover"]["command"])):
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            raise ConfigError(f"{key} deve ser uma lista de strings")
    if "--settings" in cfg["claude"]["extra_args"]:
        warnings.append("claude.extra_args contém --settings; o guard já passa um --settings com hooks")

    env = cfg["failover"]["env"]
    if not isinstance(env, dict) or not all(isinstance(v, (str, int, float)) for v in env.values()):
        raise ConfigError("failover.env deve ser um mapa NOME: valor")

    url = urllib.parse.urlparse(str(cfg["failover"]["base_url"]))
    if url.scheme not in ("http", "https") or not url.hostname:
        raise ConfigError("failover.base_url inválida")
    if url.scheme == "http" and not _is_local_host(url.hostname):
        raise ConfigError("failover.base_url com http só é permitida para localhost "
                          "(o token OAuth trafegaria sem criptografia)")
    return warnings


def redacted_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Cópia da config para exibição, escondendo valores sensíveis."""
    out = json.loads(json.dumps(cfg))
    for k in out["failover"]["env"]:
        if re.search(r"TOKEN|KEY|SECRET|PASS", k, re.I):
            out["failover"]["env"][k] = "***"
    return out


# --------------------------------------------------------------------------
# Utilitários de arquivo/estado
# --------------------------------------------------------------------------


def ensure_private_dir(path: Path) -> Path:
    if IS_WINDOWS:
        # Sem mode: a pasta herda a ACL do perfil (já privada para o usuário).
        # Com mode=0o700, o Python 3.13+ grava uma ACL que só libera o DONO de
        # cada arquivo, e arquivos criados num terminal "como administrador"
        # têm dono "Administradores": o terminal normal deixava de abri-los.
        path.mkdir(parents=True, exist_ok=True)
        return path
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o700)
    return path


def _state_access_problems() -> list[Path]:
    """Arquivos/pastas do estado que este processo não consegue abrir para escrita."""
    bad: list[Path] = []
    for d in (STATE_DIR, INSTANCES_DIR):
        if d.is_dir():
            probe = d / f".probe-{os.getpid()}"
            try:
                probe.touch()
                probe.unlink()
            except OSError:
                bad.append(d)
    try:
        files = [p for p in STATE_DIR.iterdir() if p.is_file()] if STATE_DIR.is_dir() else []
    except OSError:
        return bad if STATE_DIR in bad else [STATE_DIR, *bad]
    for f in files:
        try:
            with open(f, "ab"):
                pass
        except OSError:
            bad.append(f)
    return bad


def repair_windows_state_acl() -> None:
    """Uma vez por pasta de estado: devolve a herança de ACL do perfil às
    pastas criadas por versões antigas (ver ensure_private_dir)."""
    marker = STATE_DIR / ".acl-ok"
    if not IS_WINDOWS or not STATE_DIR.is_dir() or marker.exists():
        return
    failed: Optional[int] = None
    try:
        proc = subprocess.run(["icacls", str(STATE_DIR), "/reset", "/T", "/C", "/Q"], capture_output=True,
                              timeout=30, creationflags=0x08000000)  # CREATE_NO_WINDOW
        # O código de saída é 0 mesmo com "Acesso negado"; a última linha
        # ("...sucesso X arquivos; falha... Y arquivos") traz a contagem de falhas.
        lines = [ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]
        nums = re.findall(r"\d+", lines[-1]) if lines else []
        failed = int(nums[-1]) if proc.returncode == 0 and nums else None
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("não consegui ajustar as permissões de %s: %s", STATE_DIR, exc)
    problems = _state_access_problems()
    if failed == 0 and not problems:
        with contextlib.suppress(OSError):
            marker.touch()
    elif problems:
        print(f"guard: aviso: {len(problems)} item(ns) em {STATE_DIR} foram criados num terminal de "
              f"administrador e este terminal não consegue abri-los (ex.: {problems[0].name}). "
              f"Rode uma vez num terminal como administrador:\n"
              f'    icacls "{STATE_DIR}" /reset /T /C /Q', file=sys.stderr)


def atomic_write_json(path: Path, data: Any) -> None:
    """Grava JSON de forma atômica com permissão 0600."""
    ensure_private_dir(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, default=str)
    # No Windows, os.replace falha se outro processo (ex.: o dashboard) estiver
    # lendo o arquivo naquele instante; tentamos de novo por um curto período.
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if not IS_WINDOWS or attempt == 19:
                raise
            time.sleep(0.05)


def read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    ensure_private_dir(path.parent)
    line = (json.dumps(record, ensure_ascii=False, default=str) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


@contextlib.contextmanager
def file_lock(path: Path, timeout: float = 120.0) -> Iterator[None]:
    """Lock exclusivo entre processos (flock no Linux/macOS, msvcrt.locking
    no Windows)."""
    ensure_private_dir(path.parent)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if IS_WINDOWS:
            deadline = time.time() + timeout
            while True:
                os.lseek(fd, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.time() > deadline:
                        raise GuardError(f"não foi possível travar {path}") from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                with contextlib.suppress(OSError):
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _win_pid_alive(pid: int) -> bool:
    # ATENÇÃO: no Windows os.kill(pid, 0) NÃO testa o processo: 0 é
    # CTRL_C_EVENT e ele mandaria um Ctrl-C. Usamos a API Win32.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5  # acesso negado = existe
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if IS_WINDOWS:
        return _win_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def log_action(instance: str, action: str, reason: str, ok: bool = True) -> None:
    append_jsonl(ACTIONS_LOG, {"ts": time.time(), "instance": instance, "action": action,
                               "reason": reason, "ok": ok})


# Toast do Windows 10/11 (WinRT) via PowerShell 5.1: o pwsh 7 não carrega os
# tipos WinRT. Sem AppUserModelID próprio, usamos o do PowerShell (o toast
# aparece como "Windows PowerShell"). Se o WinRT falhar, cai para o balão da
# bandeja, que só aparece enquanto o processo vive (daí o Start-Sleep).
TOAST_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_TOAST_SCRIPT = (
    "$t=$env:CUG_NOTIFY_TITLE;$m=$env:CUG_NOTIFY_MSG;"
    "try{"
    "[void][Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];"
    "[void][Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime];"
    "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;"
    "$x.LoadXml('<toast><visual><binding template=\"ToastGeneric\"><text/><text/></binding></visual></toast>');"
    "$n=$x.GetElementsByTagName('text');"
    "[void]$n.Item(0).AppendChild($x.CreateTextNode($env:CUG_NOTIFY_TITLE));"
    "[void]$n.Item(1).AppendChild($x.CreateTextNode($env:CUG_NOTIFY_MSG));"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('" + TOAST_AUMID + "')"
    ".Show([Windows.UI.Notifications.ToastNotification]::new($x))"
    "}catch{"
    "Add-Type -AssemblyName System.Windows.Forms;"
    "$b=New-Object System.Windows.Forms.NotifyIcon;"
    "try{$b.Icon=New-Object System.Drawing.Icon($env:CUG_NOTIFY_ICON,16,16)}"
    "catch{$b.Icon=[System.Drawing.SystemIcons]::Information};"
    "$b.BalloonTipTitle=$t;$b.BalloonTipText=$m;"
    "$b.Visible=$true;$b.ShowBalloonTip(6000);Start-Sleep -Seconds 7;$b.Dispose()}")


def notify_toast(title: str, message: str) -> bool:
    """Notificação do sistema sem esperar (best effort; nunca levanta exceção).
    True = o processo da notificação foi criado."""

    def applescript_str(s: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    try:
        if IS_WINDOWS:
            # Título e mensagem vão por variável de ambiente: nada é interpolado
            # no script. CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP, tentando
            # sair do job do chamador (a sessão do Claude Code costuma negar).
            # Nada de DETACHED_PROCESS: sem console, o PowerShell é criado mas o
            # toast nunca chega ao Windows (medido no registro em 04/11).
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command",
                   _TOAST_SCRIPT]
            env = dict(os.environ, CUG_NOTIFY_TITLE=title, CUG_NOTIFY_MSG=message,
                       CUG_NOTIFY_ICON=str(asset_path("app.ico") or ""))
            for flags in (0x08000000 | 0x00000200 | 0x01000000, 0x08000000 | 0x00000200):
                try:
                    subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, creationflags=flags)
                    return True
                except OSError as exc:
                    log.debug("toast: Popen falhou (flags %#x): %s", flags, exc)
            return False
        if sys.platform == "darwin" and shutil.which("osascript"):
            script = f"display notification {applescript_str(message)} with title {applescript_str(title)}"
            subprocess.Popen(["osascript", "-e", script], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if shutil.which("notify-send"):
            subprocess.Popen(["notify-send", title, message], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("notificação falhou: %s", exc)
    return False


def desktop_notify(cfg: dict[str, Any], title: str, message: str) -> None:
    """Notificação do modo run (respeita notifications.desktop)."""
    if cfg["notifications"]["desktop"]:
        notify_toast(title, message)


def setup_logging(to_stderr: bool, verbose: bool = False) -> None:
    ensure_private_dir(STATE_DIR)
    root = logging.getLogger("claude_usage_guard")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()
    try:
        fh = logging.handlers.RotatingFileHandler(STATE_DIR / "guard.log", maxBytes=1_000_000, backupCount=3,
                                                  encoding="utf-8")
    except OSError as exc:  # o log nunca pode impedir o programa de rodar
        print(f"guard: aviso: sem log em arquivo ({exc})", file=sys.stderr)
    else:
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(process)d] %(message)s"))
        root.addHandler(fh)
    if to_stderr:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter("guard: %(levelname)s: %(message)s"))
        sh.setLevel(logging.WARNING if not verbose else logging.DEBUG)
        root.addHandler(sh)


# --------------------------------------------------------------------------
# Credenciais OAuth
# --------------------------------------------------------------------------


def claude_config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude")).expanduser()


def _read_macos_keychain() -> Optional[str]:
    if sys.platform != "darwin" or not shutil.which("security"):
        return None
    try:
        res = subprocess.run(
            ["security", "find-generic-password", "-s", MACOS_KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() or None if res.returncode == 0 else None


def load_oauth_token() -> str:
    """Lê o access token OAuth do Claude Code.

    Ordem: $CLAUDE_CODE_OAUTH_TOKEN, ~/.claude/.credentials.json
    (claudeAiOauth.accessToken; também aceita access_token no topo) e, no
    macOS, o Keychain. Nunca loga nem devolve o token em mensagens de erro.
    """
    env_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if env_token:
        return env_token

    path = claude_config_dir() / ".credentials.json"
    raw: Optional[str] = None
    if path.is_file():
        try:
            mode = path.stat().st_mode
            if not IS_WINDOWS and mode & 0o077:
                log.warning("%s pode ser lido por outros usuários (chmod 600 recomendado)", path)
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CredentialsError(f"não foi possível ler {path}: {exc.strerror}") from None
    else:
        raw = _read_macos_keychain()
    if not raw:
        raise CredentialsError("credenciais do Claude Code não encontradas; rode `claude` e faça login "
                               "(no macOS o token fica no Keychain)")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise CredentialsError("arquivo de credenciais não é um JSON válido") from None

    node = data.get("claudeAiOauth") if isinstance(data.get("claudeAiOauth"), dict) else data
    token = node.get("accessToken") or node.get("access_token")
    if not isinstance(token, str) or not token:
        raise CredentialsError("nenhum accessToken OAuth nas credenciais (login com chave de API? "
                               "o endpoint de uso só existe para assinaturas Pro/Max)")
    expires = node.get("expiresAt") or node.get("expires_at")
    if isinstance(expires, (int, float)):
        expires_s = expires / 1000 if expires > 1e12 else expires
        if time.time() >= expires_s - 30:
            raise TokenExpiredError("token OAuth expirado; use o `claude` normalmente que ele renova "
                                    "o token sozinho, e o guard relê as credenciais")
    return token


# --------------------------------------------------------------------------
# Endpoint de uso
# --------------------------------------------------------------------------


def _parse_iso(val: Any) -> Optional[dt.datetime]:
    if not isinstance(val, str) or not val:
        return None
    try:
        parsed = dt.datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


@dataclasses.dataclass
class UsageWindow:
    """Uma janela de limite (ex.: five_hour) com utilização em % (0–100)."""

    name: str
    utilization: Optional[float]
    resets_at: Optional[dt.datetime]

    def resets_in(self, now: Optional[float] = None) -> Optional[float]:
        if not self.resets_at:
            return None
        return max(0.0, self.resets_at.timestamp() - (now or time.time()))


@dataclasses.dataclass
class UsageSnapshot:
    windows: dict[str, UsageWindow]
    fetched_at: float

    @classmethod
    def from_api(cls, data: dict[str, Any], fetched_at: Optional[float] = None) -> "UsageSnapshot":
        """Interpreta a resposta do endpoint de forma defensiva: qualquer chave
        cujo valor seja um objeto com 'utilization' vira uma janela."""
        windows: dict[str, UsageWindow] = {}
        for key, val in data.items():
            if not isinstance(val, dict) or "utilization" not in val:
                continue
            util = val.get("utilization")
            util_f = float(util) if isinstance(util, (int, float)) and not isinstance(util, bool) else None
            if util_f is not None:
                util_f = max(0.0, min(100.0, util_f))
            windows[key] = UsageWindow(key, util_f, _parse_iso(val.get("resets_at")))
        if "five_hour" not in windows and "seven_day" not in windows:
            raise UsageUnavailableError("resposta do endpoint de uso sem five_hour/seven_day "
                                        "(o formato pode ter mudado)")
        return cls(windows, fetched_at or time.time())

    def pct(self, name: str) -> Optional[float]:
        w = self.windows.get(name)
        return w.utilization if w else None

    def age(self, now: Optional[float] = None) -> float:
        return (now or time.time()) - self.fetched_at

    def to_json(self) -> dict[str, Any]:
        return {"fetched_at": self.fetched_at, "windows": {
            k: {"utilization": w.utilization, "resets_at": w.resets_at.isoformat() if w.resets_at else None}
            for k, w in self.windows.items()}}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "UsageSnapshot":
        return cls.from_api(data["windows"], fetched_at=float(data["fetched_at"]))


def _validate_usage_url(url: str) -> str:
    """O token só pode ir para a Anthropic (ou localhost, para testes)."""
    p = urllib.parse.urlparse(url)
    if p.scheme == "https" and p.hostname and (p.hostname == "anthropic.com" or p.hostname.endswith(".anthropic.com")):
        return url
    if p.scheme in ("http", "https") and _is_local_host(p.hostname):
        return url
    raise ConfigError(f"CUG_USAGE_URL recusada (só anthropic.com ou localhost): {url}")


def _local_opener() -> urllib.request.OpenerDirector:
    """Opener sem proxy HTTP do sistema (para falar com 127.0.0.1)."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


class UsageClient:
    """Cliente do endpoint de uso com retry, backoff e cache compartilhado
    entre processos (o dashboard e o `run` não duplicam requisições)."""

    def __init__(self, url: Optional[str] = None, timeout: float = 10.0, retries: int = 3):
        self.url = _validate_usage_url(url or os.environ.get("CUG_USAGE_URL") or DEFAULT_USAGE_URL)
        self.timeout = timeout
        self.retries = retries
        self.cache_path = STATE_DIR / "usage_cache.json"
        self.lock_path = STATE_DIR / "usage_cache.lock"
        host = urllib.parse.urlparse(self.url).hostname
        self._open = _local_opener().open if _is_local_host(host) else urllib.request.urlopen

    def fetch(self) -> UsageSnapshot:
        """Uma consulta à rede. Levanta CredentialsError, TokenExpiredError,
        RateLimitedError ou UsageUnavailableError."""
        token = load_oauth_token()
        req = urllib.request.Request(self.url, method="GET", headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": OAUTH_BETA_HEADER,
            "Accept": "application/json",
            "User-Agent": f"claude-usage-guard/{__version__}",
        })
        last: Optional[BaseException] = None
        for attempt in range(self.retries):
            try:
                with self._open(req, timeout=self.timeout) as resp:
                    body = resp.read(1_000_000)
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise UsageUnavailableError("resposta do endpoint de uso não é um objeto JSON")
                return UsageSnapshot.from_api(data)
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    raise TokenExpiredError("token OAuth recusado (HTTP 401); use o `claude` para "
                                            "renová-lo, o guard relê as credenciais") from None
                if exc.code == 403:
                    raise CredentialsError("acesso negado ao endpoint de uso (HTTP 403); o token "
                                           "pode não ter o escopo necessário") from None
                if exc.code == 429:
                    ra = exc.headers.get("Retry-After") if exc.headers else None
                    raise RateLimitedError(float(ra) if ra and ra.isdigit() else None) from None
                if 500 <= exc.code < 600:
                    last = exc
                else:
                    raise UsageUnavailableError(f"endpoint de uso respondeu HTTP {exc.code}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as exc:
                last = exc
            if attempt < self.retries - 1:
                time.sleep(2 ** (attempt + 1))
        reason = getattr(last, "reason", None) or last
        raise UsageUnavailableError(f"endpoint de uso indisponível: {reason}")

    def get(self, max_age: float, lock_timeout: float = 120.0) -> UsageSnapshot:
        """Devolve o cache se tiver menos de max_age segundos; senão consulta a
        rede (respeitando o cooldown de um 429 anterior)."""
        with file_lock(self.lock_path, timeout=lock_timeout):
            cached = read_json(self.cache_path) or {}
            snap = None
            if cached.get("snapshot"):
                with contextlib.suppress(Exception):
                    snap = UsageSnapshot.from_json(cached["snapshot"])
            if snap and snap.age() < max_age:
                return snap
            cooldown = float(cached.get("cooldown_until") or 0)
            if time.time() < cooldown:
                raise RateLimitedError(cooldown - time.time())
            try:
                snap = self.fetch()
            except RateLimitedError as exc:
                cached["cooldown_until"] = time.time() + (exc.retry_after or 300)
                atomic_write_json(self.cache_path, cached)
                raise
            atomic_write_json(self.cache_path, {"snapshot": snap.to_json(), "cooldown_until": 0})
            return snap

    def cached(self) -> Optional[UsageSnapshot]:
        data = read_json(self.cache_path) or {}
        with contextlib.suppress(Exception):
            return UsageSnapshot.from_json(data["snapshot"])
        return None


class UsageMonitor(threading.Thread):
    """Thread que consulta o uso periodicamente, com backoff em erros."""

    def __init__(self, client: UsageClient, interval: float,
                 on_token_expired: Optional[Callable[[], Any]] = None):
        super().__init__(name="usage-monitor", daemon=True)
        self.client = client
        self.on_token_expired = on_token_expired
        self.interval = max(MIN_POLL_SECONDS, interval)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.snapshot: Optional[UsageSnapshot] = client.cached()
        self.error: Optional[str] = None

    def poll_once(self) -> float:
        """Faz uma leitura e devolve quantos segundos esperar até a próxima."""
        try:
            snap = self.client.get(max_age=self.interval - 1)
            with self._lock:
                self.snapshot, self.error = snap, None
            return self.interval
        except RateLimitedError as exc:
            wait = max(exc.retry_after or 0, self.interval * 2)
            self._set_error(f"limite de requisições; nova tentativa em {int(wait)}s")
            return min(wait, 1800)
        except TokenExpiredError as exc:
            self._set_error(str(exc))
            if self.on_token_expired:
                with contextlib.suppress(Exception):
                    self.on_token_expired()
            return 60
        except GuardError as exc:
            self._set_error(str(exc))
            return min(self.interval * 2, 900)
        except Exception as exc:  # nunca deixar a thread morrer
            log.exception("erro inesperado no monitor de uso")
            self._set_error(f"erro inesperado: {exc}")
            return min(self.interval * 2, 900)

    def _set_error(self, msg: str) -> None:
        log.warning("uso: %s", msg)
        with self._lock:
            self.error = msg

    def run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.poll_once())

    def stop(self) -> None:
        self._stop.set()

    def latest(self) -> tuple[Optional[UsageSnapshot], Optional[str]]:
        with self._lock:
            return self.snapshot, self.error


# --------------------------------------------------------------------------
# Política de mitigação (função pura, fácil de testar)
# --------------------------------------------------------------------------

ACT_FAILOVER = "failover"
ACT_CLEAR = "clear"
ACT_COMPACT = "compact"
ACT_SWITCH = "switch_model"
ACT_RESTORE = "restore_model"


@dataclasses.dataclass
class GuardState:
    """Estado mutável de uma sessão protegida."""

    model_switched: bool = False
    failover_active: bool = False
    failover_notified: bool = False
    compacted_window: Optional[int] = None  # chave da janela de 5h já compactada
    last_compact_at: float = 0.0
    clear_requested: bool = False
    last_activity_at: float = dataclasses.field(default_factory=time.time)
    turns_since_clear: int = 0
    context_tokens: Optional[int] = None
    context_measured_at: float = 0.0
    session_id: Optional[str] = None


def _over(value: Optional[float], threshold: float) -> bool:
    return value is not None and threshold > 0 and value >= threshold


def _window_key(snap: UsageSnapshot) -> int:
    """Identifica a janela de 5h atual (resets_at arredondado para a hora)."""
    w = snap.windows.get("five_hour")
    if w and w.resets_at:
        return int((w.resets_at.timestamp() + 1800) // 3600)
    return int(snap.fetched_at // (5 * 3600))


def decide(cfg: dict[str, Any], snap: Optional[UsageSnapshot], state: GuardState,
           now: Optional[float] = None) -> list[tuple[str, str]]:
    """Decide quais mitigações aplicar, em ordem de prioridade.

    `snap` deve ser None se o dado estiver velho demais: nesse caso só as
    ações que não dependem do uso (sinal de clear, ociosidade, contexto)
    são consideradas. Devolve [(ação, motivo), ...].
    """
    now = now or time.time()
    acts: list[tuple[str, str]] = []
    s5 = snap.pct("five_hour") if snap else None
    s7 = snap.pct("seven_day") if snap else None
    fo, cl, cp, ms = cfg["failover"], cfg["clear"], cfg["compact"], cfg["model_switch"]

    # d) failover: limiar crítico em qualquer janela.
    if fo["enabled"] and not state.failover_active and not state.failover_notified:
        if _over(s5, fo["session_threshold"]) or _over(s7, fo["weekly_threshold"]):
            acts.append((ACT_FAILOVER, f"uso crítico (5h {s5}%, 7d {s7}%)"))

    # a) clear: sinal explícito ou ociosidade longa (o cache de prompt já
    #    expirou, então o próximo turno pagaria o contexto inteiro de novo).
    want_clear = False
    if cl["enabled"]:
        if cl["on_signal"] and state.clear_requested:
            acts.append((ACT_CLEAR, "tarefa sinalizada como concluída"))
            want_clear = True
        elif (cl["idle_minutes"] > 0 and state.turns_since_clear > 0
              and now - state.last_activity_at >= cl["idle_minutes"] * 60):
            acts.append((ACT_CLEAR, f"ociosa há {cl['idle_minutes']}+ min"))
            want_clear = True

    # b) compact: uso da sessão em patamar intermediário, uma vez por janela,
    #    ou contexto grande (medido no transcript após o último compact).
    #    Só compacta se houver conversa (compactar sessão vazia gasta à toa).
    if (cp["enabled"] and not want_clear and state.turns_since_clear > 0
            and now - state.last_compact_at >= cp["cooldown_seconds"]):
        if snap and _over(s5, cp["session_threshold"]) and state.compacted_window != _window_key(snap):
            acts.append((ACT_COMPACT, f"sessão em {s5:.0f}% (limiar {cp['session_threshold']}%)"))
        elif (cp["context_tokens_threshold"] > 0 and state.context_tokens is not None
              and state.context_tokens >= cp["context_tokens_threshold"]
              and state.context_measured_at > state.last_compact_at):
            acts.append((ACT_COMPACT, f"contexto com {state.context_tokens} tokens"))

    # c) troca de modelo e restauração depois que a janela reinicia.
    if ms["enabled"]:
        if not state.model_switched and (_over(s5, ms["session_threshold"]) or _over(s7, ms["weekly_threshold"])):
            acts.append((ACT_SWITCH, f"uso 5h {s5}% / 7d {s7}% → {ms['model']}"))
        elif (state.model_switched and ms["restore"] and s5 is not None and s5 < ms["restore_below"]
              and not _over(s7, ms["weekly_threshold"])):
            acts.append((ACT_RESTORE, f"sessão voltou para {s5:.0f}%"))
    return acts


# --------------------------------------------------------------------------
# Sessões do Desktop (aba Code): níveis de cota, notas e decisão
# --------------------------------------------------------------------------

DESKTOP_LEVELS = ("normal", "attention", "high", "critical")
DESKTOP_WINDOWS = (("five_hour", "session"), ("seven_day", "weekly"))
NOTE_PREFIX = "[usage-guard]"
_WINDOW_NOTE_LABEL = {"five_hour": "Cota 5h", "seven_day": "Cota semanal"}
_WINDOW_SHORT = {"five_hour": "5h", "seven_day": "semanal"}
_LEVEL_ADVICE = {
    "attention": ("Modo econômico: respostas diretas, delegue buscas e leituras longas a subagentes com model "
                  "haiku, evite reler arquivos grandes. Detalhes: skill economia-de-cota."),
    "high": ("Economia forte: só o essencial; subagentes haiku/sonnet para o que não exige raciocínio difícil; "
             "antes de tarefas longas, confirme com o usuário e sugira /model sonnet para trabalho rotineiro."),
    "critical": ("Conclua o passo atual, grave um resumo de passagem em HANDOFF.md e diga ao usuário quando a "
                 "cota reinicia. Não comece tarefas novas."),
}


def quota_level(cfg: dict[str, Any], snap: Optional[UsageSnapshot]) -> tuple[str, Optional[str]]:
    """(nível, janela que o definiu). O pior entre 5h e 7d; empate fica com a de 5h."""
    if snap is None:
        return "normal", None
    d = cfg["desktop"]
    best, best_win = 0, None
    for win, suffix in DESKTOP_WINDOWS:
        val = snap.pct(win)
        for idx in (3, 2, 1):
            if _over(val, d[f"{DESKTOP_LEVELS[idx]}_{suffix}"]):
                if idx > best:
                    best, best_win = idx, win
                break
    return DESKTOP_LEVELS[best], best_win


def level_note(level: str, window: Optional[str], pct: Optional[float], resets_in: Optional[float]) -> str:
    pct_s = "?" if pct is None else f"{pct:.0f}%"
    if level == "normal":
        return f"{NOTE_PREFIX} Cota normalizada ({_WINDOW_SHORT.get(window or '', '5h')} em {pct_s}). " \
               "Pode trabalhar normalmente."
    label = _WINDOW_NOTE_LABEL.get(window or "", "Cota")
    return f"{NOTE_PREFIX} {label} em {pct_s} (reinicia em {_fmt_duration(resets_in)}). {_LEVEL_ADVICE[level]}"


def context_note(tokens: int) -> str:
    return (f"{NOTE_PREFIX} Contexto com {tokens // 1000}k tokens. Ao terminar a tarefa atual, sugira ao "
            "usuário /compact (mesmo assunto) ou /clear com resumo de passagem (assunto novo).")


# Pedidos dos botões da janela (fila por sessão, entregue pelo desktop-hook).
# Ordem da tupla = ordem de entrega, não importa a ordem dos cliques.
PENDING_ACTIONS = ("economy_on", "economy_off", "compact", "tools", "research")
ACTION_LABELS = {"economy_on": "Economizar", "economy_off": "Desligar economia", "compact": "Compactar",
                 "tools": "Skills/MCPs", "research": "Pesquisar"}
_ACTION_OPPOSITE = {"economy_on": "economy_off", "economy_off": "economy_on"}


_REQUEST_HEADER = {
    "Stop": "Pedido do usuário pelo botão \"{label}\" do Claude Usage Guard (não é erro; faça agora): ",
    "UserPromptSubmit": ("Pedido do usuário pelo botão \"{label}\" do Claude Usage Guard (faça antes do resto da "
                         "mensagem dele): "),
}
_REQUEST_TEXT = {
    "compact": ("grave HANDOFF.md (modelo da skill economia-de-cota) e devolva uma linha pronta \"/compact <o que "
                "manter>\" para ele colar. Não comece tarefa nova antes. Se o próximo assunto for outro, recomende "
                "/clear e depois ler o HANDOFF.md."),
    "economy_on": ("modo econômico nesta sessão até ele desligar (skill economia-de-cota, nível attention). "
                   "Confirme em uma linha."),
    "economy_off": ("modo econômico desligado; volte ao normal, a menos que outra nota [usage-guard] de cota peça "
                    "economia. Confirme em uma linha."),
    "tools": ("use a skill ferramentas-do-projeto: analise o projeto, sugira skills, MCPs, plugins e hooks (o que "
              "pôr e o que tirar) e instale só o que ele aprovar."),
    "research": ("use a skill pesquisar-otimizacoes: pesquise primeiro como usar o Claude Code neste projeto "
                 "gastando menos, depois boas práticas do stack; grave OTIMIZACOES.md e proponha as 3 a 5 mudanças "
                 "de maior ganho; aplique só o que ele aprovar."),
}
ECONOMY_REMINDER = (f"{NOTE_PREFIX} Modo econômico ligado pelo usuário nesta sessão (skill economia-de-cota, "
                    "nível attention).")


def request_notes(actions: list[str], event: str) -> str:
    """Texto dos pedidos para o Claude: uma linha por ação, cabeçalho conforme
    o canal (fim do turno pelo Stop ou junto da mensagem do usuário)."""
    header = _REQUEST_HEADER[event]
    return "\n".join(f"{NOTE_PREFIX} {header.format(label=ACTION_LABELS[a])}{_REQUEST_TEXT[a]}" for a in actions)


_LEVEL_HEADLINE = {"attention": "em atenção", "high": "alta", "critical": "crítica"}
TOAST_TITLE = "Claude Usage Guard"


def quota_headline(level: str, window: Optional[str], pct: Optional[float], resets_in: Optional[float]) -> str:
    """Texto curto para toast e faixa da janela: 'Cota 5h alta: 83% · reinicia em 1h05m'."""
    pct_s = "?" if pct is None else f"{pct:.0f}%"
    return (f"{_WINDOW_NOTE_LABEL.get(window or '', 'Cota')} {_LEVEL_HEADLINE.get(level, level)}: {pct_s}"
            f" · reinicia em {_fmt_duration(resets_in)}")


@dataclasses.dataclass
class DesktopSessionState:
    """Estado de uma sessão do Desktop (arquivo desktop/<session_id>.json)."""

    session_id: str
    cwd: str = ""
    transcript_path: str = ""
    updated_at: float = 0.0
    context_tokens: Optional[int] = None
    context_measured_at: float = 0.0
    context_noted_at: Optional[int] = None
    last_level: Optional[str] = None
    last_note: Optional[str] = None
    last_note_at: float = 0.0
    context_toast_done: bool = False
    last_event: Optional[str] = None
    economy_mode: bool = False          # modo econômico ligado pelo botão da janela
    delivered_actions: list[str] = dataclasses.field(default_factory=list)
    delivered_at: float = 0.0
    delivered_via: Optional[str] = None  # "Stop" (fim do turno) ou "UserPromptSubmit"

    def to_json(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "DesktopSessionState":
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def apply_delivery(state: DesktopSessionState, actions: list[str], event: str, now: float) -> DesktopSessionState:
    """Estado da sessão depois de entregar os pedidos (pura)."""
    st = dataclasses.replace(state, delivered_actions=list(actions), delivered_at=now, delivered_via=event)
    if "economy_on" in actions:
        st.economy_mode = True
    if "economy_off" in actions:
        st.economy_mode = False
    # Nota curta: o texto inteiro dos pedidos deixaria o cartão da janela alto.
    st.last_note = f"{NOTE_PREFIX} entregues: " + ", ".join(ACTION_LABELS.get(a, a) for a in actions)
    st.last_note_at = now
    return st


def merge_concurrent_delivery(state: DesktopSessionState,
                              on_disk: Optional[DesktopSessionState]) -> DesktopSessionState:
    """Dois hooks do guard em paralelo gravam o mesmo arquivo sem trava: se o
    disco já traz uma entrega mais nova que a que este hook leu, mantém o modo
    econômico e os campos delivered_* do disco em vez de sobrescrevê-los."""
    if on_disk is None or on_disk.delivered_at <= state.delivered_at:
        return state
    return dataclasses.replace(state, economy_mode=on_disk.economy_mode,
                               delivered_actions=list(on_disk.delivered_actions),
                               delivered_at=on_disk.delivered_at, delivered_via=on_disk.delivered_via)


@dataclasses.dataclass
class ToastRequest:
    key: str      # "<janela>:<reinício em horas>:<nível>" ou "context:<sessão>"
    title: str
    message: str


def _reset_key(snap: UsageSnapshot, window: str) -> int:
    w = snap.windows.get(window)
    return int((w.resets_at.timestamp() + 1800) // 3600) if w and w.resets_at else 0


def advise(cfg: dict[str, Any], snap: Optional[UsageSnapshot], state: DesktopSessionState, event: str,
           source: Optional[str], now: float) -> tuple[list[str], list[ToastRequest], DesktopSessionState]:
    """Decide as notas para o Claude e os toasts para o usuário. Pura: devolve
    um estado novo e não toca em arquivos, rede ou relógio."""
    d = cfg["desktop"]
    st = dataclasses.replace(state)
    notes: list[str] = []
    toasts: list[ToastRequest] = []
    if event == "SessionStart" and source in ("clear", "compact"):
        st.context_tokens = None
        st.context_noted_at = None
    if event not in ("SessionStart", "UserPromptSubmit"):
        return notes, toasts, st

    fresh = snap if snap is not None and snap.age(now) <= cfg["max_stale_seconds"] else None
    if fresh is not None:
        level, win = quota_level(cfg, fresh)
        note = None
        if event == "SessionStart" or st.last_level is None:
            if level != "normal":
                note = level
        elif level != st.last_level:
            note = level
        if note == "normal":
            win = next((w for w in ("five_hour", "seven_day") if fresh.pct(w) is not None), None)
        if note is not None and win is not None:
            w = fresh.windows[win]
            notes.append(level_note(level, win, w.utilization, w.resets_in(now)))
            if level in ("high", "critical"):
                toasts.append(ToastRequest(f"{win}:{_reset_key(fresh, win)}:{level}", TOAST_TITLE,
                                           quota_headline(level, win, w.utilization, w.resets_in(now))))
        st.last_level = level
    if event == "SessionStart" and source in ("clear", "compact") and st.economy_mode:
        notes.append(ECONOMY_REMINDER)  # /clear e /compact apagam a instrução do contexto

    tokens = st.context_tokens
    if (event == "UserPromptSubmit" and tokens is not None and tokens >= d["context_tokens_threshold"]
            and (st.context_noted_at is None or tokens >= st.context_noted_at + d["context_repeat_tokens"])):
        notes.append(context_note(tokens))
        st.context_noted_at = tokens
        if not st.context_toast_done:
            st.context_toast_done = True
            folder = Path(st.cwd).name if st.cwd else "Desktop"
            toasts.append(ToastRequest(f"context:{st.session_id}", TOAST_TITLE,
                                       f"Sessão em {folder} com {tokens // 1000}k tokens de contexto. "
                                       "Ao terminar a tarefa, use /compact ou /clear."))
    if notes:
        st.last_note = notes[-1]
        st.last_note_at = now
    return notes, toasts, st


# --------------------------------------------------------------------------
# Proxy de failover
# --------------------------------------------------------------------------


class ProxyManager:
    """Usa um proxy local já em execução ou inicia `failover.command`.

    O comando é configurável porque cada proxy (claude-spillway, LiteLLM,
    o endpoint compatível com Anthropic do Ollama...) tem flags próprias.
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg["failover"]
        self.base_url = str(self.cfg["base_url"]).rstrip("/")
        self.proc: Optional[subprocess.Popen[bytes]] = None
        host = urllib.parse.urlparse(self.base_url).hostname
        self._open = _local_opener().open if _is_local_host(host) else urllib.request.urlopen

    def is_up(self) -> bool:
        try:
            with self._open(self.base_url + str(self.cfg["health_path"]), timeout=2):
                return True
        except urllib.error.HTTPError:
            return True  # respondeu (mesmo 404): o servidor está de pé
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def ensure_running(self) -> bool:
        if self.proc and self.proc.poll() is None and self.is_up():
            return True
        if self.is_up():
            log.info("proxy já ativo em %s", self.base_url)
            return True
        command = self.cfg["command"]
        if not command:
            log.error("proxy não responde em %s e failover.command está vazio", self.base_url)
            return False
        exe = shutil.which(command[0])
        if not exe:
            log.error("comando do proxy não encontrado: %s", command[0])
            return False
        logfile = open(STATE_DIR / "proxy.log", "ab")  # noqa: SIM115 (fica aberto com o processo)
        log.info("iniciando proxy: %s", shlex.join([exe, *command[1:]]))
        detach: dict[str, Any] = ({"creationflags": 0x00000200 | 0x08000000}  # NEW_PROCESS_GROUP | NO_WINDOW
                                  if IS_WINDOWS else {"start_new_session": True})
        self.proc = subprocess.Popen([exe, *command[1:]], stdin=subprocess.DEVNULL, stdout=logfile,
                                     stderr=subprocess.STDOUT, **detach)
        logfile.close()
        deadline = time.time() + float(self.cfg["startup_timeout_seconds"])
        while time.time() < deadline:
            if self.proc.poll() is not None:
                log.error("proxy saiu com código %s (veja %s)", self.proc.returncode, STATE_DIR / "proxy.log")
                return False
            if self.is_up():
                return True
            time.sleep(0.5)
        log.error("proxy não respondeu em %ss", self.cfg["startup_timeout_seconds"])
        self.stop()
        return False

    def child_env(self) -> dict[str, str]:
        """Variáveis para o processo do claude. Valores aceitam ${VAR}, para
        não precisar escrever segredos no YAML."""
        env = {"ANTHROPIC_BASE_URL": self.base_url}
        for k, v in self.cfg["env"].items():
            env[str(k)] = os.path.expandvars(str(v))
        return env

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


# --------------------------------------------------------------------------
# Sessão em terminal (PTY no Linux/macOS, ConPTY no Windows)
# --------------------------------------------------------------------------


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            n = os.write(fd, view)
        except InterruptedError:
            continue
        view = view[n:]


def _terminal_size() -> tuple[int, int]:
    """(colunas, linhas) do terminal atual."""
    for stream in (sys.stdout, sys.stdin):
        with contextlib.suppress(OSError, ValueError, AttributeError):
            size = os.get_terminal_size(stream.fileno())
            return size.columns, size.lines
    return 120, 40


class TerminalSession:
    """Base: roda um programa num pseudo-terminal, repassa teclado e tela de
    forma transparente e permite "digitar" texto no prompt (inject)."""

    def __init__(self, argv: list[str], env: dict[str, str],
                 on_tick: Callable[["TerminalSession"], None], tick_interval: float = 0.5):
        self.argv, self.env, self.on_tick, self.tick_interval = argv, env, on_tick, tick_interval
        self.child_pid: Optional[int] = None
        now = time.time()
        self.last_output_at = now
        self.last_input_at = now
        self.input_dirty = False  # há texto digitado e ainda não enviado?

    def _track_input(self, data: bytes) -> None:
        self.last_input_at = time.time()
        for m in INPUT_TOKEN_RE.finditer(data.decode("utf-8", "replace")):
            if m.group("w32") is not None:
                f = m.group("w32").split(";")
                if f[3] != "1" or not f[2] or f[2] == "0":
                    continue  # tecla solta, ou sem caractere (setas, Shift...)
                self._track_char(chr(int(f[2]) % 0x110000))
            elif m.group("paste") is not None:
                self.input_dirty = self.input_dirty or bool(m.group("paste"))
            elif m.group("ch") is not None:
                self._track_char(m.group("ch"))
            # demais sequências ESC (setas, foco, mouse, Esc) não mudam o campo

    def _track_char(self, ch: str) -> None:
        if ch in ("\r", "\n", "\x03", "\x04"):
            self.input_dirty = False  # Enter enviou; Ctrl-C limpa o campo
        elif ch != "\x1b":
            self.input_dirty = True

    def _write_child(self, text: str) -> None:
        raise NotImplementedError

    def inject(self, text: str) -> None:
        """Digita `text` + Enter no prompt do programa."""
        self._write_child(text)
        time.sleep(0.3)  # deixa o TUI processar o texto antes do Enter
        self._write_child("\r")
        self.last_output_at = time.time()

    def _tick(self) -> None:
        try:
            self.on_tick(self)
        except Exception:  # um bug no guard nunca pode derrubar sua sessão
            log.exception("erro no controlador (sessão continua)")

    def run(self) -> int:
        raise NotImplementedError


class PosixPtySession(TerminalSession):
    """Linux/macOS: pty.fork + select."""

    master: Optional[int] = None

    def _write_child(self, text: str) -> None:
        assert self.master is not None
        _write_all(self.master, text.encode())

    def _sync_winsize(self) -> None:
        if self.master is None:
            return
        for fd in (sys.stdout.fileno(), sys.stdin.fileno()):
            with contextlib.suppress(OSError):
                size = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)
                fcntl.ioctl(self.master, termios.TIOCSWINSZ, size)
                return
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))

    def run(self) -> int:
        pid, master = pty.fork()
        if pid == 0:  # processo filho
            try:
                os.execve(self.argv[0], self.argv, self.env)
            except OSError as exc:
                os.write(2, f"guard: falha ao executar {self.argv[0]}: {exc}\n".encode())
            os._exit(127)

        self.child_pid, self.master = pid, master
        stdin_fd, stdout_fd = sys.stdin.fileno(), sys.stdout.fileno()
        old_attrs = termios.tcgetattr(stdin_fd) if os.isatty(stdin_fd) else None
        self._sync_winsize()
        old_winch = signal.signal(signal.SIGWINCH, lambda *_: self._sync_winsize())
        try:
            if old_attrs is not None:
                tty.setraw(stdin_fd)
            self._loop(stdin_fd, stdout_fd)
        finally:
            if old_attrs is not None:
                termios.tcsetattr(stdin_fd, termios.TCSAFLUSH, old_attrs)
            signal.signal(signal.SIGWINCH, old_winch)
            with contextlib.suppress(OSError):
                os.close(master)
            self.master = None
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else status >> 8

    def _loop(self, stdin_fd: int, stdout_fd: int) -> None:
        assert self.master is not None
        fds = [self.master, stdin_fd]
        last_tick = 0.0
        while True:
            try:
                ready, _, _ = select.select(fds, [], [], self.tick_interval)
            except InterruptedError:
                continue
            if self.master in ready:
                try:
                    data = os.read(self.master, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:  # Linux: filho terminou
                        return
                    raise
                if not data:  # macOS: filho terminou
                    return
                _write_all(stdout_fd, data)
                self.last_output_at = time.time()
            if stdin_fd in ready:
                data = os.read(stdin_fd, 4096)
                if not data:
                    fds.remove(stdin_fd)  # stdin fechado (ex.: pipe)
                else:
                    _write_all(self.master, data)
                    self._track_input(data)
            now = time.time()
            if now - last_tick >= self.tick_interval:
                last_tick = now
                self._tick()


def _kernel32() -> Any:
    """kernel32 com argtypes declarados (evita truncar HANDLEs de 64 bits)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetStdHandle.argtypes = [wintypes.DWORD]
    k32.GetStdHandle.restype = wintypes.HANDLE
    k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.ReadConsoleW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                 ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    return k32


class WinConsole:
    """Console do Windows em modo "raw + sequências VT" (como um terminal
    Unix): as teclas chegam como bytes VT (setas = ESC[A...) e a saída do
    ConPTY é interpretada com cores e cursor. Restaura o modo original."""

    ENABLE_PROCESSED_INPUT, ENABLE_LINE_INPUT, ENABLE_ECHO_INPUT = 0x1, 0x2, 0x4
    ENABLE_VIRTUAL_TERMINAL_INPUT = 0x200
    ENABLE_PROCESSED_OUTPUT, ENABLE_VT_PROCESSING, DISABLE_NEWLINE_AUTO_RETURN = 0x1, 0x4, 0x8

    def __init__(self) -> None:
        self.k32 = _kernel32()
        self.h_in = self.k32.GetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF))   # STD_INPUT_HANDLE
        self.h_out = self.k32.GetStdHandle(wintypes.DWORD(-11 & 0xFFFFFFFF))  # STD_OUTPUT_HANDLE
        self.saved: dict[int, int] = {}

    def _mode(self, handle: Any) -> Optional[int]:
        mode = wintypes.DWORD()
        return mode.value if self.k32.GetConsoleMode(handle, ctypes.byref(mode)) else None

    def enable_vt_output(self) -> None:
        mode = self._mode(self.h_out)
        if mode is not None:
            self.k32.SetConsoleMode(self.h_out, mode | self.ENABLE_PROCESSED_OUTPUT | self.ENABLE_VT_PROCESSING)

    def enter_raw(self) -> None:
        for handle in (self.h_in, self.h_out):
            mode = self._mode(handle)
            if mode is not None:
                self.saved[handle] = mode
        if self.h_in in self.saved:
            mode = self.saved[self.h_in]
            mode &= ~(self.ENABLE_PROCESSED_INPUT | self.ENABLE_LINE_INPUT | self.ENABLE_ECHO_INPUT)
            self.k32.SetConsoleMode(self.h_in, mode | self.ENABLE_VIRTUAL_TERMINAL_INPUT)
        if self.h_out in self.saved:
            self.k32.SetConsoleMode(self.h_out, self.saved[self.h_out] | self.ENABLE_PROCESSED_OUTPUT
                                    | self.ENABLE_VT_PROCESSING | self.DISABLE_NEWLINE_AUTO_RETURN)

    def restore(self) -> None:
        for handle, mode in self.saved.items():
            self.k32.SetConsoleMode(handle, mode)
        self.saved.clear()

    def read_input(self) -> str:
        """Bloqueia até haver teclas; devolve texto (UTF-16 → str, acentos ok)."""
        buf = ctypes.create_unicode_buffer(4096)
        count = wintypes.DWORD()
        if not self.k32.ReadConsoleW(self.h_in, buf, 4096, ctypes.byref(count), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return buf[: count.value]


# Uma única thread lê o teclado durante toda a vida do processo; cada sessão
# (inclusive a reaberta no failover) consome desta fila. Assim nenhuma tecla
# fica presa numa thread de uma sessão que já terminou.
_console_queue: "queue.Queue[str]" = queue.Queue()
_console_reader: Optional[threading.Thread] = None


def _ensure_console_reader(console: WinConsole) -> None:
    global _console_reader
    if _console_reader is not None:
        return

    def loop() -> None:
        while True:
            try:
                text = console.read_input()
            except OSError:
                time.sleep(0.2)
                continue
            if text:
                _console_queue.put(text)

    _console_reader = threading.Thread(target=loop, name="console-input", daemon=True)
    _console_reader.start()


class WindowsConPtySession(TerminalSession):
    """Windows 10 1809+ / 11: pseudo-console (ConPTY) via pywinpty."""

    proc: Any = None

    def _write_child(self, text: str) -> None:
        self.proc.write(text)

    def _pump_output(self, done: threading.Event) -> None:
        out = sys.stdout.buffer  # bytes UTF-8 sem conversão \n → \r\n (quebraria o TUI)
        try:
            while True:
                try:
                    data = self.proc.read(65536)
                except EOFError:
                    break
                if not data:
                    if not self.proc.isalive():
                        break
                    time.sleep(0.01)
                    continue
                out.write(data.encode("utf-8", "replace"))
                out.flush()
                self.last_output_at = time.time()
        except Exception:
            log.exception("erro lendo a saída do Claude Code")
        finally:
            done.set()

    def run(self) -> int:
        try:
            from winpty import PtyProcess  # type: ignore
        except ImportError:
            raise GuardError("no Windows o `run` precisa do pywinpty: py -m pip install pywinpty "
                             "(o .exe gerado pelo build_exe.bat já inclui)") from None
        cols, rows = _terminal_size()
        self.proc = PtyProcess.spawn(self.argv, cwd=os.getcwd(), env=self.env, dimensions=(rows, cols))
        self.child_pid = self.proc.pid
        console = WinConsole()
        console.enter_raw()
        _ensure_console_reader(console)
        out_done = threading.Event()
        threading.Thread(target=self._pump_output, args=(out_done,), name="pty-output", daemon=True).start()
        size, last_tick = (cols, rows), 0.0
        try:
            while not out_done.is_set():
                try:
                    text = _console_queue.get(timeout=0.05)
                except queue.Empty:
                    text = None
                if text:
                    with contextlib.suppress(EOFError):
                        self._write_child(text)
                    self._track_input(text.encode("utf-8", "replace"))
                now = time.time()
                if now - last_tick >= self.tick_interval:
                    last_tick = now
                    new_size = _terminal_size()  # Windows não tem SIGWINCH
                    if new_size != size:
                        size = new_size
                        with contextlib.suppress(Exception):
                            self.proc.setwinsize(new_size[1], new_size[0])
                    self._tick()
                    if not self.proc.isalive():
                        out_done.wait(1.0)  # deixa a última saída ser desenhada
                        break
        finally:
            console.restore()
        deadline = time.time() + 3
        while self.proc.isalive() and time.time() < deadline:
            time.sleep(0.05)
        code = self.proc.exitstatus
        with contextlib.suppress(Exception):
            self.proc.close()
        return int(code) if isinstance(code, int) else 0


def make_session(argv: list[str], env: dict[str, str],
                 on_tick: Callable[[TerminalSession], None]) -> TerminalSession:
    cls = WindowsConPtySession if IS_WINDOWS else PosixPtySession
    return cls(argv, env, on_tick)


def npm_shim_target(shim_path: str, text: Optional[str] = None) -> Optional[list[str]]:
    """Lê um claude.cmd gerado pelo npm e devolve o comando real
    ([node, cli.js] ou [algum.exe]). O ConPTY não executa .cmd e passar pelo
    cmd.exe embaralharia as aspas dos argumentos."""
    try:
        text = text if text is not None else Path(shim_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    base = Path(shim_path).parent
    m = re.search(r'"%dp0%\\([^"]+?\.(?:c|m)?js)"', text, re.I)
    if m:
        script = base / m.group(1).replace("\\", "/")
        if not script.is_file():
            return None
        local_node = base / "node.exe"
        node = str(local_node) if local_node.is_file() else shutil.which("node")
        return [node, str(script)] if node else None
    m = re.search(r'"%dp0%\\([^"]+?\.exe)"', text, re.I)
    if m:
        exe = base / m.group(1).replace("\\", "/")
        return [str(exe)] if exe.is_file() else None
    return None


def claude_launch_prefix(binary: str) -> list[str]:
    """Comando que inicia o Claude Code (sem os argumentos)."""
    if not IS_WINDOWS or not binary.lower().endswith((".cmd", ".bat")):
        return [binary]  # Linux/macOS, ou claude.exe do instalador nativo
    target = npm_shim_target(binary)
    if target:
        return target
    log.warning("não consegui ler %s; usando cmd.exe (argumentos com aspas podem falhar)", binary)
    return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", binary]


# --------------------------------------------------------------------------
# Instância, hooks e leitura do transcript
# --------------------------------------------------------------------------


def instance_dir(instance_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{8,32}", instance_id):
        raise GuardError("id de instância inválido")
    return INSTANCES_DIR / instance_id


def app_dir() -> Path:
    """Pasta do programa: a do .exe (PyInstaller) ou a deste script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def asset_path(name: str) -> Optional[Path]:
    """Arquivo da pasta assets/ (ao lado do script/.exe ou embutido no .exe)."""
    for base in (getattr(sys, "_MEIPASS", None), app_dir()):
        if base and (Path(base) / "assets" / name).is_file():
            return Path(base) / "assets" / name
    return None


def self_command() -> list[str]:
    """Como chamar este programa de novo (para os hooks)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    if IS_WINDOWS and " " in sys.executable and shutil.which("py"):
        # o hook só usa a biblioteca padrão: qualquer Python 3 serve
        return ["py", "-3", str(Path(__file__).resolve())]
    return [sys.executable, str(Path(__file__).resolve())]


def hook_command(parts: Optional[list[str]] = None, windows: bool = IS_WINDOWS, sub: str = "hook") -> str:
    """Linha de comando do hook. No Windows usa barras normais e só põe aspas
    quando há espaços, para funcionar em Git Bash, cmd e PowerShell."""
    parts = list(parts or self_command()) + [sub]
    if not windows:
        return shlex.join(parts)
    out = []
    for p in parts:
        if not SHELL_SAFE_RE.fullmatch(p) and set(p) & SHELL_META:
            p = _short_path(p)  # O'Neil, (x), & ... : o nome 8.3 não tem nada disso
        p = p.replace("\\", "/")
        out.append(p if SHELL_SAFE_RE.fullmatch(p) else f'"{p}"')
    return " ".join(out)


# Partes do comando do hook que rodam sem aspas no Git Bash, no cmd e no
# PowerShell (letras com acento incluídas). O resto vai entre aspas duplas.
SHELL_SAFE_RE = re.compile(r"[\w./:\\\-+=@,~]+")
SHELL_META = set("'`$&()[]{};|<>!^%#*?")


def _short_path(path: str) -> str:
    """Nome curto 8.3 do Windows (C:\\PROGRA~1\\...), se o volume tiver."""
    if not IS_WINDOWS:
        return path
    with contextlib.suppress(Exception):
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024)  # type: ignore[attr-defined]
        if 0 < n < 1024:
            return buf.value
    return path


def build_hook_settings() -> dict[str, Any]:
    """Settings para `claude --settings`: hooks que reportam o estado da
    sessão para este programa. Não altera o settings.json do usuário."""
    hook = [{"type": "command", "command": hook_command(), "timeout": 5}]
    plain = [{"hooks": hook}]
    return {"hooks": {
        "SessionStart": plain,
        "UserPromptSubmit": plain,
        "PreToolUse": [{"matcher": "*", "hooks": hook}],
        "Notification": plain,
        "Stop": plain,
    }}


def write_hook_settings(idir: Path) -> str:
    """Grava os settings num arquivo (passar JSON pela linha de comando é
    frágil no Windows por causa das aspas)."""
    path = idir / "settings.json"
    atomic_write_json(path, build_hook_settings())
    return str(path)


def read_context_tokens(transcript_path: str) -> Optional[int]:
    """Tamanho do contexto do último turno (input + cache), lido do fim do
    transcript JSONL do Claude Code. Ignora turnos de subagentes."""
    path = Path(transcript_path).expanduser()
    try:
        if path.suffix != ".jsonl" or not path.is_file():
            return None
        with open(path, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - 512 * 1024))
            chunk = fh.read()
    except OSError:
        return None
    for line in reversed(chunk.splitlines()):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "assistant" or obj.get("isSidechain"):
            continue
        usage = (obj.get("message") or {}).get("usage")
        if isinstance(usage, dict):
            keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            return sum(int(usage.get(k) or 0) for k in keys)
    return None


def transcript_interrupted(transcript_path: str, since: float = 0.0) -> bool:
    """O turno terminou com Esc? Recusar um pedido de permissão ou interromper
    o Claude não dispara o hook Stop (nem o idle_prompt), mas grava no
    transcript uma mensagem do usuário "[Request interrupted by user...]".
    Só vale se essa mensagem for de `since` em diante (epoch)."""
    path = Path(transcript_path).expanduser()
    try:
        if path.suffix != ".jsonl" or not path.is_file():
            return False
        with open(path, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - 64 * 1024))
            chunk = fh.read()
    except OSError:
        return False
    for line in reversed(chunk.splitlines()):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get("type") not in ("user", "assistant") or obj.get("isSidechain"):
            continue  # linhas de custo, modo etc. e turnos de subagentes
        if obj["type"] != "user":
            return False
        content = (obj.get("message") or {}).get("content")
        blocks = [content] if isinstance(content, str) else [
            b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"]
        if not any(str(t).startswith("[Request interrupted by user") for t in blocks):
            return False
        when = _parse_iso(obj.get("timestamp"))
        return when is not None and when.timestamp() >= since
    return False


# O `/model X` do Claude Code também grava X como padrão de novas sessões no
# settings.json do usuário. O guard guarda o valor original e o devolve depois
# de cada /model que ele mesmo digita (o seu settings.json fica como estava).
_ABSENT, _UNKNOWN = object(), object()


def user_settings_path() -> Path:
    return claude_config_dir() / "settings.json"


def read_default_model() -> Any:
    """Valor de "model" no settings.json; _ABSENT se não há a chave e
    _UNKNOWN se o arquivo não pôde ser lido (aí nada é restaurado)."""
    try:
        data, _ = read_settings_json(user_settings_path())
    except FileNotFoundError:
        return _ABSENT
    except (OSError, ValueError):
        return _UNKNOWN
    return data.get("model", _ABSENT)


def restore_default_model(original: Any) -> bool:
    """Devolve "model" ao valor original. True se precisou mexer no arquivo."""
    if original is _UNKNOWN:
        return False
    path = user_settings_path()
    try:
        data, text = read_settings_json(path)
    except (OSError, ValueError):
        return False
    if data.get("model", _ABSENT) == original:
        return False
    if original is _ABSENT:
        data.pop("model", None)
    else:
        data["model"] = original
    write_settings_json(path, data, text)
    return True


class GuardController:
    """Liga monitor de uso + política + sessão PTY. Roda na thread principal,
    chamado a cada tick do loop de E/S."""

    def __init__(self, cfg: dict[str, Any], instance_id: str, monitor: UsageMonitor,
                 state: GuardState, proxy: Optional[ProxyManager]):
        self.cfg, self.instance_id, self.monitor, self.state, self.proxy = cfg, instance_id, monitor, state, proxy
        self.dir = instance_dir(instance_id)
        self.hook_file = self.dir / "hooks.jsonl"
        self.hook_offset = 0
        self.hook_event: Optional[str] = None
        self.hook_blocked = False  # Notification de permissão pendente
        self.last_injection_at = 0.0
        self.last_status_write = 0.0
        self.last_blocker: Optional[str] = ""
        self.transcript_path: Optional[str] = None
        self.last_interrupt_check = 0.0
        self.busy_since = 0.0  # hora do último UserPromptSubmit/PreToolUse
        self.default_model = read_default_model()  # antes de qualquer /model nosso
        self.model_restore_until = 0.0
        self.relaunch_requested = False
        self.current_model: Optional[str] = cfg["model_switch"]["model"] if state.model_switched else None
        self.recent: list[str] = []

    # ---- leitura de eventos dos hooks -------------------------------------
    def _read_hooks(self) -> None:
        try:
            with open(self.hook_file, "rb") as fh:
                fh.seek(self.hook_offset)
                chunk = fh.read()
        except FileNotFoundError:
            return
        complete = chunk[: chunk.rfind(b"\n") + 1]
        self.hook_offset += len(complete)
        for line in complete.splitlines():
            try:
                self._on_hook(json.loads(line))
            except (ValueError, TypeError):
                continue

    def _on_hook(self, ev: dict[str, Any]) -> None:
        name = ev.get("event")
        ts = float(ev.get("ts") or time.time())
        if ev.get("session_id"):
            self.state.session_id = str(ev["session_id"])
        if ev.get("transcript_path"):
            self.transcript_path = str(ev["transcript_path"])
        if name == "Notification":
            msg = str(ev.get("message", "")).lower()
            ntype = str(ev.get("notification_type", ""))
            idle = ntype == "idle_prompt" or "waiting for your input" in msg
            self.hook_blocked = not idle
            self.hook_event = "Stop" if idle else "Notification"
            return
        if name not in IDLE_EVENTS | BUSY_EVENTS:
            return  # PreCompact etc. não mudam o estado
        self.hook_event, self.hook_blocked = name, False
        if name in BUSY_EVENTS:
            self.busy_since = ts
        if name == "UserPromptSubmit":
            self.state.last_activity_at = ts
        elif name == "Stop":
            self._turn_ended(ts)
        elif name == "SessionStart":
            source = ev.get("source")
            if source == "resume":  # --continue/--resume: já existe conversa
                self.state.turns_since_clear = max(1, self.state.turns_since_clear)
            elif source in ("clear", "compact"):
                self.state.context_tokens = None
            if source == "clear":  # /clear manual também atende o pedido pendente
                self.state.turns_since_clear = 0
                self.state.clear_requested = False

    def _turn_ended(self, ts: float) -> None:
        self.state.last_activity_at = ts
        self.state.turns_since_clear += 1
        if self.transcript_path:
            tokens = read_context_tokens(self.transcript_path)
            if tokens is not None:
                self.state.context_tokens, self.state.context_measured_at = tokens, ts

    def _check_interrupted(self, sess: TerminalSession, now: float) -> None:
        """Ocupado (ou num pedido de permissão), mas com a tela parada: confere
        no transcript se o turno acabou com Esc, que não dispara o Stop."""
        if not (self.hook_blocked or self.hook_event in BUSY_EVENTS) or not self.transcript_path:
            return
        if now - sess.last_output_at < self.cfg["idle"]["output_quiet_seconds"]:
            return
        if now - self.last_interrupt_check < 3:
            return
        self.last_interrupt_check = now
        if transcript_interrupted(self.transcript_path, since=self.busy_since - 1):
            log.info("turno interrompido pelo usuário (Esc); sessão ociosa")
            self.hook_event, self.hook_blocked = "Stop", False
            self._turn_ended(now)

    # ---- segurança da injeção ----------------------------------------------
    def session_state(self, sess: TerminalSession, now: float) -> str:
        if self.hook_event is None:
            return "desconhecido"
        if self.hook_blocked:
            return "aguardando permissão"
        if self.hook_event in BUSY_EVENTS:
            return "trabalhando"
        if now - sess.last_output_at < self.cfg["idle"]["output_quiet_seconds"]:
            return "trabalhando"
        return "ocioso"

    def safe_to_inject(self, sess: TerminalSession, now: float) -> bool:
        why = self._injection_blocker(sess, now)
        if why != self.last_blocker:  # com -v, registra cada mudança de motivo
            self.last_blocker = why
            log.debug("injeção %s", f"bloqueada: {why}" if why else "liberada")
        return why is None

    def _injection_blocker(self, sess: TerminalSession, now: float) -> Optional[str]:
        idle = self.cfg["idle"]
        if now - self.last_injection_at < idle["min_gap_between_injections_seconds"]:
            return "injeção recente"
        if sess.input_dirty:
            return "texto pela metade no campo"
        if now - sess.last_input_at < idle["input_quiet_seconds"]:
            return "usuário digitando"
        if now - sess.last_output_at < idle["output_quiet_seconds"]:
            return "tela mudando"
        if self.hook_event is None:
            return None if idle["allow_without_hooks"] else "hooks ainda não reportaram"
        if self.hook_blocked:
            return "aguardando permissão"
        return None if self.hook_event in IDLE_EVENTS else f"Claude ocupado ({self.hook_event})"

    # ---- tick -------------------------------------------------------------
    def on_tick(self, sess: TerminalSession) -> None:
        now = time.time()
        self._read_hooks()
        self._check_interrupted(sess, now)
        if self.model_restore_until:
            self.restore_user_default_model(now)
        req = self.dir / "clear.request"
        if req.exists():
            self.state.clear_requested = True
            with contextlib.suppress(OSError):
                req.unlink()
        snap, err = self.monitor.latest()
        fresh = snap if snap and snap.age(now) <= self.cfg["max_stale_seconds"] else None
        if now - self.last_status_write >= 2:
            self.last_status_write = now
            self.write_status(sess, now, snap, err)
        if not self.safe_to_inject(sess, now):
            return
        acts = decide(self.cfg, fresh, self.state, now)
        if acts:
            self.execute(sess, *acts[0], now=now)

    def execute(self, sess: TerminalSession, action: str, reason: str, now: float) -> None:
        ms = self.cfg["model_switch"]
        st = self.state
        if action == ACT_FAILOVER:
            st.failover_notified = True
            if self.proxy and self.cfg["failover"]["relaunch_session"]:
                if self.proxy.ensure_running():
                    self._inject(sess, "/exit", now)
                    self.relaunch_requested = True
                    self._record(action, reason + " → reabrindo sessão via proxy")
                else:
                    self._record(action, reason + " → proxy indisponível", ok=False)
            else:
                self._record(action, reason + " → próxima sessão usará o proxy")
                desktop_notify(self.cfg, "Claude Usage Guard",
                               "Uso crítico. Saia e reabra com `claude_usage_guard.py run` para usar o proxy.")
            return
        if action == ACT_CLEAR:
            self._inject(sess, "/clear", now)
            st.clear_requested = False
            st.turns_since_clear = 0
            st.context_tokens = None
        elif action == ACT_COMPACT:
            self._inject(sess, "/compact", now)
            st.last_compact_at = now
            snap, _ = self.monitor.latest()
            if snap:
                st.compacted_window = _window_key(snap)
        elif action == ACT_SWITCH:
            self._inject(sess, f"/model {ms['model']}", now)
            st.model_switched, self.current_model = True, ms["model"]
            self.model_restore_until = now + 15
            desktop_notify(self.cfg, "Claude Usage Guard", f"Modelo trocado para {ms['model']}: {reason}")
        elif action == ACT_RESTORE:
            self._inject(sess, f"/model {ms['restore_model']}", now)
            st.model_switched, self.current_model = False, None
            self.model_restore_until = now + 15
        self._record(action, reason)

    def restore_user_default_model(self, now: float, final: bool = False) -> None:
        """Depois de um /model nosso, devolve o padrão do settings.json.
        Confere por alguns segundos, até o Claude Code gravar a mudança."""
        try:
            if restore_default_model(self.default_model):
                log.info("modelo padrão do settings.json restaurado (o /model do guard vale só nesta sessão)")
                self.model_restore_until = 0.0
                return
        except OSError as exc:
            log.warning("não consegui restaurar o modelo padrão do settings.json: %s", exc)
        if final or now > self.model_restore_until:
            self.model_restore_until = 0.0

    def _inject(self, sess: TerminalSession, text: str, now: float) -> None:
        log.info("injetando %r", text)
        sess.inject(text)
        self.last_injection_at = now

    def _record(self, action: str, reason: str, ok: bool = True) -> None:
        log.info("ação %s: %s", action, reason)
        log_action(self.instance_id, action, reason, ok)

    def write_status(self, sess: TerminalSession, now: float, snap: Optional[UsageSnapshot], err: Optional[str]) -> None:
        atomic_write_json(self.dir / "status.json", {
            "instance": self.instance_id, "pid": os.getpid(), "child_pid": sess.child_pid,
            "cwd": os.getcwd(), "updated_at": now, "state": self.session_state(sess, now),
            "model_override": self.current_model, "failover_active": self.state.failover_active,
            "proxy_url": self.proxy.base_url if (self.proxy and self.state.failover_active) else None,
            "context_tokens": self.state.context_tokens, "clear_requested": self.state.clear_requested,
            "usage_error": err, "hooks_ok": self.hook_event is not None,
        })


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

WINDOW_LABELS = {
    "five_hour": "Sessão (5h)",
    "seven_day": "Semanal (7d)",
    "seven_day_opus": "Opus (7d)",
    "seven_day_sonnet": "Sonnet (7d)",
}


def _display_windows(snap: UsageSnapshot) -> list[str]:
    """Janelas conhecidas primeiro; as desconhecidas depois, omitindo as que
    vêm sem utilização (o endpoint real manda, p.ex., "extra_usage": null)."""
    known = [n for n in WINDOW_LABELS if n in snap.windows]
    extra = sorted(n for n, w in snap.windows.items()
                   if n not in WINDOW_LABELS and w.utilization is not None)
    return known + extra


def _window_level(cfg: dict[str, Any], name: str, pct: Optional[float]) -> str:
    """Nível de alerta de uma janela: "dim", "normal", "warn" ou "crit".
    Janelas sem rótulo são internas do endpoint (ex.: "iguana_necktie") e não
    entram na política: ficam esmaecidas, sem cor de alerta."""
    if pct is None or name not in WINDOW_LABELS:
        return "dim"
    weekly = name != "five_hour"
    warn = cfg["model_switch"]["weekly_threshold" if weekly else "session_threshold"]
    crit = cfg["failover"]["weekly_threshold" if weekly else "session_threshold"]
    return "crit" if pct >= crit else ("warn" if pct >= warn else "normal")


def _fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, sec = divmod(s, 60)
    if d:
        return f"{d}d{h:02d}h"
    return f"{h}h{m:02d}m" if h else (f"{m}m" if m else f"{sec}s")


# Paleta da marca (assets/colors.png): azul-celeste #2DAAF4, preto e branco.
# Fundo preto/branco fica a cargo do tema do seu terminal; o azul marca o
# título, as seções e as barras em nível normal. Amarelo/vermelho seguem como
# alerta (avisam que um limiar foi cruzado).
BRAND = "38;2;45;170;244"
BRAND_BOLD = "1;" + BRAND


class Colors:
    def __init__(self, enabled: bool):
        self.on = enabled

    def __call__(self, code: str, text: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if self.on else text


def list_instances() -> list[dict[str, Any]]:
    out = []
    if not INSTANCES_DIR.is_dir():
        return out
    for d in INSTANCES_DIR.iterdir():
        st = read_json(d / "status.json")
        if st and pid_alive(st.get("pid")):
            out.append(st)
        elif d.is_dir() and time.time() - d.stat().st_mtime > 3600:
            shutil.rmtree(d, ignore_errors=True)  # restos de instâncias mortas
    return sorted(out, key=lambda s: s.get("instance", ""))


def recent_actions(limit: int = 8) -> list[dict[str, Any]]:
    try:
        with open(ACTIONS_LOG, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - 64 * 1024))
            lines = fh.read().splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        with contextlib.suppress(ValueError):
            out.append(json.loads(line))
    return out


def render_dashboard(cfg: dict[str, Any], snap: Optional[UsageSnapshot], err: Optional[str],
                     instances: list[dict[str, Any]], actions: list[dict[str, Any]],
                     now: Optional[float] = None, color: bool = True) -> str:
    now = now or time.time()
    c = Colors(color)
    width = int(cfg["dashboard"]["bar_width"])
    lines = [c(BRAND_BOLD, f" Claude Usage Guard {__version__}") + c("2", "   " + time.strftime("%H:%M:%S", time.localtime(now))), ""]

    if snap:
        age = snap.age(now)
        stale = age > cfg["max_stale_seconds"]
        lines.append(c("2", f" dados de {_fmt_duration(age)} atrás") + (c("31", "  (DESATUALIZADO: ações pausadas)") if stale else ""))
        for name in _display_windows(snap):
            w = snap.windows[name]
            pct = w.utilization
            code = {"dim": "2", "normal": BRAND, "warn": "33", "crit": "31"}[_window_level(cfg, name, pct)]
            if pct is None:
                bar, pct_s = "·" * width, "  n/d"
            else:
                filled = int(round(pct / 100 * width))
                bar = "█" * filled + "░" * (width - filled)
                pct_s = f"{pct:5.1f}%"
            label = WINDOW_LABELS.get(name, name)
            lines.append(f" {label[:15]:<16}{c(code, bar)} {c(code, pct_s)}  reinicia em {_fmt_duration(w.resets_in(now))}")
    else:
        lines.append(c("33", " sem dados de uso ainda"))
    if err:
        lines.append(c("31", f" ! {err}"))

    t = cfg
    lines += ["", c("2", " limiares (5h): "
                         f"compact {t['compact']['session_threshold']}% · "
                         f"modelo {t['model_switch']['session_threshold']}% · "
                         f"failover {t['failover']['session_threshold']}%"
                         + ("" if t["failover"]["enabled"] else " (desligado)")), ""]

    lines.append(c(BRAND_BOLD, " Sessões protegidas"))
    if not instances:
        lines.append(c("2", "  nenhuma (inicie com: claude_usage_guard.py run)"))
    for inst in instances:
        ctx = inst.get("context_tokens")
        bits = [
            f"#{inst.get('instance', '?')[:8]}",
            f"estado: {inst.get('state')}",
            f"modelo: {inst.get('model_override') or 'padrão'}",
            f"proxy: {'ATIVO ' + str(inst.get('proxy_url')) if inst.get('failover_active') else 'off'}",
            f"contexto: {ctx // 1000}k tok" if isinstance(ctx, int) else "contexto: —",
        ]
        if inst.get("clear_requested"):
            bits.append("clear pendente")
        if not inst.get("hooks_ok"):
            bits.append(c("33", "hooks ainda não reportaram"))
        lines.append("  " + "  ".join(bits))
        lines.append(c("2", f"    {inst.get('cwd', '')}"))

    lines += ["", c(BRAND_BOLD, " Ações recentes")]
    if not actions:
        lines.append(c("2", "  nenhuma"))
    for a in reversed(actions):
        when = time.strftime("%d/%m %H:%M", time.localtime(float(a.get("ts", 0))))
        mark = c(BRAND, "✓") if a.get("ok", True) else c("31", "✗")
        lines.append(f"  {mark} {when}  {a.get('action', ''):<14} #{str(a.get('instance', ''))[:8]}  {a.get('reason', '')}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Janela gráfica (tkinter): os mesmos dados do dashboard, numa janela
# --------------------------------------------------------------------------

GUI_PID_FILE = STATE_DIR / "gui.pid"
# Paleta da marca (assets/colors.png): preto, branco e azul-celeste #2DAAF4.
# Amarelo/vermelho só quando um limiar é cruzado, como no dashboard.
GUI_COLORS = {"bg": "#000000", "panel": "#121212", "track": "#2A2A2A", "fg": "#FFFFFF",
              "dim": "#8C8C8C", "normal": "#2DAAF4", "warn": "#F5C542", "crit": "#F0524F"}
GUI_STATE_COLORS = {"ocioso": "normal", "trabalhando": "fg", "aguardando permissão": "warn"}

# (snapshot, erro, instâncias do run, ações, sessões do Desktop)
DashboardData = tuple[Optional[UsageSnapshot], Optional[str], list[dict[str, Any]], list[dict[str, Any]],
                      list["DesktopSessionState"]]
DESKTOP_STATE_KEEP_SECONDS = 7 * 86400
GUI_LEVEL_TEXT = {"normal": "cota normal", "attention": "cota em atenção", "high": "cota alta",
                  "critical": "cota crítica"}


def list_desktop_sessions(hours: float, now: Optional[float] = None) -> list[DesktopSessionState]:
    """Sessões do Desktop atualizadas nas últimas `hours` horas, mais recentes
    primeiro. Apaga estados com mais de 7 dias."""
    now = now or time.time()
    out: list[DesktopSessionState] = []
    try:
        files = list(desktop_dir().glob("*.json"))
    except OSError:
        return out
    for f in files:
        if f.name == "alerts.json":
            continue
        try:
            if now - f.stat().st_mtime > DESKTOP_STATE_KEEP_SECONDS:
                f.unlink()
                continue
        except OSError:
            continue
        data = read_json(f)
        if not isinstance(data, dict):
            continue
        try:
            st = DesktopSessionState.from_json(data)
        except TypeError:
            continue
        recent = isinstance(st.updated_at, (int, float)) and now - st.updated_at <= hours * 3600
        # Sessão com pedido pendente continua visível (para cancelar) até o pedido expirar.
        if recent or (SESSION_ID_RE.fullmatch(str(st.session_id)) and read_pending(st.session_id)):
            out.append(st)
    with contextlib.suppress(OSError):  # pedidos de sessões que nunca mais rodaram
        for f in pending_dir().glob("*.json"):
            with contextlib.suppress(OSError):
                if now - f.stat().st_mtime > DESKTOP_STATE_KEEP_SECONDS:
                    f.unlink()
    out.sort(key=lambda st: st.updated_at, reverse=True)
    return out


DESKTOP_CARDS = 4
DELIVERED_SHOW_SECONDS = 600


def economy_button(pending: list[str], economy_mode: bool) -> tuple[str, str]:
    """(rótulo, ação do clique) do botão de modo econômico."""
    if "economy_on" in pending:
        return "✓ Economizar", "economy_on"
    if "economy_off" in pending:
        return "✓ Desligar economia", "economy_off"
    return ("Economizar: ligado", "economy_off") if economy_mode else ("Economizar", "economy_on")


def desktop_status_line(pending: list[str], st: DesktopSessionState, now: float, critical: bool) -> Optional[str]:
    """Linha de situação dos pedidos de um cartão (None se nada a dizer)."""
    parts: list[str] = []
    if pending:
        names = ", ".join(ACTION_LABELS[a] for a in pending)
        if st.last_event == "UserPromptSubmit":  # o Claude está no meio de um turno
            parts.append(f"pendente: {names} · vai no fim do turno atual (ou com a sua próxima mensagem)")
        else:
            parts.append(f"pendente: {names} · vai junto com a sua próxima mensagem (até um 'ok' serve)")
    elif st.delivered_actions and 0 <= now - st.delivered_at < DELIVERED_SHOW_SECONDS:
        names = ", ".join(ACTION_LABELS.get(a, a) for a in st.delivered_actions)
        via = "fim do turno" if st.delivered_via == "Stop" else "sua mensagem"
        parts.append(f"entregue há {_fmt_duration(now - st.delivered_at)}: {names} ({via})")
    if critical:
        parts.append("pesquisa e skills pausadas: cota crítica")
    return " · ".join(parts) or None


def gui_running() -> bool:
    try:
        pid = int(GUI_PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return pid != os.getpid() and pid_alive(pid)


def launch_gui_detached(cfg: dict[str, Any]) -> None:
    """Abre a janela em segundo plano (sem console), se ainda não estiver aberta."""
    if not cfg["gui"]["open_on_run"] or gui_running():
        return
    if not (IS_WINDOWS or sys.platform == "darwin" or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return
    env = {k: v for k, v in os.environ.items() if k != "CUG_INSTANCE_ID"}
    kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                              "stderr": subprocess.DEVNULL, "env": env}
    if IS_WINDOWS:
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW: sem console
        # e sem receber o Ctrl-C da sessão do Claude Code.
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([*self_command(), "gui"], **kwargs)
    except OSError as exc:
        log.warning("não consegui abrir a janela: %s", exc)


def open_with_default_app(path: Path) -> None:
    if IS_WINDOWS:
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class GuardWindow:
    """Janela com uso 5h/7d, sessões protegidas e ações recentes. `data`
    devolve (snapshot, erro, instâncias, ações): em uso real vem do monitor e
    dos arquivos de estado; nos testes, de dados falsos."""

    def __init__(self, cfg: dict[str, Any], data: Callable[[], DashboardData]):
        import tkinter as tk
        from tkinter import font as tkfont

        self.tk, self.cfg, self.data = tk, cfg, data
        self.clicked: dict[str, float] = {}  # instância → hora do clique em "Pedir /clear"
        self.root = root = tk.Tk()
        root.title("Claude Usage Guard")
        root.configure(bg=GUI_COLORS["bg"])
        root.geometry("600x840")
        root.minsize(520, 420)
        icon = asset_path("app.ico")
        if icon and IS_WINDOWS:
            with contextlib.suppress(tk.TclError):
                root.iconbitmap(str(icon))
        family = "Segoe UI" if IS_WINDOWS else "TkDefaultFont"
        self.f_body = tkfont.Font(family=family, size=10)
        self.f_small = tkfont.Font(family=family, size=9)
        self.f_bold = tkfont.Font(family=family, size=10, weight="bold")
        self.f_title = tkfont.Font(family=family, size=14, weight="bold")
        self.f_section = tkfont.Font(family=family, size=11, weight="bold")
        footer = tk.Frame(root, bg=GUI_COLORS["bg"], padx=16, pady=10)
        footer.pack(fill="x", side="bottom")  # antes do corpo: fica visível mesmo com a janela baixa
        # Corpo rolável: Canvas + barra vertical; a roda do mouse também rola.
        view = tk.Frame(root, bg=GUI_COLORS["bg"])
        view.pack(fill="both", expand=True)
        from tkinter import ttk
        style = ttk.Style(root)
        with contextlib.suppress(tk.TclError):
            style.theme_use("clam")  # o tema nativo do Windows ignora cores: a barra sumia no fundo preto
        style.configure("Guard.Vertical.TScrollbar", background=GUI_COLORS["dim"], troughcolor=GUI_COLORS["panel"],
                        bordercolor=GUI_COLORS["bg"], arrowcolor=GUI_COLORS["fg"], lightcolor=GUI_COLORS["dim"],
                        darkcolor=GUI_COLORS["dim"])
        style.map("Guard.Vertical.TScrollbar", background=[("active", GUI_COLORS["normal"])])
        self.scrollbar = ttk.Scrollbar(view, orient="vertical", style="Guard.Vertical.TScrollbar")
        self.scrollbar.pack(side="right", fill="y")
        self.canvas = canvas = tk.Canvas(view, bg=GUI_COLORS["bg"], highlightthickness=0, bd=0,
                                         yscrollcommand=self.scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.configure(command=canvas.yview)
        self.body = tk.Frame(canvas, bg=GUI_COLORS["bg"], padx=16, pady=12)
        body_item = canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(body_item, width=e.width))
        root.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        root.bind_all("<Button-4>", lambda _e: canvas.yview_scroll(-1, "units"))  # Linux
        root.bind_all("<Button-5>", lambda _e: canvas.yview_scroll(1, "units"))
        self._button(footer, "Abrir log", self._open_log).pack(side="right")
        self.footer_note = self._label(footer, "", "dim", self.f_small)
        self.footer_note.pack(side="left")

    # ---- widgets -----------------------------------------------------------
    def _label(self, parent: Any, text: str, color: str = "fg", font: Any = None, **kw: Any) -> Any:
        bg = kw.pop("bg", parent.cget("bg"))
        return self.tk.Label(parent, text=text, fg=GUI_COLORS[color], bg=bg, font=font or self.f_body,
                             anchor="w", justify="left", **kw)

    def _button(self, parent: Any, text: str, command: Callable[[], None], enabled: bool = True) -> Any:
        return self.tk.Button(parent, text=text, command=command, font=self.f_small, relief="flat",
                              bd=0, padx=10, pady=3, cursor="hand2" if enabled else "arrow",
                              state="normal" if enabled else "disabled",
                              bg=GUI_COLORS["normal"] if enabled else GUI_COLORS["track"],
                              fg=GUI_COLORS["bg"], activebackground=GUI_COLORS["fg"],
                              activeforeground=GUI_COLORS["bg"], disabledforeground=GUI_COLORS["dim"])

    def _section(self, title: str) -> None:
        self._label(self.body, title, "normal", self.f_section).pack(fill="x", pady=(14, 4))

    # ---- ações dos botões ---------------------------------------------------
    def _open_log(self) -> None:
        log_file = STATE_DIR / "guard.log"
        try:
            open_with_default_app(log_file)
        except OSError as exc:
            self.footer_note.configure(text=f"não abriu {log_file}: {exc}", fg=GUI_COLORS["crit"])

    def _ask_clear(self, iid: str) -> None:
        try:
            ok = request_clear(iid)
        except (OSError, GuardError) as exc:
            ok, why = False, str(exc)
        else:
            why = "a sessão já terminou"
        if ok:
            self.clicked[iid] = time.time()
            self.footer_note.configure(text=f"/clear pedido para #{iid[:8]}: roda quando a tarefa terminar",
                                       fg=GUI_COLORS["dim"])
        else:
            self.footer_note.configure(text=f"não deu para pedir /clear: {why}", fg=GUI_COLORS["crit"])
        self.refresh(reschedule=False)

    def _toggle_request(self, sid: str, action: str, expect_pending: bool, busy: bool = False) -> None:
        """Clique num botão de uma sessão do Desktop: pede ou cancela."""
        label = ACTION_LABELS[action]
        try:
            pending = toggle_request(sid, action, time.time(), expect_pending=expect_pending)
        except (OSError, GuardError, ValueError) as exc:
            self.footer_note.configure(text=f"não deu para registrar o pedido (tente de novo): {exc}",
                                       fg=GUI_COLORS["crit"])
        else:
            when = "vai no fim do turno atual" if busy else "vai com a sua próxima mensagem"
            if pending is None:  # a janela estava desatualizada
                text = (f"{label} já tinha sido entregue a #{sid[:8]}" if expect_pending
                        else f"{label} já estava pendente para #{sid[:8]}")
            elif pending:
                text = f"{label} pedido para #{sid[:8]}: {when}"
            else:
                text = f"{label} cancelado para #{sid[:8]}"
            self.footer_note.configure(text=text, fg=GUI_COLORS["dim"])
        self.refresh(reschedule=False)

    # ---- desenho -------------------------------------------------------------
    def refresh(self, reschedule: bool = True) -> None:
        try:
            self.draw(*self.data())
        except Exception:  # um erro de desenho não pode fechar a janela
            log.exception("erro ao desenhar a janela")
        if reschedule:
            self.root.after(int(float(self.cfg["dashboard"]["refresh_seconds"]) * 1000), self.refresh)

    def draw(self, snap: Optional[UsageSnapshot], err: Optional[str], instances: list[dict[str, Any]],
             actions: list[dict[str, Any]], desktop: Optional[list[DesktopSessionState]] = None,
             now: Optional[float] = None) -> None:
        now = now or time.time()
        top = self.canvas.yview()[0]  # redesenhar não pode jogar a rolagem de volta ao topo
        for child in self.body.winfo_children():
            child.destroy()
        self.root.after_idle(lambda: self._restore_scroll(top))
        head = self.tk.Frame(self.body, bg=GUI_COLORS["bg"])
        head.pack(fill="x")
        self._label(head, "Claude Usage Guard", "normal", self.f_title).pack(side="left")
        self._label(head, f"  {__version__}", "dim", self.f_small).pack(side="left", pady=(5, 0))
        self._label(head, time.strftime("%H:%M:%S", time.localtime(now)), "dim").pack(side="right")
        fresh = snap if snap and snap.age(now) <= self.cfg["max_stale_seconds"] else None
        level, window = quota_level(self.cfg, fresh)
        self._draw_banner(level, window, fresh, now)
        self._draw_usage(snap, err, now)
        self._draw_desktop_sessions(desktop or [], now, level)
        self._draw_sessions(instances, now)
        self._draw_actions(actions)

    def _restore_scroll(self, top: float) -> None:
        self.body.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(top)

    def _draw_banner(self, level: str, window: Optional[str], snap: Optional[UsageSnapshot], now: float) -> None:
        """Faixa no topo quando a cota da conta está alta (amarelo) ou crítica (vermelho)."""
        if level not in ("high", "critical") or snap is None or window is None:
            return
        w = snap.windows[window]
        color = GUI_COLORS["warn" if level == "high" else "crit"]
        band = self.tk.Frame(self.body, bg=color, padx=10, pady=6)
        band.pack(fill="x", pady=(10, 0))
        self._label(band, quota_headline(level, window, w.utilization, w.resets_in(now)), "bg", self.f_bold,
                    bg=color).pack(fill="x")

    def _draw_desktop_sessions(self, sessions: list[DesktopSessionState], now: float, level: str = "normal") -> None:
        self._section("Sessões do Desktop")
        enabled = bool(self.cfg["desktop"]["enabled"])
        if not enabled:
            self._label(self.body, "modo Desktop desligado no config (desktop.enabled): os botões não entregam "
                        "pedidos", "warn", self.f_small).pack(fill="x")
        if not sessions:
            hours = self.cfg["desktop"]["session_list_hours"]
            self._label(self.body, f"nenhuma nas últimas {hours:g}h (para ativar: claude_usage_guard "
                        "install-desktop)", "dim").pack(fill="x")
        for st in sessions[:DESKTOP_CARDS]:
            card = self.tk.Frame(self.body, bg=GUI_COLORS["panel"], padx=10, pady=5)
            card.pack(fill="x", pady=2)
            top = self.tk.Frame(card, bg=GUI_COLORS["panel"])
            top.pack(fill="x")
            name = Path(st.cwd.replace("\\", "/")).name if st.cwd else ""
            self._label(top, name or "?", "fg", self.f_bold).pack(side="left")
            self._label(top, f"  #{st.session_id[:8]}", "dim", self.f_small).pack(side="left")
            ctx = st.context_tokens
            level_color = {"high": "warn", "critical": "crit"}.get(st.last_level or "", "dim")
            bits = [f"contexto {ctx // 1000}k tokens" if isinstance(ctx, int) else "contexto —",
                    GUI_LEVEL_TEXT.get(st.last_level or "", "cota —"),
                    f"há {_fmt_duration(max(0.0, now - st.updated_at))}"]
            self._label(card, "  ·  ".join(bits), level_color, self.f_small).pack(fill="x", pady=(2, 0))
            if st.last_note:
                self._label(card, st.last_note.removeprefix(NOTE_PREFIX).strip(), "dim", self.f_small,
                            wraplength=540).pack(fill="x")
            self._draw_request_buttons(card, st, now, enabled, level == "critical")
        if len(sessions) > DESKTOP_CARDS:
            self._label(self.body, f"+ {len(sessions) - DESKTOP_CARDS} outras", "dim", self.f_small).pack(fill="x")

    def _draw_request_buttons(self, card: Any, st: DesktopSessionState, now: float, enabled: bool,
                              critical: bool) -> None:
        """Botões Compactar / Economizar / Skills/MCPs / Pesquisar e a linha de situação."""
        try:
            pending = read_pending(st.session_id)
        except GuardError:
            return  # id inválido: nunca grava fila
        busy = st.last_event == "UserPromptSubmit"
        row = self.tk.Frame(card, bg=GUI_COLORS["panel"])
        row.pack(fill="x", pady=(4, 0))
        eco_label, eco_action = economy_button(pending, st.economy_mode)
        buttons = [("compact", None), (eco_action, eco_label), ("tools", None), ("research", None)]
        for action, label in buttons:
            is_pending = action in pending
            text = label or (f"✓ {ACTION_LABELS[action]}" if is_pending else ACTION_LABELS[action])
            # Com cota crítica, pesquisa e skills ficam pausadas (um pedido já pendente ainda pode ser cancelado).
            ok = enabled and (is_pending or not (critical and action in ("tools", "research")))
            self._button(row, text, lambda a=action, p=is_pending: self._toggle_request(st.session_id, a, p, busy),
                         enabled=ok).pack(side="left", padx=(0, 6))
        line = desktop_status_line(pending, st, now, critical)
        if line:
            self._label(card, line, "warn" if pending else "dim", self.f_small, wraplength=540).pack(fill="x",
                                                                                                  pady=(3, 0))

    def _draw_usage(self, snap: Optional[UsageSnapshot], err: Optional[str], now: float) -> None:
        self._section("Uso")
        if snap:
            stale = snap.age(now) > self.cfg["max_stale_seconds"]
            self._label(self.body, f"dados de {_fmt_duration(snap.age(now))} atrás"
                        + ("  (desatualizados: ações pausadas)" if stale else ""),
                        "crit" if stale else "dim", self.f_small).pack(fill="x")
            for name in _display_windows(snap):
                self._draw_bar(name, snap.windows[name], now)
        else:
            self._label(self.body, "sem dados de uso ainda", "warn").pack(fill="x")
        if err:
            self._label(self.body, f"! {err}", "crit", self.f_small, wraplength=540).pack(fill="x")
        t = self.cfg
        self._label(self.body, f"limiares (5h): compact {t['compact']['session_threshold']}%  ·  "
                    f"modelo {t['model_switch']['session_threshold']}%  ·  "
                    f"failover {t['failover']['session_threshold']}%"
                    + ("" if t["failover"]["enabled"] else " (desligado)"), "dim", self.f_small).pack(fill="x", pady=(4, 0))

    def _draw_bar(self, name: str, w: UsageWindow, now: float) -> None:
        level = _window_level(self.cfg, name, w.utilization)
        row = self.tk.Frame(self.body, bg=GUI_COLORS["bg"])
        row.pack(fill="x", pady=3)
        self._label(row, WINDOW_LABELS.get(name, name), "dim" if level == "dim" else "fg",
                    width=15).pack(side="left")
        bar_w, bar_h = 260, 12
        canvas = self.tk.Canvas(row, width=bar_w, height=bar_h, bg=GUI_COLORS["bg"], highlightthickness=0)
        canvas.pack(side="left", padx=(0, 10))
        canvas.create_rectangle(0, 0, bar_w, bar_h, fill=GUI_COLORS["track"], width=0)
        if w.utilization is not None:
            filled = max(0, min(bar_w, round(w.utilization / 100 * bar_w)))
            if filled:
                canvas.create_rectangle(0, 0, filled, bar_h, fill=GUI_COLORS[level], width=0)
        pct = "n/d" if w.utilization is None else f"{w.utilization:.0f}%"
        self._label(row, pct, level, self.f_bold, width=5).pack(side="left")
        self._label(row, f"reinicia em {_fmt_duration(w.resets_in(now))}", "dim", self.f_small).pack(side="left")

    def _draw_sessions(self, instances: list[dict[str, Any]], now: float) -> None:
        self._section("Sessões protegidas")
        if not instances:
            self._label(self.body, "nenhuma (abra com: claude_usage_guard run)", "dim").pack(fill="x")
        for inst in instances:
            iid = str(inst.get("instance", ""))
            card = self.tk.Frame(self.body, bg=GUI_COLORS["panel"], padx=10, pady=6)
            card.pack(fill="x", pady=3)
            top = self.tk.Frame(card, bg=GUI_COLORS["panel"])
            top.pack(fill="x")
            state = str(inst.get("state") or "desconhecido")
            dot = self.tk.Canvas(top, width=10, height=10, bg=GUI_COLORS["panel"], highlightthickness=0)
            dot.create_oval(1, 1, 9, 9, fill=GUI_COLORS[GUI_STATE_COLORS.get(state, "dim")], width=0)
            dot.pack(side="left", padx=(0, 6))
            cwd = str(inst.get("cwd") or "")
            self._label(top, Path(cwd).name or cwd or "?", "fg", self.f_bold).pack(side="left")
            self._label(top, f"  #{iid[:8]}", "dim", self.f_small).pack(side="left")
            pending = inst.get("clear_requested") or now - self.clicked.get(iid, 0) < 10
            self._button(top, "/clear pendente" if pending else "Pedir /clear",
                         lambda i=iid: self._ask_clear(i), enabled=not pending).pack(side="right")
            ctx = inst.get("context_tokens")
            bits = [state, f"modelo {inst.get('model_override') or 'padrão'}",
                    f"contexto {ctx // 1000}k tokens" if isinstance(ctx, int) else "contexto —"]
            if inst.get("failover_active"):
                bits.append(f"proxy {inst.get('proxy_url')}")
            self._label(card, "  ·  ".join(bits), "dim", self.f_small).pack(fill="x", pady=(2, 0))
            if not inst.get("hooks_ok"):
                self._label(card, "hooks ainda não reportaram (o guard não digita nada até lá)",
                            "warn", self.f_small).pack(fill="x")
            if inst.get("usage_error"):
                self._label(card, f"! {inst['usage_error']}", "crit", self.f_small, wraplength=520).pack(fill="x")
            self._label(card, cwd, "dim", self.f_small).pack(fill="x")

    def _draw_actions(self, actions: list[dict[str, Any]]) -> None:
        self._section("Ações recentes")
        if not actions:
            self._label(self.body, "nenhuma", "dim").pack(fill="x")
        for a in reversed(actions):
            row = self.tk.Frame(self.body, bg=GUI_COLORS["bg"])
            row.pack(fill="x", pady=1)
            ok = a.get("ok", True)
            self._label(row, "✓" if ok else "✗", "normal" if ok else "crit", self.f_bold, width=2).pack(side="left")
            when = time.strftime("%d/%m %H:%M", time.localtime(float(a.get("ts", 0))))
            self._label(row, when, "dim", self.f_small, width=11).pack(side="left")
            self._label(row, str(a.get("action", "")), "fg", self.f_small, width=13).pack(side="left")
            self._label(row, f"#{str(a.get('instance', ''))[:8]}  {a.get('reason', '')}", "dim", self.f_small,
                        wraplength=330).pack(side="left", fill="x")

    def run(self) -> None:
        self.refresh()
        self.root.mainloop()


# --------------------------------------------------------------------------
# Comandos
# --------------------------------------------------------------------------


def _use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def resolve_claude_binary(cfg: dict[str, Any]) -> str:
    binary = cfg["claude"]["binary"]
    has_dir = "/" in binary or "\\" in binary
    if has_dir:
        found = binary if (os.path.isfile(binary) and os.access(binary, os.X_OK)) else None
    else:
        found = shutil.which(binary)  # no Windows encontra claude.exe / claude.cmd via PATHEXT
    if not found:
        raise ConfigError(f"binário do Claude Code não encontrado: {binary} (ajuste claude.binary)")
    return os.path.abspath(found)


def cmd_run(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    if not sys.stdin.isatty():
        raise GuardError("`run` precisa de um terminal interativo")
    binary = resolve_claude_binary(cfg)
    instance_id = uuid.uuid4().hex[:12]
    idir = ensure_private_dir(instance_dir(instance_id))
    client = UsageClient()
    monitor = UsageMonitor(client, cfg["poll_interval_seconds"])
    state = GuardState()
    proxy = ProxyManager(cfg) if cfg["failover"]["enabled"] else None

    # Leitura inicial para decidir modelo/proxy antes de abrir o claude.
    snap = None
    monitor.poll_once()
    snap, err = monitor.latest()
    if err:
        print(f"guard: aviso: {err} (seguindo sem dados de uso)", file=sys.stderr)

    cli_args: list[str] = list(args.claude_args)
    if cli_args and cli_args[0] == "--":
        cli_args = cli_args[1:]
    base_args = list(cfg["claude"]["extra_args"])
    env = dict(os.environ, CUG_INSTANCE_ID=instance_id, CUG_STATE_DIR=str(STATE_DIR))
    s5 = snap.pct("five_hour") if snap else None
    s7 = snap.pct("seven_day") if snap else None
    fo, ms = cfg["failover"], cfg["model_switch"]

    if proxy and (_over(s5, fo["session_threshold"]) or _over(s7, fo["weekly_threshold"])):
        if proxy.ensure_running():
            env.update(proxy.child_env())
            state.failover_active = True
            log_action(instance_id, ACT_FAILOVER, f"uso crítico na abertura (5h {s5}%, 7d {s7}%) → {proxy.base_url}")
            print(f"guard: uso crítico — Claude Code usará o proxy {proxy.base_url}", file=sys.stderr)
        else:
            print("guard: uso crítico, mas o proxy não subiu (veja ~/.claude-usage-guard/guard.log)", file=sys.stderr)

    model_flags: list[str] = []
    user_set_model = any(a == "--model" or a.startswith("--model=") for a in base_args + cli_args)
    if ms["enabled"] and not user_set_model and (_over(s5, ms["session_threshold"]) or _over(s7, ms["weekly_threshold"])):
        model_flags = ["--model", ms["model"]]
        state.model_switched = True
        log_action(instance_id, ACT_SWITCH, f"uso alto na abertura → {ms['model']}")

    launch = claude_launch_prefix(binary)
    hooks = write_hook_settings(idir)
    argv = [*launch, "--settings", hooks, *base_args, *model_flags, *cli_args]
    controller = GuardController(cfg, instance_id, monitor, state, proxy)
    monitor.start()
    launch_gui_detached(cfg)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    log.info("instância %s iniciada (%s)", instance_id, os.getcwd())
    try:
        while True:
            code = make_session(argv, env, controller.on_tick).run()
            if not controller.relaunch_requested:
                return code
            # Failover no meio da sessão: reabre a MESMA conversa via proxy.
            # Os args passados após "--" NÃO são repetidos (poderiam conter um
            # prompt posicional); só claude.extra_args do config é reaplicado.
            controller.relaunch_requested = False
            assert proxy is not None
            env.update(proxy.child_env())
            state.failover_active = True
            resume = ["--resume", state.session_id] if state.session_id else ["--continue"]
            model_flags = ["--model", ms["model"]] if state.model_switched else []
            argv = [*launch, "--settings", hooks, *base_args, *model_flags, *resume]
            print(f"\r\nguard: reabrindo a sessão via proxy {proxy.base_url}...\r\n", file=sys.stderr)
    finally:
        monitor.stop()
        if controller.model_restore_until:
            controller.restore_user_default_model(time.time(), final=True)
        if proxy and fo["stop_proxy_on_exit"]:
            proxy.stop()
        shutil.rmtree(idir, ignore_errors=True)


def cmd_dashboard(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    monitor = UsageMonitor(UsageClient(), cfg["poll_interval_seconds"])
    monitor.start()
    tty_out = sys.stdout.isatty()
    if tty_out:
        sys.stdout.write("\x1b[?25l")  # esconde o cursor
    try:
        while True:
            snap, err = monitor.latest()
            frame = render_dashboard(cfg, snap, err, list_instances(), recent_actions(), color=_use_color())
            sys.stdout.write(("\x1b[H\x1b[2J" if tty_out else "") + frame + "\n")
            sys.stdout.flush()
            if args.once:
                return 0
            time.sleep(float(cfg["dashboard"]["refresh_seconds"]))
    except KeyboardInterrupt:
        return 0
    finally:
        monitor.stop()
        if tty_out:
            sys.stdout.write("\x1b[?25h\n")


def cmd_gui(cfg: dict[str, Any], _args: argparse.Namespace) -> int:
    ensure_private_dir(STATE_DIR)
    with file_lock(STATE_DIR / "gui.lock", timeout=5):  # dois `run` ao mesmo tempo
        if gui_running():
            print("a janela do Claude Usage Guard já está aberta")
            return 0
        GUI_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    try:
        import importlib.util
        if not importlib.util.find_spec("tkinter"):
            raise GuardError("a janela precisa do tkinter (vem com o Python do python.org)")
        if IS_WINDOWS:  # texto nítido em telas com escala (125%, 150%...)
            with contextlib.suppress(Exception):
                ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
            if getattr(sys, "frozen", False):
                # Aberto por atalho/duplo clique, o .exe ganha um console preto só
                # dele: solta esse console (se houver outro processo nele, é um
                # terminal do usuário e fica como está).
                with contextlib.suppress(Exception):
                    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                    pids = (wintypes.DWORD * 4)()
                    if kernel32.GetConsoleProcessList(pids, 4) == 1:
                        kernel32.FreeConsole()
        refresh = (lambda: spawn_auth_refresh(cfg)) if cfg["desktop"]["refresh_auth_with_cli"] else None
        monitor = UsageMonitor(UsageClient(), cfg["poll_interval_seconds"], on_token_expired=refresh)
        monitor.start()
        try:
            hours = cfg["desktop"]["session_list_hours"]
            GuardWindow(cfg, lambda: (*monitor.latest(), list_instances(), recent_actions(),
                                      list_desktop_sessions(hours))).run()
        finally:
            monitor.stop()
        return 0
    finally:
        with contextlib.suppress(OSError, ValueError):
            if int(GUI_PID_FILE.read_text(encoding="utf-8").strip()) == os.getpid():
                GUI_PID_FILE.unlink()


def cmd_status(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    snap = UsageClient().get(max_age=cfg["poll_interval_seconds"])
    if args.json:
        print(json.dumps(snap.to_json(), indent=2))
        return 0
    for name in _display_windows(snap):
        w = snap.windows[name]
        pct = "n/d" if w.utilization is None else f"{w.utilization:.1f}%"
        print(f"{WINDOW_LABELS.get(name, name):<14} {pct:>7}   reinicia em {_fmt_duration(w.resets_in())}")
    return 0


def cmd_signal(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    target = args.instance or os.environ.get("CUG_INSTANCE_ID")
    ids = [target] if target else [i["instance"] for i in list_instances()]
    if not ids:
        print("nenhuma sessão protegida em execução", file=sys.stderr)
        return 1
    for iid in ids:
        if not request_clear(iid):
            print(f"instância {iid} não encontrada", file=sys.stderr)
            return 1
        print(f"/clear agendado para #{iid} (executa quando a tarefa atual terminar)")
    return 0


def request_clear(instance_id: str) -> bool:
    """Pede /clear para a sessão, a ser feito quando a tarefa atual terminar."""
    d = instance_dir(instance_id)
    if not d.is_dir():
        return False
    (d / "clear.request").touch(mode=0o600)
    return True


def cmd_hook(_cfg: Any, _args: argparse.Namespace) -> int:
    """Chamado pelos hooks do Claude Code. Precisa ser rápido, silencioso
    (stdout de SessionStart iria para o contexto e gastaria tokens!) e nunca
    falhar."""
    with contextlib.suppress(Exception):
        iid = os.environ.get("CUG_INSTANCE_ID", "")
        d = instance_dir(iid)
        if not d.is_dir():
            return 0
        raw = sys.stdin.buffer.read(2_000_000).decode("utf-8", "replace")
        data = json.loads(raw) if raw.strip() else {}
        append_jsonl(d / "hooks.jsonl", {
            "ts": time.time(),
            "event": str(data.get("hook_event_name", ""))[:40],
            "session_id": str(data.get("session_id", ""))[:80] or None,
            "transcript_path": str(data.get("transcript_path", ""))[:1024] or None,
            "source": str(data.get("source", ""))[:20] or None,
            "notification_type": str(data.get("notification_type", ""))[:40] or None,
            "message": str(data.get("message", ""))[:200] or None,
        })
    return 0


DESKTOP_EVENTS = ("SessionStart", "UserPromptSubmit", "Stop")
HOOK_DEADLINE_SECONDS = 4.0     # o Claude Code corta o hook em 5 s
HOOK_FETCH_MAX_SECONDS = 2.5
HOOK_REQUEST_CUTOFF_SECONDS = 2.5  # depois disso o hook não mexe na fila (o prazo de 4 s poderia cortá-lo)
FETCH_BACKOFF_SECONDS = 60
SESSION_ID_RE = re.compile(r"[0-9A-Za-z-]{8,80}")
ALERT_KEEP_SECONDS = 8 * 86400


def desktop_dir() -> Path:
    return STATE_DIR / "desktop"


def desktop_state_path(session_id: str) -> Path:
    """Arquivo de estado da sessão. O id vira nome de arquivo: só aceita o
    formato que o Claude Code usa (sem barras nem pontos)."""
    if not isinstance(session_id, str) or not SESSION_ID_RE.fullmatch(session_id):
        raise GuardError(f"session_id inválido: {str(session_id)[:40]!r}")
    return desktop_dir() / f"{session_id}.json"


# Fila de pedidos dos botões da janela (entregue pelo desktop-hook)


PENDING_MAX_AGE_SECONDS = 4 * 3600  # pedido não entregue em 4 h expira


def pending_dir() -> Path:
    return desktop_dir() / "pending"


def pending_lock_path() -> Path:
    return desktop_dir() / "pending.lock"


def desktop_pending_path(session_id: str) -> Path:
    """Fila de pedidos da sessão (id validado como em desktop_state_path)."""
    desktop_state_path(session_id)
    return pending_dir() / f"{session_id}.json"


def _ordered(actions: Iterable[str]) -> list[str]:
    wanted = set(actions)
    return [a for a in PENDING_ACTIONS if a in wanted]


_WARNED_BAD_QUEUES: set[tuple[str, int]] = set()


def _load_requests(path: Path) -> dict[str, float]:
    """ação → hora do pedido. Arquivo ausente, corrompido ou velho = fila vazia
    (um pedido esquecido não pode chegar a uma sessão retomada dias depois)."""
    try:
        if time.time() - path.stat().st_mtime > PENDING_MAX_AGE_SECONDS:
            return {}
    except OSError:
        return {}
    data = read_json(path)
    reqs = data.get("requests") if isinstance(data, dict) else None
    if not isinstance(reqs, list):
        # A janela relê a fila a cada 5 s: avisa uma vez por versão do arquivo.
        key = (str(path), path.stat().st_mtime_ns if path.exists() else 0)
        if key not in _WARNED_BAD_QUEUES:
            _WARNED_BAD_QUEUES.add(key)
            log.warning("fila de pedidos ilegível, tratada como vazia: %s", path)
        return {}
    out: dict[str, float] = {}
    for r in reqs:
        if isinstance(r, dict) and r.get("action") in PENDING_ACTIONS:
            at = r.get("at")
            out[r["action"]] = float(at) if isinstance(at, (int, float)) else 0.0
    return out


def _save_requests(path: Path, session_id: str, reqs: dict[str, float]) -> None:
    if not reqs:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        return
    atomic_write_json(path, {"session_id": session_id,
                             "requests": [{"action": a, "at": reqs[a]} for a in _ordered(reqs)]})


def read_pending(session_id: str) -> list[str]:
    """Ações pendentes, na ordem de entrega (sem trava: só para mostrar)."""
    return _ordered(_load_requests(desktop_pending_path(session_id)))


def toggle_request(session_id: str, action: str, now: float, expect_pending: Optional[bool] = None,
                   lock_timeout: float = 2.0) -> Optional[bool]:
    """Clique num botão: pede a ação ou, se já pendente, cancela. Devolve se
    ela ficou pendente. Com `expect_pending`, só age se o disco ainda mostra o
    que a janela mostrava; se não mostra (ex.: o hook já entregou o pedido que
    o clique queria cancelar), não muda nada e devolve None."""
    if action not in PENDING_ACTIONS:
        raise ValueError(f"ação desconhecida: {action!r}")
    path = desktop_pending_path(session_id)
    with file_lock(pending_lock_path(), timeout=lock_timeout):
        reqs = _load_requests(path)
        pending = action in reqs
        if expect_pending is not None and pending != expect_pending:
            return None
        if pending:
            del reqs[action]
        else:
            reqs.pop(_ACTION_OPPOSITE.get(action, ""), None)
            reqs[action] = now
        _save_requests(path, session_id, reqs)
        return not pending


CLEAR_INHERIT_SECONDS = 600


def inherit_economy_mode(cwd: str, session_id: str, now: float) -> bool:
    """Depois de /clear (id de sessão novo): o modo econômico estava ligado na
    sessão mais recente da mesma pasta, ativa nos últimos 10 minutos?"""
    best: Optional[DesktopSessionState] = None
    with contextlib.suppress(OSError):
        for f in desktop_dir().glob("*.json"):
            data = read_json(f)
            if not isinstance(data, dict) or data.get("session_id") == session_id or data.get("cwd") != cwd:
                continue
            with contextlib.suppress(TypeError):
                st = DesktopSessionState.from_json(data)
                if (isinstance(st.updated_at, (int, float)) and 0 <= now - st.updated_at <= CLEAR_INHERIT_SECONDS
                        and (best is None or st.updated_at > best.updated_at)):
                    best = st
    return bool(best and best.economy_mode)


def take_requests(session_id: str, lock_timeout: float = 1.0) -> list[str]:
    """Retira da fila todas as ações pendentes (o hook as entrega em seguida)."""
    path = desktop_pending_path(session_id)
    with file_lock(pending_lock_path(), timeout=lock_timeout):
        reqs = _load_requests(path)
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    return _ordered(reqs)


def restore_requests(session_id: str, actions: list[str], now: float, lock_timeout: float = 1.0) -> None:
    """Devolve à fila ações retiradas que não chegaram a ser escritas."""
    path = desktop_pending_path(session_id)
    with file_lock(pending_lock_path(), timeout=lock_timeout):
        reqs = _load_requests(path)
        for a in actions:
            if a in PENDING_ACTIONS and a not in reqs and _ACTION_OPPOSITE.get(a) not in reqs:
                reqs[a] = now
        _save_requests(path, session_id, reqs)


def load_snapshot_for_hook(cfg: dict[str, Any], network: bool = True) -> Optional[UsageSnapshot]:
    """Cota para o hook: cache fresco; senão uma consulta curta (sem retry,
    timeout curto, sem esperar a trava de outro processo); senão o cache velho
    dentro de max_stale_seconds; senão None."""
    wait = min(float(cfg["desktop"]["usage_fetch_timeout_seconds"]), HOOK_FETCH_MAX_SECONDS)
    try:
        client = UsageClient(timeout=wait, retries=1)
        snap = client.cached()
        if snap is not None and snap.age() < cfg["poll_interval_seconds"]:
            return snap
        backoff = desktop_dir() / "fetch_backoff.json"
        held = read_json(backoff)
        if network and not (isinstance(held, dict) and float(held.get("until") or 0) > time.time()):
            # Gravado ANTES de tentar: se a rede travar e o prazo do hook matar
            # o processo, os próximos prompts não pagam a mesma espera.
            atomic_write_json(backoff, {"until": time.time() + FETCH_BACKOFF_SECONDS})
            try:
                snap = client.get(max_age=cfg["poll_interval_seconds"], lock_timeout=wait)
            except TokenExpiredError:
                with contextlib.suppress(OSError):
                    backoff.unlink()  # não é a rede: depois de renovar, pode tentar
                if cfg["desktop"]["refresh_auth_with_cli"]:
                    spawn_auth_refresh(cfg)
            except GuardError as exc:
                log.debug("desktop-hook: sem cota nova: %s", exc)
            else:
                with contextlib.suppress(OSError):
                    backoff.unlink()
                return snap
        snap = client.cached()
    except GuardError as exc:
        log.debug("desktop-hook: sem cota: %s", exc)
        return None
    return snap if snap is not None and snap.age() <= cfg["max_stale_seconds"] else None


AUTH_REFRESH_MIN_SECONDS = 20 * 60
CLAUDE_REFRESH_ARGS = ["-p", "ok", "--model", "haiku", "--tools", "", "--system-prompt", "Responda apenas: ok",
                       "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
                       "--no-session-persistence", "--output-format", "json"]


def _auth_stamp() -> Path:
    return STATE_DIR / "auth_refresh.json"


def _stamp_age(key: str, now: float) -> float:
    d = read_json(_auth_stamp())
    try:
        return now - float(d.get(key) or 0) if isinstance(d, dict) else now
    except (TypeError, ValueError):
        return now


def _update_stamp(**values: float) -> None:
    d = read_json(_auth_stamp())
    atomic_write_json(_auth_stamp(), {**(d if isinstance(d, dict) else {}), **values})


def spawn_auth_refresh(_cfg: dict[str, Any]) -> bool:
    """Lança `refresh-auth` em segundo plano (no máximo a cada 20 min)."""
    now = time.time()
    if min(_stamp_age("requested_at", now), _stamp_age("ran_at", now)) < AUTH_REFRESH_MIN_SECONDS:
        return False
    _update_stamp(requested_at=now)
    kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                              "stderr": subprocess.DEVNULL,
                              "env": {k: v for k, v in os.environ.items() if k != "CUG_INSTANCE_ID"}}
    if not IS_WINDOWS:
        kwargs["start_new_session"] = True
    for flags in ((0x08000000 | 0x00000200 | 0x01000000, 0x08000000 | 0x00000200) if IS_WINDOWS else (0,)):
        if IS_WINDOWS:
            kwargs["creationflags"] = flags
        try:
            subprocess.Popen([*self_command(), "refresh-auth"], **kwargs)
            return True
        except OSError as exc:
            log.debug("refresh-auth: Popen falhou: %s", exc)
    return False


def cmd_refresh_auth(cfg: dict[str, Any], _args: argparse.Namespace) -> int:
    """Renova o token do CLI com uma chamada mínima ao `claude` oficial (o guard
    nunca renova o token por conta própria) e já deixa o cache de uso pronto."""
    now = time.time()
    if _stamp_age("ran_at", now) < AUTH_REFRESH_MIN_SECONDS:
        log.info("refresh-auth: renovado há pouco; nada a fazer")
        return 0
    try:
        load_oauth_token()
        expired = False
    except TokenExpiredError:
        expired = True
    except CredentialsError as exc:
        log.warning("refresh-auth: %s", exc)
        return 1
    if expired:
        try:
            with file_lock(STATE_DIR / "auth_refresh.lock", timeout=1):
                _update_stamp(ran_at=now)
                cmd = claude_launch_prefix(resolve_claude_binary(cfg)) + CLAUDE_REFRESH_ARGS
                env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC", "CUG_"))}
                if os.environ.get("CLAUDE_CONFIG_DIR"):
                    env["CLAUDE_CONFIG_DIR"] = os.environ["CLAUDE_CONFIG_DIR"]
                r = subprocess.run(cmd, env=env, cwd=str(STATE_DIR), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=90,
                                   **({"creationflags": 0x08000000} if IS_WINDOWS else {}))
                log.info("refresh-auth: claude -p terminou com código %s", r.returncode)
        except (GuardError, OSError, subprocess.SubprocessError) as exc:
            log.warning("refresh-auth: não deu para renovar: %s", exc)
            return 1
    try:
        UsageClient().get(max_age=0)
        with contextlib.suppress(OSError):
            (desktop_dir() / "fetch_backoff.json").unlink()
    except GuardError as exc:
        log.warning("refresh-auth: uso ainda indisponível: %s", exc)
    return 0


def filter_new_toasts(toasts: list[ToastRequest], now: float) -> list[ToastRequest]:
    """Só os toasts ainda não mostrados (por qualquer sessão), registrando-os."""
    if not toasts:
        return []
    path = desktop_dir() / "alerts.json"
    with file_lock(desktop_dir() / "alerts.lock", timeout=2):
        seen = read_json(path)
        if not isinstance(seen, dict):
            seen = {}
        seen = {k: v for k, v in seen.items()
                if isinstance(v, (int, float)) and now - v < ALERT_KEEP_SECONDS}
        new = [t for t in toasts if t.key not in seen]
        for t in new:
            seen[t.key] = now
        atomic_write_json(path, seen)
    return new


def cmd_desktop_hook(cfg: dict[str, Any], _args: argparse.Namespace) -> int:
    """Hook das sessões do Claude Desktop (SessionStart, UserPromptSubmit,
    Stop). Só escreve no stdout o JSON da nota; nunca falha."""
    started = time.monotonic()
    raw = sys.stdin.buffer.read(2_000_000).decode("utf-8", "replace")
    if not cfg["desktop"]["enabled"] or not raw.strip():
        return 0
    try:
        data = json.loads(raw)
    except ValueError:
        log.debug("desktop-hook: entrada não é JSON")
        return 0
    if not isinstance(data, dict) or data.get("hook_event_name") not in DESKTOP_EVENTS:
        return 0
    event = data["hook_event_name"]
    path = desktop_state_path(data.get("session_id"))  # GuardError se inválido
    now = time.time()
    stored = read_json(path)
    state = None
    if isinstance(stored, dict):
        with contextlib.suppress(TypeError):
            state = DesktopSessionState.from_json(stored)
    is_new = state is None or state.session_id != data["session_id"]
    if is_new:
        state = DesktopSessionState(data["session_id"])
    state.cwd = str(data.get("cwd") or state.cwd)[:1024]
    state.transcript_path = str(data.get("transcript_path") or state.transcript_path)[:1024]
    state.updated_at = now
    state.last_event = event
    source = data.get("source") if isinstance(data.get("source"), str) else None
    if is_new and event == "SessionStart" and source == "clear":
        # O /clear abre uma sessão com id novo: o modo econômico vem da anterior.
        state.economy_mode = inherit_economy_mode(state.cwd, state.session_id, now)
    if event == "Stop" and state.transcript_path:
        tokens = read_context_tokens(state.transcript_path)
        if tokens is not None:
            state.context_tokens, state.context_measured_at = tokens, now
    snap = load_snapshot_for_hook(cfg, network=event != "Stop")
    notes, toasts, state = advise(cfg, snap, state, event, source, now)
    # Pedidos dos botões: retirados da fila só agora, logo antes de escrever.
    # Retirar (e não ler e apagar depois) evita entregar duas vezes quando dois
    # hooks do guard rodam em paralelo; perto do prazo, nem mexe na fila.
    actions: list[str] = []
    wants = event == "UserPromptSubmit" or (event == "Stop" and data.get("stop_hook_active") is not True)
    elapsed = time.monotonic() - started
    if wants and elapsed < HOOK_REQUEST_CUTOFF_SECONDS:
        try:  # espera da trava limitada para caber no prazo do hook
            actions = take_requests(state.session_id, lock_timeout=min(1.0, max(0.05, 3.0 - elapsed)))
        except (GuardError, OSError) as exc:
            log.warning("desktop-hook: fila de pedidos indisponível: %s", exc)
    out: Optional[dict[str, Any]] = None
    if event == "Stop" and actions:
        out = {"decision": "block", "reason": request_notes(actions, event)}
    elif event != "Stop" and (notes or actions):
        lines = notes + ([request_notes(actions, event)] if actions else [])
        out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": "\n".join(lines)}}
    if out is not None:
        log.info("desktop-hook: %s %s: notas %s | pedidos %s", event, state.session_id[:8],
                 " | ".join(notes) or "-", ", ".join(actions) or "-")
        try:
            # ASCII puro: o JSON chega igual qualquer que seja a codificação do pipe.
            sys.stdout.buffer.write(json.dumps(out).encode("ascii"))
            sys.stdout.flush()
        except Exception:
            if actions:  # não chegaram ao Claude: voltam para a fila
                with contextlib.suppress(Exception):
                    restore_requests(state.session_id, actions, now)
            raise
    # Estado só depois da saída: falhar aqui (antivírus, disco) não perde pedido
    # já retirado, e um pedido devolvido à fila não fica marcado como entregue.
    # Sem trava no estado: se outro hook entregou algo enquanto este rodava,
    # o que ele gravou (economy_mode, delivered_*) não pode ser desfeito aqui.
    disk = read_json(path)
    if isinstance(disk, dict):
        with contextlib.suppress(TypeError, ValueError):
            state = merge_concurrent_delivery(state, DesktopSessionState.from_json(disk))
    if actions:
        state = apply_delivery(state, actions, event, now)
    try:
        atomic_write_json(path, state.to_json())
    except OSError as exc:
        log.warning("desktop-hook: estado da sessão não gravado: %s", exc)
    # Registra os alertas mesmo com o toast desligado: religá-lo não repete
    # avisos de uma janela que já passou por eles. Falhar aqui não perde a nota.
    show = cfg["desktop"]["toast"] and cfg["notifications"]["desktop"]
    try:
        for t in filter_new_toasts(toasts, now):
            if show:
                notify_toast(t.title, t.message)
    except (OSError, GuardError) as exc:
        log.warning("desktop-hook: toasts não registrados: %s", exc)
    return 0


def run_desktop_hook(args: argparse.Namespace) -> int:
    """Caminho rápido do desktop-hook: log só em arquivo, sem reparo de ACL,
    e qualquer erro vira código 0 sem saída (o Claude Code segue normal)."""
    def deadline() -> None:  # rede lenta, disco travado...: sai calado antes do corte
        with contextlib.suppress(Exception):
            log.warning("desktop-hook: prazo de %.0f s estourado; saindo sem nota", HOOK_DEADLINE_SECONDS)
        os._exit(0)

    timer = threading.Timer(HOOK_DEADLINE_SECONDS, deadline)
    timer.daemon = True
    timer.start()
    with contextlib.suppress(Exception):
        setup_logging(to_stderr=False, verbose=args.verbose)
    try:
        cfg, _ = load_config(args.config)
        return cmd_desktop_hook(cfg, args)
    except Exception:  # o hook nunca pode falhar
        with contextlib.suppress(Exception):
            log.exception("desktop-hook falhou")
        return 0


# --------------------------------------------------------------------------
# Instalação para o Claude Desktop (hooks no settings.json, skill e atalho)
# --------------------------------------------------------------------------

SKILL_NAMES = ("economia-de-cota", "ferramentas-do-projeto", "pesquisar-otimizacoes")


# SHA-256 das versões empacotadas anteriores: uma cópia idêntica a uma delas não
# foi editada pelo usuário e é atualizada (ou removida) sem pedir --force.
# Ao mudar uma skill, acrescente aqui o hash da versão que saiu.
SKILL_PREVIOUS_SHA256: dict[str, set[str]] = {
    "economia-de-cota": {"1a1a597eda9fd25216cd3f8ad057a6d4cfd98c96bd6d8a6555d13b3bfc78e817",   # 1.3.0
                         "b99cf6cfe2ca9fe8f1aa97377fff494f20e7b0547154ce443b7c8258f6bdac4d"},  # 1.4.0 provisória
}


def skill_asset(name: str) -> str:
    return f"skills/{name}/SKILL.md"


def _skill_is_ours(name: str, dst: Path, src: Optional[Path]) -> bool:
    """A cópia instalada é a empacotada (atual ou anterior), sem edição do usuário?"""
    data = dst.read_bytes()
    if src is not None and data == src.read_bytes():
        return True
    return hashlib.sha256(data).hexdigest() in SKILL_PREVIOUS_SHA256.get(name, set())


def install_skill(name: str, force: bool) -> None:
    """Copia a skill empacotada; mantém a do usuário se ele a editou (com
    --force, substitui guardando backup)."""
    src = asset_path(skill_asset(name))
    dst = claude_config_dir() / "skills" / name / "SKILL.md"
    if src is None:
        print(f"skill {name}: ERRO arquivo empacotado não encontrado (assets/skills)")
    elif dst.is_file() and not _skill_is_ours(name, dst, src) and not force:
        print(f"skill {name}: {dst} foi modificada; mantive a sua (use --force para substituir, com backup)")
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_file() and not _skill_is_ours(name, dst, src):
            bak = dst.with_name(f"SKILL.md.bak-{_stamp()}")
            shutil.copy2(dst, bak)
            print(f"skill {name}: backup da sua versão em {bak}")
        shutil.copyfile(src, dst)
        print(f"skill {name}: {dst}")


def uninstall_skill(name: str) -> None:
    """Remove a skill só se ela for idêntica à empacotada."""
    src = asset_path(skill_asset(name))
    dst = claude_config_dir() / "skills" / name / "SKILL.md"
    if not dst.is_file():
        return
    if _skill_is_ours(name, dst, src):
        dst.unlink()
        with contextlib.suppress(OSError):
            dst.parent.rmdir()  # só se ficou vazia
        print(f"skill {name}: removida ({dst})")
    else:
        print(f"skill {name}: {dst} foi modificada; não removi")


def _replace_with_retry(tmp: Path, path: Path) -> None:
    # No Windows, os.replace falha se outro processo estiver lendo o arquivo.
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if not IS_WINDOWS or attempt == 19:
                with contextlib.suppress(OSError):
                    tmp.unlink()
                raise
            time.sleep(0.05)


def read_settings_json(path: Path) -> tuple[dict[str, Any], str]:
    """(dados, texto original). Aceita BOM UTF-8 (Bloco de Notas) e CRLF.
    Levanta OSError (inclusive FileNotFoundError) ou ValueError."""
    text = path.read_bytes().decode("utf-8")
    body = text.lstrip("﻿")
    data = json.loads(body) if body.strip() else {}
    if not isinstance(data, dict):
        raise ValueError("o topo do arquivo não é um objeto JSON")
    return data, text


def write_settings_json(path: Path, data: dict[str, Any], original_text: str) -> None:
    """Grava de forma atômica com indentação 2, mantendo BOM, CRLF e a quebra
    de linha final do original (arquivo novo: LF e quebra final)."""
    nl = "\r\n" if "\r\n" in original_text else "\n"
    body = json.dumps(data, indent=2, ensure_ascii=False)
    if nl != "\n":
        body = body.replace("\n", nl)  # json.dumps escapa quebras dentro de strings
    final = nl if (not original_text.strip("﻿") or original_text.endswith("\n")) else ""
    bom = "﻿" if original_text.startswith("﻿") else ""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.cug.tmp")
    tmp.write_bytes((bom + body + final).encode("utf-8"))
    _replace_with_retry(tmp, path)


def is_guard_desktop_hook(hook: Any) -> bool:
    cmd = hook.get("command") if isinstance(hook, dict) else None
    return isinstance(cmd, str) and "desktop-hook" in cmd and "claude_usage_guard" in cmd


def _without_guard_hooks(settings: dict[str, Any]) -> dict[str, Any]:
    """Cópia sem as entradas do guard; remove só o que ele esvaziou."""
    out = json.loads(json.dumps(settings))
    hooks = out.get("hooks")
    if not isinstance(hooks, dict):
        return out
    for event in DESKTOP_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        kept, removed = [], False
        for g in groups:
            inner = g.get("hooks") if isinstance(g, dict) else None
            if isinstance(inner, list) and any(is_guard_desktop_hook(h) for h in inner):
                removed = True
                inner = [h for h in inner if not is_guard_desktop_hook(h)]
                if not inner:
                    continue
                g = {**g, "hooks": inner}
            kept.append(g)
        if removed and not kept:
            del hooks[event]
        elif removed:
            hooks[event] = kept
    if not hooks and settings.get("hooks"):
        del out["hooks"]
    return out


def merge_desktop_hooks(settings: dict[str, Any], command: str) -> dict[str, Any]:
    """Cópia com os hooks do guard (substituindo os anteriores) no fim de cada
    evento; os hooks do usuário ficam intactos e na mesma ordem."""
    out = _without_guard_hooks(settings)
    hooks = out.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise GuardError('"hooks" do settings.json não é um objeto')
    for event in DESKTOP_EVENTS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise GuardError(f'"hooks.{event}" do settings.json não é uma lista')
        groups.append({"hooks": [{"type": "command", "command": command, "timeout": 5}]})
    return out


def strip_desktop_hooks(settings: dict[str, Any]) -> dict[str, Any]:
    return _without_guard_hooks(settings)


def _guard_hook_commands(settings: dict[str, Any]) -> list[str]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return []
    return [h["command"] for ev in DESKTOP_EVENTS for g in (hooks.get(ev) or [])
            if isinstance(g, dict) for h in (g.get("hooks") or []) if is_guard_desktop_hook(h)]


def desktop_hooks_status() -> tuple[bool, bool]:
    """(hooks do Desktop instalados?, o programa que eles chamam existe?)"""
    try:
        data, _ = read_settings_json(user_settings_path())
    except (OSError, ValueError):
        return False, False
    cmds = _guard_hook_commands(data)
    if not cmds:
        return False, False
    for cmd in cmds:
        try:
            parts = shlex.split(cmd)
        except ValueError:
            return True, False
        targets = [p for p in parts if "claude_usage_guard" in p]
        if not targets or not all(Path(p).is_file() for p in targets):
            return True, False
    return True, True


def start_menu_shortcut_path() -> Path:
    base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Claude Usage Guard.lnk"


def create_start_menu_shortcut() -> Optional[Path]:
    """Atalho no Menu Iniciar que abre a janela do guard (best effort)."""
    if not IS_WINDOWS:
        return None
    lnk = start_menu_shortcut_path()
    parts = self_command()
    target = shutil.which(parts[0]) or parts[0]
    script = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:CUG_LNK);"
              "$s.TargetPath=$env:CUG_LNK_TARGET;$s.Arguments=$env:CUG_LNK_ARGS;"
              "$s.WorkingDirectory=$env:CUG_LNK_DIR;$s.IconLocation=$env:CUG_LNK_ICON;"
              "$s.Description='Claude Usage Guard';$s.Save()")
    env = dict(os.environ, CUG_LNK=str(lnk), CUG_LNK_TARGET=target,
               CUG_LNK_ARGS=subprocess.list2cmdline(parts[1:] + ["gui"]),
               CUG_LNK_DIR=str(app_dir()), CUG_LNK_ICON=str(asset_path("app.ico") or target))
    try:
        lnk.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                           capture_output=True, text=True, timeout=30, creationflags=0x08000000)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("atalho do Menu Iniciar não criado: %s", exc)
        return None
    if r.returncode != 0 or not lnk.exists():
        log.warning("atalho do Menu Iniciar não criado: %s", (r.stderr or "").strip()[:300])
        return None
    return lnk


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def cmd_install_desktop(_cfg: dict[str, Any], args: argparse.Namespace) -> int:
    """Instala os hooks do Desktop no settings.json do usuário, a skill e o atalho."""
    path = user_settings_path()
    try:
        data, original = read_settings_json(path)
        exists = True
    except FileNotFoundError:
        data, original, exists = {}, "", False
    except (OSError, ValueError) as exc:
        print(f"guard: erro: não consegui ler {path} ({exc}). Nada foi alterado; corrija o arquivo e "
              "rode de novo.", file=sys.stderr)
        return 1
    command = hook_command(sub="desktop-hook")
    new = merge_desktop_hooks(data, command)
    backup = None
    if exists:
        backup = path.with_name(f"{path.name}.bak-{_stamp()}")
        shutil.copy2(path, backup)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    write_settings_json(path, new, original)
    print(f"settings.json: {path}")
    print(f"  hooks SessionStart, UserPromptSubmit e Stop → {command}")
    print(f"  backup: {backup}" if backup else "  (arquivo novo)")

    for name in SKILL_NAMES:
        install_skill(name, args.force)

    lnk = create_start_menu_shortcut()
    if lnk:
        print(f"atalho: {lnk}")
    print("Pronto. Os hooks valem para cada sessão nova do Claude Desktop (aba Code); "
          "as que já estão abertas não mudam.")
    return 0


def cmd_uninstall_desktop(_cfg: dict[str, Any], _args: argparse.Namespace) -> int:
    """Remove só o que o install-desktop pôs. Backups ficam."""
    path = user_settings_path()
    try:
        data, original = read_settings_json(path)
    except FileNotFoundError:
        data, original = None, ""
    except (OSError, ValueError) as exc:
        print(f"guard: erro: não consegui ler {path} ({exc}). Nada foi alterado.", file=sys.stderr)
        return 1
    if data is not None and _guard_hook_commands(data):
        backup = path.with_name(f"{path.name}.bak-{_stamp()}")
        shutil.copy2(path, backup)
        write_settings_json(path, strip_desktop_hooks(data), original)
        print(f"settings.json: hooks do guard removidos de {path} (backup: {backup})")
    else:
        print(f"settings.json: nenhum hook do guard em {path}")

    for name in SKILL_NAMES:
        uninstall_skill(name)
    lnk = start_menu_shortcut_path()
    if lnk.exists():
        with contextlib.suppress(OSError):
            lnk.unlink()
            print(f"atalho: removido ({lnk})")
    return 0


def cmd_check_config(cfg: dict[str, Any], args: argparse.Namespace, path: Optional[Path]) -> int:
    print(f"config: {path or '(padrões embutidos)'}")
    print(json.dumps(redacted_config(cfg), indent=2, ensure_ascii=False))
    ok = True
    try:
        binary = resolve_claude_binary(cfg)
        print(f"claude: {binary}")
        print(f"comando de execução: {claude_launch_prefix(binary)}")
    except ConfigError as exc:
        print(f"claude: ERRO {exc}")
        ok = False
    print(f"comando dos hooks: {hook_command()}")
    if IS_WINDOWS:
        import importlib.util
        if importlib.util.find_spec("winpty"):
            print("pywinpty: instalado")
        else:
            print("pywinpty: AUSENTE (necessário para `run`: py -m pip install pywinpty)")
            ok = False
    try:
        load_oauth_token()
        print("credenciais OAuth: encontradas")
    except CredentialsError as exc:
        print(f"credenciais OAuth: ERRO {exc}")
        ok = False
    installed, exe_ok = desktop_hooks_status()
    if not installed:
        print("hooks do Claude Desktop: não instalados (opcional: install-desktop)")
    elif exe_ok:
        print("hooks do Claude Desktop: instalados")
    else:
        print("hooks do Claude Desktop: instalados, mas o programa registrado não existe mais "
              "(mudou de pasta?). Rode install-desktop de novo a partir do lugar novo.")
        ok = False
    if cfg["failover"]["enabled"]:
        up = ProxyManager(cfg).is_up()
        print(f"proxy {cfg['failover']['base_url']}: {'respondendo' if up else 'parado (será iniciado se houver command)'}")
    return 0 if ok else 1


def cmd_demo(cfg: dict[str, Any], _args: argparse.Namespace) -> int:
    """Simulação offline: mostra que decisões a política toma conforme o uso
    sobe, e um quadro do dashboard. Não usa rede nem abre o Claude Code."""
    cfg = json.loads(json.dumps(cfg))
    cfg["failover"]["enabled"] = True
    now = time.time()
    resets = dt.datetime.fromtimestamp(now + 2 * 3600, dt.timezone.utc).isoformat()
    state = GuardState(last_activity_at=now, turns_since_clear=3)  # sessão com conversa
    print("Simulação da política (failover ligado só nesta demo):\n")
    for s5, s7 in [(20, 10), (45, 12), (62, 14), (66, 15), (72, 18), (85, 20), (91, 22), (15, 23)]:
        snap = UsageSnapshot.from_api({"five_hour": {"utilization": s5, "resets_at": resets},
                                       "seven_day": {"utilization": s7, "resets_at": resets}}, now)
        if s5 == 15:  # janela reiniciou
            snap.windows["five_hour"].resets_at = dt.datetime.fromtimestamp(now + 7 * 3600, dt.timezone.utc)
        acts = decide(cfg, snap, state, now)
        print(f"  5h={s5:>3}% 7d={s7:>3}%  →  {', '.join(a for a, _ in acts) or 'nada'}")
        # aplica os efeitos de estado que o controlador aplicaria
        for act, _ in acts:
            if act == ACT_COMPACT:
                state.compacted_window, state.last_compact_at = _window_key(snap), now - cfg["compact"]["cooldown_seconds"]
            elif act == ACT_SWITCH:
                state.model_switched = True
            elif act == ACT_RESTORE:
                state.model_switched = False
            elif act == ACT_FAILOVER:
                state.failover_notified = True
    state.clear_requested = True
    print(f"\n  após `signal clear`  →  {', '.join(a for a, _ in decide(cfg, None, state, now))}\n")
    snap = UsageSnapshot.from_api({"five_hour": {"utilization": 72.5, "resets_at": resets},
                                   "seven_day": {"utilization": 31.0, "resets_at": resets}}, now - 40)
    fake_inst = [{"instance": "a1b2c3d4e5f6", "state": "ocioso", "model_override": "haiku",
                  "failover_active": False, "context_tokens": 84_300, "hooks_ok": True, "cwd": os.getcwd()}]
    fake_actions = [{"ts": now - 600, "instance": "a1b2c3d4e5f6", "action": ACT_COMPACT, "reason": "sessão em 61%"},
                    {"ts": now - 120, "instance": "a1b2c3d4e5f6", "action": ACT_SWITCH, "reason": "uso 5h 72% → haiku"}]
    print(render_dashboard(cfg, snap, None, fake_inst, fake_actions, now, color=_use_color()))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claude_usage_guard.py",
                                description="Guarda de consumo de cota para o Claude Code.")
    p.add_argument("--config", help="caminho do config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="abre o Claude Code sob proteção")
    r.add_argument("claude_args", nargs=argparse.REMAINDER, help="argumentos para o claude (após --)")
    d = sub.add_parser("dashboard", help="painel em tempo real")
    d.add_argument("--once", action="store_true", help="desenha um quadro e sai")
    sub.add_parser("gui", help="janela com uso, sessões e ações (abre sozinha com o run)")
    s = sub.add_parser("status", help="mostra o uso atual")
    s.add_argument("--json", action="store_true")
    g = sub.add_parser("signal", help="sinaliza eventos para sessões protegidas")
    g.add_argument("what", choices=["clear"])
    g.add_argument("--instance", help="id da instância (padrão: atual ou todas)")
    sub.add_parser("hook", help=argparse.SUPPRESS)
    sub.add_parser("desktop-hook", help=argparse.SUPPRESS)
    sub.add_parser("refresh-auth", help=argparse.SUPPRESS)
    i = sub.add_parser("install-desktop", help="instala hooks, skill e atalho para o Claude Desktop (aba Code)")
    i.add_argument("--force", action="store_true", help="substitui a skill mesmo se você a modificou (com backup)")
    sub.add_parser("uninstall-desktop", help="remove o que o install-desktop instalou")
    sub.add_parser("check-config", help="valida config, binário e credenciais")
    sub.add_parser("demo", help="simulação offline da política e do dashboard")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "hook":  # caminho rápido: sem config nem logging
        return cmd_hook(None, args)
    if args.command == "desktop-hook":  # idem, para as sessões do Claude Desktop
        return run_desktop_hook(args)
    if IS_WINDOWS:
        # Console do Windows: cores/ANSI ligados e nada de erro de encoding.
        # Redirecionado (pipe/arquivo), o Python usaria cp1252 e "→", "█" e
        # acentos virariam "?"; UTF-8 é o que PowerShell 7 e editores esperam.
        for stream in (sys.stdout, sys.stderr):
            with contextlib.suppress(Exception):
                if stream.isatty():
                    stream.reconfigure(errors="replace")  # type: ignore[union-attr]
                else:
                    stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        with contextlib.suppress(Exception):
            WinConsole().enable_vt_output()
    repair_windows_state_acl()
    setup_logging(to_stderr=args.command != "run", verbose=args.verbose)
    try:
        cfg, path = load_config(args.config)
        handlers = {"run": cmd_run, "dashboard": cmd_dashboard, "gui": cmd_gui, "status": cmd_status,
                    "signal": cmd_signal, "demo": cmd_demo, "install-desktop": cmd_install_desktop,
                    "uninstall-desktop": cmd_uninstall_desktop, "refresh-auth": cmd_refresh_auth}
        if args.command == "check-config":
            return cmd_check_config(cfg, args, path)
        return handlers[args.command](cfg, args)
    except GuardError as exc:
        print(f"guard: erro: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"guard: erro: sem permissão para abrir {exc.filename or exc}", file=sys.stderr)
        if IS_WINDOWS:
            print(f'  corrija uma vez num terminal como administrador:  icacls "{STATE_DIR}" /reset /T /C /Q',
                  file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    # Exemplos:
    #   python3 claude_usage_guard.py demo            # veja a política sem rede
    #   python3 claude_usage_guard.py check-config    # valide o ambiente
    #   python3 claude_usage_guard.py run             # use no dia a dia
    #   python3 claude_usage_guard.py dashboard       # em outro painel do tmux
    sys.exit(main())
