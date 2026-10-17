package br.com.ipedtools.mcp.pcba;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class RascunhoRelatorioTest {

    @TempDir
    Path caso;

    @Test
    @SuppressWarnings("unchecked")
    void escreveCamposEAnalisesMarcandoAIa() throws Exception {
        RascunhoRelatorio r = new RascunhoRelatorio(caso);
        assertFalse((Boolean) r.resumo().get("existe"));
        r.definirCampo("texto_apresentacao", "Trata-se de caso fictício. Processo [NÚMERO DO PROCESSO].");
        r.definirAnalise("whatsapp", null, "Texto da análise fictícia.", null);
        r.definirAnalise("WHATSAPP", null, "Texto revisto.", null);

        Map<String, Object> d = r.ler();
        List<Object> analises = (List<Object>) d.get("analises");
        assertEquals(1, analises.size());
        Map<String, Object> wa = (Map<String, Object>) analises.get(0);
        assertEquals("Texto revisto.", wa.get("texto"));
        assertEquals("[CONCLUSÃO DO ANALISTA SOBRE WHATSAPP]", wa.get("conclusao"));
        Map<String, Object> ia = (Map<String, Object>) d.get("ia_editou");
        assertTrue(ia.containsKey("texto_apresentacao"));
        assertTrue(ia.containsKey("analises.WHATSAPP"));
        assertTrue(RascunhoRelatorio.lacunas(d).contains("[NÚMERO DO PROCESSO]"));
        try (var s = Files.list(caso.resolve("iped-pcba-relatorio").resolve("historico"))) {
            assertEquals(2, s.count());
        }
        assertThrows(IllegalArgumentException.class, () -> r.definirCampo("analistas", "x"));
    }

    @Test
    void conclusaoDaIaFicaEntreColchetes() {
        assertEquals("[SUGESTÃO DA IA — REVISAR: Os dados indicam contato frequente (ver item 12).]",
                RascunhoRelatorio.sugestao("Os dados indicam contato frequente [ver item 12].", "WHATSAPP"));
        assertEquals("[CONCLUSÃO A CARGO DO ANALISTA]",
                RascunhoRelatorio.sugestao(" [CONCLUSÃO A CARGO DO ANALISTA] ", "WHATSAPP"));
        assertEquals("[CONCLUSÃO DO ANALISTA SOBRE WHATSAPP]", RascunhoRelatorio.sugestao("  ", "WHATSAPP"));
    }

    @Test
    void preservaCamposQueAIaNaoConhece() throws Exception {
        Path arq = caso.resolve("iped-pcba-relatorio").resolve("rt.json");
        Files.createDirectories(arq.getParent());
        Files.writeString(arq, "{\"hashes\":[\"a — SHA-256: X\"],\"incluir_clausulas\":false}");
        new RascunhoRelatorio(caso).definirCampo("processo", "0000000-00.2026.8.05.0000");
        Map<String, Object> d = new RascunhoRelatorio(caso).ler();
        assertEquals(List.of("a — SHA-256: X"), d.get("hashes"));
        assertEquals(false, d.get("incluir_clausulas"));
    }
}
