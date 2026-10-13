package br.com.ipedtools.mcp.pcba;

import java.io.File;
import java.io.IOException;
import java.lang.reflect.Parameter;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import br.com.ipedtools.mcp.service.IpedCoreService;
import io.quarkiverse.mcp.server.Tool;
import io.quarkiverse.mcp.server.ToolArg;
import io.quarkiverse.mcp.server.ToolCallException;
import io.vertx.core.json.Json;
import io.vertx.core.json.JsonObject;
import jakarta.annotation.Priority;
import jakarta.inject.Inject;
import jakarta.interceptor.AroundInvoke;
import jakarta.interceptor.Interceptor;
import jakarta.interceptor.InvocationContext;

/**
 * Registra cada chamada de ferramenta feita pela IA: quem, quando, qual caso, quais argumentos,
 * o resultado (ok, erro ou bloqueado), o tamanho e o SHA-256 da resposta e quanto tempo levou.
 *
 * O log fica junto do caso, em {@code <caso>/iped-pcba-auditoria/mcp-auditoria.jsonl}, para
 * acompanhar o caso na cadeia de custódia. Se a pasta do caso não aceitar gravação, ou se nenhum
 * caso estiver aberto, vai para {@code ~/.iped-pcba/auditoria/}. Com {@code pcba.auditoria.pasta}
 * definido, vai sempre para lá.
 *
 * Se não for possível gravar o log, a resposta não é entregue à IA.
 */
@Auditado
@Interceptor
@Priority(Interceptor.Priority.APPLICATION)
public class AuditoriaInterceptor {

    private static final Logger LOGGER = LoggerFactory.getLogger(AuditoriaInterceptor.class);
    static final String ARQUIVO = "mcp-auditoria.jsonl";
    static final String SESSAO = UUID.randomUUID().toString();
    private static final Map<Path, RegistroAuditoria> REGISTROS = new ConcurrentHashMap<>();

    @Inject
    ConfigPcba config;

    @AroundInvoke
    Object auditar(InvocationContext ctx) throws Exception {
        Tool tool = ctx.getMethod().getAnnotation(Tool.class);
        if (tool == null) {
            return ctx.proceed();
        }
        String nome = tool.name().isEmpty() ? ctx.getMethod().getName() : tool.name();
        JsonObject args = argumentos(ctx);
        long inicio = System.nanoTime();

        if (config.somenteLeitura() && ConfigPcba.ehEscrita(nome)) {
            gravar(nome, args, "bloqueado", null, "modo somente leitura", inicio);
            throw new ToolCallException("Bloqueado: o MCP da PCBA está em modo somente leitura. "
                    + "A ferramenta '" + nome + "' altera o caso e só pode ser usada se o analista "
                    + "iniciar o MCP com pcba.somente-leitura=false.");
        }

        Object resultado;
        try {
            resultado = ctx.proceed();
        } catch (Exception | Error e) {
            gravar(nome, args, "erro", null, e.getClass().getSimpleName() + ": " + e.getMessage(), inicio);
            throw e;
        }
        gravar(nome, args, "ok", resultado, null, inicio);
        return resultado;
    }

    private void gravar(String nome, JsonObject args, String situacao, Object resultado, String detalhe, long inicio) {
        JsonObject r = new JsonObject()
                .put("ts", OffsetDateTime.now().toString())
                .put("sessao", SESSAO)
                .put("usuario", System.getProperty("user.name", ""))
                .put("maquina", maquina())
                .put("transporte", config.transporte())
                .put("caso", casoAberto())
                .put("ferramenta", nome)
                .put("argumentos", args)
                .put("situacao", situacao);
        if (detalhe != null) {
            r.put("detalhe", detalhe);
        }
        if (resultado != null) {
            byte[] bytes = serializar(resultado).getBytes(StandardCharsets.UTF_8);
            r.put("resposta_bytes", bytes.length).put("resposta_sha256", RegistroAuditoria.sha256(bytes));
            if (config.guardarRespostas()) {
                r.put("resposta", new String(bytes, StandardCharsets.UTF_8));
            }
        }
        r.put("duracao_ms", (System.nanoTime() - inicio) / 1_000_000);
        try {
            registro().gravar(r);
        } catch (IOException e) {
            LOGGER.error("Falha ao gravar a auditoria: {}", e.getMessage());
            throw new ToolCallException("Falha ao gravar o log de auditoria; a resposta não foi entregue. " + e.getMessage());
        }
    }

    RegistroAuditoria registro() throws IOException {
        Path destino = destino();
        RegistroAuditoria r = REGISTROS.get(destino);
        if (r == null) {
            r = new RegistroAuditoria(destino);
            if (REGISTROS.putIfAbsent(destino, r) == null) {
                LOGGER.info("Auditoria em {}", destino);
            }
        }
        return r;
    }

    Path destino() {
        if (config.pastaAuditoria().isPresent()) {
            return Path.of(config.pastaAuditoria().get()).toAbsolutePath().resolve(ARQUIVO);
        }
        String caso = casoAberto();
        if (caso != null) {
            Path pasta = Path.of(caso, "iped-pcba-auditoria");
            if (gravavel(pasta)) {
                return pasta.resolve(ARQUIVO);
            }
        }
        return Path.of(System.getProperty("user.home"), ".iped-pcba", "auditoria", ARQUIVO);
    }

    private static boolean gravavel(Path pasta) {
        try {
            Files.createDirectories(pasta);
            return Files.isWritable(pasta);
        } catch (IOException | SecurityException e) {
            return false;
        }
    }

    private static String casoAberto() {
        try {
            IpedCoreService s = IpedCoreService.getInstance();
            if (s.isCaseOpen()) {
                File d = s.getCaseDirectory();
                return d == null ? null : d.getAbsolutePath();
            }
        } catch (Throwable ignored) {
            // sem IPED no classpath (testes) ou serviço ainda não iniciado
        }
        return null;
    }

    private static JsonObject argumentos(InvocationContext ctx) {
        JsonObject out = new JsonObject();
        Parameter[] ps = ctx.getMethod().getParameters();
        Object[] vs = ctx.getParameters();
        for (int i = 0; i < ps.length; i++) {
            ToolArg a = ps[i].getAnnotation(ToolArg.class);
            if (a == null) {
                continue;
            }
            String n = a.name().isEmpty() ? ps[i].getName() : a.name();
            Object v = vs[i];
            try {
                out.put(n, v == null ? null : Json.decodeValue(Json.encode(v)));
            } catch (RuntimeException e) {
                out.put(n, String.valueOf(v));
            }
        }
        return out;
    }

    static String serializar(Object o) {
        if (o instanceof CharSequence s) {
            return s.toString();
        }
        try {
            return Json.encode(o);
        } catch (RuntimeException e) {
            return String.valueOf(o);
        }
    }

    private static String maquina() {
        String h = System.getenv("COMPUTERNAME");
        if (h == null || h.isBlank()) {
            try {
                h = InetAddress.getLocalHost().getHostName();
            } catch (IOException e) {
                h = "";
            }
        }
        return h;
    }
}
