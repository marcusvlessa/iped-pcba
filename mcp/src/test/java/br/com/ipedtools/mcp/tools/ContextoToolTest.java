package br.com.ipedtools.mcp.tools;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ContextoToolTest {

    @TempDir
    Path caso;

    @Test
    void semArquivoExplicaComoPreparar() {
        Map<?, ?> r = (Map<?, ?>) ContextoTool.executar(caso.toFile(), "listar", "", "", 0);
        assertTrue(String.valueOf(r.get("erro")).contains("Preparar para Claude"));
    }

    @Test
    void listaBuscaELe() throws Exception {
        Files.createDirectories(caso.resolve("iped-pcba-ia"));
        String longo = "linha fictícia ".repeat(1000) + "PIX para FULANO";
        Files.writeString(caso.resolve(ContextoTool.ARQUIVO), """
            {"arquivos":[{"nome":"docs/bo.txt","sha256":"abc","texto":"Suspeito FULANO DE TAL, telefone fictício"},
                         {"nome":"docs/longo.txt","sha256":"def","texto":"%s"}]}""".formatted(longo));
        Map<?, ?> l = (Map<?, ?>) ContextoTool.executar(caso.toFile(), "", "", "", 0);
        assertEquals(2, ((List<?>) l.get("arquivos")).size());
        Map<?, ?> b = (Map<?, ?>) ContextoTool.executar(caso.toFile(), "buscar", "fulano", "", 0);
        assertEquals(2, ((List<?>) b.get("achados")).size());
        Map<?, ?> r = (Map<?, ?>) ContextoTool.executar(caso.toFile(), "ler", "", "longo", 0);
        assertEquals(8000, r.get("continuar_com_inicio"));
        Map<?, ?> r2 = (Map<?, ?>) ContextoTool.executar(caso.toFile(), "ler", "", "docs/longo.txt", 8000);
        assertTrue(String.valueOf(r2.get("texto")).endsWith("PIX para FULANO"));
    }
}
