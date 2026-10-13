package br.com.ipedtools.mcp.pcba;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import io.vertx.core.json.JsonObject;

class RegistroAuditoriaTest {

    @TempDir
    Path tmp;

    @Test
    void encadeiaHashesEContinuaAposReabrir() throws Exception {
        Path arq = tmp.resolve("sub/mcp-auditoria.jsonl");
        RegistroAuditoria r = new RegistroAuditoria(arq);
        String h1 = r.gravar(new JsonObject().put("ferramenta", "a").put("texto", "ação com acento"));
        String h2 = r.gravar(new JsonObject().put("ferramenta", "b"));

        // reabrir (novo processo) continua a cadeia de onde parou
        RegistroAuditoria r2 = new RegistroAuditoria(arq);
        r2.gravar(new JsonObject().put("ferramenta", "c"));

        List<String> linhas = Files.readAllLines(arq, StandardCharsets.UTF_8);
        assertEquals(3, linhas.size());
        String anterior = RegistroAuditoria.INICIO;
        long seq = 1;
        for (String l : linhas) {
            JsonObject o = new JsonObject(l);
            assertEquals(seq++, o.getLong("seq"));
            assertEquals(anterior, o.getString("anterior"));
            String corpo = l.substring(0, l.lastIndexOf(",\"hash\":")) + "}";
            assertEquals(RegistroAuditoria.sha256(anterior + corpo), o.getString("hash"));
            assertTrue(l.endsWith("\"}"));
            anterior = o.getString("hash");
        }
        assertEquals(h1, new JsonObject(linhas.get(0)).getString("hash"));
        assertEquals(h2, new JsonObject(linhas.get(1)).getString("hash"));
    }

    @Test
    void chamadasSimultaneasMantemACadeia() throws Exception {
        Path arq = tmp.resolve("mcp-auditoria.jsonl");
        Thread[] ts = new Thread[8];
        for (int t = 0; t < ts.length; t++) {
            final int id = t;
            // cada thread com sua instância, como dois processos no mesmo caso
            RegistroAuditoria r = new RegistroAuditoria(arq);
            ts[t] = new Thread(() -> {
                for (int i = 0; i < 25; i++) {
                    try {
                        r.gravar(new JsonObject().put("t", id).put("i", i));
                    } catch (Exception e) {
                        throw new RuntimeException(e);
                    }
                }
            });
            ts[t].start();
        }
        for (Thread t : ts) {
            t.join();
        }
        List<String> linhas = Files.readAllLines(arq, StandardCharsets.UTF_8);
        assertEquals(200, linhas.size());
        String anterior = RegistroAuditoria.INICIO;
        for (int i = 0; i < linhas.size(); i++) {
            JsonObject o = new JsonObject(linhas.get(i));
            assertEquals(i + 1L, o.getLong("seq"));
            assertEquals(anterior, o.getString("anterior"));
            anterior = o.getString("hash");
        }
    }
}
