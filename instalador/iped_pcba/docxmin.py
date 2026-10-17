"""Gerador mínimo de .docx só com a biblioteca padrão do Python.

O Python que vem dentro do IPED não tem pip nem python-docx, então o relatório é montado
direto em OOXML: parágrafos, tabelas, imagem JPEG/PNG, cabeçalho e rodapé por seção e os
campos PAGE/NUMPAGES. O resultado abre no Word e no LibreOffice e pode ser editado à vontade.
"""

import os
import re
import struct
import zipfile
from xml.sax.saxutils import escape

EMU_CM = 360000
TWIP_CM = 567
LACUNA = re.compile(r"(\[[^\[\]]*\])")
NUMERO = re.compile(r"^-?(R\$\s*)?-?\d[\d.,]*%?$")

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')


def tamanho_imagem(caminho):
    """(largura, altura) em pixels de um JPEG ou PNG."""
    with open(caminho, "rb") as f:
        dados = f.read()
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", dados[16:24])
    if dados[:2] != b"\xff\xd8":
        raise ValueError("Imagem deve ser JPEG ou PNG: " + caminho)
    i = 2
    while i < len(dados):
        if dados[i] != 0xFF:
            i += 1
            continue
        marca = dados[i + 1]
        if marca in (0xD8, 0xD9) or 0xD0 <= marca <= 0xD7:
            i += 2
            continue
        comp = struct.unpack(">H", dados[i + 2:i + 4])[0]
        if 0xC0 <= marca <= 0xCF and marca not in (0xC4, 0xC8, 0xCC):
            alt, larg = struct.unpack(">HH", dados[i + 5:i + 9])
            return larg, alt
        i += 2 + comp
    raise ValueError("JPEG sem dimensões: " + caminho)


class Bloco(object):
    """Sequência de parágrafos e tabelas (corpo, cabeçalho ou rodapé)."""

    def __init__(self, doc):
        self.doc = doc
        self.xml = []

    # ------------------------------------------------------------ texto
    def _runs(self, texto, negrito=False, italico=False, tam=12, cor=None, lacunas=True):
        partes = LACUNA.split(str(texto if texto is not None else "")) if lacunas else [str(texto)]
        saida = []
        for parte in partes:
            if not parte:
                continue
            vermelho = lacunas and LACUNA.fullmatch(parte)
            props = ['<w:rFonts w:ascii="{0}" w:hAnsi="{0}" w:cs="{0}"/>'.format(self.doc.fonte)]
            if negrito or vermelho:
                props.append("<w:b/>")
            if italico:
                props.append("<w:i/>")
            c = "FF0000" if vermelho else cor
            if c:
                props.append('<w:color w:val="{}"/>'.format(c))
            props.append('<w:sz w:val="{0}"/><w:szCs w:val="{0}"/>'.format(int(tam * 2)))
            linhas = parte.split("\n")
            corpo = '<w:br/>'.join('<w:t xml:space="preserve">{}</w:t>'.format(escape(l)) for l in linhas)
            saida.append("<w:r><w:rPr>{}</w:rPr>{}</w:r>".format("".join(props), corpo))
        return "".join(saida)

    def _ppr(self, alinhar, antes, depois, extra=""):
        alin = {"just": "both", "centro": "center", "esq": "left", "dir": "right"}[alinhar]
        return ('<w:pPr>{}<w:spacing w:before="{}" w:after="{}" w:line="288" w:lineRule="auto"/>'
                '<w:jc w:val="{}"/></w:pPr>').format(extra, int(antes * 20), int(depois * 20), alin)

    def paragrafo(self, texto="", negrito=False, italico=False, alinhar="just", tam=12,
                  antes=0, depois=6, cor=None):
        self.xml.append("<w:p>{}{}</w:p>".format(
            self._ppr(alinhar, antes, depois),
            self._runs(texto, negrito, italico, tam, cor) if texto else ""))

    def rotulo(self, rotulo, valor, tam=12):
        """'RÓTULO: valor', rótulo em negrito."""
        self.xml.append("<w:p>{}{}{}</w:p>".format(
            self._ppr("just", 0, 2), self._runs(rotulo + " ", negrito=True, tam=tam, lacunas=False),
            self._runs(valor, tam=tam)))

    def campos_pagina(self, tam=8):
        r = self._runs
        fld = '<w:fldSimple w:instr="{}">' + r("1", tam=tam) + '</w:fldSimple>'
        self.xml.append("<w:p>{}{}{}{}{}</w:p>".format(
            self._ppr("centro", 0, 0), r("Página ", tam=tam), fld.format("PAGE"),
            r(" de ", tam=tam), fld.format("NUMPAGES")))

    def imagem(self, caminho, largura_cm, alinhar="centro"):
        rid, nome = self.doc.registrar_imagem(caminho, self)
        lpx, apx = tamanho_imagem(caminho)
        cx = int(largura_cm * EMU_CM)
        cy = int(cx * apx / float(lpx))
        n = self.doc.proximo_id()
        desenho = (
            '<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            '<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{n}" name="Imagem {n}"/>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic><pic:nvPicPr><pic:cNvPr id="{n}" name="{nome}"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>').format(
                cx=cx, cy=cy, n=n, nome=escape(nome), rid=rid)
        self.xml.append("<w:p>{}{}</w:p>".format(self._ppr(alinhar, 0, 0), desenho))

    # ------------------------------------------------------------ tabela
    def tabela(self, cabecalho, linhas, larguras_cm=None, tam=10, bordas=True, alinhamentos=None,
               fundo_cabecalho="D9D9D9"):
        ncol = len(cabecalho) if cabecalho else len(linhas[0])
        larguras_cm = larguras_cm or [15.5 / ncol] * ncol
        if not alinhamentos:
            # coluna só com números (valores, quantidades) fica alinhada à direita
            alinhamentos = []
            for i in range(ncol):
                vals = [str(l[i]).strip() for l in linhas if i < len(l) and l[i] not in (None, "")]
                alinhamentos.append("dir" if vals and all(NUMERO.match(v) for v in vals) else "esq")
        borda = ('<w:tblBorders>' + "".join(
            '<w:{} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'.format(b)
            for b in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>'
            if bordas else '<w:tblBorders>' + "".join(
                '<w:{} w:val="nil"/>'.format(b)
                for b in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>')
        xml = ['<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:jc w:val="center"/>{}'
               '<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>{}</w:tblGrid>'.format(
                   borda, "".join('<w:gridCol w:w="{}"/>'.format(int(l * TWIP_CM)) for l in larguras_cm))]

        def linha(celulas, negrito, fundo):
            xml.append("<w:tr>")
            for i, valor in enumerate(celulas):
                sombra = '<w:shd w:val="clear" w:color="auto" w:fill="{}"/>'.format(fundo) if fundo else ""
                alin = "centro" if negrito else alinhamentos[i]
                xml.append('<w:tc><w:tcPr><w:tcW w:w="{}" w:type="dxa"/>{}</w:tcPr><w:p>{}{}</w:p></w:tc>'.format(
                    int(larguras_cm[i] * TWIP_CM), sombra, self._ppr(alin, 1, 1),
                    self._runs(valor, negrito=negrito, tam=tam)))
            xml.append("</w:tr>")

        if cabecalho:
            linha(cabecalho, True, fundo_cabecalho)
        for l in linhas:
            linha(["" if v is None else v for v in l], False, None)
        xml.append("</w:tbl>")
        self.xml.append("".join(xml))
        self.paragrafo("", depois=4)


class Documento(object):
    def __init__(self, fonte="Arial"):
        self.fonte = fonte
        self.secoes = []          # (Bloco corpo, cabeçalho|None, rodapé|None, margens)
        self._midia = {}
        self._rels_extra = []     # (id, tipo, alvo) do document.xml
        self._partes = {}         # nome -> xml (cabeçalhos/rodapés)
        self._rels_partes = {}    # nome da parte -> [(id, alvo)]
        self._n = 0

    def proximo_id(self):
        self._n += 1
        return self._n

    def nova_secao(self, margens=(3.0, 2.5, 2.5, 3.0), cabecalho=False, rodape=False):
        """margens: (cima, direita, baixo, esquerda) em cm. Devolve (corpo, cabeçalho, rodapé)."""
        corpo = Bloco(self)
        cab = Bloco(self) if cabecalho else None
        rod = Bloco(self) if rodape else None
        n = len(self.secoes) + 1
        if cab:
            cab._parte = "header{}.xml".format(n)
        if rod:
            rod._parte = "footer{}.xml".format(n)
        self.secoes.append((corpo, cab, rod, margens))
        return corpo, cab, rod

    def registrar_imagem(self, caminho, bloco):
        ext = os.path.splitext(caminho)[1].lower().lstrip(".")
        ext = "jpeg" if ext == "jpg" else ext
        if caminho not in self._midia:
            self._midia[caminho] = "imagem{}.{}".format(len(self._midia) + 1, ext)
        nome = self._midia[caminho]
        dono = getattr(bloco, "_parte", "document.xml")
        rels = self._rels_partes.setdefault(dono, [])
        rid = "rIdImg{}".format(len(rels) + 1)
        rels.append((rid, "media/" + nome))
        return rid, nome

    def salvar(self, caminho):
        # cada cabeçalho/rodapé vira uma parte; as imagens dele ficam nas rels da parte
        corpo_xml = []
        rels_doc = []
        for i, (corpo, cab, rod, margens) in enumerate(self.secoes):
            refs = []
            for tipo, bloco in (("header", cab), ("footer", rod)):
                if bloco is None:
                    continue
                nome = "{}{}.xml".format(tipo, i + 1)
                rid = "rId{}{}".format(tipo, i + 1)
                rels_doc.append((rid, tipo, nome))
                refs.append('<w:{}Reference w:type="default" r:id="{}"/>'.format(tipo, rid))
                self._partes[nome] = (tipo, bloco)
            cima, dir_, baixo, esq = margens
            sect = ('<w:sectPr>{}<w:pgSz w:w="11906" w:h="16838"/>'
                    '<w:pgMar w:top="{}" w:right="{}" w:bottom="{}" w:left="{}" w:header="454" '
                    'w:footer="454" w:gutter="0"/></w:sectPr>').format(
                        "".join(refs), int(cima * TWIP_CM), int(dir_ * TWIP_CM),
                        int(baixo * TWIP_CM), int(esq * TWIP_CM))
            if i == len(self.secoes) - 1:
                corpo_xml.append("".join(corpo.xml))
                corpo_xml.append(sect)
            else:
                corpo_xml.append("".join(corpo.xml))
                corpo_xml.append("<w:p><w:pPr>{}</w:pPr></w:p>".format(sect))
        documento = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<w:document {}><w:body>{}</w:body></w:document>').format(NS, "".join(corpo_xml))

        def rels_xml(itens):
            return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    + "".join('<Relationship Id="{}" Type="{}" Target="{}"/>'.format(*x) for x in itens)
                    + '</Relationships>')

        base = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
        itens_doc = [("rIdEstilos", base + "styles", "styles.xml")]
        itens_doc += [(rid, base + tipo, nome) for rid, tipo, nome in rels_doc]
        itens_doc += [(rid, base + "image", alvo) for rid, alvo in self._rels_partes.get("document.xml", [])]

        tipos_img = {os.path.splitext(n)[1].lstrip("."): 1 for n in self._midia.values()}
        ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>']
        for ext in tipos_img:
            ct.append('<Default Extension="{0}" ContentType="image/{0}"/>'.format(ext))
        ct.append('<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
                  'officedocument.wordprocessingml.document.main+xml"/>')
        ct.append('<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
                  'officedocument.wordprocessingml.styles+xml"/>')
        for nome, (tipo, _) in self._partes.items():
            ct.append('<Override PartName="/word/{}" ContentType="application/vnd.openxmlformats-'
                      'officedocument.wordprocessingml.{}+xml"/>'.format(nome, tipo))
        ct.append("</Types>")

        estilos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<w:styles {}><w:docDefaults><w:rPrDefault><w:rPr>'
                   '<w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:cs="{f}" w:eastAsia="{f}"/>'
                   '<w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="pt-BR"/></w:rPr></w:rPrDefault>'
                   '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="288" w:lineRule="auto"/></w:pPr>'
                   '</w:pPrDefault></w:docDefaults>'
                   '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
                   '</w:style></w:styles>').format(NS, f=self.fonte)

        os.makedirs(os.path.dirname(os.path.abspath(caminho)) or ".", exist_ok=True)
        tmp = caminho + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", "".join(ct))
            z.writestr("_rels/.rels", rels_xml([("rId1", base + "officeDocument", "word/document.xml")]))
            z.writestr("word/document.xml", documento)
            z.writestr("word/styles.xml", estilos)
            z.writestr("word/_rels/document.xml.rels", rels_xml(itens_doc))
            for nome, (tipo, bloco) in self._partes.items():
                z.writestr("word/" + nome, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                           '<w:{t} {ns}>{c}</w:{t}>'.format(t="hdr" if tipo == "header" else "ftr", ns=NS,
                                                             c="".join(bloco.xml) or "<w:p/>"))
                rels = self._rels_partes.get(nome)
                if rels:
                    z.writestr("word/_rels/{}.rels".format(nome),
                               rels_xml([(rid, base + "image", alvo) for rid, alvo in rels]))
            for origem, nome in self._midia.items():
                z.write(origem, "word/media/" + nome)
        os.replace(tmp, caminho)
        return caminho
