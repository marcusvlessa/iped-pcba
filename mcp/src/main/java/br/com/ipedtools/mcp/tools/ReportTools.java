package br.com.ipedtools.mcp.tools;

import java.io.File;
import java.util.Map;

import br.com.ipedtools.mcp.pcba.Auditado;
import br.com.ipedtools.mcp.pcba.RascunhoRelatorio;
import br.com.ipedtools.mcp.service.IpedCoreService;
import io.quarkiverse.mcp.server.Tool;
import io.quarkiverse.mcp.server.ToolArg;
import jakarta.enterprise.context.ApplicationScoped;

/** Rascunho do Relatório Técnico (RT) do caso, no modelo da PCBA. O .docx sai pelo painel. */
@Auditado
@ApplicationScoped
public class ReportTools {

    private static RascunhoRelatorio rascunho() {
        IpedCoreService service = IpedCoreService.getInstance();
        if (!service.isCaseOpen()) {
            throw new IllegalStateException("Nenhum caso está aberto no momento.");
        }
        File caso = service.getCaseDirectory();
        return new RascunhoRelatorio(caso.toPath());
    }

    @Tool(
        name = "get_report_draft",
        description = """
            Reads the draft of the Technical Report (Relatório Técnico, RT) of the open case, in the
            PCBA template: qualification block, presentation, objective, facts, phone registration,
            one analysis per provider (WhatsApp, Google, Apple...) with the INVESTIGADO | CONTA | PERÍODO
            table, methodology (IPED, MD5, SHA-256) and requests. Also lists the gaps still marked
            [IN BRACKETS] and the fields you may write. Telematic summaries imported in the dashboard
            are already inside 'analises'.
            """
    )
    public Map<String, Object> getReportDraft() {
        try {
            return rascunho().resumo();
        } catch (Exception e) {
            return Map.of("erro", String.valueOf(e.getMessage()));
        }
    }

    @Tool(
        name = "update_report_field",
        description = """
            Writes one text field of the RT draft (e.g. texto_apresentacao, texto_fatos_relacoes,
            resumo_executivo). Write in Portuguese, continuous prose, third person, no bullet points.
            Never invent case numbers, CPF, IMEI, hashes, accounts or dates: keep them [IN BRACKETS].
            The examiner reviews every field you write before generating the .docx.
            """
    )
    public String updateReportField(
            @ToolArg(name = "field", description = "Field name, one of campos_editaveis from get_report_draft", required = true)
            String field,
            @ToolArg(name = "value", description = "Text in Portuguese", required = true)
            String value
    ) {
        try {
            return rascunho().definirCampo(field, value);
        } catch (Exception e) {
            return "Erro: " + e.getMessage();
        }
    }

    @Tool(
        name = "update_report_analysis",
        description = """
            Creates or updates the analysis section of one provider (WHATSAPP, GOOGLE, APPLE, META...)
            in the RT draft: the analysis text and, optionally, a suggested conclusion. Base the text
            only on evidence found in the case and cite item ids or queries you used. The conclusion
            belongs to the examiner: a suggested conclusion is stored entirely in brackets as
            [SUGESTÃO DA IA — REVISAR: ...] so it prints in red until the examiner rewrites it.
            """
    )
    public String updateReportAnalysis(
            @ToolArg(name = "provider", description = "Provider name, e.g. WHATSAPP", required = true)
            String provider,
            @ToolArg(name = "text", description = "Analysis text in Portuguese (continuous prose)", required = false)
            String text,
            @ToolArg(name = "conclusion", description = "Suggested conclusion (optional)", required = false)
            String conclusion,
            @ToolArg(name = "title", description = "Section title (optional)", required = false)
            String title
    ) {
        try {
            return rascunho().definirAnalise(provider, title, text, conclusion);
        } catch (Exception e) {
            return "Erro: " + e.getMessage();
        }
    }
}
