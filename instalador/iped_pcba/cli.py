"""Linha de comando do instalador.

  python -m iped_pcba diagnosticar --iped "C:\\IPED\\iped-4.3.1"
  python -m iped_pcba aplicar      --iped "C:\\IPED\\iped-4.3.1" --temp D:\\IPEDTemp [--simular]
  python -m iped_pcba reverter     --iped "C:\\IPED\\iped-4.3.1" [--backup 20261013-120000]
"""

import argparse
import json
import os
import sys

from . import __version__
from .configurar import (Backup, aplicar_plano, gerar_lancadores, gravar_maquina,
                         listar_backups, reverter)
from .detectar import detectar, tipo_disco_do_caminho
from .localizar import localizar_iped
from .mcp import instalar_mcp
from .perfis import PERFIS, criar_perfis
from .recomendar import escolher_temp, recomendar

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _args(argv):
    ap = argparse.ArgumentParser(prog="iped_pcba",
                                 description="Instalador IPED-PCBA {}".format(__version__))
    sub = ap.add_subparsers(dest="comando")

    def comum(p):
        p.add_argument("--iped", help="pasta raiz do IPED; se omitida, é procurada na máquina")

    d = sub.add_parser("diagnosticar", help="mostra a máquina e o plano, sem alterar nada")
    comum(d)
    a = sub.add_parser("aplicar", help="aplica o plano com backup")
    comum(a)
    for p in (d, a):
        p.add_argument("--papel", choices=["cliente", "servidor"], default="cliente",
                       help="cliente = estação do analista; servidor = Linux central")
        p.add_argument("--temp", help="pasta temporária do IPED (de preferência em SSD/NVMe)")
        p.add_argument("--saida-ssd", action="store_true", help="os casos serão gravados em SSD")
        p.add_argument("--servidor-transcricao", metavar="HOST:PORTA",
                       help="nó de descoberta da transcrição no servidor central")
        p.add_argument("--json", action="store_true", help="saída em JSON")
    a.add_argument("--simular", action="store_true", help="mostra o que mudaria, sem gravar")
    a.add_argument("--sem-perfis", action="store_true", help="não gera os perfis pcba-*")
    a.add_argument("--sem-mcp", action="store_true", help="não instala o MCP (IA)")

    sub.add_parser("localizar", help="lista as instalações do IPED encontradas")
    r = sub.add_parser("reverter", help="restaura um backup")
    comum(r)
    r.add_argument("--backup", help="nome do backup (padrão: o mais recente)")
    r.add_argument("--listar", action="store_true", help="só lista os backups")
    return ap.parse_args(argv)


def _plano(args):
    maquina = detectar(args.iped)
    if args.temp:
        temp, tipo = args.temp, tipo_disco_do_caminho(args.temp, maquina)
        args.temp_motivo = "informada pelo usuário"
    else:
        temp, tipo, args.temp_motivo = escolher_temp(maquina)
    args.temp = temp
    plano = recomendar(maquina, papel=args.papel, pasta_temp=temp, tipo_disco_temp=tipo,
                       servidor_transcricao=args.servidor_transcricao,
                       saida_em_ssd=args.saida_ssd, motivo_temp=args.temp_motivo)
    return maquina, plano


def _resumo(maquina, plano):
    cpu = maquina.get("cpu", {})
    linhas = [
        "Máquina   : {} ({})".format(maquina.get("hostname"), maquina.get("so_versao")),
        "CPU       : {} | {} núcleos, {} threads".format(cpu.get("nome"), cpu.get("fisicos"),
                                                         cpu.get("logicos")),
        "RAM       : {} GB  -> heap do IPED: {} GB".format(maquina.get("ram_gb"), plano.heap_gb),
    ]
    for d in maquina.get("discos", []):
        linhas.append("Disco     : {} | {} | {} GB".format(d.get("nome"), d.get("tipo"),
                                                         d.get("tamanho_gb")))
    gpus = maquina.get("gpus") or []
    if gpus:
        for g in gpus:
            linhas.append("GPU       : {} | {} GB VRAM | driver {} | CUDA {}".format(
                g["nome"], g["vram_gb"], g["driver"], g["cuda"] or "?"))
    else:
        linhas.append("GPU       : nenhuma NVIDIA detectada")
    iped = maquina.get("iped", {})
    linhas.append("IPED      : {} | versão {} | perfis: {}".format(
        iped.get("raiz"), iped.get("versao") or "?", ", ".join(iped.get("perfis") or []) or "-"))
    linhas.append("Temp      : {}".format(plano.valor("LocalConfig.txt", "indexTemp") or "padrão do sistema"))
    linhas.append("Transcrição: {}".format(plano.transcricao))
    linhas.append("")
    linhas.append("Alterações propostas:")
    for a in plano.alteracoes:
        linhas.append("  {} : {} = {}   ({})".format(a.arquivo, a.chave, a.valor, a.motivo))
    if plano.avisos:
        linhas.append("")
        linhas.append("Avisos:")
        for av in plano.avisos:
            linhas.append("  - " + av)
    return "\n".join(linhas)


def main(argv=None):
    try:
        return _main(argv)
    except PermissionError as e:
        print("ERRO: sem permissão para gravar em {}. Feche o IPED e rode o instalador como "
              "administrador (ou instale o IPED fora de Program Files).".format(e.filename),
              file=sys.stderr)
        return 3


def _main(argv=None):
    args = _args(argv if argv is not None else sys.argv[1:])
    if not args.comando:
        _args(["-h"])
        return 2
    if args.comando == "localizar":
        for i in localizar_iped():
            print("{}\t{}".format(i["versao"] or "?", i["raiz"]))
        return 0

    if not args.iped:
        achados = localizar_iped()
        if not achados:
            print("ERRO: nenhuma instalação do IPED encontrada. Informe a pasta com --iped.",
                  file=sys.stderr)
            return 1
        args.iped = achados[0]["raiz"]
        print("IPED encontrado: {} (versão {})".format(args.iped, achados[0]["versao"] or "?"),
              file=sys.stderr)
        for outro in achados[1:]:
            print("  outra instalação ignorada: {} ({})".format(outro["raiz"], outro["versao"] or "?"),
                  file=sys.stderr)
    raiz = os.path.abspath(args.iped)

    if args.comando == "reverter":
        if args.listar:
            for n in listar_backups(raiz):
                print(n)
            return 0
        nome, arquivos = reverter(raiz, args.backup)
        print("Backup {} restaurado ({} itens).".format(nome, len(arquivos)))
        for f in arquivos:
            print("  " + f)
        return 0

    maquina, plano = _plano(args)
    if args.comando == "diagnosticar":
        if args.json:
            print(json.dumps({"maquina": maquina, "plano": plano.como_dict()},
                             indent=2, ensure_ascii=False))
        else:
            print(_resumo(maquina, plano))
        return 0

    if not maquina["iped"].get("encontrado"):
        print("ERRO: {} não parece ser uma instalação do IPED (falta IPEDConfig.txt).".format(raiz),
              file=sys.stderr)
        return 1

    if args.temp and not args.simular and not os.path.isdir(args.temp):
        os.makedirs(args.temp)
    backup = Backup(raiz)
    mudancas = aplicar_plano(raiz, plano, backup, simular=args.simular)
    perfis = {} if args.sem_perfis else criar_perfis(raiz, backup, simular=args.simular)
    lancadores = []
    mcp = None if args.sem_mcp else instalar_mcp(raiz, maquina["so"], REPO, backup,
                                                 simular=args.simular)
    if not args.simular:
        lancadores = gerar_lancadores(raiz, plano, sorted(PERFIS), maquina["so"], backup,
                                      papel=args.papel)
        gravar_maquina(raiz, maquina, plano, mudancas, backup)
    pasta_backup = None if args.simular else backup.fechar({"versao_instalador": __version__})

    if args.json:
        print(json.dumps({"mudancas": mudancas, "perfis": sorted(perfis), "lancadores": lancadores,
                          "mcp": mcp, "backup": pasta_backup, "avisos": plano.avisos},
                         indent=2, ensure_ascii=False))
        return 0
    print(_resumo(maquina, plano))
    print("")
    print("SIMULAÇÃO: nada foi gravado." if args.simular else "Aplicado.")
    for m in mudancas:
        if "erro" in m:
            print("  ! {}: {}".format(m["arquivo"], m["erro"]))
        else:
            print("  {} : {} {} -> {}".format(m["arquivo"], m["chave"], m["de"], m["para"]))
    for p in sorted(perfis):
        print("  perfil {} ({} chaves)".format(p, len(perfis[p])))
    for l in lancadores:
        print("  lançador " + l)
    if mcp:
        if mcp.get("aviso"):
            print("  ! " + mcp["aviso"])
        else:
            print("  MCP (IA): {} (Java {})".format(mcp["lancador"], mcp["java"]))
            print("    Para usar no Claude Desktop ou LM Studio, acrescente ao arquivo de configuração:")
            print("    " + json.dumps(mcp["config_clientes"], ensure_ascii=False))
    if pasta_backup:
        print("Backup em {}. Para desfazer: python -m iped_pcba reverter --iped \"{}\"".format(
            pasta_backup, raiz))
    return 0
