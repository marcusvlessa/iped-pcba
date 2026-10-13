package br.com.ipedtools.mcp.pcba;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class VisaoCasoTest {

    /** Caso fictício: datas de itens; os de "WhatsApp" contam como comunicação. */
    static final List<String[]> ITENS = List.of(
            new String[] {"2023-11-30T23:59:59Z", "Imagens"},
            new String[] {"2024-01-15T10:00:00Z", "WhatsApp"},
            new String[] {"2024-01-31T23:00:00Z", "Imagens"},
            new String[] {"2024-02-01T00:00:00Z", "WhatsApp"},
            new String[] {"2024-04-03T12:00:00Z", "WhatsApp"});

    static final Pattern FAIXA = Pattern.compile("timeStamp:\\[\"([^\"]+)\" TO \"([^\"]+)\"\\}");

    final List<String> consultas = new ArrayList<>();

    final VisaoCaso.Contador contador = q -> {
        consultas.add(q);
        Matcher m = FAIXA.matcher(q);
        if (m.find()) {
            String ini = m.group(1), fim = m.group(2);
            boolean so = q.contains("category:\"WhatsApp\"");
            return (int) ITENS.stream().filter(i -> i[0].compareTo(ini) >= 0 && i[0].compareTo(fim) < 0)
                    .filter(i -> !so || i[1].equals("WhatsApp")).count();
        }
        if (q.equals("category:\"WhatsApp\"")) return 3;
        if (q.equals("category:\"Imagens\"")) return 2;
        return 0;
    };

    @Test
    void linhaDoTempoPorMesComBuracosEPontasCortadas() throws Exception {
        String filtro = VisaoCaso.filtroComunicacao(List.of("Imagens", "WhatsApp", "Vazia"));
        assertEquals("(category:\"WhatsApp\")", filtro);
        List<Map<String, Object>> meses = VisaoCaso.linhaDoTempo(contador, 2020, 2026, filtro);
        assertEquals("2023-11", meses.get(0).get("mes"));
        assertEquals("2024-04", meses.get(meses.size() - 1).get("mes"));
        assertEquals(6, meses.size()); // nov, dez, jan, fev, mar (zero), abr
        Map<String, Object> jan = meses.get(2);
        assertEquals("2024-01", jan.get("mes"));
        assertEquals(2, jan.get("total"));
        assertEquals(1, jan.get("comunicacao"));
        assertEquals(1, meses.get(3).get("total")); // 01/02 00:00 não conta em janeiro
        assertEquals(0, meses.get(4).get("total"));
        // anos sem itens não descem aos meses
        assertTrue(consultas.stream().noneMatch(q -> q.contains("2021-03-01")));
    }

    @Test
    void categoriasOrdenadasSemVazias() throws Exception {
        List<Map<String, Object>> c = VisaoCaso.categorias(contador, List.of("Imagens", "Vazia", "WhatsApp"));
        assertEquals(2, c.size());
        assertEquals("WhatsApp", c.get(0).get("nome"));
        assertEquals("category:\"a\\\"b\"", "category:" + VisaoCaso.aspas("a\"b"));
        assertNull(VisaoCaso.filtroComunicacao(List.of("Imagens", "Documentos")));
    }

    @Test
    void dispositivosSoComCamposUteis() {
        Map<String, Object> info = Map.of("evidences", List.of(Map.of("name", "celular.ufdr", "type", "Android",
                "likely_owners", List.of("FULANO (FICTÍCIO)"), "user_accounts", List.of("x"))));
        List<Map<String, Object>> d = VisaoCaso.dispositivos(info);
        assertEquals("celular.ufdr", d.get(0).get("name"));
        assertFalse(d.get(0).containsKey("user_accounts"));
        assertTrue(VisaoCaso.dispositivos(Map.of()).isEmpty());
    }

    @Test
    void gravaJson(@TempDir Path dir) throws Exception {
        Path arq = dir.resolve("iped-pcba-painel").resolve("visao.json");
        VisaoCaso.gravar(Map.of("erros", Map.of()), arq.toFile());
        assertTrue(Files.readString(arq).contains("\"erros\""));
    }
}
