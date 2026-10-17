"""Linha de comando do instalador.

  python -m iped_pcba diagnosticar --iped "C:\\IPED\\iped-4.3.1"
  python -m iped_pcba aplicar      --iped "C:\\IPED\\iped-4.3.1" --temp D:\\IPEDTemp [--simular]
  python -m iped_pcba reverter     --iped "C:\\IPED\\iped-4.3.1" [--backup 20261013-120000]
  python -m iped_pcba painel       --iped "C:\\IPED\\iped-4.3.1"   (abre o painel no navegador)
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
from .painel import instalar_painel
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
    a.add_argument("--somente-leitura", action="store_true",
                   help="MCP sem as ferramentas de escrita (marcadores); o padrão é liberar")

    pn = sub.add_parser("painel", help="abre o painel no navegador")
    comum(pn)
    pn.add_argument("--porta", type=int, default=0, help="porta local (padrão: livre)")
    pn.add_argument("--sem-navegador", action="store_true", help="não abre o navegador")

    rl = sub.add_parser("relatorio", help="relatório técnico (RT) do caso em .docx")
    rl.add_argument("acao", choices=["gerar", "lacunas", "telematica"],
                    help="gerar = .docx; lacunas = o que falta preencher; "
                         "telematica = resume um CSV de registros padronizados no RT do caso")
    rl.add_argument("--caso", help="pasta do caso (o rascunho fica em <caso>/iped-pcba-relatorio/rt.json)")
    rl.add_argument("--dados", help="JSON do RT (em vez do rascunho do caso)")
    rl.add_argument("--saida", help="arquivo .docx de saída")
    rl.add_argument("--registros", help="CSV de registros telemáticos padronizados")
    rl.add_argument("--investigado", action="append", default=[], metavar="CONTA=NOME",
                    help="nome do investigado de uma conta (pode repetir)")
    rl.add_argument("--unidade", help="JSON da unidade (padrão: ~/.iped-pcba/unidade.json)")

    sk = sub.add_parser("skills", help="skills de análise para Claude Code, Hermes e Claude Desktop")
    sk.add_argument("--instalar", action="store_true", help="instala nos programas encontrados e gera os .zip")
    sk.add_argument("--destino", action="append", choices=["claude-code", "hermes", "zip"],
                    help="instala só neste destino (pode repetir)")

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


def executar_aplicacao(raiz, maquina, plano, papel="cliente", perfis=True, mcp=True,
                       escrita=True, simular=False):
    """Grava o plano (com backup), os perfis pcba-*, os lançadores, o MCP e o painel."""
    temp = plano.valor("LocalConfig.txt", "indexTemp")
    if temp and temp != "default" and not simular and not os.path.isdir(temp):
        os.makedirs(temp)
    backup = Backup(raiz)
    mudancas = aplicar_plano(raiz, plano, backup, simular=simular)
    feitos = criar_perfis(raiz, backup, simular=simular) if perfis else {}
    lancadores = []
    info_mcp = instalar_mcp(raiz, maquina["so"], REPO, backup, simular=simular,
                            escrita=escrita) if mcp else None
    if not simular:
        lancadores = gerar_lancadores(raiz, plano, sorted(PERFIS), maquina["so"], backup,
                                      papel=papel)
        lancadores += instalar_painel(raiz, maquina["so"], backup)
        gravar_maquina(raiz, maquina, plano, mudancas, backup)
    pasta_backup = None if simular else backup.fechar({"versao_instalador": __version__})
    return {"mudancas": mudancas, "perfis": sorted(feitos), "lancadores": lancadores,
            "mcp": info_mcp, "backup": pasta_backup}


def main(argv=None):
    try:
        return _main(argv)
    except PermissionError as e:
        print("ERRO: sem permissão para gravar em {}. Feche o IPED e rode o instalador como "
              "administrador (ou instale o IPED fora de Program Files).".format(e.filename),
              file=sys.stderr)
        return 3


def _relatorio(args):
    from . import rt
    if not (args.caso or args.dados):
        print("ERRO: informe --caso ou --dados.", file=sys.stderr)
        return 2
    unidade = rt.ler_unidade(args.unidade)
    if args.dados:
        with open(args.dados, encoding="utf-8") as f:
            dados = json.load(f)
    else:
        dados = rt.ler_rt(args.caso)
    if args.acao == "telematica":
        if not (args.registros and args.caso):
            print("ERRO: informe --caso e --registros.", file=sys.stderr)
            return 2
        nomes = dict(x.split("=", 1) for x in args.investigado if "=" in x)
        dados, info = incorporar_telematica(args.caso, args.registros, nomes)
        print("{} registros lidos, {} linhas rejeitadas, {} conta(s) em {} provedor(es).".format(
            info["registros"], len(info["rejeitadas"]), info["contas"], info["provedores"]))
        print("Rascunho atualizado: " + rt.arq_rt(args.caso))
        return 0
    if args.acao == "lacunas":
        faltas = rt.lacunas(dados, unidade)
        for onde, txt in faltas:
            print("{}\t{}".format(onde, txt))
        print("{} lacuna(s).".format(len(faltas)), file=sys.stderr)
        return 0
    saida = args.saida or os.path.join(args.caso or os.path.dirname(os.path.abspath(args.dados)),
                                       rt.PASTA_CASO, "RT.docx")
    print(rt.gerar_docx(dados, saida, unidade))
    return 0


def incorporar_telematica(caso, registros, investigados=None):
    """Lê o CSV padronizado e põe uma análise por provedor no rascunho do RT do caso.

    Análises que a pessoa já editou (sem 'gerado_automaticamente') nunca são substituídas.
    """
    from . import rt, telematica
    regs, rejeitadas = telematica.ler_csv(registros)
    resumos = telematica.resumir(regs)
    novas = telematica.analises_para_rt(resumos, investigados)
    dados = rt.ler_rt(caso)
    manter = [a for a in dados.get("analises") or []
              if not a.get("gerado_automaticamente")
              or a.get("provedor") not in {n["provedor"] for n in novas}]
    editadas = {a.get("provedor") for a in manter if not a.get("gerado_automaticamente")}
    dados["analises"] = manter + [n for n in novas if n["provedor"] not in editadas]
    rt.gravar_rt(caso, dados)
    from .visao import gravar_telematica
    gravar_telematica(caso, telematica.painel(regs), registros)
    return dados, {"registros": len(regs), "rejeitadas": rejeitadas, "contas": len(resumos),
                   "provedores": len({s["provedor"] for s in resumos}),
                   "resumos": telematica.resumo_json(resumos)}


def _main(argv=None):
    args = _args(argv if argv is not None else sys.argv[1:])
    if not args.comando:
        _args(["-h"])
        return 2
    if args.comando == "relatorio":
        return _relatorio(args)
    if args.comando == "skills":
        from . import skills
        if args.instalar or args.destino:
            for f in skills.instalar(args.destino):
                print("{}\t{}\t{}".format(f["destino"], f["skill"], f["acao"]))
            return 0
        for d in skills.situacao()["destinos"]:
            print("{} ({}): {}".format(d["nome"], d["pasta"], ", ".join(
                "{}={}".format(i["skill"], i["estado"]) for i in d["itens"])))
        return 0
    if args.comando == "localizar":
        for i in localizar_iped():
            print("{}\t{}".format(i["versao"] or "?", i["raiz"]))
        return 0

    if not args.iped:
        achados = localizar_iped()
        if not achados and args.comando == "painel":
            from .painel import servir
            return servir(None, porta=args.porta, navegador=not args.sem_navegador)
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

    if args.comando == "painel":
        from .painel import servir
        return servir(raiz, porta=args.porta, navegador=not args.sem_navegador)

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

    r = executar_aplicacao(raiz, maquina, plano, papel=args.papel, perfis=not args.sem_perfis,
                           mcp=not args.sem_mcp, escrita=not args.somente_leitura,
                           simular=args.simular)
    mudancas, perfis, lancadores, mcp, pasta_backup = (
        r["mudancas"], r["perfis"], r["lancadores"], r["mcp"], r["backup"])

    if args.json:
        print(json.dumps(dict(r, avisos=plano.avisos), indent=2, ensure_ascii=False))
        return 0
    print(_resumo(maquina, plano))
    print("")
    print("SIMULAÇÃO: nada foi gravado." if args.simular else "Aplicado.")
    for m in mudancas:
        if "erro" in m:
            print("  ! {}: {}".format(m["arquivo"], m["erro"]))
        else:
            print("  {} : {} {} -> {}".format(m["arquivo"], m["chave"], m["de"], m["para"]))
    for p in perfis:
        print("  perfil " + p)
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
