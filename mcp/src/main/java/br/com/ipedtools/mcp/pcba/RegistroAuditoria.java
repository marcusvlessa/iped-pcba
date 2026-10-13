package br.com.ipedtools.mcp.pcba;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import io.vertx.core.json.JsonObject;

/**
 * Arquivo JSONL de auditoria com encadeamento de hashes.
 *
 * Cada linha é um objeto JSON cujo último campo é "hash". O conteúdo sem esse campo
 * (o "corpo") traz em "anterior" o hash da linha anterior, e
 * hash = sha256(anterior + corpo). Apagar, inserir ou alterar uma linha quebra a cadeia,
 * o que o verificador (python -m iped_pcba.auditoria) aponta.
 */
public final class RegistroAuditoria {

    public static final String INICIO = "0".repeat(64);
    private static final Pattern FIM = Pattern.compile(",\"hash\":\"([0-9a-f]{64})\"}$");

    private final Path arquivo;

    public RegistroAuditoria(Path arquivo) throws IOException {
        this.arquivo = arquivo.toAbsolutePath();
        Files.createDirectories(this.arquivo.getParent());
    }

    public Path arquivo() {
        return arquivo;
    }

    /**
     * Acrescenta o registro (sem "seq", "anterior" e "hash", que são preenchidos aqui).
     * Usa trava de arquivo e relê a última linha a cada gravação, então chamadas simultâneas
     * e mais de um processo do MCP no mesmo caso mantêm a cadeia íntegra.
     */
    public String gravar(JsonObject registro) throws IOException {
        synchronized (RegistroAuditoria.class) {
            try (FileChannel ch = FileChannel.open(arquivo, StandardOpenOption.CREATE,
                    StandardOpenOption.READ, StandardOpenOption.WRITE);
                    FileLock trava = ch.lock()) {
                String anterior = INICIO;
                long seq = 0;
                String ultima = ultimaLinha(ch);
                if (ultima != null) {
                    Matcher m = FIM.matcher(ultima);
                    if (!m.find()) {
                        throw new IOException("Última linha do log de auditoria sem hash: " + arquivo);
                    }
                    anterior = m.group(1);
                    seq = new JsonObject(ultima).getLong("seq", 0L);
                }
                JsonObject corpo = new JsonObject().put("seq", seq + 1);
                registro.forEach(e -> corpo.put(e.getKey(), e.getValue()));
                corpo.put("anterior", anterior);
                String texto = corpo.encode();
                String hash = sha256(anterior + texto);
                String linha = texto.substring(0, texto.length() - 1) + ",\"hash\":\"" + hash + "\"}\n";
                ch.position(ch.size());
                ByteBuffer buf = ByteBuffer.wrap(linha.getBytes(StandardCharsets.UTF_8));
                while (buf.hasRemaining()) {
                    ch.write(buf);
                }
                ch.force(true);
                return hash;
            }
        }
    }

    public static String sha256(String texto) {
        return sha256(texto.getBytes(StandardCharsets.UTF_8));
    }

    public static String sha256(byte[] dados) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(dados));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private static String ultimaLinha(FileChannel ch) throws IOException {
        long tam = ch.size();
        if (tam == 0) {
            return null;
        }
        // lê o fim do arquivo em blocos crescentes até achar a linha inteira
        for (long bloco = 64 * 1024; ; bloco *= 4) {
            long ini = Math.max(0, tam - bloco);
            ByteBuffer buf = ByteBuffer.allocate((int) (tam - ini));
            while (buf.hasRemaining() && ch.read(buf, ini + buf.position()) >= 0) {
                // continua lendo
            }
            String t = new String(buf.array(), 0, buf.position(), StandardCharsets.UTF_8).stripTrailing();
            if (t.isEmpty()) {
                return null;
            }
            int nl = t.lastIndexOf('\n');
            if (nl >= 0 || ini == 0) {
                return t.substring(nl + 1);
            }
        }
    }
}
