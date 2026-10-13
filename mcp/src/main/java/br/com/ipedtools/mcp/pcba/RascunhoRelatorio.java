package br.com.ipedtools.mcp.pcba;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

/**
 * Rascunho do Relatório Técnico do caso, o mesmo arquivo que o painel edita:
 * {@code <caso>/iped-pcba-relatorio/rt.json}. O .docx é gerado pelo painel.
 *
 * Cada campo que a IA escreve fica listado em "ia_editou", para o painel pedir revisão
 * humana. Antes de cada gravação a versão anterior vai para historico/.
 */
public class RascunhoRelatorio {

    public static final String PASTA = "iped-pcba-relatorio";

    /** Campos de texto que a IA pode escrever (os mesmos do painel). */
    public static final Set<String> CAMPOS = new LinkedHashSet<>(List.of(
            "numero_rt", "data_rt", "nome_operacao", "assunto", "destinatario_ao", "processo", "difusao",
            "juiz_autorizador", "vara_comarca", "resumo_executivo", "texto_apresentacao", "texto_objetivo",
            "texto_fatos_relacoes", "texto_cadastro_telefonico", "texto_cancelamento", "metodologia",
            "providencias_intro"));

    private static final Pattern LACUNA = Pattern.compile("\\[[^\\[\\]]*\\]");
    private static final ObjectMapper JSON = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);

    private final Path arquivo;

    public RascunhoRelatorio(Path caso) {
        this.arquivo = caso.resolve(PASTA).resolve("rt.json");
    }

    public Path arquivo() {
        return arquivo;
    }

    public Map<String, Object> ler() throws IOException {
        if (!Files.isRegularFile(arquivo)) {
            Map<String, Object> vazio = new LinkedHashMap<>();
            for (String c : CAMPOS) {
                vazio.put(c, "");
            }
            vazio.put("analises", new ArrayList<>());
            vazio.put("pedidos", new ArrayList<>());
            return vazio;
        }
        return JSON.readValue(arquivo.toFile(), new TypeReference<LinkedHashMap<String, Object>>() {});
    }

    /** Resumo para a IA: o rascunho e as lacunas [ENTRE COLCHETES] que ainda faltam. */
    public Map<String, Object> resumo() throws IOException {
        Map<String, Object> dados = ler();
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("arquivo", arquivo.toString());
        r.put("existe", Files.isRegularFile(arquivo));
        r.put("rascunho", dados);
        r.put("lacunas", lacunas(dados));
        r.put("campos_editaveis", CAMPOS);
        r.put("observacao", "Rascunho do RT no modelo da PCBA. Escreva em prosa corrida, sem tópicos, "
                + "terceira pessoa. Não invente processo, CPF, IMEI, hash, conta ou período: deixe entre "
                + "colchetes, que sai em vermelho. A conclusão de cada análise é do analista; se escrever, "
                + "deixe claro que é sugestão. O analista revisa e gera o .docx no painel.");
        return r;
    }

    public static List<String> lacunas(Object valor) {
        List<String> saida = new ArrayList<>();
        varrer(valor, saida);
        return saida;
    }

    @SuppressWarnings("unchecked")
    private static void varrer(Object v, List<String> saida) {
        if (v instanceof String s) {
            Matcher m = LACUNA.matcher(s);
            while (m.find()) {
                saida.add(m.group());
            }
        } else if (v instanceof Map<?, ?> m) {
            for (Map.Entry<?, ?> e : m.entrySet()) {
                if (!"ia_editou".equals(e.getKey())) {
                    varrer(e.getValue(), saida);
                }
            }
        } else if (v instanceof List<?> l) {
            for (Object x : l) {
                varrer(x, saida);
            }
        }
    }

    public synchronized String definirCampo(String campo, String valor) throws IOException {
        if (!CAMPOS.contains(campo)) {
            throw new IllegalArgumentException("Campo desconhecido: " + campo + ". Use um destes: " + CAMPOS);
        }
        Map<String, Object> dados = ler();
        dados.put(campo, valor == null ? "" : valor);
        marcar(dados, campo);
        gravar(dados);
        return "Campo '" + campo + "' gravado no rascunho do RT. O analista deve revisar no painel.";
    }

    @SuppressWarnings("unchecked")
    public synchronized String definirAnalise(String provedor, String titulo, String texto, String conclusao)
            throws IOException {
        if (provedor == null || provedor.isBlank()) {
            throw new IllegalArgumentException("Informe o provedor (ex.: WHATSAPP, GOOGLE, APPLE).");
        }
        String prov = provedor.trim().toUpperCase();
        Map<String, Object> dados = ler();
        List<Object> analises = (List<Object>) dados.computeIfAbsent("analises", k -> new ArrayList<>());
        Map<String, Object> alvo = null;
        for (Object o : analises) {
            if (o instanceof Map<?, ?> m && prov.equalsIgnoreCase(String.valueOf(m.get("provedor")))) {
                alvo = (Map<String, Object>) m;
                break;
            }
        }
        boolean nova = alvo == null;
        if (nova) {
            alvo = new LinkedHashMap<>();
            alvo.put("provedor", prov);
            alvo.put("titulo", "DA ANÁLISE DOS DADOS TELEMÁTICOS – " + prov);
            alvo.put("tabela", new ArrayList<>());
            alvo.put("texto", "");
            alvo.put("conclusao", "[CONCLUSÃO DO ANALISTA SOBRE " + prov + "]");
            analises.add(alvo);
        }
        if (titulo != null && !titulo.isBlank()) {
            alvo.put("titulo", titulo);
        }
        if (texto != null) {
            alvo.put("texto", texto);
        }
        if (conclusao != null) {
            alvo.put("conclusao", conclusao);
        }
        alvo.remove("gerado_automaticamente");
        marcar(dados, "analises." + prov);
        gravar(dados);
        return (nova ? "Análise criada" : "Análise atualizada") + " para " + prov
                + " no rascunho do RT. O analista deve revisar no painel.";
    }

    @SuppressWarnings("unchecked")
    private static void marcar(Map<String, Object> dados, String campo) {
        Map<String, Object> ia = (Map<String, Object>) dados.computeIfAbsent("ia_editou", k -> new LinkedHashMap<>());
        ia.put(campo, LocalDateTime.now().withNano(0).toString());
    }

    private void gravar(Map<String, Object> dados) throws IOException {
        Files.createDirectories(arquivo.getParent());
        if (Files.isRegularFile(arquivo)) {
            Path hist = arquivo.getParent().resolve("historico");
            Files.createDirectories(hist);
            String carimbo = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSSSSS"));
            Files.copy(arquivo, hist.resolve("rt-" + carimbo + "-ia.json"));
        }
        Path tmp = arquivo.resolveSibling("rt.json.tmp");
        Files.writeString(tmp, JSON.writeValueAsString(dados), StandardCharsets.UTF_8);
        Files.move(tmp, arquivo, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
    }
}
