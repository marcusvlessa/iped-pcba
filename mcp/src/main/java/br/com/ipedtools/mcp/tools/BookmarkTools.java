package br.com.ipedtools.mcp.tools;

import java.util.List;
import java.util.Map;

import br.com.ipedtools.mcp.service.IpedCoreService;
import io.quarkiverse.mcp.server.Tool;
import io.quarkiverse.mcp.server.ToolArg;
import br.com.ipedtools.mcp.pcba.Auditado;
import jakarta.enterprise.context.ApplicationScoped;

@Auditado
@ApplicationScoped
public class BookmarkTools {

    @Tool(
        name = "list_bookmarks",
        description = """
            Lists all existing bookmarks (tags, labels, and evidence folders) in the IPED case.
            
            WHEN TO USE:
            - Bookmarks in IPED are used by forensic examiners to organize evidence for the official forensic report (laudo pericial).
            - Call this tool to inspect existing tags before adding new items or creating new bookmarks.
            """
    )
    public List<String> listBookmarks() {
        IpedCoreService service = IpedCoreService.getInstance();
        if (!service.isCaseOpen()) {
            return List.of("[Erro: Nenhum caso está aberto no momento.]");
        }
        return service.listBookmarks();
    }

    @Tool(
        name = "add_to_bookmark",
        description = """
            Adds one or more evidence items to an IPED bookmark (tag) for inclusion in the forensic investigation report (laudo pericial).
            If the bookmark does not already exist, it is automatically created in IPED.
            
            WHEN TO USE:
            - Use this tool whenever the user instructs to bookmark, flag, mark, or save an evidence item.
              Examples:
                * 'Adicione esse documento aos marcadores'
                * 'Marque esse arquivo como Prova Principal'
                * 'Salve os achados na pasta Suspeita de Fraude'
            """
    )
    public String addToBookmark(
            @ToolArg(name = "bookmark_name", description = "The name of the target bookmark tag (e.g. 'Evidências Relevantes', 'Fraude Financeira')", required = true)
            String bookmarkName,
            @ToolArg(name = "doc_ids", description = "List of integer document IDs to bookmark", required = true)
            List<Integer> docIds
    ) {
        IpedCoreService service = IpedCoreService.getInstance();
        if (!service.isCaseOpen()) {
            return "Erro: Nenhum caso está aberto no momento.";
        }
        return service.addBookmark(bookmarkName, docIds);
    }

    @Tool(
        name = "remove_from_bookmark",
        description = """
            Removes evidence items from an existing IPED bookmark (undoes add_to_bookmark).
            Use when the user asks to unmark or take items out of a bookmark.
            """
    )
    public String removeFromBookmark(
            @ToolArg(name = "bookmark_name", description = "Existing bookmark name", required = true)
            String bookmarkName,
            @ToolArg(name = "doc_ids", description = "List of integer document IDs to remove", required = true)
            List<Integer> docIds
    ) {
        IpedCoreService service = IpedCoreService.getInstance();
        if (!service.isCaseOpen()) {
            return "Erro: Nenhum caso está aberto no momento.";
        }
        return service.removeFromBookmark(bookmarkName, docIds);
    }

    @Tool(
        name = "set_bookmark_comment",
        description = """
            Writes the comment of an IPED bookmark (creates the bookmark if needed). The comment is shown
            in IPED and in the HTML report. Use it to record why the items were bookmarked
            (the reasoning and the query used), so the examiner can review it.
            Optionally sets whether the bookmark goes into the report.
            """
    )
    public String setBookmarkComment(
            @ToolArg(name = "bookmark_name", description = "Bookmark name", required = true)
            String bookmarkName,
            @ToolArg(name = "comment", description = "Comment text (in Portuguese)", required = true)
            String comment,
            @ToolArg(name = "in_report", description = "true to include the bookmark in the report, false to exclude; omit to keep", required = false)
            Boolean inReport
    ) {
        IpedCoreService service = IpedCoreService.getInstance();
        if (!service.isCaseOpen()) {
            return "Erro: Nenhum caso está aberto no momento.";
        }
        return service.setBookmarkComment(bookmarkName, comment, inReport);
    }

    @Tool(
        name = "bookmark_search_results",
        description = """
            Runs an IPED/Lucene query and adds the matching items (up to max_items, default 500, max 5000)
            to a bookmark, creating it if needed. Use it to organize evidence in bulk, e.g. all chats
            mentioning a PIX key or all images of a category. Check the query with search_documents first.
            """
    )
    public Map<String, Object> bookmarkSearchResults(
            @ToolArg(name = "bookmark_name", description = "Target bookmark name", required = true)
            String bookmarkName,
            @ToolArg(name = "query", description = "IPED/Lucene query (same syntax as search_documents)", required = true)
            String query,
            @ToolArg(name = "max_items", description = "Maximum items to bookmark (default 500, max 5000)", required = false)
            Integer maxItems
    ) {
        IpedCoreService service = IpedCoreService.getInstance();
        if (!service.isCaseOpen()) {
            return Map.of("error", "Nenhum caso está aberto no momento.");
        }
        return service.bookmarkSearchResults(bookmarkName, query, maxItems == null ? 500 : maxItems);
    }
}
