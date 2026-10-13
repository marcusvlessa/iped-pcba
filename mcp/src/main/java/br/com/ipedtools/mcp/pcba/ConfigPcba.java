package br.com.ipedtools.mcp.pcba;

import java.util.Optional;
import java.util.Set;

import org.eclipse.microprofile.config.inject.ConfigProperty;

import jakarta.enterprise.context.ApplicationScoped;

/** Opções da PCBA, lidas de application.properties, propriedades de sistema ou variáveis de ambiente. */
@ApplicationScoped
public class ConfigPcba {

    /** Ferramentas que alteram o caso. Ficam escondidas e bloqueadas no modo somente leitura. */
    public static final Set<String> FERRAMENTAS_DE_ESCRITA = Set.of("add_to_bookmark", "set_item_checked",
            "remove_from_bookmark", "set_bookmark_comment", "bookmark_search_results");

    @ConfigProperty(name = "pcba.somente-leitura", defaultValue = "true")
    boolean somenteLeitura;

    @ConfigProperty(name = "pcba.auditoria.pasta")
    Optional<String> pastaAuditoria;

    @ConfigProperty(name = "pcba.auditoria.guardar-respostas", defaultValue = "false")
    boolean guardarRespostas;

    @ConfigProperty(name = "pcba.transporte", defaultValue = "stdio")
    String transporte;

    public boolean somenteLeitura() {
        return somenteLeitura;
    }

    public Optional<String> pastaAuditoria() {
        return pastaAuditoria.filter(s -> !s.isBlank());
    }

    public boolean guardarRespostas() {
        return guardarRespostas;
    }

    public String transporte() {
        return transporte;
    }

    public static boolean ehEscrita(String ferramenta) {
        return FERRAMENTAS_DE_ESCRITA.contains(ferramenta);
    }
}
