package br.com.ipedtools.mcp.pcba;

import io.quarkiverse.mcp.server.FilterContext;
import io.quarkiverse.mcp.server.McpMethod;
import io.quarkiverse.mcp.server.ToolFilter;
import io.quarkiverse.mcp.server.ToolManager.ToolInfo;
import jakarta.inject.Inject;
import jakarta.inject.Singleton;

/**
 * No modo somente leitura a IA nem vê as ferramentas que alteram o caso (tools/list).
 * Se o cliente chamar assim mesmo, a chamada passa por aqui e o interceptor de auditoria
 * a bloqueia e registra como "bloqueado", para a tentativa ficar no log.
 */
@Singleton
public class FiltroSomenteLeitura implements ToolFilter {

    @Inject
    ConfigPcba config;

    @Override
    public boolean test(ToolInfo tool, FilterContext context) {
        if (context.method() == McpMethod.TOOLS_CALL) {
            return true;
        }
        return !(config.somenteLeitura() && ConfigPcba.ehEscrita(tool.name()));
    }
}
