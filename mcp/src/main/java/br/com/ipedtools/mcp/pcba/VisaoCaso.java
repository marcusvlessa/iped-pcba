package br.com.ipedtools.mcp.pcba;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.LocalDateTime;
import java.time.Year;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import com.fasterxml.jackson.databind.ObjectMapper;

import br.com.ipedtools.mcp.service.IpedCoreService;
import iped.engine.search.IPEDSearcher;

/**
 * Números do caso para os gráficos do painel ("Visão do caso"): categorias, marcadores,
 * itens por mês, principais contatos, rede de comunicações e dispositivos.
 *
 * Roda sem o servidor MCP ({@code --exportar-visao <arquivo.json> --case <caso>}) e grava o
 * resultado em {@code <caso>/iped-pcba-painel/visao.json}. Só lê o caso. Cada parte é
 * independente: se uma falhar, as outras saem e o erro vai em "erros".
 */
public class VisaoCaso {

    public static final String PASTA = "iped-pcba-painel";
    public static final String ARQUIVO = "visao.json";
    static final int ANO_INICIAL = 1990;

    /** Quantos itens do caso atendem a uma consulta do IPED. */
    public interface Contador {
        int contar(String consulta) throws Exception;
    }

    /** Contagens usadas nos alertas do painel. */
    static final Map<String, String> ESPECIAIS = Map.of(
            "apagados", "deleted:true",
            "recuperados_carving", "carved:true",
            "alerta_hash", "hashDb\\:status:alert");

    private static final Pattern COMUNICACAO = Pattern.compile(
            "(?i).*(chat|mensag|message|whatsapp|telegram|signal|sms|mms|call|chamada|liga[cç]|e-?mail).*");

    public static Map<String, Object> gerar(IpedCoreService s) {
        Contador c = consulta -> new IPEDSearcher(s.getSource(), consulta).search().getLength();
        Map<String, Object> v = new LinkedHashMap<>();
        Map<String, String> erros = new LinkedHashMap<>();
        v.put("gerado_em", LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        v.put("caso", s.getCaseDirectory().getAbsolutePath());

        parte(erros, "geral", () -> {
            Map<String, Object> g = new LinkedHashMap<>();
            g.put("total_itens", s.getTotalIndexedItems());
            g.put("fontes", s.listSources());
            v.put("geral", g);
        });
        List<String> cats = new ArrayList<>();
        parte(erros, "categorias", () -> {
            cats.addAll(s.listCategories());
            v.put("categorias", categorias(c, cats));
        });
        parte(erros, "marcadores", () -> {
            var bm = s.getSource().getBookmarks();
            List<Map<String, Object>> lista = new ArrayList<>();
            for (Map.Entry<Integer, String> e : bm.getBookmarkMap().entrySet()) {
                lista.add(item("nome", e.getValue(), "total", bm.getBookmarkCount(e.getKey())));
            }
            v.put("marcadores", lista);
        });
        parte(erros, "linha_do_tempo", () -> {
            String filtro = filtroComunicacao(cats);
            Map<String, Object> lt = new LinkedHashMap<>();
            lt.put("meses", linhaDoTempo(c, ANO_INICIAL, Year.now().getValue() + 1, filtro));
            lt.put("categorias_comunicacao", cats.stream().filter(x -> COMUNICACAO.matcher(x).matches())
                    .collect(Collectors.toList()));
            v.put("linha_do_tempo", lt);
        });
        parte(erros, "contatos", () -> v.put("contatos", s.getTopContacts(15).get("contacts")));
        parte(erros, "rede", () -> v.put("rede", s.getCommunicationsGraph("", 2, 60)));
        parte(erros, "dispositivos", () -> v.put("dispositivos", dispositivos(s.getDeviceAndOwnerInfo())));
        parte(erros, "ia_filtros", () -> {
            Object fs = s.listAiFilters().get("filters");
            List<Map<String, Object>> out = new ArrayList<>();
            if (fs instanceof List) {
                for (Object o : (List<?>) fs) {
                    if (o instanceof Map) {
                        Map<?, ?> f = (Map<?, ?>) o;
                        out.add(item("id", f.get("filter_type"), "nome", f.get("name"), "total", f.get("count")));
                    }
                }
            }
            v.put("ia_filtros", out);
        });
        Map<String, Object> esp = new LinkedHashMap<>();
        for (Map.Entry<String, String> e : ESPECIAIS.entrySet()) {
            parte(erros, "especiais." + e.getKey(), () -> esp.put(e.getKey(), c.contar(e.getValue())));
        }
        v.put("especiais", esp);
        v.put("erros", erros);
        return v;
    }

    interface Parte {
        void executar() throws Exception;
    }

    private static void parte(Map<String, String> erros, String nome, Parte p) {
        try {
            p.executar();
        } catch (Throwable t) {
            erros.put(nome, t.getClass().getSimpleName() + ": " + t.getMessage());
        }
    }

    static Map<String, Object> item(Object... kv) {
        Map<String, Object> m = new LinkedHashMap<>();
        for (int i = 0; i + 1 < kv.length; i += 2) {
            m.put(String.valueOf(kv[i]), kv[i + 1]);
        }
        return m;
    }

    static String aspas(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    /** Total por categoria, da maior para a menor; categorias vazias ficam de fora. */
    static List<Map<String, Object>> categorias(Contador c, List<String> cats) throws Exception {
        List<Map<String, Object>> out = new ArrayList<>();
        for (String cat : cats) {
            int n = c.contar("category:" + aspas(cat));
            if (n > 0) {
                out.add(item("nome", cat, "total", n));
            }
        }
        out.sort((a, b) -> Integer.compare((int) b.get("total"), (int) a.get("total")));
        return out;
    }

    /** Consulta que restringe às categorias de comunicação, ou null se o caso não tiver nenhuma. */
    static String filtroComunicacao(List<String> cats) {
        List<String> com = cats.stream().filter(x -> COMUNICACAO.matcher(x).matches())
                .map(x -> "category:" + aspas(x)).collect(Collectors.toList());
        return com.isEmpty() ? null : "(" + String.join(" OR ", com) + ")";
    }

    /** Datas de ini (inclusive) até fim (exclusive). */
    static String faixa(String ini, String fim) {
        return "timeStamp:[\"" + ini + "\" TO \"" + fim + "\"}";
    }

    /**
     * Itens com alguma data em cada mês (horário UTC do índice). Conta primeiro por ano e só
     * desce aos meses dos anos que têm itens. Meses vazios entre o primeiro e o último ficam
     * com zero, para o gráfico não esconder buracos.
     */
    static List<Map<String, Object>> linhaDoTempo(Contador c, int anoIni, int anoFim, String filtro)
            throws Exception {
        List<Integer> anos = new ArrayList<>();
        for (int a = anoIni; a <= anoFim; a++) {
            if (c.contar(faixa(a + "-01-01T00:00:00Z", (a + 1) + "-01-01T00:00:00Z")) > 0) {
                anos.add(a);
            }
        }
        List<Map<String, Object>> meses = new ArrayList<>();
        if (anos.isEmpty()) {
            return meses;
        }
        for (int a = anos.get(0); a <= anos.get(anos.size() - 1); a++) {
            for (int m = 1; m <= 12; m++) {
                String ini = String.format("%d-%02d-01T00:00:00Z", a, m);
                String fim = m == 12 ? String.format("%d-01-01T00:00:00Z", a + 1)
                        : String.format("%d-%02d-01T00:00:00Z", a, m + 1);
                int total = anos.contains(a) ? c.contar(faixa(ini, fim)) : 0;
                int com = total > 0 && filtro != null ? c.contar(faixa(ini, fim) + " AND " + filtro) : 0;
                meses.add(item("mes", String.format("%d-%02d", a, m), "total", total, "comunicacao", com));
            }
        }
        // corta meses vazios nas pontas
        int i = 0, j = meses.size() - 1;
        while (i <= j && (int) meses.get(i).get("total") == 0) i++;
        while (j >= i && (int) meses.get(j).get("total") == 0) j--;
        return new ArrayList<>(meses.subList(i, j + 1));
    }

    @SuppressWarnings("unchecked")
    static List<Map<String, Object>> dispositivos(Map<String, Object> info) {
        List<Map<String, Object>> out = new ArrayList<>();
        Object evs = info == null ? null : info.get("evidences");
        if (!(evs instanceof List)) {
            return out;
        }
        for (Object o : (List<Object>) evs) {
            if (!(o instanceof Map)) continue;
            Map<String, Object> e = (Map<String, Object>) o;
            Map<String, Object> d = new LinkedHashMap<>();
            for (String k : List.of("name", "type", "likely_owners", "owner_phone_numbers", "owner_emails",
                    "device_properties", "total_accounts_found")) {
                if (e.get(k) != null) d.put(k, e.get(k));
            }
            out.add(d);
        }
        return out;
    }

    /** Grava de forma atômica (o painel pode estar lendo o arquivo anterior). */
    public static void gravar(Map<String, Object> visao, File destino) throws Exception {
        Path p = destino.toPath();
        if (p.getParent() != null) {
            Files.createDirectories(p.getParent());
        }
        Path tmp = p.resolveSibling(p.getFileName() + ".tmp");
        Files.writeString(tmp, new ObjectMapper().writerWithDefaultPrettyPrinter().writeValueAsString(visao),
                StandardCharsets.UTF_8);
        Files.move(tmp, p, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
    }

    /** Modo linha de comando: abre o caso, grava o JSON e devolve o código de saída. */
    public static int exportar(String caso, String saida) {
        if (caso == null || caso.isBlank()) {
            System.err.println("ERRO: informe --case <pasta do caso>");
            return 2;
        }
        try {
            IpedCoreService s = IpedCoreService.getInstance();
            s.openCase(new File(caso));
            if (!s.isCaseOpen()) {
                System.err.println("ERRO: não consegui abrir o caso " + caso);
                return 1;
            }
            File destino = saida == null || saida.isBlank()
                    ? new File(new File(caso, PASTA), ARQUIVO) : new File(saida);
            gravar(gerar(s), destino);
            System.out.println(destino.getAbsolutePath());
            return 0;
        } catch (Throwable t) {
            System.err.println("ERRO: " + t);
            return 1;
        }
    }
}
