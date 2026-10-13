package br.com.ipedtools.mcp.pcba;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Optional;

import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import io.vertx.ext.web.Router;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;

/**
 * Proteção do transporte HTTP (servidor Linux central).
 *
 * - Escuta só em 127.0.0.1 por padrão.
 * - Com a variável PCBA_MCP_TOKEN definida, toda requisição precisa de
 *   "Authorization: Bearer <token>".
 * - Escutar em outro endereço sem token é recusado: o servidor não sobe.
 */
@ApplicationScoped
public class SegurancaHttp {

    private static final Logger LOGGER = LoggerFactory.getLogger(SegurancaHttp.class);

    @ConfigProperty(name = "pcba.transporte", defaultValue = "stdio")
    String transporte;

    @ConfigProperty(name = "pcba.http.token")
    Optional<String> token;

    @ConfigProperty(name = "quarkus.http.host", defaultValue = "127.0.0.1")
    String host;

    void proteger(@Observes Router router) {
        if (!"http".equals(transporte)) {
            return;
        }
        String esperado = token.map(String::trim).orElse("");
        if (esperado.isEmpty()) {
            if (!ehLocal(host)) {
                throw new IllegalStateException("Recusado: o MCP HTTP escutaria em " + host
                        + " sem token. Defina PCBA_MCP_TOKEN ou use --host 127.0.0.1.");
            }
            LOGGER.warn("MCP HTTP sem token, aceitando apenas conexões locais ({}).", host);
            return;
        }
        byte[] alvo = ("Bearer " + esperado).getBytes(StandardCharsets.UTF_8);
        router.route().order(Integer.MIN_VALUE).handler(ctx -> {
            String h = ctx.request().getHeader("Authorization");
            if (h != null && MessageDigest.isEqual(alvo, h.trim().getBytes(StandardCharsets.UTF_8))) {
                ctx.next();
            } else {
                ctx.response().setStatusCode(401).putHeader("WWW-Authenticate", "Bearer").end();
            }
        });
        LOGGER.info("MCP HTTP protegido por token em {}.", host);
    }

    static boolean ehLocal(String h) {
        return "127.0.0.1".equals(h) || "localhost".equalsIgnoreCase(h) || "::1".equals(h);
    }
}
