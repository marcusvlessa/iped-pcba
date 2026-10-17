"""Cliente MCP mínimo (STDIO, JSON-RPC por linha) para o painel testar o MCP instalado.

Só biblioteca padrão, para rodar no Python que vem com o IPED.
"""

import json
import os
import queue
import subprocess
import threading
import time

MAX_LIXO = 200  # linhas que não são JSON-RPC toleradas no STDOUT por chamada


class ErroMcp(Exception):
    pass


class ClienteMcp(object):
    def __init__(self, comando, timeout=120, env=None):
        self.timeout = timeout
        self._id = 0
        self._fila = queue.Queue()
        self.stderr = []
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        self.proc = subprocess.Popen(comando, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=env, creationflags=flags)
        threading.Thread(target=self._ler_saida, daemon=True).start()
        threading.Thread(target=self._ler_erro, daemon=True).start()

    def _ler_saida(self):
        for linha in self.proc.stdout:
            self._fila.put(linha.decode("utf-8", "replace"))
        self._fila.put(None)

    def _ler_erro(self):
        for linha in self.proc.stderr:
            self.stderr.append(linha.decode("utf-8", "replace").rstrip())
            del self.stderr[:-200]

    def _enviar(self, obj):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def chamar(self, metodo, params=None):
        self._id += 1
        meu = self._id
        self._enviar({"jsonrpc": "2.0", "id": meu, "method": metodo, "params": params or {}})
        limite = time.time() + self.timeout
        lixo = 0
        while True:
            resto = limite - time.time()
            if resto <= 0:
                raise ErroMcp("o MCP não respondeu a '{}' em {} s".format(metodo, self.timeout))
            try:
                linha = self._fila.get(timeout=resto)
            except queue.Empty:
                continue
            if linha is None:
                raise ErroMcp("o MCP encerrou. Últimas mensagens:\n" + "\n".join(self.stderr[-15:]))
            linha = linha.strip()
            if not linha:
                continue
            try:
                msg = json.loads(linha) if linha.startswith("{") else None
            except ValueError:
                msg = None
            if not isinstance(msg, dict):
                # aviso da JVM ou de biblioteca nativa no STDOUT: guarda no log e segue lendo
                self.stderr.append("[stdout] " + linha[:300])
                lixo += 1
                if lixo > MAX_LIXO:
                    raise ErroMcp("o MCP escreveu {} linhas que não são JSON-RPC no STDOUT. Última: {}".format(
                        lixo, linha[:300]))
                continue
            if msg.get("id") != meu:
                continue
            if "error" in msg:
                raise ErroMcp(json.dumps(msg["error"], ensure_ascii=False))
            return msg.get("result")

    def iniciar(self):
        r = self.chamar("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                       "clientInfo": {"name": "painel-pcba", "version": "1"}})
        self._enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return r

    def ferramentas(self):
        return [t["name"] for t in self.ferramentas_completas()]

    def ferramentas_completas(self):
        """Nome, descrição e inputSchema de cada ferramenta (para entregar ao modelo de IA)."""
        return (self.chamar("tools/list") or {}).get("tools", [])

    def ferramenta(self, nome, argumentos=None):
        r = self.chamar("tools/call", {"name": nome, "arguments": argumentos or {}}) or {}
        textos = [c.get("text", "") for c in r.get("content", []) if c.get("type") == "text"]
        return {"erro": bool(r.get("isError")), "texto": "\n".join(textos)}

    def fechar(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        for f in (self.proc.stdout, self.proc.stderr):
            try:
                f.close()
            except Exception:
                pass
